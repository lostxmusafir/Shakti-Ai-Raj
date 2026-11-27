from app.ai.orchestration.ambiguity import AmbiguityDetector
from app.ai.planning.schemas import AnalysisPlan, DatasetRef
from app.ai.verification.verifier import ResultVerifier
from app.models.file import StoredFile


def _file(columns):
    return StoredFile(
        id="f1", owner_user_id="u1", unit_id="unit1", original_name="data.csv",
        content_type="text/csv", size_bytes=1, storage_key="data.csv",
        schema_profile={"columns": columns},
    )


def test_unit_in_question_uses_single_schema_size_measure_without_metric_interrupt():
    file = _file([
        {"name": "ID", "role": "dimension", "inferred_type": "integer"},
        {"name": "Transaction Size (KB)", "role": "measure", "inferred_type": "float"},
    ])

    interrupt = AmbiguityDetector.detect("How much data was sent in MB?", {"f1": file})

    assert interrupt is None


def test_verifier_accepts_requested_average_measure_in_sql_only_plan():
    file = _file([
        {"name": "Action", "role": "dimension", "inferred_type": "string"},
        {"name": "Transaction Size (KB)", "role": "measure", "inferred_type": "float"},
    ])
    plan = AnalysisPlan(
        intent="top_n",
        result_shape="ranked_rows",
        question="Which action has the highest average transaction amount?",
        datasets=[DatasetRef(file_id="f1", alias="ds_1")],
        group_by=["Action"],
        sql_query="SELECT action, AVG(size_kb) AS avg_size_kb FROM v GROUP BY action ORDER BY avg_size_kb DESC LIMIT 1",
        requested_concepts=["action", "avg_size_kb"],
    )
    result = {
        "columns": ["action", "avg_size_kb"],
        "rows": [{"action": "Blocked", "avg_size_kb": 100.0}],
        "row_count": 1,
        "query_hash": "query",
        "result_hash": "result",
    }

    verification = ResultVerifier.verify(plan, result, {"f1": file})

    assert verification["passed"] is True


def test_verifier_rejects_count_for_requested_revenue_measure():
    file = _file([{"name": "Revenue", "role": "measure", "inferred_type": "float"}])
    plan = AnalysisPlan(
        intent="scalar_metric",
        result_shape="scalar_metric",
        question="Revenue kitna hai?",
        datasets=[DatasetRef(file_id="f1", alias="ds_1")],
        sql_query="SELECT COUNT(*) AS revenue FROM ds_1",
    )
    result = {
        "columns": ["revenue"],
        "rows": [{"revenue": 42}],
        "row_count": 1,
        "query_hash": "query",
        "result_hash": "result",
    }

    verification = ResultVerifier.verify(plan, result, {"f1": file})

    assert verification["passed"] is False
    assert verification["provenance"]["semantic_status"] == "SEMANTIC_FAIL"
