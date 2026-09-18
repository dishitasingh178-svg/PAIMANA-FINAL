from typing import Any, List, Optional

from pydantic import BaseModel, Field


class ConversationMessage(BaseModel):
    """
    One message from the conversation history.

    role:
        user      = message written by the user
        assistant = previous PAIMANA response
    """

    role: str
    content: str


class AssistantRequest(BaseModel):
    """
    Request sent to the PAIMANA AI assistant.
    """

    user_id: Optional[str] = None

    query: str

    voice: bool = False

    conversation_history: List[ConversationMessage] = Field(
        default_factory=list
    )


class AssistantResponse(BaseModel):
    """
    Response returned by the PAIMANA AI assistant.
    """

    answer_text: str

    answer_audio_url: Optional[str] = None

    structured_data: Optional[Any] = None