"""Shared Phase 2 corpus expansion and plan-shape checks.

This module is benchmark-only. It is not imported by production application code.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List


def expand_questions(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    expanded: List[Dict[str, Any]] = []
    for base in payload.get("questions", []):
        variants = base.get("variants") or [{
            "suffix": "base",
            "question": base.get("question", ""),
            "language": base.get("language", "unknown"),
            "difficulty": base.get("difficulty", "simple"),
        }]
        shared = {key: value for key, value in base.items() if key != "variants"}
        for variant in variants:
            item = dict(shared)
            suffix = str(variant.get("suffix") or "variant")
            item.update({key: value for key, value in variant.items() if key != "suffix"})
            item["base_q_id"] = str(base["q_id"])
            item["q_id"] = f"{base['q_id']}-{suffix}"
            expanded.append(item)
    ids = [item["q_id"] for item in expanded]
    if len(ids) != len(set(ids)):
        raise ValueError("Phase 2 question IDs must be unique")
    return expanded


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _columns(plan: Dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for item in plan.get("aggregations") or []:
        values.add(_norm(item.get("column")))
    for item in plan.get("joins") or []:
        values.update(_norm(item.get(key)) for key in ("left_column", "right_column"))
    return values


def inferred_operation(plan: Dict[str, Any]) -> str:
    sql = _norm(plan.get("sql_query"))
    group_by = plan.get("group_by") or []
    aggregations = plan.get("aggregations") or []
    functions = {_norm(item.get("function")) for item in aggregations}
    joins = plan.get("joins") or []
    is_rank = bool(plan.get("limit") == 1 or plan.get("intent") in ("top_n", "bottom_n"))

    if any(_norm(item.get("join_type")) == "anti" for item in joins) or " anti join " in f" {sql} ":
        return "anti_join_count"
    if "count_distinct" in functions or "count(distinct" in sql:
        return "distinct_count"
    if group_by:
        if "sum" in functions or "sum(" in sql:
            if is_rank or "limit 1" in sql:
                return "group_rank"
            return "grouped_sum"
        if "count" in functions or "count(" in sql:
            if is_rank or "limit 1" in sql:
                return "group_rank"
            return "grouped_count"
    if "sum" in functions or "sum(" in sql:
        return "sum"
    if "count_nonzero" in functions:
        return "filtered_count"
    if plan.get("filters"):
        return "filtered_count"
    if "count(" in sql or "count" in functions:
        return "filtered_count" if " where " in f" {sql} " else "row_count"
    return _norm(plan.get("intent")) or "unknown"


def plan_shape(question: Dict[str, Any], plan: Dict[str, Any]) -> tuple[bool, List[str]]:
    errors: List[str] = []
    sql = _norm(plan.get("sql_query"))
    actual_group = [_norm(column) for column in (plan.get("group_by") or [])]
    expected_group = [_norm(column) for column in (question.get("expected_group_by") or [])]
    if actual_group != expected_group:
        errors.append(f"group_by {actual_group!r} != {expected_group!r}")

    actual_operation = inferred_operation(plan)
    expected_operation = _norm(question.get("expected_operation") or question.get("expected_intent"))
    if actual_operation != expected_operation:
        errors.append(f"operation {actual_operation!r} != {expected_operation!r}")

    actual_functions = {_norm(item.get("function")) for item in (plan.get("aggregations") or [])}
    expected_functions = {_norm(value) for value in (question.get("expected_aggregate_functions") or [])}
    if expected_functions and not expected_functions <= actual_functions and not all(
        f"{value}(" in sql for value in expected_functions
    ):
        errors.append(f"aggregate functions {actual_functions!r} miss {expected_functions!r}")

    filter_values = " ".join(
        f"{item.get('column', '')} {item.get('operator', '')} {item.get('value', '')}"
        for item in (plan.get("filters") or [])
    )
    searchable = sql + " " + " ".join(_columns(plan)) + " " + _norm(filter_values)
    for metric in question.get("expected_metric_columns", []):
        if _norm(metric) not in searchable:
            errors.append(f"missing metric {metric!r}")

    for token in question.get("expected_filter_tokens", []):
        if _norm(token) not in sql:
            errors.append(f"missing filter token {token!r}")

    if question.get("expected_group_by") is None and actual_group:
        errors.append("unrequested grouping")
    return not errors, errors

