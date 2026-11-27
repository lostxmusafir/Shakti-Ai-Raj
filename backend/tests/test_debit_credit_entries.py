import duckdb
import pytest

from app.ai.orchestration.orchestrator import AnalysisOrchestrator
from app.ai.planning.schemas import AnalysisPlan, DatasetRef, AggregateOperation
from app.ai.verification.verifier import ResultVerifier
from app.analysis.execution.duckdb_engine import DuckDBEngine
from app.analysis.profiling.profiler import DataProfiler
from app.models.file import StoredFile


@pytest.mark.parametrize("question", [
    "Debit aur credit entries alag alag kitni hain?",
    "How many debit and credit entries are there separately?",
    "Debit credit count batao",
    "Kitne debit aur kitne credit transactions hain?",
])
@pytest.mark.asyncio
async def test_entry_counts_have_two_scalar_metrics(tmp_path, question):
    path = tmp_path / "transactions.csv"
    path.write_text("Debit,Credit\n,\n0,50\n25,0\n30,0\n0,15\n", encoding="utf-8")
    file = StoredFile(id="transactions", owner_user_id="user", original_name=path.name,
                      content_type="text/csv", size_bytes=path.stat().st_size, storage_key=path.name,
                      schema_profile=DataProfiler.profile_file(str(path), path.name))
    files = {file.id: file}
    plan = await AnalysisOrchestrator()._plan_with_ai(question, [file.id], files, "DATA_ANALYSIS")
    assert plan.intent == "comparative_count"
    assert not plan.group_by and not plan.filters
    assert "GROUP BY" not in plan.sql_query.upper()
    result = DuckDBEngine.execute(plan, files, {file.id: str(path)})
    independent = duckdb.sql(f"SELECT COUNT(*) FILTER (WHERE Debit <> 0), COUNT(*) FILTER (WHERE Credit <> 0) FROM read_csv_auto('{path.as_posix()}')").fetchall()[0]
    assert result["rows"] == [{"debit_entries": independent[0], "credit_entries": independent[1]}]
    assert result["rows"] == [{"debit_entries": 2, "credit_entries": 2}]
    assert ResultVerifier.verify(plan, result, files)["passed"] is True

    old_plan = AnalysisPlan(question=question, datasets=[DatasetRef(file_id=file.id, alias="ds_1")],
                            group_by=["Debit", "Credit"],
                            aggregations=[AggregateOperation(function="count", column="*", alias="record_count")])
    old_result = DuckDBEngine.execute(old_plan, files, {file.id: str(path)})
    assert ResultVerifier.verify(old_plan, old_result, files)["passed"] is False


def test_top_debit_amounts_remain_value_analysis(tmp_path):
    path = tmp_path / "transactions.csv"
    path.write_text("Debit,Credit\n10,0\n10,0\n20,0\n", encoding="utf-8")
    file = StoredFile(id="transactions", owner_user_id="user", original_name=path.name,
                      content_type="text/csv", size_bytes=path.stat().st_size, storage_key=path.name,
                      schema_profile=DataProfiler.profile_file(str(path), path.name))
    plan = AnalysisOrchestrator()._plan_fallback("Top debit amounts dikhao", [file.id], {file.id: file}, "DATA_ANALYSIS")
    assert plan.intent != "comparative_count"
    assert plan.group_by == ["Debit"]
