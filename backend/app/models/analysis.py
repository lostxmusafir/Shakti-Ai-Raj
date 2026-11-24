from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class AnalysisRun(BaseModel):
    id: str = Field(default_factory=lambda: "")
    chat_id: str
    message_id: str
    user_id: str
    unit_id: Optional[str] = "default_unit"
    status: str = "created"  # created, queued, understanding, planning, executing, verifying, completed, failed
    intent: Optional[str] = None
    question: str = ""
    plan: Optional[Dict[str, Any]] = Field(default_factory=dict)
    input_file_ids: List[str] = Field(default_factory=list)
    policy_ids: List[str] = Field(default_factory=list)
    execution_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = Field(default_factory=dict)
    verification: Optional[Dict[str, Any]] = Field(default_factory=dict)
    provenance: Optional[Dict[str, Any]] = Field(default_factory=dict)
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
