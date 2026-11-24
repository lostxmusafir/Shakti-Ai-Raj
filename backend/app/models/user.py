from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field

class User(BaseModel):
    id: str = Field(default_factory=lambda: "")
    email: str
    name: str
    hashed_password: str
    role: str = "employee"  # employee, unit_admin, super_admin, tech_admin
    unit_id: Optional[str] = "default_unit"
    status: str = "active"  # active, suspended
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
