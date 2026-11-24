from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class StoredFile(BaseModel):
    id: str = Field(default_factory=lambda: "")
    owner_user_id: str
    unit_id: Optional[str] = "default_unit"
    original_name: str
    content_type: str
    size_bytes: int
    storage_key: str
    status: str = "uploaded"  # uploaded, ready, error
    schema_profile: Optional[Dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
