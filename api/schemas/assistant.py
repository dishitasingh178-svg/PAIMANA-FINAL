from pydantic import BaseModel
from typing import Optional, Any


class AssistantRequest(BaseModel):
    user_id: Optional[str] = None
    query: str
    voice: bool = False


class AssistantResponse(BaseModel):
    answer_text: str
    answer_audio_url: Optional[str] = None
    structured_data: Optional[Any] = None