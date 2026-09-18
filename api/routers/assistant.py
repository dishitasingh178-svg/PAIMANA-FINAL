from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db

from api.schemas.assistant import (
    AssistantRequest,
    AssistantResponse,
)

from api.services.llm_service import LLMService
from api.services.tool_registry import TOOL_REGISTRY


router = APIRouter(
    prefix="/api/v1/assistant",
    tags=["Assistant"],
)


# =============================================================
# GEMINI ASSISTANT SERVICE
# =============================================================

llm_service = LLMService(
    tool_registry=TOOL_REGISTRY
)


# =============================================================
# CONVERSATION HISTORY VALIDATION
# =============================================================

def prepare_conversation_history(
    history,
) -> list:
    """
    Convert API conversation history into a format that can
    safely be passed to the LLM service.

    Only user and assistant messages are accepted.
    Empty messages are ignored.
    """

    cleaned_history = []

    for message in history:

        role = str(message.role).strip().lower()

        content = str(message.content).strip()

        if not content:
            continue

        if role not in {"user", "assistant"}:
            continue

        cleaned_history.append(
            {
                "role": role,
                "content": content,
            }
        )

    return cleaned_history


# =============================================================
# MAIN ASSISTANT ENDPOINT
# =============================================================

@router.post(
    "",
    response_model=AssistantResponse,
)
@router.post(
    "/",
    response_model=AssistantResponse,
)
def ask_assistant(
    request: AssistantRequest,
    db: Session = Depends(get_db),
):
    """
    Main PAIMANA AI assistant endpoint.

    Flow:

        React
          ↓
        FastAPI
          ↓
        Conversation history
          ↓
        Gemini
          ↓
        PAIMANA tools
          ↓
        PostgreSQL
          ↓
        Gemini
          ↓
        Final answer
    """

    query = request.query.strip()

    # ---------------------------------------------------------
    # Empty query
    # ---------------------------------------------------------

    if not query:

        return AssistantResponse(
            answer_text=(
                "Please enter a question about PAIMANA."
            ),
            answer_audio_url=None,
            structured_data=None,
        )

    # ---------------------------------------------------------
    # Prepare previous conversation
    # ---------------------------------------------------------

    conversation_history = (
        prepare_conversation_history(
            request.conversation_history
        )
    )

    # ---------------------------------------------------------
    # Generate Gemini response
    # ---------------------------------------------------------

    result = llm_service.generate_response(
        user_query=query,
        db=db,
        conversation_history=conversation_history,
    )

    # ---------------------------------------------------------
    # Extract answer
    # ---------------------------------------------------------

    answer = result.get(
        "answer",
        "I could not generate a response.",
    )

    # ---------------------------------------------------------
    # Structured data
    #
    # This includes tool calls so the frontend can optionally
    # display project/risk information separately later.
    # ---------------------------------------------------------

    structured_data: Dict[str, Any] = {
        "success": result.get("success", False),
        "tool_calls": result.get(
            "tool_calls",
            [],
        ),
    }

    # Include error information only when something failed.

    if not result.get("success", False):

        structured_data["error"] = result.get(
            "error"
        )

    return AssistantResponse(
        answer_text=answer,
        answer_audio_url=None,
        structured_data=structured_data,
    )