from datetime import date

import duckdb
from app.ai.orchestration import langgraph_workflow
from app.ai.orchestration.langgraph_workflow import LangGraphAnalystWorkflow
from app.ai.orchestration.temporal import resolve_temporal_window
from app.ai.planning.schemas import AnalysisPlan, AggregateOperation, Condition, DatasetRef
from app.ai.verification.verifier import ResultVerifier
from app.ai.verification import verifier as verifier_module
from app.analysis.execution.compiler import QueryCompiler
from app.models.file import StoredFile


def test_last_month_window_is_calendar_month_and_end_exclusive():
    assert resolve_temporal_window("Last month ka revenue batao", as_of=date(2026, 11, 26)) == {
        "period": "last_month",
        "start": "2026-10-01",
        "end": "2026-11-01",
    }


def test_date_range_compiles_as_typed_half_open_filter():
    plan = AnalysisPlan(
        question="Last month transactions",
        datasets=[DatasetRef(file_id="f1", alias="ds_1")],
        filters=[Condition(column="Record Date", operator="date_range", value={"start": "2026-10-01", "end": "2026-11-01"})],
        aggregations=[AggregateOperation(function="count", column="*", alias="records")],
    )

    sql, params = QueryCompiler.compile(plan)
    assert "TRY_CAST" in sql
    assert "TRY_STRPTIME" in sql
    assert params == ["2026-10-01", "2026-11-01"]
    con = duckdb.connect()
    con.execute('CREATE TABLE ds_1 ("Record Date" VARCHAR)')
    con.executemany('INSERT INTO ds_1 VALUES (?)', [
        ("2026-10-01",),
        ("18 Oct 2026, 12:49:00 GMT+0530",),
        ("2026-11-01",),
    ])
    assert con.execute(sql, params).fetchone() == (2,)
    con.close()


def test_selected_date_binding_is_added_to_plan(monkeypatch):
    monkeypatch.setattr(
        langgraph_workflow,
        "resolve_temporal_window",
        lambda question: {"period": "last_month", "start": "2026-10-01", "end": "2026-11-01"},
    )
    file = StoredFile(
        id="f1", owner_user_id="u1", unit_id="unit1", original_name="transactions.csv",
        content_type="text/csv", size_bytes=1, storage_key="transactions.csv",
        schema_profile={"columns": [{"name": "Record Date", "role": "timestamp", "inferred_type": "string"}]},
    )
    plan = AnalysisPlan(
        question="Last month ka revenue batao",
        datasets=[DatasetRef(file_id="f1", alias="ds_1")],
        aggregations=[AggregateOperation(function="sum", column="Revenue", alias="total_revenue")],
        resolved_bindings=[{"concept": "date_column", "binding": "Record Date", "resolved_by": "user"}],
    )

    LangGraphAnalystWorkflow._apply_temporal_scope(plan, plan.question, {"f1": file})

    date_filter = next(f for f in plan.filters if f.operator == "date_range")
    assert date_filter.column == "Record Date"
    assert date_filter.value == {"start": "2026-10-01", "end": "2026-11-01"}
    assert plan.resolved_bindings[0]["period"] == "last_month"


def test_verifier_rejects_count_result_that_omits_requested_metric_and_date(monkeypatch):
    monkeypatch.setattr(verifier_module, "resolve_temporal_window", lambda question: {
        "period": "last_month", "start": "2026-10-01", "end": "2026-11-01"
    })
    file = StoredFile(
        id="f1",
        owner_user_id="u1",
        unit_id="unit1",
        original_name="transactions.csv",
        content_type="text/csv",
        size_bytes=1,
        storage_key="transactions.csv",
        schema_profile={
            "row_count": 2,
            "columns": [{"name": "Record Date", "role": "timestamp", "inferred_type": "string"}],
        },
    )
    plan = AnalysisPlan(
        intent="scalar_count",
        result_shape="scalar_metric",
        question="Last month ka revenue batao",
        datasets=[DatasetRef(file_id="f1", alias="ds_1")],
        aggregations=[AggregateOperation(function="count", column="*", alias="total_records")],
        resolved_bindings=[{"concept": "date_column", "binding": "Record Date", "period": "last_month", "start": "2026-10-01", "end": "2026-11-01"}],
    )
    result = {
        "columns": ["total_records"],
        "rows": [{"total_records": 2}],
        "row_count": 1,
        "recompute": {"total_records": 2},
        "query_hash": "query",
        "result_hash": "result",
    }

    verification = ResultVerifier.verify(plan, result, {"f1": file})

    assert verification["passed"] is False
    assert verification["provenance"]["semantic_status"] == "SEMANTIC_FAIL"
    assert any(check["status"] == "failed" for check in verification["checks"] if check["gate"] in {"V7_TEMPORAL", "V7_METRIC"})


def test_verifier_passes_matching_metric_and_temporal_filter(monkeypatch):
    monkeypatch.setattr(verifier_module, "resolve_temporal_window", lambda question: {
        "period": "last_month", "start": "2026-10-01", "end": "2026-11-01"
    })
    file = StoredFile(
        id="f1", owner_user_id="u1", unit_id="unit1", original_name="transactions.csv",
        content_type="text/csv", size_bytes=1, storage_key="transactions.csv",
        schema_profile={"row_count": 2, "columns": [{"name": "Record Date", "role": "timestamp", "inferred_type": "string"}]},
    )
    window = {"period": "last_month", "start": "2026-10-01", "end": "2026-11-01"}
    plan = AnalysisPlan(
        intent="scalar_metric", result_shape="scalar_metric", question="Last month ka revenue batao",
        datasets=[DatasetRef(file_id="f1", alias="ds_1")],
        filters=[Condition(column="Record Date", operator="date_range", value={"start": window["start"], "end": window["end"]})],
        aggregations=[AggregateOperation(function="sum", column="Revenue", alias="total_revenue")],
        resolved_bindings=[{"concept": "metric", "binding": "Revenue"}, {"concept": "date_column", "binding": "Record Date", **window}],
    )
    result = {"columns": ["total_revenue"], "rows": [{"total_revenue": 75}], "row_count": 1,
              "recompute": {"total_revenue": 75}, "query_hash": "query", "result_hash": "result"}

    verification = ResultVerifier.verify(plan, result, {"f1": file})

    assert verification["passed"] is True
