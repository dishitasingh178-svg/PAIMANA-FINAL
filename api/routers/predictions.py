from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import String, cast, func
from sqlalchemy.orm import Session

from database import get_db
from api.models.models import Project, Prediction, Alert
from api.ml.feature_engineering import build_feature_snapshot
from api.schemas.prediction import PredictionRequest, PredictionResponse
import ml_package.predictor as predictor

router = APIRouter(prefix="/api/v1/predictions", tags=["Predictions"])


@router.post("", response_model=PredictionResponse)
@router.post("/", response_model=PredictionResponse)
def create_prediction(request: PredictionRequest, db: Session = Depends(get_db)):
    project_id = str(request.project_id).strip()
    project = db.query(Project).filter(func.trim(cast(Project.project_id, String)) == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found in the database")

    target_month = (request.report_month or datetime.utcnow().strftime("%Y-%m")).strip()[:7]
    try:
        features_df = build_feature_snapshot(project_id=project_id, target_report_month=target_month, db=db)
        prediction_result = predictor.predict_project_row(features_df)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
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
