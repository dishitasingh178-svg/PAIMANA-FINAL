from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from api.models.models import Alert
from api.services.alert_priority import CLOSED, TriageContext, actionable_alerts, priority_projects, transition_status

router = APIRouter(prefix="/api/v1/alerts", tags=["Alerts"])
AlertStatus = Literal["NEW", "ACKNOWLEDGED", "UNDER_REVIEW", "RESOLVED", "DISMISSED"]


class AlertStatusRequest(BaseModel):
    status: AlertStatus
    review_note: Optional[str] = Field(default=None, max_length=5000)


@router.get("")
@router.get("/")
def get_alerts(
    status: Optional[AlertStatus] = None,
    severity: Optional[Literal["WATCH", "ELEVATED", "CRITICAL"]] = None,
    alert_class: Optional[Literal["PREDICTIVE", "DETERIORATION", "OBSERVED_ISSUE"]] = None,
    min_priority: float = Query(default=0, ge=0, le=100),
    project_id: Optional[str] = None,
    include_closed: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    items = [a for a in actionable_alerts(db)
             if (a["status"] == status if status else include_closed or a["status"] not in CLOSED)
             and (not severity or a["severity"] == severity)
             and (not alert_class or a["alert_class"] == alert_class)
             and (not project_id or a["project_id"] == project_id)
             and a["priority_score"] >= min_priority]
    return items[offset:offset + limit]


@router.get("/priority")
def get_priority(limit: int = Query(default=10, ge=1, le=100), db: Session = Depends(get_db)):
    return priority_projects(actionable_alerts(db))[:limit]


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    items = actionable_alerts(db)
    return {"new": sum(a["status"] == "NEW" for a in items),
            "immediate": sum(p["priority_label"] == "IMMEDIATE" for p in priority_projects(items)),
            "under_review": sum(a["status"] == "UNDER_REVIEW" for a in items),
            "resolved": sum(a["status"] == "RESOLVED" for a in items)}


@router.patch("/{alert_id}/status")
def update_status(alert_id: int, payload: AlertStatusRequest, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).with_for_update().first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    transition_status(alert, payload.status, payload.review_note)
    db.commit()
    db.refresh(alert)
    return TriageContext(db).serialize(alert)
