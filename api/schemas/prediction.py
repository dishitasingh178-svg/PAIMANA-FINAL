from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class PredictionRequest(BaseModel):
    project_id: str
    report_month: Optional[str] = None

class PredictionResponse(BaseModel):
    project_id: str
    report_month: str
    cost_risk_probability: float
    schedule_risk_probability: float
    cox_risk: float
    cox_risk_probability: float
    composite_risk_score: float
    risk_tier: str
    model_version: str

    class Config:
        from_attributes = True  # Allows mapping from SQLAlchemy ORM models