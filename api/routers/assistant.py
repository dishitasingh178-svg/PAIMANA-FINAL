from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from api.models.models import Project, Prediction
from api.schemas.assistant import AssistantRequest, AssistantResponse

router = APIRouter(prefix="/api/v1/assistant", tags=["Assistant"])


@router.post("", response_model=AssistantResponse)
@router.post("/", response_model=AssistantResponse)
def ask_assistant(request: AssistantRequest, db: Session = Depends(get_db)):
    query = request.query.strip().lower()
    if "critical" in query:
        rows = (
            db.query(Project, Prediction)
            .join(Prediction, Prediction.project_id == Project.project_id)
            .filter(Prediction.composite_risk_score >= 75)
            .order_by(Prediction.composite_risk_score.desc())
            .limit(10).all()
        )
        if rows:
            names = ", ".join(p.project_name for p, _ in rows)
            answer = f"I found {len(rows)} critical-risk prediction records. Highest-priority projects include: {names}."
        else:
            answer = "No critical-risk predictions are currently stored. Run predictions for the imported projects first."
    else:
        answer = "I can currently answer portfolio risk questions from stored PAIMANA predictions. Try: 'Which projects are at critical risk?'"
    return AssistantResponse(answer_text=answer, answer_audio_url=None, structured_data=None)
