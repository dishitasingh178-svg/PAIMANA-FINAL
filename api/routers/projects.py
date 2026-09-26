from datetime import date
import os
import tempfile
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session

from database import get_db
from api.models.models import Project, ProjectUpdate, Prediction
from api.services.project_ingestion import ingest_project_record
from api.services.job_manager import PDF_STAGES, create_job, submit_job
from api.services.pdf_pipeline import PDF_MAX_BYTES, run_pdf_job

from api.ml.feature_engineering import build_feature_snapshot
import ml_package.predictor as predictor

router = APIRouter(prefix="/api/v1/projects", tags=["Projects"])


_pdf_upload_lock = __import__("threading").Lock()
_pdf_last_upload_at = 0.0


class ProjectListItem(BaseModel):
    id: str
    name: str
    agency: str
    sector: str
    original_cost: float
    anticipated_cost: float
    milestones_achieved: int
    milestones_total: int
    risk_score: float
    risk_label: str


class ProjectDetailResponse(BaseModel):
    id: str
    name: str
    agency: str
    sector: str
    state: str
    approval_date: str
    original_comm: str
    anti_comm: str
    original_cost: float
    anticipated_cost: float
    expenditure: float
    delay_months: int
    milestones_achieved: int
    milestones_total: int
    cost_escalation_pct: float

    # Overall risk
    risk_score: float
    risk_label: str

    # Individual ML model outputs
    cost_risk_probability: float
    schedule_risk_probability: float
    cox_risk_probability: float


class ProjectCreateRequest(BaseModel):
    project_id: str = Field(min_length=1)

    project_name: Optional[str] = None
    implementing_agency: Optional[str] = None
    sector: Optional[str] = None
    state: Optional[str] = None

    date_of_approval: Optional[date] = None

    original_cost_crore: Optional[float] = None
    revised_cost_crore: Optional[float] = None
    anticipated_cost_crore: Optional[float] = None
    cumulative_expenditure_crore: Optional[float] = None

    original_commissioning_date: Optional[date] = None
    revised_commissioning_date: Optional[date] = None
    anticipated_commissioning_date: Optional[date] = None

    delay_original_months: Optional[float] = None
    delay_revised_months: Optional[float] = None

    milestones_achieved: Optional[int] = None
    milestones_total: Optional[int] = None


def _latest_update(
    db: Session,
    project_id: str
) -> Optional[ProjectUpdate]:
    return (
        db.query(ProjectUpdate)
        .filter(
            func.trim(cast(ProjectUpdate.project_id, String))
            == project_id.strip()
        )
        .order_by(ProjectUpdate.report_month.desc())
        .first()
    )


def _latest_prediction(
    db: Session,
    project_id: str
) -> Optional[Prediction]:
    return (
        db.query(Prediction)
        .filter(
            func.trim(cast(Prediction.project_id, String))
            == project_id.strip()
        )
        .order_by(
            Prediction.generated_at.desc(),
            Prediction.prediction_id.desc()
        )
        .first()
    )


def _delay_months(
    original: Optional[date],
    revised: Optional[date]
) -> int:
    if not original or not revised:
        return 0

    return (
        (revised.year - original.year) * 12
        + (revised.month - original.month)
    )


def _risk_from_prediction(pred: Optional[Prediction]):
    if not pred:
        return 0.0, "UNASSESSED"

    return (
        float(pred.composite_risk_score or 0.0),
        str(pred.risk_tier or "UNASSESSED")
    )


