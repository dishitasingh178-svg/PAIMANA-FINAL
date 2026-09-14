from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session

from database import get_db
from api.models.models import Project, ProjectUpdate, Prediction


router = APIRouter(prefix="/api/v1/projects", tags=["Projects"])


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
    risk_score: float
    risk_label: str


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
    # ---------------------------------------------------------
    # 1. Clean and validate Project ID
    # ---------------------------------------------------------

    project_id = data.project_id.strip()

    if not project_id:
        raise HTTPException(
            status_code=422,
            detail="Project ID cannot be empty."
        )

    # ---------------------------------------------------------
    # 2. Check whether Project ID already exists
    # ---------------------------------------------------------

    existing = (
        db.query(Project)
        .filter(
            func.trim(cast(Project.project_id, String))
            == project_id
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Project ID '{project_id}' "
                "already exists."
            ),
        )

    # ---------------------------------------------------------
    # 3. Create the main Project record
    # ---------------------------------------------------------

    project = Project(
        project_id=project_id,
        project_name=data.project_name,
        implementing_agency=data.implementing_agency,
        sector=data.sector,
        state=data.state,
        date_of_approval=data.date_of_approval,
        original_cost_crore=data.original_cost_crore,
        original_commissioning_date=(
            data.original_commissioning_date
        ),
    )

    db.add(project)
    db.flush()

    # ---------------------------------------------------------
    # 4. Determine report month
    # ---------------------------------------------------------

    if data.date_of_approval:
        report_month = (
            data.date_of_approval.strftime("%Y-%m")
        )
    else:
        report_month = date.today().strftime("%Y-%m")

    # ---------------------------------------------------------
    # 5. Create the first ProjectUpdate record
    # ---------------------------------------------------------

    update = ProjectUpdate(
        project_id=project_id,
        report_month=report_month,
        serial_no=1,

        revised_cost_crore=(
            data.revised_cost_crore
        ),

        anticipated_cost_crore=(
            data.anticipated_cost_crore
        ),

        cumulative_expenditure_crore=(
            data.cumulative_expenditure_crore
        ),

        revised_commissioning_date=(
            data.revised_commissioning_date
        ),

        anticipated_commissioning_date=(
            data.anticipated_commissioning_date
        ),

        delay_original_months=(
            data.delay_original_months
        ),

        delay_revised_months=(
            data.delay_revised_months
        ),

        milestones_achieved=(
            data.milestones_achieved
        ),

        milestones_total=(
            data.milestones_total
        ),
    )

    db.add(update)

    # ---------------------------------------------------------
    # 6. Commit both Project + ProjectUpdate
    # ---------------------------------------------------------

    db.commit()

    # ---------------------------------------------------------
    # 7. Return information needed by frontend
    # ---------------------------------------------------------

    return {
        "project_id": project_id,
        "project_name": project.project_name,
        "report_month": report_month,
        "message": "Project created successfully",
    }