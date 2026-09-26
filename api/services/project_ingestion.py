"""Canonical project ingestion service.

All input adapters (manual form, PDF now, CSV later) converge here before
persistence so Project and ProjectUpdate are created/updated consistently.
"""

import re
from datetime import date, datetime
from typing import Any, Callable, Dict, Iterable, Optional

from sqlalchemy.orm import Session

from api.models.models import Project, ProjectUpdate


REPORT_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
MONTH_YEAR_RE = re.compile(r"^(\d{1,2})/(\d{4})$")


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").replace("₹", "").strip())
    except (TypeError, ValueError):
        raise ValueError(f"Invalid numeric value: {value}")


def _to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        raise ValueError(f"Invalid integer value: {value}")


def _to_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text or text in {"-", "--", "—", "N.R.", "NR"}:
        return None

    match = MONTH_YEAR_RE.fullmatch(text)
    if match:
        month, year = int(match.group(1)), int(match.group(2))
        if not 1 <= month <= 12:
            raise ValueError(f"Invalid month/year date: {text}")
        return date(year, month, 1)

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    raise ValueError(f"Invalid date value: {text}")


def _normalize_report_month(value: Any) -> str:
    if value is None or str(value).strip() == "":
        raise ValueError("report_month is required")

    text = str(value).strip()[:7]
    match = REPORT_MONTH_RE.fullmatch(text)
    if not match:
        raise ValueError(f"Invalid report_month: {value}; expected YYYY-MM")

    month = int(match.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"Invalid report_month: {value}")

    return text


def normalize_project_record(record: Dict[str, Any]) -> Dict[str, Any]:
    project_id = _clean_text(record.get("project_id"))
    if not project_id:
        raise ValueError("project_id is required")

    project_name = _clean_text(record.get("project_name"))
    if not project_name:
        raise ValueError(f"Project '{project_id}' is missing project_name")

    report_month_value = record.get("report_month")
    if report_month_value is None:
        approval = _to_date(record.get("date_of_approval"))
        report_month_value = (
            approval.strftime("%Y-%m") if approval else date.today().strftime("%Y-%m")
        )

    serial_no = _to_int(record.get("serial_no"))
    if serial_no is None:
        serial_no = 1

    return {
        "project_id": project_id,
        "project_name": project_name,
        "sector": _clean_text(record.get("sector")),
        "implementing_agency": _clean_text(record.get("implementing_agency")),
        "state": _clean_text(record.get("state")),
        "date_of_approval": _to_date(record.get("date_of_approval")),
        "original_cost_crore": _to_float(record.get("original_cost_crore")),
        "original_commissioning_date": _to_date(record.get("original_commissioning_date")),
        "report_month": _normalize_report_month(report_month_value),
        "serial_no": serial_no,
        "revised_cost_crore": _to_float(record.get("revised_cost_crore")),
        "anticipated_cost_crore": _to_float(record.get("anticipated_cost_crore")),
        "cumulative_expenditure_crore": _to_float(record.get("cumulative_expenditure_crore")),
        "revised_commissioning_date": _to_date(record.get("revised_commissioning_date")),
        "anticipated_commissioning_date": _to_date(record.get("anticipated_commissioning_date")),
        "delay_original_months": _to_float(record.get("delay_original_months")),
        "delay_revised_months": _to_float(record.get("delay_revised_months")),
        "milestones_achieved": _to_int(record.get("milestones_achieved")),
        "milestones_total": _to_int(record.get("milestones_total")),
        "source_file": record.get("source_file"),
        "source_page": record.get("source_page"),
    }


def ingest_project_record(db: Session, record: Dict[str, Any]) -> Dict[str, Any]:
    data = normalize_project_record(record)
    project_id = data["project_id"]
    report_month = data["report_month"]

    project = db.query(Project).filter(Project.project_id == project_id).first()
    project_created = project is None

    if project is None:
        project = Project(
            project_id=project_id,
            project_name=data["project_name"],
            sector=data["sector"],
            implementing_agency=data["implementing_agency"],
            state=data["state"],
            date_of_approval=data["date_of_approval"],
            original_cost_crore=data["original_cost_crore"],
            original_commissioning_date=data["original_commissioning_date"],
        )
        db.add(project)
        db.flush()
    else:
        # Update only project-level values represented by this source record.
        project.project_name = data["project_name"] or project.project_name
        for field in (
            "sector",
            "implementing_agency",
            "state",
            "date_of_approval",
            "original_cost_crore",
            "original_commissioning_date",
        ):
            value = data[field]
            if value is not None:
                setattr(project, field, value)

    update = (
        db.query(ProjectUpdate)
        .filter(
            ProjectUpdate.project_id == project_id,
            ProjectUpdate.report_month == report_month,
        )
        .first()
    )
    update_created = update is None

    if update is None:
        update = ProjectUpdate(
            project_id=project_id,
            report_month=report_month,
        )
        db.add(update)

    for field in (
        "serial_no",
        "revised_cost_crore",
        "anticipated_cost_crore",
        "cumulative_expenditure_crore",
        "revised_commissioning_date",
        "anticipated_commissioning_date",
        "delay_original_months",
        "delay_revised_months",
        "milestones_achieved",
        "milestones_total",
    ):
        setattr(update, field, data[field])

    db.flush()

    serial_no = _to_int(record.get("serial_no"))
    if serial_no is None:
        serial_no = 1

    return {
        "project_id": project_id,
        "report_month": report_month,
        "project_created": project_created,
        "update_created": update_created,
        "source_file": data.get("source_file"),
        "source_page": data.get("source_page"),
    }


def ingest_project_records(
    db: Session,
    records: Iterable[Dict[str, Any]],
    progress_callback: Optional[Callable[[int, int, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    records = list(records)
    result = {
        "projects_found": len(records),
        "projects_created": 0,
        "projects_updated": 0,
        "updates_created": 0,
        "updates_updated": 0,
        "errors": [],
        "affected_pairs": [],
    }

    for index, record in enumerate(records, start=1):
        page = record.get("source_page")
        try:
            # A savepoint keeps one malformed record from rolling back the
            # rest of an otherwise valid PDF import.
            with db.begin_nested():
                outcome = ingest_project_record(db, record)

            if outcome["project_created"]:
                result["projects_created"] += 1
            else:
                result["projects_updated"] += 1

            if outcome["update_created"]:
                result["updates_created"] += 1
            else:
                result["updates_updated"] += 1

            result["affected_pairs"].append(
                (outcome["project_id"], outcome["report_month"])
            )
        except Exception as exc:
            result["errors"].append({
                "page": page,
                "reason": str(exc),
            })

        if progress_callback:
            progress_callback(index, len(records), result)

    # Keep prediction work deterministic and duplicate-free.
    result["affected_pairs"] = sorted(set(result["affected_pairs"]))
    return result
