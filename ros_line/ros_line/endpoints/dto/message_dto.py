from pydantic import BaseModel
from typing import Optional
class ChatRequestDTO(BaseModel):
    """Represent all the attributes asked for the LLM Query."""
    message: str
    user_id: str
    mime_type: Optional[str] = None
    file_base64: Optional[str] = None