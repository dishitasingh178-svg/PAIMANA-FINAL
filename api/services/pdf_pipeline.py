"""Observable PDF ingestion pipeline.

Runs the same steps the upload endpoint used to run inline (validation,
extraction, ingestion, commit, predictions + early warnings) but in a
background worker, publishing every step through a JobReporter so the
frontend can follow along over SSE.
"""

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from database import SessionLocal
from api.services.pdf_extractor import extract_pdf
from api.services.project_ingestion import ingest_project_records, normalize_project_record
from api.services.prediction_service import generate_predictions_for_pairs
import ml_package.predictor as predictor


PDF_MAX_BYTES = 25 * 1024 * 1024
PDF_MAX_PAGES = 400
PDF_PARSE_TIMEOUT_SECONDS = 60
ACCEPTED_CONTENT_TYPES = {None, "application/pdf", "application/octet-stream"}

# Throttle for high-frequency progress events (seconds).
PROGRESS_INTERVAL = 0.2


class PipelineError(Exception):
    """A user-facing failure that ends the job."""


def validate_pdf_signature(path):
    with open(path, "rb") as handle:
        return handle.read(5) == b"%PDF-"


def extract_pdf_with_timeout(path, progress_callback=None):
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(extract_pdf, path, progress_callback)
    try:
        return future.result(timeout=PDF_PARSE_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        future.cancel()
        raise
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def format_extraction_errors(errors):
    formatted = []
    for error in errors or []:
        text = str(error)
        match = re.match(r"page\s+(\d+),\s*serial\s+(\d+):\s*(.*)", text, re.I)
        if match:
            formatted.append({
                "page": int(match.group(1)),
                "reason": f"Serial {match.group(2)}: {match.group(3)}",
            })
        else:
            formatted.append({"page": None, "reason": text})
    return formatted


class _Throttle:
    def __init__(self, interval=PROGRESS_INTERVAL):
        self.interval = interval
        self.last = 0.0

    def ready(self, force=False):
        now = time.monotonic()
        if force or now - self.last >= self.interval:
            self.last = now
            return True
        return False


def _validate(reporter, temp_path, content_type):
    reporter.stage_started("validating", "Validating document")

    if content_type not in ACCEPTED_CONTENT_TYPES:
        raise PipelineError("Only PDF files are accepted.")
    reporter.detail("validating", f"MIME type verified ({content_type or 'unspecified'})")

    if not validate_pdf_signature(temp_path):
        raise PipelineError("The uploaded file is not a valid PDF document.")
    reporter.detail("validating", "PDF signature verified")

    import fitz
    try:
        doc = fitz.open(temp_path)
        page_count = doc.page_count
        doc.close()
    except Exception as exc:
        raise PipelineError(f"The PDF could not be opened: {exc}")

    if page_count == 0:
        raise PipelineError("The uploaded PDF contains no pages.")
    if page_count > PDF_MAX_PAGES:
        raise PipelineError(f"PDF exceeds the {PDF_MAX_PAGES}-page limit.")

    reporter.detail("validating", f"Pages detected: {page_count}", counters={"pages": page_count})
    reporter.stage_completed("validating", "Document is valid")
    return page_count


def _extract(reporter, temp_path):
    reporter.stage_started("extracting", "Locating project-detail table")
    throttle = _Throttle()

    def on_progress(event, **info):
        if event == "section_found":
            pages = info["pages"]
            reporter.detail(
                "extracting",
                f"Project table found on pages {pages[0] + 1}–{pages[-1] + 1} ({len(pages)} pages)",
                counters={"table_pages": len(pages)},
            )
            if info.get("report_month"):
                reporter.detail("extracting", f"Report month: {info['report_month']}",
                                counters={"report_month": info["report_month"]})
        elif event == "page_done":
            if throttle.ready(force=info["done"] == info["total"]):
                reporter.progress(
                    "extracting",
                    info["done"] / info["total"],
                    f"Parsing page {info['page_no']} — {info['done']}/{info['total']} pages, "
                    f"{info['records']} records",
                    counters={"records_extracted": info["records"], "parse_errors": info["errors"]},
                )

    try:
        records, _pages, extraction_errors = extract_pdf_with_timeout(temp_path, on_progress)
    except FutureTimeoutError:
        raise PipelineError("PDF parsing timed out.")
    except Exception as exc:
        raise PipelineError(f"PDF extraction failed: {exc}")

    if not records:
        # e.g. "Target project-detail section was not found": nothing to ingest,
        # so don't let the job end as a success.
        reason = "; ".join(str(e) for e in extraction_errors[:3])
        raise PipelineError(
            "No project records were extracted from the PDF"
            + (f" ({reason})." if reason else ".")
        )

    reporter.stage_completed(
        "extracting",
        f"{len(records)} records extracted, {len(extraction_errors)} rows could not be parsed",
        counters={"records_extracted": len(records), "parse_errors": len(extraction_errors)},
    )
    return records, extraction_errors


def _normalize(reporter, records):
    """Dry-run normalization so problems show up before touching the database.

    Ingestion re-normalizes each record itself; this pass only reports.
    """
    reporter.stage_started("normalizing", "Normalizing dates, costs and identifiers")
    valid, invalid = 0, 0
    sectors, months = set(), set()
    for record in records:
        try:
            data = normalize_project_record(record)
            valid += 1
            if data["sector"]:
                sectors.add(data["sector"])
            months.add(data["report_month"])
        except Exception:
            invalid += 1

    if months:
        reporter.detail("normalizing", f"Report month: {', '.join(sorted(months))}")
    reporter.detail("normalizing", f"Sectors detected: {len(sectors)}", counters={"sectors": len(sectors)})
    reporter.stage_completed(
        "normalizing",
        f"{valid} records normalized, {invalid} rejected",
        counters={"records_valid": valid, "records_rejected": invalid},
    )


def _ingest(reporter, records):
    reporter.stage_started("ingesting", f"Writing {len(records)} records to the database")
    throttle = _Throttle()

    def on_progress(done, total, partial):
        if throttle.ready(force=done == total):
            reporter.progress(
                "ingesting",
                done / total if total else 1.0,
                f"Ingesting record {done}/{total}",
                counters={
                    "projects_created": partial["projects_created"],
                    "projects_updated": partial["projects_updated"],
                    "updates_created": partial["updates_created"],
                    "updates_updated": partial["updates_updated"],
                },
            )

    db = SessionLocal()
    try:
        result = ingest_project_records(db, records, on_progress)
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            raise PipelineError(f"Database ingestion failed: {exc}")
    finally:
        db.close()

    reporter.detail("ingesting", "Transaction committed")
    reporter.stage_completed(
        "ingesting",
        f"{result['projects_created']} new projects, {result['projects_updated']} updated, "
        f"{result['updates_created'] + result['updates_updated']} monthly updates",
    )
    return result


def _predict(reporter, affected_pairs):
    if not affected_pairs:
        reporter.stage_skipped("predicting", "No project updates to score")
        reporter.stage_skipped("alerting", "No predictions, so no early warnings")
        return None

    model_version = getattr(predictor, "manifest", {}).get("package_version", "1.0.0")
    reporter.stage_started(
        "predicting",
        f"Scoring {len(affected_pairs)} project updates (model v{model_version})",
    )
    # Alerts are generated per prediction by the alert engine, so both
    # stages run together.
    reporter.stage_started("alerting", "Evaluating early-warning rules per prediction")
    throttle = _Throttle()

    def on_progress(summary):
        force = summary["done"] == summary["total"]
        counters = {
            "predictions_done": summary["done"],
            "predictions_total": summary["total"],
            "predictions_failed": summary["failed"],
            "alerts_created": summary["alerts_created"],
        }
        if throttle.ready(force=force):
            reporter.progress(
                "predicting",
                summary["done"] / summary["total"],
                f"Predicted {summary['done']}/{summary['total']} — {summary['last_project_id']}",
                counters=counters,
            )
            reporter.progress(
                "alerting",
                summary["done"] / summary["total"],
                f"{summary['alerts_created']} early warnings raised so far",
            )

    summary = generate_predictions_for_pairs(affected_pairs, on_progress)

    reporter.stage_completed(
        "predicting",
        f"{summary['succeeded']} predictions generated, {summary['failed']} failed",
        counters={"predictions_done": summary["done"], "predictions_failed": summary["failed"]},
    )
    by_severity = ", ".join(
        f"{count} {severity}" for severity, count in sorted(summary["alerts_by_severity"].items())
    )
    if by_severity:
        reporter.detail("alerting", f"By severity: {by_severity}")
    reporter.stage_completed(
        "alerting",
        f"{summary['alerts_created']} new early-warning alerts",
        counters={"alerts_created": summary["alerts_created"]},
    )
    return summary


def run_pdf_job(reporter, temp_path, filename, content_type, size_bytes):
    try:
        reporter.started()
        reporter.stage_started("received", "PDF received")
        reporter.detail("received", f"{filename} ({size_bytes / (1024 * 1024):.2f} MB)")
        reporter.stage_completed("received", filename)

        page_count = _validate(reporter, temp_path, content_type)
        records, extraction_errors = _extract(reporter, temp_path)
        _normalize(reporter, records)
        result = _ingest(reporter, records)
        errors = format_extraction_errors(extraction_errors) + result["errors"]
        summary = _predict(reporter, result["affected_pairs"])

        reporter.completed({
            "success": True,
            "filename": filename,
            "pages": page_count,
            "projects_found": result["projects_found"],
            "projects_created": result["projects_created"],
            "projects_updated": result["projects_updated"],
            "updates_created": result["updates_created"],
            "updates_updated": result["updates_updated"],
            "predictions_generated": summary["succeeded"] if summary else 0,
            "predictions_failed": summary["failed"] if summary else 0,
            "alerts_created": summary["alerts_created"] if summary else 0,
            "alerts_by_severity": summary["alerts_by_severity"] if summary else {},
            "errors": errors,
        })
    except PipelineError as exc:
        reporter.failed(str(exc))
    except Exception as exc:
        reporter.failed(f"Unexpected error: {exc}")
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
