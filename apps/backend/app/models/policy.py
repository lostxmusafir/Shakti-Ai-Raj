from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class PolicyRule(BaseModel):
    rule_id: str
    description: str
    condition: Dict[str, Any]  # field, operator, value/value_source
    exceptions: List[str] = Field(default_factory=list)
    severity: str = "medium"  # low, medium, high, critical

class Policy(BaseModel):
    id: str = Field(default_factory=lambda: "")
    policy_code: str
    title: str
    department: str
    unit_ids: List[str] = Field(default_factory=list)
    status: str = "active"  # draft, active, archived
    version: int = 1
    effective_from: str = "2026-01-01"
    effective_until: Optional[str] = None
    description: str = ""
    rules: List[PolicyRule] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
