from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel

class FileResponse(BaseModel):
    id: str
    original_name: str
    content_type: str
    size_bytes: int
    status: str
    schema_profile: Optional[Dict[str, Any]] = None
    created_at: datetime
