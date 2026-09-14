from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import String, cast, func

from database import get_db
from api.models.models import Alert, Project

router = APIRouter(prefix="/api/v1/alerts", tags=["Alerts"])


@router.get("")
@router.get("/")
def get_alerts(db: Session = Depends(get_db)):
    rows = (
        db.query(Alert, Project)
        .join(Project, Project.project_id == Alert.project_id)
        .filter(Alert.is_resolved.is_(False))
        .order_by(Alert.triggered_at.desc())
        .limit(100)
        .all()
    )
    alerts = [
        {
            "alert_id": int(alert.alert_id),
            "project_id": str(alert.project_id).strip(),
            "project_name": project.project_name or f"Project #{alert.project_id}",
            "sector": project.sector or "Infrastructure",
            "issue_summary": alert.message,
            "trigger_reason": alert.alert_type,
            "severity": alert.severity,
            "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else None,
        }
        for alert, project in rows
    ]
    return alerts
