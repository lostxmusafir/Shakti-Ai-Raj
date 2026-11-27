import json
from pathlib import Path

from contract import expand_questions, inferred_operation, plan_shape


ROOT = Path(__file__).resolve().parents[3]


def test_phase2_expands_to_48_answer_free_cases():
    payload = json.loads((Path(__file__).parent / "questions.json").read_text(encoding="utf-8"))
    questions = expand_questions(payload)
    assert len(questions) == 48
    assert len({item["q_id"] for item in questions}) == 48
    assert all("sql" not in item and "expected_answer" not in item for item in questions)


def test_plan_shape_rejects_unrequested_grouping():
    question = {
        "expected_operation": "sum",
        "expected_group_by": [],
        "expected_metric_columns": ["Profit"],
        "expected_aggregate_functions": ["sum"],
    }
    plan = {
        "sql_query": 'SELECT "Profit", COUNT(*) FROM data GROUP BY "Profit"',
        "group_by": ["Profit"],
        "aggregations": [{"function": "count", "column": "*"}],
        "filters": [],
        "joins": [],
    }
    ok, errors = plan_shape(question, plan)
    assert not ok
    assert any("group_by" in error for error in errors)


def test_inferred_operation_distinguishes_rank_from_grouped_sum():
    rank = {
        "intent": "top_n",
        "limit": 1,
        "group_by": ["Country"],
        "aggregations": [{"function": "sum", "column": "Profit"}],
    }
    grouped = {
        "intent": "grouped_distribution",
        "limit": 50,
        "group_by": ["Country"],
        "aggregations": [{"function": "sum", "column": "Profit"}],
    }
    assert inferred_operation(rank) == "group_rank"
    assert inferred_operation(grouped) == "grouped_sum"
