"""Contract tests for the generic planner.

These assert that anything GenericPlanner.build_plan emits can be validated by
PlanValidator, compiled by QueryCompiler and executed by DuckDB, and that plan
features without an executor are refused instead of silently dropped.
"""
from types import SimpleNamespace

import duckdb
import pytest

from app.ai.planning.generic_planner import (
    EXECUTABLE_AGGREGATES,
    GenericPlanner,
    Interpretation,
    UnsupportedPlanError,
)
from app.ai.planning.schemas import AggregateOperation, AnalysisPlan, Condition, DatasetRef
from app.ai.planning.validator import SUPPORTED_AGGREGATES, PlanValidator
from app.analysis.execution.compiler import QueryCompiler
from app.core.exceptions import PlanValidationError

PROFILE = {
    "row_count": 6,
    "columns": [
        {"name": "loan_id", "inferred_type": "string", "unique_count": 6, "null_count": 0},
        {"name": "city", "inferred_type": "string", "unique_count": 3, "null_count": 0,
         "top_values": {"Pune": 3, "Mumbai": 2, "Delhi": 1}},
        {"name": "emi", "inferred_type": "float", "unique_count": 6, "null_count": 0},
        {"name": "cancellation", "inferred_type": "string", "unique_count": 2, "null_count": 0,
         "top_values": {"yes": 2, "no": 4}},
    ],
}
FILES_MAP = {"f1": SimpleNamespace(schema_profile=PROFILE)}
ROWS = [
    ("L1", "Pune", 100.0, "no"),
    ("L2", "Pune", 200.0, "no"),
    ("L3", "Pune", 300.0, "yes"),
    ("L4", "Mumbai", 500.0, "no"),
    ("L5", "Mumbai", 600.0, "no"),
    ("L6", "Delhi", 700.0, "yes"),
]


def _build(interpretation: Interpretation) -> AnalysisPlan:
    return GenericPlanner.build_plan(interpretation, "question", ["f1"], PROFILE)


def _execute(plan: AnalysisPlan):
    validated = PlanValidator.validate_plan(plan, FILES_MAP)
    sql, params = QueryCompiler.compile(validated)
    connection = duckdb.connect()
    try:
        connection.execute(
            'CREATE TABLE "ds_1" (loan_id VARCHAR, city VARCHAR, emi DOUBLE, cancellation VARCHAR)'
        )
        connection.executemany('INSERT INTO "ds_1" VALUES (?, ?, ?, ?)', ROWS)
        return connection.execute(sql, params).fetchall()
    finally:
        connection.close()


def test_executable_aggregates_match_validator_allowlist():
    assert EXECUTABLE_AGGREGATES == SUPPORTED_AGGREGATES


def test_grouped_sum_validates_compiles_and_executes():
    interpretation = Interpretation(intent="top_n")
    interpretation.group_by = ["city"]
    interpretation.aggregations = [("sum", "emi", None, "total_emi")]
    interpretation.sort = [("total_emi", False)]
    interpretation.limit = 2

    plan = _build(interpretation)

    assert plan.group_by == ["city"]
    assert plan.aggregations == [
        AggregateOperation(function="sum", column="emi", alias="total_emi")
    ]
    sql, _ = QueryCompiler.compile(plan)
    assert 'ORDER BY "total_emi" DESC' in sql
    assert _execute(plan) == [("Mumbai", 1100.0), ("Delhi", 700.0)]


def test_conditional_count_hoists_the_condition_to_the_plan():
    interpretation = Interpretation(intent="conditional_count")
    interpretation.aggregations = [
        ("count", None, Condition(column="emi", operator="greater_than", value=400), "record_count")
    ]

    plan = _build(interpretation)

    assert plan.aggregations == [
        AggregateOperation(function="count", column=None, alias="record_count")
    ]
    assert plan.filters == [Condition(column="emi", operator="greater_than", value=400)]
    assert _execute(plan) == [(3,)]


def test_per_aggregate_filter_with_two_aggregates_is_refused():
    interpretation = Interpretation(intent="ratio")
    interpretation.group_by = ["city"]
    interpretation.aggregations = [
        ("sum", "emi", Condition(column="cancellation", operator="equals", value="yes"), "num"),
        ("count", None, None, "den"),
    ]

    with pytest.raises(UnsupportedPlanError, match="per-aggregate filter"):
        _build(interpretation)


def test_derived_metric_is_refused():
    interpretation = Interpretation(intent="percentage")
    interpretation.derived = [("per_entity_metric", "numerator", "denominator", 1.0, "group")]

    with pytest.raises(UnsupportedPlanError, match="derived metric"):
        _build(interpretation)


def test_having_is_refused():
    interpretation = Interpretation(intent="grouped_count")
    interpretation.group_by = ["city"]
    interpretation.aggregations = [("count", None, None, "record_count")]
    interpretation.having = [("record_count", ">=", 3, None)]

    with pytest.raises(UnsupportedPlanError, match="HAVING"):
        _build(interpretation)


def test_per_group_ranking_is_refused():
    interpretation = Interpretation(intent="ranked_group_metric")
    interpretation.group_by = ["city"]
    interpretation.aggregations = [("count", None, None, "record_count")]
    interpretation.rank_partition = ["city"]
    interpretation.rank_order = "record_count"

    with pytest.raises(UnsupportedPlanError, match="per-group ranking"):
        _build(interpretation)


def test_date_grouping_is_refused():
    interpretation = Interpretation(intent="time_series")
    interpretation.aggregations = [("sum", "emi", None, "total_emi")]
    interpretation.date_column = "disbursed_on"

    with pytest.raises(UnsupportedPlanError, match="date grouping"):
        _build(interpretation)


def test_aggregate_outside_the_executor_allowlist_is_refused():
    interpretation = Interpretation(intent="percentage")
    interpretation.aggregations = [("percentage", None, None, "pct")]

    with pytest.raises(UnsupportedPlanError, match="aggregate 'percentage'"):
        _build(interpretation)


def test_clarification_is_refused_rather_than_returned_as_a_plan():
    interpretation = Interpretation(intent="scalar_metric")
    interpretation.clarification = "Which measure should I use?"

    with pytest.raises(UnsupportedPlanError, match="Which measure"):
        _build(interpretation)


def test_count_distinct_validates_compiles_and_executes():
    interpretation = Interpretation(intent="distinct_count")
    interpretation.aggregations = [("count_distinct", "city", None, "distinct_cities")]

    plan = _build(interpretation)

    assert plan.aggregations == [
        AggregateOperation(function="count_distinct", column="city", alias="distinct_cities")
    ]
    sql, _ = QueryCompiler.compile(plan)
    assert 'COUNT(DISTINCT "city")' in sql
    assert _execute(plan) == [(3,)]


def test_count_distinct_without_a_column_is_rejected_by_the_validator():
    plan = AnalysisPlan(
        question="how many distinct values",
        datasets=[DatasetRef(file_id="f1", alias="ds_1")],
        aggregations=[
            AggregateOperation(function="count_distinct", column="*", alias="distinct_count")
        ],
    )

    with pytest.raises(PlanValidationError, match="count_distinct"):
        PlanValidator.validate_plan(plan, FILES_MAP)
