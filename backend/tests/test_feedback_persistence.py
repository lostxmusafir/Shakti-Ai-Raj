import pytest

from app.ai.learning.feedback_service import FeedbackService, FeedbackSubmission
from app.db.mongodb import MongoDBManager


@pytest.mark.asyncio
async def test_feedback_persists_through_existing_repository(tmp_path):
    await MongoDBManager.connect()
    dataset = tmp_path / "feedback.csv"
    dataset.write_text("id,val\n1,100\n2,200\n", encoding="utf-8")
    service = FeedbackService()
    record = await service.record_feedback_async(FeedbackSubmission(
        analysis_id="analysis-persisted",
        user_id="user-1",
        unit_id="unit-1",
        question="Total value kitna hai?",
        category="incorrect_calculation",
        correction_sql="SELECT SUM(val) AS total FROM dataset",
        dataset_path=str(dataset),
    ))
    assert record.verification_status == "verified"
    saved = await service.repository.get_by_id(record.id)
    assert saved is not None
    assert saved.analysis_id == "analysis-persisted"
