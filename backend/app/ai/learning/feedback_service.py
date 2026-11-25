import os
import json
import logging
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel, Field
import duckdb
from app.db.repository import BaseRepository

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
GOLDEN_FILE = os.path.join(BASE_DIR, "data", "benchmark", "golden", "golden_examples_300.json")

FeedbackCategory = Literal[
    "correct",
    "incorrect_answer",
    "wrong_filter",
    "wrong_dataset",
    "incorrect_calculation",
    "missing_policy_context",
    "column_mapping_error"
]

class FeedbackSubmission(BaseModel):
    analysis_id: str
    user_id: str
    unit_id: str
    user_role: str = "employee"
    question: str
    category: FeedbackCategory
    comment: Optional[str] = None
    correction_sql: Optional[str] = None
    dataset_path: Optional[str] = None
    approved_by: Optional[str] = None

class FeedbackRequest(BaseModel):
    category: FeedbackCategory
    comment: Optional[str] = None
    correction: Optional[Dict[str, Any]] = None
    correction_sql: Optional[str] = None
    dataset_path: Optional[str] = None

class FeedbackRecord(BaseModel):
    id: str = ""
    feedback_id: str
    analysis_id: str
    user_id: str
    unit_id: str
    question: str
    category: FeedbackCategory
    comment: Optional[str] = None
    correction_sql: Optional[str] = None
    verification_status: str = "unverified"
    promotion_status: str = "pending"
    verified_rows: Optional[List[Dict[str, Any]]] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class FeedbackService:
    """
    Manages user feedback, corrections, and promotion of verified examples
    into the golden benchmark store following human-in-the-loop validation.
    """

    def __init__(self):
        self.repository = BaseRepository("learning_feedback", FeedbackRecord)

    async def record_feedback_async(self, submission: FeedbackSubmission) -> FeedbackRecord:
        record = self.record_feedback(submission)
        return await self.repository.create(record)

    @classmethod
    def record_feedback(cls, submission: FeedbackSubmission) -> FeedbackRecord:
        feedback_id = f"fb_{hashlib.sha256(f'{submission.analysis_id}_{submission.question}_{datetime.now().isoformat()}'.encode()).hexdigest()[:12]}"
        
        record = FeedbackRecord(
            feedback_id=feedback_id,
            analysis_id=submission.analysis_id,
            user_id=submission.user_id,
            unit_id=submission.unit_id,
            question=submission.question,
            category=submission.category,
            comment=submission.comment,
            correction_sql=submission.correction_sql,
            verification_status="unverified",
            promotion_status="pending"
        )

        # If a corrected SQL is provided and dataset path exists, independently verify via DuckDB
        if submission.correction_sql and submission.dataset_path and os.path.exists(submission.dataset_path):
            try:
                con = duckdb.connect(":memory:")
                ext = os.path.splitext(submission.dataset_path)[1].lower()
                if ext == ".csv":
                    con.execute("CREATE TABLE dataset AS SELECT * FROM read_csv_auto(?)", [submission.dataset_path])
                    con.execute("CREATE VIEW v AS SELECT * FROM dataset")
                con.execute("SET enable_external_access = false")
                cursor = con.execute(submission.correction_sql)
                cols = [desc[0] for desc in cursor.description]
                raw_rows = cursor.fetchall()
                verified_rows = [dict(zip(cols, r)) for r in raw_rows]
                con.close()

                record.verification_status = "verified"
                record.verified_rows = verified_rows[:20]
            except Exception as e:
                logger.error(f"Failed to independently verify corrected SQL: {e}")
                record.verification_status = "verification_failed"

        # Super-admin or unit_admin auto-promotion for verified corrections
        if record.verification_status == "verified" and submission.user_role in ["super_admin", "unit_admin", "tech_admin"]:
            cls.promote_to_golden(record, approved_by=submission.approved_by or submission.user_id)
            record.promotion_status = "promoted"

        return record

    @classmethod
    def promote_to_golden(cls, record: FeedbackRecord, approved_by: str) -> bool:
        if record.verification_status != "verified":
            raise ValueError("Only independently verified feedback corrections can be promoted to golden store.")
            
        golden_file = os.environ.get("GOLDEN_EXAMPLES_PATH", GOLDEN_FILE)
        if not os.path.exists(golden_file):
            logger.warning(f"Golden file not found at {golden_file}")
            return False

        try:
            with open(golden_file, "r", encoding="utf-8") as f:
                golden_data = json.load(f)

            new_example = {
                "example_id": f"ex-fb-{record.feedback_id}",
                "dataset_name": "user_feedback_promotion",
                "question": record.question,
                "language": "hinglish" if any(ord(c) > 127 for c in record.question) or "kisne" in record.question.lower() else "english",
                "intent": "data_analysis",
                "split": "train",
                "source_type": "user_correction",
                "approval_status": "approved",
                "approved_by": approved_by,
                "column_mapping": {},
                "sql_query": record.correction_sql,
                "expected_answer": {
                    "row_count": len(record.verified_rows or []),
                    "rows": record.verified_rows or []
                },
                "unit_id": record.unit_id
            }

            golden_data.append(new_example)

            with open(golden_file, "w", encoding="utf-8") as f:
                json.dump(golden_data, f, indent=2)

            logger.info(f"Successfully promoted feedback {record.feedback_id} to golden example store.")
            return True
        except Exception as e:
            logger.error(f"Failed to append promoted golden example: {e}")
            return False

feedback_service = FeedbackService()
