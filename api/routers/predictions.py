from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from api.schemas.prediction import PredictionRequest, PredictionResponse
from api.services.prediction_service import generate_prediction

router = APIRouter(prefix="/api/v1/predictions", tags=["Predictions"])


@router.post("", response_model=PredictionResponse)
@router.post("/", response_model=PredictionResponse)
def create_prediction(request: PredictionRequest, db: Session = Depends(get_db)):
    project_id = str(request.project_id).strip()
    target_month = (request.report_month or "").strip()[:7]

    if not target_month:
        from datetime import datetime
        target_month = datetime.utcnow().strftime("%Y-%m")

    try:
        return generate_prediction(db, project_id, target_month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Model inference failed: {exc}")

    db_prediction = Prediction(
        project_id=str(project.project_id).strip(),
        report_month=target_month,
        **prediction_result,
    )
    db.add(db_prediction)

    if prediction_result["risk_tier"] in {"ELEVATED", "CRITICAL"}:
        db.add(Alert(
            project_id=str(project.project_id).strip(),
            alert_type="ML_RISK_WARNING",
            severity=prediction_result["risk_tier"],
            message=f"Project reached {prediction_result['risk_tier']} status (Score: {prediction_result['composite_risk_score']:.1f}/100).",
        ))

    db.commit()
    db.refresh(db_prediction)
    return db_prediction
