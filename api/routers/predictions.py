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
