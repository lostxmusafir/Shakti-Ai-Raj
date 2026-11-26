"""Multi-dimension scoring for the blind internet evaluation.

Each question is scored on ten independent dimensions. A single PASS/FAIL is
deliberately not produced: the report keeps intent, schema mapping, filters,
aggregation, shape, execution, numbers, verification, relevance and readability
separate so failures stay diagnosable.
"""

from __future__ import annotations

import re
from typing import Any

from .ground_truth import select_measure

NULL_SENSITIVE_IDS = {
    "internet-001-q3",
    "internet-010-q3",
    "internet-011-q3",
    "internet-011-q4",
    "internet-017-q3",
    "internet-018-q3",
    "internet-019-q3",
    "internet-021-q3",
    "internet-022-q3",
    "internet-023-q3",
    "internet-024-q3",
    "internet-026-q3",
}

FOLLOWUP_IDS = {"internet-001-q6", "internet-001-q7", "internet-001-q8", "internet-003-q6", "internet-003-q7",
                "internet-003-q8", "internet-005-q6", "internet-005-q7", "internet-005-q8", "internet-009-q6",
                "internet-009-q7", "internet-009-q8", "internet-013-q6", "internet-013-q7", "internet-013-q8",
                "internet-017-q6", "internet-017-q7", "internet-017-q8", "internet-019-q6", "internet-019-q7",
                "internet-019-q8", "internet-021-q6", "internet-021-q7", "internet-021-q8", "internet-025-q6",
                "internet-025-q7", "internet-025-q8", "internet-027-q6", "internet-027-q7", "internet-027-q8"}

CLARIFICATION_MARKERS = (
    "clarify", "which metric", "which measure", "do you mean", "did you mean",
    "kya matlab", "kaunsa metric", "kis metric", "please specify", "can you confirm",
    "ambiguous", "not sure which",
)

INTERNAL_ALIAS = re.compile(r"\b(agg_\d+|total_count|record_count|metric_val|avg_\w+|sum_\w+|cnt|_n)\b", re.IGNORECASE)


def _normalise(text: Any) -> str:
    return str(text).strip().lower()


def _sql_of(actual: dict[str, Any]) -> str:
    plan = actual.get("plan") or {}
    sql = plan.get("sql_query") or (actual.get("result") or {}).get("compiled_sql") or ""
    return sql or ""


def _rows_of(actual: dict[str, Any]) -> list[list[Any]]:
    return (actual.get("result") or {}).get("rows") or []


def _columns_of(actual: dict[str, Any]) -> list[str]:
    return (actual.get("result") or {}).get("columns") or []


def _has_group_by(sql: str) -> bool:
    return bool(re.search(r"\bgroup\s+by\b", sql, re.IGNORECASE))


def _agg_functions(sql: str) -> set[str]:
    return {match.group(1).lower() for match in re.finditer(r"\b(count|sum|avg|min|max|median|corr)\s*\(", sql, re.IGNORECASE)}


def _numbers_match(actual: float, expected: float) -> bool:
    if expected == 0:
        return abs(actual) <= 0.05
    return abs(actual - expected) <= max(0.05, abs(expected) * 0.005)


def _label_match(expected_value: Any, actual_value: Any) -> bool:
    if expected_value is None:
        return True
    left, right = _normalise(expected_value), _normalise(actual_value)
    return left == right or left in right or right in left


def _normalised_sql(sql: str) -> str:
    return re.sub(r'\s+', " ", sql.lower().replace('"', "").replace("`", ""))


def _condition_present(condition: str, sql: str, sql_norm: str) -> bool:
    condition_norm = re.sub(r"\s+", " ", condition.lower().strip())
    if condition_norm in sql_norm:
        return True
    tokens = [token for token in re.findall(r"[a-z_][a-z0-9_]*|'[^']*'|-?\d+", condition_norm) if token]
    if not tokens:
        return False
    return all(token in sql_norm for token in tokens)


