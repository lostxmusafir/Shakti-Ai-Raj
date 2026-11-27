from typing import List, Optional
from pydantic import BaseModel, Field

class AIContext(BaseModel):
    user_id: str
    unit_id: str = "default_unit"
    role: str = "employee"
    chat_id: str
    file_ids: List[str] = Field(default_factory=list)
    ai_tier: str = "low"  # Both tiers currently use the free Zhipu GLM-4.5-Flash model.
    allowed_tools: List[str] = Field(default_factory=lambda: [
        "inspect_file", "describe_columns", "query_dataset", "aggregate_dataset", "evaluate_rule"
    ])
