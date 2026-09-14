from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from api.models.models import Project, Prediction

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


def latest_predictions(db: Session):
    rows = db.query(Prediction).order_by(Prediction.project_id, Prediction.generated_at.desc(), Prediction.prediction_id.desc()).all()
    result = {}
    for row in rows:
        result.setdefault(str(row.project_id).strip(), row)
    return result


@router.get("/sectors")
def get_sector_analytics(db: Session = Depends(get_db)):
    preds = latest_predictions(db)
    projects = {str(p.project_id).strip(): p for p in db.query(Project).all()}
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
    projects = {str(p.project_id).strip(): p for p in db.query(Project).all()}
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