def score_question(
    question: dict[str, Any],
    expected: dict[str, Any],
    actual: dict[str, Any],
    mode: str = "planner",
) -> dict[str, Any]:
    q_id = question["q_id"]
    sql = _sql_of(actual)
    sql_lower = sql.lower()
    rows = _rows_of(actual)
    columns = _columns_of(actual)
    answer = actual.get("answer") or ""
    error = actual.get("error")
    expected_intent = question["expected_intent"]
    needs_clarification = bool(question.get("needs_clarification"))
    expected_rows = question.get("expected_row_count")
    failures: list[str] = []
    dimensions: dict[str, bool] = {}

    # 1. intent -----------------------------------------------------------
    clarified = any(marker in answer.lower() for marker in CLARIFICATION_MARKERS)
    if needs_clarification:
        intent_ok = clarified and not _agg_functions(sql)
        if not intent_ok:
            failures.append("AMBIGUOUS_BUT_NOT_CLARIFIED")
    elif error:
        intent_ok = False
        failures.append("WRONG_INTENT")
    elif expected_intent in {"row_count", "filtered_count"}:
        intent_ok = "count" in _agg_functions(sql) and not _has_group_by(sql)
    elif expected_intent == "group_rank":
        # Ranking may be an aggregate-by-group or a raw metric ordered with a limit.
        intent_ok = _has_group_by(sql) or ("order by" in sql_lower and "limit" in sql_lower)
    elif expected_intent == "group_avg":
        intent_ok = _has_group_by(sql)
    elif expected_intent == "derived_ratio":
        intent_ok = _has_group_by(sql) or ("/" in sql and bool(_agg_functions(sql)))
    elif expected_intent == "comparison":
        intent_ok = _has_group_by(sql) or len(_agg_functions(sql)) >= 2
    elif expected_intent in {"aggregate_metric", "filtered_metric"}:
        intent_ok = bool(_agg_functions(sql)) and not _has_group_by(sql)
    elif expected_intent == "correlation":
        intent_ok = "corr" in _agg_functions(sql)
    else:
        intent_ok = bool(sql)
    if not intent_ok and not needs_clarification and "WRONG_INTENT" not in failures:
        failures.append("WRONG_INTENT")
    dimensions["intent_understanding"] = intent_ok

    # 2. schema mapping ---------------------------------------------------
    group_column = question.get("expected_group_column")
    required_metrics = [column for column in question.get("expected_metric_columns", [])]
    group_ok = True if not group_column else _normalise(group_column) in sql_lower
    metric_hits = sum(1 for column in required_metrics if _normalise(column) in sql_lower)
    metrics_ok = True if not required_metrics else metric_hits > 0
    schema_ok = group_ok and metrics_ok
    if not schema_ok:
        failures.append("UNRELATED_GROUP_BY" if not group_ok and _has_group_by(sql) else "WRONG_COLUMN")
    dimensions["schema_mapping"] = schema_ok

    # 3. filters ----------------------------------------------------------
    expected_filters = question.get("expected_filters", [])
    sql_norm = _normalised_sql(sql)
    filter_hits = sum(1 for condition in expected_filters if _condition_present(condition, sql, sql_norm))
    filter_ok = filter_hits == len(expected_filters)
    if not filter_ok:
        failures.append("DROPPED_CONDITION" if expected_filters else "WRONG_COLUMN")
    dimensions["filter_accuracy"] = filter_ok

    # 4. aggregation ------------------------------------------------------
    aggregate_fns = _agg_functions(sql)
    if expected_intent in {"row_count", "filtered_count"}:
        agg_ok = "count" in aggregate_fns
    elif expected_intent in {"aggregate_metric", "filtered_metric"}:
        agg_ok = bool(aggregate_fns - {"count"})
    elif expected_intent == "derived_ratio":
        agg_ok = bool(aggregate_fns) and ("/" in sql or _has_group_by(sql))
    elif expected_intent == "comparison":
        agg_ok = bool(aggregate_fns) or _has_group_by(sql)
    elif expected_intent == "group_rank":
        # Either an aggregate ranked by group, or a raw metric ranked directly.
        agg_ok = (bool(aggregate_fns) and _has_group_by(sql)) or (
            "order by" in sql_lower and "limit" in sql_lower
        )
    elif expected_intent == "correlation":
        agg_ok = "corr" in aggregate_fns
    elif needs_clarification:
        agg_ok = not aggregate_fns
    else:
        agg_ok = bool(aggregate_fns)
    if not agg_ok and not error:
        failures.append("WRONG_AGGREGATION")
    dimensions["aggregation_accuracy"] = agg_ok

    # 5. result shape -----------------------------------------------------
    if needs_clarification:
        shape_ok = clarified
    elif expected_rows is None:
        shape_ok = bool(rows)
    else:
        shape_ok = len(rows) == expected_rows
    if not shape_ok and not error:
        failures.append("WRONG_RESULT_SHAPE")
    dimensions["result_shape_accuracy"] = shape_ok

    # 6. execution --------------------------------------------------------
    execution_ok = error is None and bool(columns)
    if not execution_ok:
        failures.append("EXECUTION_ERROR")
    dimensions["sql_execution"] = execution_ok

    # 7. numerical correctness -------------------------------------------
    expected_measure = expected.get("primary_number")
    expected_measures = expected.get("measures") or []
    actual_measure = None
    actual_measures: list[float] = []
    if rows:
        actual_columns = columns or list(rows[0].keys())
        as_lists = [[row.get(column) for column in actual_columns] for row in rows]
        _, actual_measures = select_measure(actual_columns, as_lists)
        actual_measure = actual_measures[0] if actual_measures else None
    if needs_clarification:
        numeric_ok = clarified
    elif expected_measure is None:
        numeric_ok = False
    elif actual_measure is None:
        numeric_ok = False
    else:
        numeric_ok = _numbers_match(float(actual_measure), float(expected_measure))
        if (
            numeric_ok
            and question["expected_intent"] in {"derived_ratio", "comparison", "group_rank", "group_avg", "correlation"}
            and len(expected_measures) > 1
            and actual_measures
            and len(actual_measures) == len(expected_measures)
        ):
            numeric_ok = all(
                _numbers_match(float(a), float(e)) for a, e in zip(actual_measures, expected_measures)
            )
    if not numeric_ok and not error:
        if any("IS NULL" in condition or "= 0" in condition or "< 0" in condition for condition in expected_filters):
            failures.append("NULL_SEMANTICS_ERROR")
        else:
            failures.append("WRONG_AGGREGATION")
    dimensions["numerical_correctness"] = numeric_ok

    # 8. semantic verification -------------------------------------------
    verification = actual.get("verification") or {}
    verification_passed = bool(verification.get("passed"))
    semantic_ok = verification_passed and numeric_ok
    if verification_passed and not numeric_ok:
        failures.append("FALSE_VERIFICATION_PASS")
    dimensions["semantic_verification"] = semantic_ok

    # 9. answer relevance -------------------------------------------------
    if needs_clarification:
        relevance_ok = clarified
    else:
        expected_labels = []
        if expected.get("rows"):
            expected_labels = [str(value) for value in expected["rows"][0][:-1] if isinstance(value, str)]
        label_ok = any(_normalise(label) in answer.lower() for label in expected_labels) if expected_labels else True
        number_ok = False
        if expected_measure is not None:
            for candidate in {
                f"{float(expected_measure):,.2f}",
                f"{float(expected_measure):,.0f}",
                f"{float(expected_measure):.2f}",
                str(expected_measure).split(".")[0],
            }:
                if candidate and candidate in answer:
                    number_ok = True
                    break
        relevance_ok = bool(answer.strip()) and (label_ok or number_ok)
    if not relevance_ok and not error and mode != "reference":
        failures.append("ANSWER_FORMAT_ERROR")
    # The reference mode executes ground-truth SQL directly and produces no
    # user-facing answer, so answer quality is not measured there.
    dimensions["answer_relevance"] = relevance_ok if mode != "reference" else None

    # 10. human readability ----------------------------------------------
    stripped = answer.strip()
    readable_ok = (
        len(stripped.split()) >= 6
        and stripped.count("|") < 3
        and not INTERNAL_ALIAS.findall(stripped)
        and not stripped.startswith("{")
    )
    if not readable_ok and not error and mode != "reference":
        failures.append("ANSWER_FORMAT_ERROR")
    dimensions["human_readability"] = readable_ok if mode != "reference" else None

    if mode != "reference" and q_id in FOLLOWUP_IDS and not intent_ok:
        failures.append("FOLLOWUP_CONTEXT_ERROR")
    if question.get("expected_intent") in {"group_rank", "derived_ratio"} and any(
        "year" in condition.lower() or "date" in condition.lower() for condition in expected_filters
    ):
        if "year" not in sql_lower and "date" not in sql_lower:
            failures.append("TEMPORAL_ERROR")

    return {
        "q_id": q_id,
        "dataset_id": question["dataset_id"],
        "language": question["language"],
        "difficulty": question["difficulty"],
        "null_sensitive": q_id in NULL_SENSITIVE_IDS,
        "followup": q_id in FOLLOWUP_IDS,
        "dimensions": dimensions,
        "failures": sorted(set(failures)),
        "actual_sql": sql,
        "actual_columns": columns,
        "actual_row_count": len(rows),
        "actual_measure": actual_measure,
        "expected_measure": expected_measure,
        "error": error,
    }
