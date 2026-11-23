from datetime import datetime, timezone
from pydantic import BaseModel, Field

class Unit(BaseModel):
    id: str = Field(default_factory=lambda: "")
    name: str
    code: str
    status: str = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
