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
    QuestionEngine,
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
        {"name": "branch", "inferred_type": "string", "unique_count": 4, "null_count": 0,
         "top_values": {"North": 2, "South": 2, "East": 1, "West": 1}},
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


# ---------------------------------------------------------------------------
# Capture-group parsing
# ---------------------------------------------------------------------------

def test_hinglish_top_n_count_parses_with_its_own_groups():
    interp = QuestionEngine(PROFILE).analyze("sabse zyada records kis city ke hain")

    assert interp.intent == "top_n"
    assert interp.group_by == ["city"]
    assert interp.aggregations == [("count", None, None, "metric")]
    assert interp.sort == [("metric", False)]


def test_hinglish_bottom_n_count_sorts_ascending():
    interp = QuestionEngine(PROFILE).analyze("sabse kam records kis city ke hain")

    assert interp.intent == "bottom_n"
    assert interp.sort == [("metric", True)]


def test_english_record_count_phrasings_still_parse():
    engine = QuestionEngine(PROFILE)
    highest = engine.analyze("which city has the highest number of records")
    least = engine.analyze("which city has the least number of records")

    assert (highest.intent, highest.sort) == ("top_n", [("metric", False)])
    assert (least.intent, least.sort) == ("bottom_n", [("metric", True)])
    assert highest.group_by == least.group_by == ["city"]


@pytest.mark.parametrize("question", [
    "sabse zyada records kis city ke hain",
    "sabse kam records kis city ke hain",
    "kis city me records sabse zyada hai",
    "kis city ka emi per branch sabse zyada",
    "kis city ka emi per branch sabse kam",
    "which city has the highest emi per branch",
    "har branch ke liye kaunsa city sabse zyada records wala hai",
    "for every branch which city has the most records",
    "for each branch which city has the lowest number of records",
])
def test_rule_parsing_never_raises(question):
    interp = QuestionEngine(PROFILE).analyze(question)

    assert isinstance(interp, Interpretation)
    assert 0.0 <= interp.confidence <= 1.0


def test_per_entity_ratio_resolves_group_measure_and_entity():
    interp = QuestionEngine(PROFILE).analyze("which city has the highest emi per branch")

    assert interp.intent == "ratio"
    assert interp.group_by == ["city"]
    assert interp.aggregations == [
        ("sum", "emi", None, "numerator"),
        ("count_distinct", "branch", None, "denominator"),
    ]
    assert interp.derived == [
        ("per_entity_metric", "numerator", "denominator", 1.0, "group")
    ]


def test_rank_within_group_parses_when_the_pattern_defines_no_direction_group():
    engine = QuestionEngine(PROFILE)
    hinglish = engine.analyze("har branch ke liye kaunsa city sabse zyada records wala hai")
    lowest = engine.analyze("for each branch which city has the lowest number of records")

    assert hinglish.intent == "ranked_group_metric"
    assert hinglish.rank_partition == ["branch"]
    assert hinglish.group_by == ["branch", "city"]
    assert "rank_ascending" not in hinglish.notes
    assert "rank_ascending" in lowest.notes


def test_parsed_ratio_is_refused_because_derived_metrics_are_unexecutable():
    interp = QuestionEngine(PROFILE).analyze("which city has the highest emi per branch")

    with pytest.raises(UnsupportedPlanError, match="derived metric"):
        _build(interp)


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


# ---------------------------------------------------------------------------
# Section 8 assertions & feature tests
# ---------------------------------------------------------------------------

def test_numeric_filter_compiles_and_executes():
    engine = QuestionEngine(PROFILE)
    interp = engine.analyze("how many records have emi > 500")

    assert interp.intent == "conditional_count"
    assert interp.filters == [Condition(column="emi", operator="greater_than", value=500)]
    assert interp.confidence >= 0.9

    plan = _build(interp)
    assert plan.filters == [Condition(column="emi", operator="greater_than", value=500)]
    sql, params = QueryCompiler.compile(plan)
    assert 'WHERE "emi" > ?' in sql
    assert params == [500]
    assert _execute(plan) == [(2,)]  # L5: 600, L6: 700


