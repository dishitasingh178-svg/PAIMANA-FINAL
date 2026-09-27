from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import distinct_on

from database import get_db
from api.models.models import Project, Prediction, ProjectUpdate

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


def _postgres(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def latest_predictions(db: Session):
    # Most recently generated prediction per project. Only the score is read by
    # these endpoints, and PostgreSQL keeps just one row per project.
    query = db.query(Prediction.project_id, Prediction.composite_risk_score)
    if _postgres(db):
        query = query.ext(distinct_on(Prediction.project_id))
    rows = query.order_by(Prediction.project_id, Prediction.generated_at.desc(), Prediction.prediction_id.desc()).all()
    result = {}
    for row in rows:
        result.setdefault(str(row.project_id).strip(), row)
    return result


def _project_rows(db: Session):
    """The project columns these analytics read (not whole ORM objects)."""
    return db.query(Project.project_id, Project.sector, Project.state, Project.original_cost_crore).all()


@router.get("/sectors")
def get_sector_analytics(db: Session = Depends(get_db)):
    preds = latest_predictions(db)
    projects = {str(p.project_id).strip(): p for p in _project_rows(db)}
    data = {}
    for pid, pred in preds.items():
        p = projects.get(pid)
        if not p: continue
        s = p.sector or "Unknown"
        bucket = data.setdefault(s, {"projects": 0, "low": 0, "watch": 0, "elevated": 0, "critical": 0})
        bucket["projects"] += 1
        score = float(pred.composite_risk_score or 0)
        if score >= 75: bucket["critical"] += 1
        elif score >= 50: bucket["elevated"] += 1
        elif score >= 25: bucket["watch"] += 1
        else: bucket["low"] += 1
    return {"data": [{"sector": k, **v} for k, v in sorted(data.items())]}


@router.get("/states")
def get_state_analytics(db: Session = Depends(get_db)):
    preds = latest_predictions(db)
    projects = {str(p.project_id).strip(): p for p in _project_rows(db)}
    data = {}
    for pid, pred in preds.items():
        p = projects.get(pid)
        if not p: continue
        s = p.state or "Unknown"
        bucket = data.setdefault(s, {"projects": 0, "high_risk": 0})
        bucket["projects"] += 1
        if float(pred.composite_risk_score or 0) >= 50: bucket["high_risk"] += 1
    return {"data": [{"state": k, **v} for k, v in sorted(data.items())]}


@router.get("/trends")
def get_trend_analytics(db: Session = Depends(get_db)):
    rows = db.query(Prediction.report_month, func.avg(Prediction.composite_risk_score)).group_by(Prediction.report_month).order_by(Prediction.report_month).all()
    return {"data": [{"report_month": month, "average_risk_score": round(float(avg or 0), 2)} for month, avg in rows]}


ONGOING_DEFINITION = (
    "Latest reported anticipated (else revised) commissioning date is today or later, "
    "or no commissioning date has been reported."
)
RISK_EXPOSURE_DEFINITION = (
    "Sum over ongoing projects of latest cost (crore) x composite risk score / 100. "
    "Ongoing projects without a prediction contribute nothing and are counted in ongoing_unscored."
)
PREDICTION_BASIS = (
    "Most recently generated prediction per project (same convention as /analytics/sectors and "
    "/analytics/states); this is not necessarily the latest report month."
)


@router.get("/state-summary")
def get_state_summary(db: Session = Depends(get_db)):
    """Read-only per-state portfolio summary for the dashboard map.

    - ongoing: see ONGOING_DEFINITION (the schema has no project status column).
    - latest_cost_crore: latest update's anticipated cost, else revised cost,
      else the original sanctioned cost.
    - Risk counts use the same latest prediction per project as /analytics/states.
    - risk_exposure_crore: see RISK_EXPOSURE_DEFINITION.
    - Projects with a blank state are returned with state=None, never reassigned.
    """
    today = date.today()
    preds = latest_predictions(db)
    # Only the columns needed (plain rows, not ORM objects): the updates table is large.
    latest_updates = {}
    update_query = db.query(
        ProjectUpdate.project_id, ProjectUpdate.anticipated_cost_crore, ProjectUpdate.revised_cost_crore,
        ProjectUpdate.anticipated_commissioning_date, ProjectUpdate.revised_commissioning_date,
    )
    if _postgres(db):
        # (project_id, report_month) is unique: one row per project, read by
        # walking the (project_id, report_month) index backwards.
        update_query = update_query.ext(distinct_on(ProjectUpdate.project_id)).order_by(
            ProjectUpdate.project_id.desc(), ProjectUpdate.report_month.desc())
    else:
        update_query = update_query.order_by(ProjectUpdate.project_id, ProjectUpdate.report_month.desc(), ProjectUpdate.id.desc())
    for update in update_query:
        latest_updates.setdefault(str(update.project_id).strip(), update)

    buckets = {}
    for project in _project_rows(db):
        pid = str(project.project_id).strip()
        key = (project.state or "").strip().upper() or None
        b = buckets.setdefault(key, {
            "projects": 0, "ongoing": 0,
            "original_cost_crore": 0.0, "latest_cost_crore": 0.0, "ongoing_latest_cost_crore": 0.0,
            "high_risk": 0, "critical": 0, "ongoing_high_risk": 0, "unscored": 0,
            "risk_exposure_crore": 0.0, "ongoing_unscored": 0,
        })
        update = latest_updates.get(pid)
        target = (update.anticipated_commissioning_date or update.revised_commissioning_date) if update else None
        ongoing = target is None or target >= today
        original = float(project.original_cost_crore or 0)
        latest_cost = float(
            (update and (update.anticipated_cost_crore or update.revised_cost_crore))
            or project.original_cost_crore or 0
        )
        b["projects"] += 1
        b["original_cost_crore"] += original
        b["latest_cost_crore"] += latest_cost
        if ongoing:
            b["ongoing"] += 1
            b["ongoing_latest_cost_crore"] += latest_cost

        pred = preds.get(pid)
        score = float(pred.composite_risk_score) if pred is not None and pred.composite_risk_score is not None else None
        if ongoing:
            if score is None:
                b["ongoing_unscored"] += 1
            else:
                b["risk_exposure_crore"] += latest_cost * score / 100.0
        if score is None:
            b["unscored"] += 1
        elif score >= 50:
            b["high_risk"] += 1
            if score >= 75:
                b["critical"] += 1
            if ongoing:
                b["ongoing_high_risk"] += 1

    rows = []
    for state, b in sorted(buckets.items(), key=lambda kv: (kv[0] is None, kv[0] or "")):
        rows.append({
            "state": state,
            **{k: (round(v, 2) if isinstance(v, float) else v) for k, v in b.items()},
        })
    return {
        "as_of": today.isoformat(),
        "ongoing_definition": ONGOING_DEFINITION,
        "risk_exposure_definition": RISK_EXPOSURE_DEFINITION,
        "prediction_basis": PREDICTION_BASIS,
        "data": rows,
    }
