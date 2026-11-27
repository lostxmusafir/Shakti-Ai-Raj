"""Run the unchanged production planner against the Phase 2 slice.

This runner disables external providers and uses the deterministic mock only
to force the production fallback path. It measures planning, execution, and
verification; it does not train a model or update retrieval data.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

os.environ["AI_PROVIDER"] = "mock"
os.environ["USE_MOCK_DB"] = "true"

from app.ai.orchestration.context import AIContext
from app.ai.orchestration.intent import IntentClassifier
from app.ai.orchestration.orchestrator import AnalysisOrchestrator
from app.models.file import StoredFile
from app.analysis.execution.duckdb_engine import DuckDBEngine
from app.analysis.profiling.profiler import DataProfiler
import app.ai.orchestration.orchestrator as orchestrator_module
from contract import expand_questions, plan_shape

from run import register


BASE = Path(__file__).resolve().parent
QUESTIONS_PATH = BASE / "questions.json"
GROUND_TRUTH_PATH = BASE / "ground_truth.json"
REPORT_PATH = ROOT / "data/benchmark/reports/phase3_production_planner_report.json"


def source_paths(dataset_id: str) -> dict[str, str]:
    if dataset_id == "microsoft-financial-sample":
        return {"file_1": str(ROOT / "data/benchmark/public/Financial_Sample.xlsx")}
    if dataset_id == "nexus-dynamics-incidents":
        return {"file_1": str(ROOT / "data/benchmark/public/NexusDynamics_Incidents_5000.csv")}
    if dataset_id == "hr-employees":
        return {"file_1": str(ROOT / "data/benchmark/synthetic/hr/employees.csv")}
    if dataset_id == "hr-payroll":
        return {"file_1": str(ROOT / "data/benchmark/synthetic/hr/payroll_summary.csv")}
    if dataset_id == "hr-employees-payroll":
        return {
            "file_1": str(ROOT / "data/benchmark/synthetic/hr/employees.csv"),
            "file_2": str(ROOT / "data/benchmark/synthetic/hr/payroll_summary.csv"),
        }
    raise ValueError(f"Unknown dataset: {dataset_id}")


def stored_file(file_id: str, path: str) -> StoredFile:
    profile = DataProfiler.profile_file(path, Path(path).name)
    return StoredFile(
        id=file_id,
        owner_user_id="phase3-benchmark",
        unit_id="default_unit",
        original_name=Path(path).name,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if path.endswith(".xlsx") else "text/csv",
        size_bytes=Path(path).stat().st_size,
        storage_key=Path(path).name,
        status="ready",
        schema_profile=profile,
    )


def truth_rows(dataset_id: str, sql: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    con = duckdb.connect(":memory:")
    try:
        register(con, dataset_id)
        cursor = con.execute(sql)
        return [item[0] for item in cursor.description], cursor.fetchall()
    finally:
        con.close()


def scalar_equal(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=0.005, abs_tol=0.05)
    if left is None or right is None:
        return left is right
    return str(left).strip().lower() == str(right).strip().lower()


def compare_rows(actual: dict[str, Any], expected: list[tuple[Any, ...]], preserve_order: bool) -> bool:
    rows = actual.get("rows") or []
    if len(rows) != len(expected):
        return False
    columns = actual.get("columns") or []
    actual_values = [[row.get(column) for column in columns] for row in rows]
    if not preserve_order:
        actual_values = sorted(actual_values, key=lambda row: tuple(str(value) for value in row))
        expected = sorted(expected, key=lambda row: tuple(str(value) for value in row))
    return all(
        len(actual_row) == len(expected_row)
        and all(scalar_equal(left, right) for left, right in zip(actual_row, expected_row))
        for actual_row, expected_row in zip(actual_values, expected)
    )


async def run() -> dict[str, Any]:
    questions = expand_questions(json.loads(QUESTIONS_PATH.read_text(encoding="utf-8")))
    answer_items = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))["answers"]
    answers = {item["q_id"]: item for item in answer_items}
    results: list[dict[str, Any]] = []
    for question in questions:
        paths = source_paths(question["dataset_id"])
        file_ids = list(paths)
        files = {file_id: stored_file(file_id, path) for file_id, path in paths.items()}
        path_map = files and paths
        orchestrator = AnalysisOrchestrator.__new__(AnalysisOrchestrator)
        intent = IntentClassifier.classify(question["question"], file_ids)
        try:
            # The production fallback is the deterministic path under test;
            # bypassing the mock provider keeps invalid placeholder IDs out
            # of this benchmark and guarantees no external call.
            plan = orchestrator._plan_fallback(question["question"], file_ids, files, intent)
            engine_result = DuckDBEngine.execute(plan, files, path_map)
            verification = orchestrator_module.ResultVerifier.verify(
                plan, engine_result, files, user_unit_id="default_unit", user_role="super_admin"
            )
            truth_columns, expected_rows = truth_rows(
                question["dataset_id"], answers[question["base_q_id"]]["sql"]
            )
            plan_for_shape = plan.model_dump()
            plan_for_shape["sql_query"] = plan.sql_query or engine_result.get("compiled_sql")
            shape_ok, shape_errors = plan_shape(question, plan_for_shape)
            q_lower = question["question"].lower()
            preserve_order = any(term in q_lower for term in ("top", "highest", "sabse zyada", "rank"))
            result_ok = compare_rows(engine_result, expected_rows, preserve_order=preserve_order)
            verification_ok = bool(verification.get("passed"))
            item = {
                "q_id": question["q_id"],
                "base_q_id": question["base_q_id"],
                "question": question["question"],
                "language": question["language"],
                "intent_classifier": intent,
                "plan_intent": plan.intent,
                "group_by": plan.group_by,
                "aggregations": [aggregate.model_dump() for aggregate in plan.aggregations],
                "filters": [condition.model_dump() for condition in plan.filters],
                "sql": plan.sql_query or engine_result.get("compiled_sql"),
                "plan_shape_passed": shape_ok,
                "plan_shape_errors": shape_errors,
                "result_match_passed": result_ok,
                "verification_passed": verification_ok,
                "engine_rows": engine_result.get("rows"),
                "expected_columns": truth_columns,
                "expected_rows": expected_rows,
                "passed": shape_ok and result_ok and verification_ok,
            }
        except Exception as exc:  # benchmark records failures instead of hiding them
            item = {
                "q_id": question["q_id"],
                "base_q_id": question["base_q_id"],
                "question": question["question"],
                "language": question["language"],
                "intent_classifier": intent,
                "passed": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        results.append(item)
        print(f"{'PASS' if item['passed'] else 'FAIL'} {item['q_id']}: {item.get('error') or item.get('sql')}")
    payload = {
        "phase": 3,
        "corpus_version": "phase2-curated-1.1",
        "model_training": False,
        "external_provider_called": False,
        "runner_changed_production_code": False,
        "dataset_specific_production_change": False,
        "source_under_test": "current working tree",
        "planner_mode": "production_deterministic_fallback",
        "total": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "failed": sum(1 for item in results if not item["passed"]),
        "results": results,
    }
    REPORT_PATH.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    report = asyncio.run(run())
    print(f"Phase 3 production planner: {report['passed']}/{report['total']} passed")
    raise SystemExit(0 if report["failed"] == 0 else 1)
