from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import duckdb

from app.learning.examples import GoldenExample


def _same_rows(actual: List[Dict[str, Any]], expected: List[Dict[str, Any]]) -> bool:
    if len(actual) != len(expected):
        return False
    for actual_row, expected_row in zip(actual, expected):
        if set(actual_row) != set(expected_row):
            return False
        for key, expected_value in expected_row.items():
            actual_value = actual_row[key]
            if isinstance(actual_value, (int, float)) and isinstance(expected_value, (int, float)):
                if abs(float(actual_value) - float(expected_value)) > 1e-9:
                    return False
            elif actual_value != expected_value:
                return False
    return True


def evaluate_golden_examples(examples_path: str | Path, dataset_path: str | Path) -> Dict[str, Any]:
    connection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE dataset AS SELECT * FROM read_csv_auto(?)", [str(Path(dataset_path).resolve())])
    total = 0
    passed = 0
    evidence_covered = 0
    failures: List[Dict[str, Any]] = []
    for line in Path(examples_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        example = GoldenExample.model_validate_json(line)
        total += 1
        cursor = connection.execute(example.expected_plan["sql"])
        columns = [description[0] for description in cursor.description]
        actual = [dict(zip(columns, row)) for row in cursor.fetchall()]
        result_ok = _same_rows(actual, example.expected_answer["rows"])
        evidence_ok = bool(example.evidence_ids)
        if result_ok:
            passed += 1
        if evidence_ok:
            evidence_covered += 1
        if not result_ok:
            failures.append({"example_id": example.example_id, "reason": "result_mismatch"})
        elif not evidence_ok:
            failures.append({"example_id": example.example_id, "reason": "missing_evidence"})
    connection.close()
    return {
        "total_examples": total,
        "result_accuracy": passed / total if total else 0.0,
        "evidence_coverage": evidence_covered / total if total else 0.0,
        "passed_results": passed,
        "failures": failures,
        "evaluation_mode": "deterministic_duckdb_replay",
        "baseline_comparison": "not_run",
    }
