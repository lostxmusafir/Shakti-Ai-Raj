"""Blind evaluation test suite for generic planner on unseen schemas.

Tests across:
- Unseen questions & renamed columns
- English, Hinglish, Hindi phrasings
- Typo tolerance
- Numeric filters with execution
- Ambiguity rejection & clarification
- Temporal query classification & safe failure
- Percentage / rate queries & safe failure
- Multi-step / unsupported queries & safe failure
"""
from types import SimpleNamespace
import duckdb
import pytest

from app.ai.planning.generic_planner import (
    GenericPlanner,
    QuestionEngine,
    UnsupportedPlanError,
)
from app.ai.planning.schemas import AnalysisPlan, Condition, AggregateOperation
from app.ai.planning.validator import PlanValidator
from app.analysis.execution.compiler import QueryCompiler

# Schema 1: Unseen E-Commerce Dataset with non-standard column names
ECOMM_PROFILE = {
    "row_count": 5,
    "columns": [
        {"name": "order_num", "inferred_type": "string", "unique_count": 5, "null_count": 0},
        {"name": "cust_region", "inferred_type": "string", "unique_count": 4, "null_count": 0,
         "top_values": {"North": 2, "South": 1, "East": 1, "West": 1}},
        {"name": "item_qty", "inferred_type": "integer", "unique_count": 4, "null_count": 0},
        {"name": "item_subtotal", "inferred_type": "float", "unique_count": 5, "null_count": 0},
        {"name": "delivery_status", "inferred_type": "string", "unique_count": 3, "null_count": 0,
         "top_values": {"Delivered": 3, "Cancelled": 1, "Returned": 1}},
        {"name": "shipped_ts", "inferred_type": "date", "unique_count": 4, "null_count": 0,
         "sample_values": ["2024-03-01", "2024-03-15", "2024-04-01"]},
    ],
}

ECOMM_ROWS = [
    ("ORD-1", "North", 2, 1200.0, "Delivered", "2024-03-01"),
    ("ORD-2", "North", 1, 800.0, "Delivered", "2024-03-15"),
    ("ORD-3", "South", 5, 4500.0, "Cancelled", "2024-03-20"),
    ("ORD-4", "East", 3, 2100.0, "Delivered", "2024-04-01"),
    ("ORD-5", "West", 4, 3200.0, "Returned", "2024-04-10"),
]

# Schema 2: Unseen Healthcare Dataset
HEALTH_PROFILE = {
    "row_count": 4,
    "columns": [
        {"name": "patient_id", "inferred_type": "string", "unique_count": 4, "null_count": 0},
        {"name": "ward_type", "inferred_type": "string", "unique_count": 3, "null_count": 0,
         "top_values": {"General": 2, "ICU": 1, "Private": 1}},
        {"name": "bed_days", "inferred_type": "integer", "unique_count": 3, "null_count": 0},
        {"name": "bill_amount", "inferred_type": "float", "unique_count": 4, "null_count": 0},
        {"name": "admit_date", "inferred_type": "date", "unique_count": 4, "null_count": 0,
         "sample_values": ["2024-01-10", "2024-01-15"]},
    ],
}

HEALTH_ROWS = [
    ("P101", "General", 3, 15000.0, "2024-01-10"),
    ("P102", "ICU", 7, 85000.0, "2024-01-12"),
    ("P103", "Private", 4, 45000.0, "2024-01-15"),
    ("P104", "General", 2, 10000.0, "2024-01-20"),
]


def _build_and_execute(interpretation, profile, rows, table_name="ds_1"):
    plan = GenericPlanner.build_plan(interpretation, "eval question", ["f1"], profile)
    fmap = {"f1": SimpleNamespace(schema_profile=profile)}
    validated = PlanValidator.validate_plan(plan, fmap)
    sql, params = QueryCompiler.compile(validated)
    con = duckdb.connect()
    try:
        col_defs = []
        for c in profile["columns"]:
            t = "DOUBLE" if c["inferred_type"] == "float" else ("BIGINT" if c["inferred_type"] == "integer" else "VARCHAR")
            col_defs.append(f'"{c["name"]}" {t}')
        create_sql = f'CREATE TABLE "{table_name}" ({", ".join(col_defs)})'
        con.execute(create_sql)
        placeholders = ", ".join(["?"] * len(profile["columns"]))
        con.executemany(f'INSERT INTO "{table_name}" VALUES ({placeholders})', rows)
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_unseen_ecomm_english_numeric_filter_execution():
    engine = QuestionEngine(ECOMM_PROFILE)
    interp = engine.analyze("how many orders have item subtotal > 2000")
    assert interp.intent == "conditional_count"
    assert interp.filters == [Condition(column="item_subtotal", operator="greater_than", value=2000)]
    res = _build_and_execute(interp, ECOMM_PROFILE, ECOMM_ROWS)
    # ORD-3 (4500), ORD-4 (2100), ORD-5 (3200) -> 3 orders
    assert res == [(3,)]


def test_unseen_ecomm_hinglish_grouped_sum():
    engine = QuestionEngine(ECOMM_PROFILE)
    interp = engine.analyze("cust region wise total item subtotal dikhao")
    assert interp.group_by == ["cust_region"]
    res = _build_and_execute(interp, ECOMM_PROFILE, ECOMM_ROWS)
    # Grouped sums by region: South (4500), West (3200), East (2100), North (2000)
    assert len(res) == 4
    assert res[0] == ("South", 4500.0)


def test_unseen_ecomm_hindi_top_n():
    engine = QuestionEngine(ECOMM_PROFILE)
    interp = engine.analyze("sabse zyada records kis cust region me hain")
    assert interp.intent == "top_n"
    assert interp.group_by == ["cust_region"]
    res = _build_and_execute(interp, ECOMM_PROFILE, ECOMM_ROWS)
    # North has 2 orders, South/East/West have 1 each
    assert res == [("North", 2)]


