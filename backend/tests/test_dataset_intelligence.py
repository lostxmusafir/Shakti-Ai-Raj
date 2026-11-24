import os

from app.ai.orchestration.orchestrator import AnalysisOrchestrator
from app.ai.planning.schemas import AnalysisPlan
from app.ai.verification.verifier import ResultVerifier
from app.analysis.profiling.profiler import DataProfiler
from app.models.file import StoredFile


def _nexus_file() -> StoredFile:
    path = os.path.abspath("data/samples/NexusDynamics_Incidents_5000.csv")
    return StoredFile(
        id="nexus",
        owner_user_id="user_1",
        original_name="NexusDynamics_Incidents_5000.csv",
        content_type="text/csv",
        size_bytes=os.path.getsize(path),
        storage_key="nexus.csv",
        schema_profile=DataProfiler.profile_file(path, "NexusDynamics_Incidents_5000.csv"),
    )


def test_hinglish_sender_volume_plan_uses_profiled_columns():
    stored_file = _nexus_file()
    plan = AnalysisOrchestrator()._plan_fallback(
        "Bahar sabse zyada data kisne bheja",
        [stored_file.id],
        {stored_file.id: stored_file},
        "DATA_ANALYSIS",
    )

    assert plan.group_by == ["Source"]
    assert plan.aggregations[0].function == "sum"
    assert plan.aggregations[0].column == "Transaction Size (KB)"
    assert plan.sort[0].ascending is False
    assert any(condition.column == "Destination" for condition in plan.filters)


def test_blocked_question_uses_actual_status_values():
    stored_file = _nexus_file()
    plan = AnalysisOrchestrator()._plan_fallback(
        "Blocked incidents",
        [stored_file.id],
        {stored_file.id: stored_file},
        "DATA_ANALYSIS",
    )

    assert any(
        condition.column == "Action" and condition.value == "Blocked"
        for condition in plan.filters
    )
    assert plan.aggregations[0].function == "count"
    assert plan.group_by


def test_verifier_does_not_claim_recompute_pass_without_check():
    stored_file = _nexus_file()
    plan = AnalysisPlan(
        question="Count rows",
        datasets=[{"file_id": stored_file.id, "alias": "dataset"}],
        aggregations=[{"function": "count", "column": "*", "alias": "matched_count"}],
    )
    result = {"columns": ["matched_count"], "rows": [{"matched_count": 1}], "row_count": 1}

    verification = ResultVerifier.verify(plan, result, {stored_file.id: stored_file})

    recompute_check = next(
        check for check in verification["checks"] if check["gate"] == "V3_RECOMPUTE"
    )
    assert recompute_check["status"] != "passed"
    assert verification["passed"] is False
