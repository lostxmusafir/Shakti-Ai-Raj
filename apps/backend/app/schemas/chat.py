from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

class CreateChatRequest(BaseModel):
    title: Optional[str] = "New Analysis"

class ChatSessionResponse(BaseModel):
    id: str
    user_id: str
    unit_id: Optional[str] = None
    title: str
    created_at: datetime
    updated_at: datetime

class SendMessageRequest(BaseModel):
    content: str
    file_ids: List[str] = Field(default_factory=list)

class MessageResponse(BaseModel):
    id: str
    chat_id: str
    user_id: str
    role: str
    content: str
    attachments: List[str] = Field(default_factory=list)
    analysis_id: Optional[str] = None
    created_at: datetime
