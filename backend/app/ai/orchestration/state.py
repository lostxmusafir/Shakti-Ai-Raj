from enum import Enum

class AnalysisState(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    UNDERSTANDING = "understanding"
    RETRIEVING_CONTEXT = "retrieving_context"
    PLANNING = "planning"
    VALIDATING_PLAN = "validating_plan"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    INTERRUPTED = "interrupted"
    GENERATING_ANSWER = "generating_answer"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