@pytest.mark.parametrize("query,op,val", [
    ("how many records have emi >= 500", "greater_than_or_equal", 500),
    ("how many records have emi < 300", "less_than", 300),
    ("how many records have emi <= 200", "less_than_or_equal", 200),
    ("how many records have emi greater than 400", "greater_than", 400),
    ("how many records have emi less than 400", "less_than", 400),
    ("emi 500 se zyada kitne records hain", "greater_than", 500),
    ("emi 300 se kam kitne records hain", "less_than", 300),
])
def test_numeric_filter_operator_variations(query, op, val):
    engine = QuestionEngine(PROFILE)
    interp = engine.analyze(query)

    assert interp.intent == "conditional_count"
    assert interp.filters == [Condition(column="emi", operator=op, value=val)]
    plan = _build(interp)
    assert plan.filters == [Condition(column="emi", operator=op, value=val)]


def test_percentage_condition_populates_filters_and_fails_safely():
    engine = QuestionEngine(PROFILE)
    interp = engine.analyze("percentage of records have cancellation = yes")

    assert interp.intent == "percentage"
    assert interp.filters == [Condition(column="cancellation", operator="equals", value="yes")]

    with pytest.raises(UnsupportedPlanError, match="derived metric"):
        _build(interp)


def test_temporal_trend_without_date_column_clarifies():
    engine = QuestionEngine(PROFILE)
    interp = engine.analyze("monthly total emi trend")

    assert interp.intent == "time_series"
    assert interp.granularity == "month"
    assert interp.clarification is not None
    assert "date" in interp.clarification.lower()
    assert interp.confidence <= 0.4

    with pytest.raises(UnsupportedPlanError, match="No date or timestamp"):
        _build(interp)


def test_temporal_trend_with_date_column_classifies_and_fails_safely():
    prof = dict(PROFILE)
    prof["columns"] = list(PROFILE["columns"]) + [
        {"name": "disbursed_on", "inferred_type": "date", "unique_count": 5, "null_count": 0, "sample_values": ["2024-01-01"]}
    ]
    engine = QuestionEngine(prof)
    interp = engine.analyze("monthly total emi trend")

    assert interp.intent == "time_series"
    assert interp.date_column == "disbursed_on"
    assert interp.granularity == "month"

    with pytest.raises(UnsupportedPlanError, match="date grouping"):
        _build(interp)


def test_ambiguous_question_returns_clarification_and_low_confidence():
    engine = QuestionEngine(PROFILE)
    interp = engine.analyze("which city is the best")

    assert interp.clarification is not None
    assert interp.confidence <= 0.4
    with pytest.raises(UnsupportedPlanError):
        _build(interp)


def test_unresolved_filter_hint_never_returns_unfiltered_scalar_with_high_confidence():
    engine = QuestionEngine(PROFILE)
    interp = engine.analyze("how many records where unknown_column > 999")

    # Must NOT return an unfiltered scalar count with confidence >= 0.9
    if not interp.filters:
        assert interp.confidence <= 0.5


@pytest.mark.asyncio
async def test_orchestrator_feature_flag_wiring():
    from unittest.mock import AsyncMock, MagicMock
    from app.core.config import settings
    from app.ai.orchestration.orchestrator import AnalysisOrchestrator

    fmap = {"f1": SimpleNamespace(schema_profile=PROFILE, original_name="test.csv")}
    orch = AnalysisOrchestrator()
    orch.ai_provider = MagicMock()
    orch.ai_provider.generate_structured = AsyncMock(side_effect=Exception("AI provider offline"))

    settings.ENABLE_GENERIC_PLANNER = True
    try:
        plan = await orch._plan_with_ai("how many records have emi > 500", ["f1"], fmap, "DATA_ANALYSIS")
        assert plan.filters == [Condition(column="emi", operator="greater_than", value=500)]
    finally:
        settings.ENABLE_GENERIC_PLANNER = False

