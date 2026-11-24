from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field

class ChatSession(BaseModel):
    id: str = Field(default_factory=lambda: "")
    user_id: str
    unit_id: Optional[str] = "default_unit"
    title: str = "New Analysis"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
