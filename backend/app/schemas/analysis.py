from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field

class AnalysisResponse(BaseModel):
    id: str
    chat_id: str
    message_id: str
    user_id: str
    status: str
    thread_id: Optional[str] = None
    intent: Optional[str] = None
    question: str
    plan: Optional[Dict[str, Any]] = None
    pending_interrupt: Optional[Dict[str, Any]] = None
    resolved_bindings: List[Dict[str, Any]] = Field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    verification: Optional[Dict[str, Any]] = None
    provenance: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