@router.post("/upload-pdf", status_code=202)
def upload_project_pdf(
    file: UploadFile = File(...),
):
    """Store the upload and hand it to a background job.

    Validation, extraction, ingestion, predictions and early warnings all
    run in the job; follow them at GET /api/v1/jobs/{job_id}/events.
    """
    global _pdf_last_upload_at

    import time
    now = time.monotonic()
    with _pdf_upload_lock:
        if now - _pdf_last_upload_at < 2.0:
            raise HTTPException(status_code=429, detail="Please wait before uploading another PDF.")
        _pdf_last_upload_at = now

    temp_path = None
    handed_off = False
    try:
        fd, temp_path = tempfile.mkstemp(prefix="paimana_pdf_", suffix=".pdf")
        os.close(fd)

        # The body has to be read while the request is open, so the size
        # limit is enforced here; everything else is checked in the job.
        total = 0
        with open(temp_path, "wb") as out:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > PDF_MAX_BYTES:
                    raise HTTPException(413, detail="PDF exceeds the 25 MB upload limit.")
                out.write(chunk)

        if total == 0:
            raise HTTPException(400, detail="The uploaded PDF is empty.")

        filename = os.path.basename(file.filename or "upload.pdf")
        job_id = create_job("pdf_upload", PDF_STAGES, {
            "filename": filename,
            "size_bytes": total,
        })
        submit_job(job_id, run_pdf_job, temp_path, filename, file.content_type, total)
        handed_off = True

        return {
            "success": True,
            "job_id": job_id,
            "status": "queued",
            "filename": filename,
            "status_url": f"/api/v1/jobs/{job_id}",
            "events_url": f"/api/v1/jobs/{job_id}/events",
        }
    finally:
        try:
            file.file.close()
        except Exception:
            pass
        # Once handed off, the job owns (and deletes) the temp file.
        if not handed_off and temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


@router.get("", response_model=List[ProjectListItem])
@router.get("/", response_model=List[ProjectListItem])
def get_all_projects(
    q: Optional[str] = Query(None),
    sector: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Project)

    if sector and sector.lower() != "all":
        query = query.filter(
            Project.sector.ilike(f"%{sector}%")
        )

    if q:
        search = f"%{q.strip()}%"

        query = query.filter(
            or_(
                cast(Project.project_id, String).ilike(search),
                Project.project_name.ilike(search),
                Project.implementing_agency.ilike(search),
            )
        )

    projects = (
        query
        .order_by(Project.project_id.asc())
        .limit(100)
        .all()
    )

    result = []

    for project in projects:
        pid = str(project.project_id).strip()

        update = _latest_update(db, pid)
        prediction = _latest_prediction(db, pid)

        score, tier = _risk_from_prediction(prediction)

        original_cost = float(
            project.original_cost_crore or 0.0
        )

        current_cost = (
            float(update.revised_cost_crore)
            if update
            and update.revised_cost_crore is not None
            else original_cost
        )

        achieved = (
            int(update.milestones_achieved or 0)
            if update
            else 0
        )

        total = (
            int(update.milestones_total or 0)
            if update
            else 0
        )

        if status and status.lower() not in {
            "all",
            tier.lower()
        }:
            continue

        result.append(
            ProjectListItem(
                id=pid,
                name=project.project_name or "Unnamed Project",
                agency=(
                    project.implementing_agency
                    or "Unknown Agency"
                ),
                sector=(
                    project.sector
                    or "Infrastructure"
                ),
                original_cost=original_cost,
                anticipated_cost=current_cost,
                milestones_achieved=achieved,
                milestones_total=total,
                risk_score=score,
                risk_label=tier,
            )
        )

    return result
@router.get("/{project_id}/explanation")
def get_project_explanation(
    project_id: str,
    db: Session = Depends(get_db)
):
    clean_id = str(project_id).strip()

    project = (
        db.query(Project)
        .filter(
            func.trim(cast(Project.project_id, String))
            == clean_id
        )
        .first()
    )

    if not project:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{clean_id}' not found in database."
        )

    update = _latest_update(db, clean_id)

    if not update:
        raise HTTPException(
            status_code=404,
            detail="No project update found for this project."
        )

    target_month = str(update.report_month)[:7]

    try:
        features_df = build_feature_snapshot(
            project_id=clean_id,
            target_report_month=target_month,
            db=db
        )

        explanation = predictor.get_shap_explanation(
            features_df,
            top_n=5
        )

        return explanation

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"SHAP explanation failed: {exc}"
        )

