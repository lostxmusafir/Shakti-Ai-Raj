from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    details: Optional[Dict[str, Any]] = Field(default_factory=dict)

class ErrorResponse(BaseModel):
    error: ErrorDetail