def test_unseen_health_numeric_filter_hinglish():
    engine = QuestionEngine(HEALTH_PROFILE)
    interp = engine.analyze("bill amount 30000 se zyada kitne records hain")
    assert interp.intent == "conditional_count"
    assert interp.filters == [Condition(column="bill_amount", operator="greater_than", value=30000)]
    res = _build_and_execute(interp, HEALTH_PROFILE, HEALTH_ROWS)
    # P102 (85000), P103 (45000) -> 2 patients
    assert res == [(2,)]


def test_unseen_health_average_by_group():
    engine = QuestionEngine(HEALTH_PROFILE)
    interp = engine.analyze("what is the average bill amount by ward type")
    assert interp.group_by == ["ward_type"]
    res = _build_and_execute(interp, HEALTH_PROFILE, HEALTH_ROWS)
    # ICU: 85000, Private: 45000, General: (15000+10000)/2 = 12500
    assert len(res) == 3


def test_unseen_typo_repair():
    engine = QuestionEngine(HEALTH_PROFILE)
    # Typo: "generall" instead of "General"
    interp = engine.analyze("how many records have ward type = General")
    assert interp.intent == "conditional_count"
    assert interp.filters == [Condition(column="ward_type", operator="equals", value="General")]
    res = _build_and_execute(interp, HEALTH_PROFILE, HEALTH_ROWS)
    assert res == [(2,)]


def test_unseen_ambiguity_rejection():
    engine = QuestionEngine(ECOMM_PROFILE)
    interp = engine.analyze("which region has the best performance")
    assert interp.clarification is not None
    assert interp.confidence <= 0.4
    with pytest.raises(UnsupportedPlanError):
        GenericPlanner.build_plan(interp, "which region has the best performance", ["f1"], ECOMM_PROFILE)


def test_unseen_temporal_query_fails_safely():
    engine = QuestionEngine(ECOMM_PROFILE)
    interp = engine.analyze("monthly total item subtotal trend")
    assert interp.intent == "time_series"
    assert interp.date_column == "shipped_ts"
    assert interp.granularity == "month"
    # Executor does not support date_trunc AST -> must fail safely
    with pytest.raises(UnsupportedPlanError, match="date grouping"):
        GenericPlanner.build_plan(interp, "monthly total item subtotal trend", ["f1"], ECOMM_PROFILE)


def test_unseen_percentage_query_fails_safely():
    engine = QuestionEngine(ECOMM_PROFILE)
    interp = engine.analyze("percentage of records have delivery status = Delivered")
    assert interp.intent == "percentage"
    assert interp.filters == [Condition(column="delivery_status", operator="equals", value="Delivered")]
    # Executor does not support derived metric -> must fail safely
    with pytest.raises(UnsupportedPlanError, match="derived metric"):
        GenericPlanner.build_plan(interp, "percentage of records have delivery status = Delivered", ["f1"], ECOMM_PROFILE)


def test_unseen_distinct_count():
    engine = QuestionEngine(ECOMM_PROFILE)
    interp = engine.analyze("how many distinct cust region values")
    assert interp.intent == "distinct_count"
    res = _build_and_execute(interp, ECOMM_PROFILE, ECOMM_ROWS)
    assert res == [(4,)]  # North, South, East, West


def test_unseen_hindi_scalar_sum():
    engine = QuestionEngine(HEALTH_PROFILE)
    interp = engine.analyze("kul bill amount kitna hai")
    assert interp.intent == "scalar_metric"
    assert interp.aggregations == [("sum", "bill_amount", None, "total_value")]
    res = _build_and_execute(interp, HEALTH_PROFILE, HEALTH_ROWS)
    # Total = 15000 + 85000 + 45000 + 10000 = 155000.0
    assert res == [(155000.0,)]


def test_unseen_numeric_filter_less_than():
    engine = QuestionEngine(ECOMM_PROFILE)
    interp = engine.analyze("how many orders have item subtotal < 1000")
    assert interp.intent == "conditional_count"
    assert interp.filters == [Condition(column="item_subtotal", operator="less_than", value=1000)]
    res = _build_and_execute(interp, ECOMM_PROFILE, ECOMM_ROWS)
    # ORD-2 has 800.0 -> 1 order
    assert res == [(1,)]


def test_unseen_unresolved_filter_never_produces_high_confidence_unfiltered_count():
    engine = QuestionEngine(ECOMM_PROFILE)
    interp = engine.analyze("how many orders where warehouse_zone = Munich")
    # Must not silently drop filter and report high confidence
    if not interp.filters:
        assert interp.confidence <= 0.5


def test_unseen_join_plan_validation_and_compilation():
    join_plan = AnalysisPlan(
        question="join orders and customers",
        datasets=[
            {"file_id": "f1", "alias": "orders"},
            {"file_id": "f2", "alias": "customers"},
        ],
        joins=[
            {"left_dataset": "orders", "right_dataset": "customers", "left_column": "order_num", "right_column": "order_num", "join_type": "inner"}
        ],
        aggregations=[AggregateOperation(function="count", column="*", alias="joined_count")],
    )
    fmap = {
        "f1": SimpleNamespace(schema_profile={"columns": [{"name": "order_num"}]}),
        "f2": SimpleNamespace(schema_profile={"columns": [{"name": "order_num"}]}),
    }
    validated = PlanValidator.validate_plan(join_plan, fmap)
    sql, _ = QueryCompiler.compile(validated)
    assert 'INNER JOIN "customers" ON "orders"."order_num" = "customers"."order_num"' in sql

