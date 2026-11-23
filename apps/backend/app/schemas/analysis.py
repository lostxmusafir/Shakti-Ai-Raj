from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field

class AnalysisResponse(BaseModel):
    id: str
    chat_id: str
    message_id: str
    user_id: str
    status: str
    intent: Optional[str] = None
    question: str
    plan: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    verification: Optional[Dict[str, Any]] = None
    provenance: Optional[Dict[str, Any]] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
