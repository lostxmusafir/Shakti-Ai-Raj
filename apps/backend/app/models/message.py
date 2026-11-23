from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: "")
    chat_id: str
    user_id: str
    role: str  # user, assistant, system
    content: str
    attachments: List[str] = Field(default_factory=list)  # file_ids
    analysis_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