@router.get(
    "/{project_id}",
    response_model=ProjectDetailResponse
)
def get_single_project(
    project_id: str,
    db: Session = Depends(get_db)
):
    clean_id = str(project_id).strip()

    project = (
        db.query(Project)
        .filter(
            func.trim(cast(Project.project_id, String))
            == clean_id
        )
        .first()
    )

    if not project:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Project ID '{clean_id}' "
                "not found in database."
            ),
        )

    canonical_id = str(project.project_id).strip()

    update = _latest_update(db, canonical_id)
    prediction = _latest_prediction(db, canonical_id)

    score, tier = _risk_from_prediction(prediction)

    original_cost = float(
        project.original_cost_crore or 0.0
    )

    anticipated_cost = (
        float(update.anticipated_cost_crore)
        if update
        and update.anticipated_cost_crore is not None
        else (
            float(update.revised_cost_crore)
            if update
            and update.revised_cost_crore is not None
            else original_cost
        )
    )

    expenditure = (
        float(update.cumulative_expenditure_crore or 0.0)
        if update
        else 0.0
    )

    revised_date = (
        update.revised_commissioning_date
        if update
        else None
    )

    anticipated_date = (
        update.anticipated_commissioning_date
        if update
        else None
    )

    display_comm = (
        anticipated_date
        or revised_date
        or project.original_commissioning_date
    )

    delay = _delay_months(
        project.original_commissioning_date,
        revised_date or anticipated_date
    )

    achieved = (
        int(update.milestones_achieved or 0)
        if update
        else 0
    )

    total = (
        int(update.milestones_total or 0)
        if update
        else 0
    )

    escalation = (
        (
            (anticipated_cost - original_cost)
            / original_cost
            * 100.0
        )
        if original_cost > 0
        else 0.0
    )

    return ProjectDetailResponse(
        id=canonical_id,
        name=(
            project.project_name
            or "Unnamed Project"
        ),
        agency=(
            project.implementing_agency
            or "Unknown Agency"
        ),
        sector=(
            project.sector
            or "Infrastructure"
        ),
        state=(
            project.state
            or "Unknown"
        ),
        approval_date=str(
            project.date_of_approval or "--"
        ),
        original_comm=str(
            project.original_commissioning_date
            or "--"
        ),
        anti_comm=str(
            display_comm or "--"
        ),
        original_cost=original_cost,
        anticipated_cost=anticipated_cost,
        expenditure=expenditure,
        delay_months=int(delay),
        milestones_achieved=achieved,
        milestones_total=total,
        cost_escalation_pct=round(
            escalation,
            2
        ),
        risk_score=score,
        risk_label=tier,

        cost_risk_probability=(
            float(prediction.cost_risk_probability)
            if prediction
            and prediction.cost_risk_probability is not None
            else 0.0
        ),

        schedule_risk_probability=(
            float(prediction.schedule_risk_probability)
            if prediction
            and prediction.schedule_risk_probability is not None
            else 0.0
        ),

        cox_risk_probability=(
            float(prediction.cox_risk_probability)
            if prediction
            and prediction.cox_risk_probability is not None
            else 0.0
        ),
    )


@router.post(
    "",
    response_model=dict,
    status_code=201
)
@router.post(
    "/",
    response_model=dict,
    status_code=201
)
def create_project(
    data: ProjectCreateRequest,
    db: Session = Depends(get_db),
):
    project_id = data.project_id.strip()
    if not project_id:
        raise HTTPException(status_code=422, detail="Project ID cannot be empty.")

    record = data.model_dump()
    record["project_id"] = project_id

    try:
        outcome = ingest_project_record(db, record)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Project ingestion failed: {exc}")

    return {
        "project_id": outcome["project_id"],
        "project_name": data.project_name,
        "report_month": outcome["report_month"],
        "message": (
            "Project created successfully"
            if outcome["project_created"]
            else "Project updated successfully"
        ),
    }
