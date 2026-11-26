"""Deterministic ground-truth computation for the blind internet corpus.

Every expected answer is produced by executing the hand-written SQL held in the
sealed key against the frozen dataset sample, in a fresh in-memory DuckDB
connection. No model output is involved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data" / "benchmark" / "internet"
QUESTIONS_PATH = Path(__file__).resolve().parent / "questions.json"
KEY_PATH = Path(__file__).resolve().parent / "ground_truth.json"
RESULTS_PATH = DATA_DIR / "ground_truth_results.json"


def load_questions() -> dict[str, Any]:
    return json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))


def load_key() -> dict[str, Any]:
    return json.loads(KEY_PATH.read_text(encoding="utf-8"))


def sample_path(dataset_id: str) -> Path:
    return DATA_DIR / "samples" / f"{dataset_id}.csv"


def execute_sql(dataset_id: str, sql: str) -> dict[str, Any]:
    connection = duckdb.connect(":memory:")
    connection.execute("SET threads = 1")
    try:
        connection.execute(
            "CREATE TABLE data AS SELECT * FROM read_csv_auto(?)",
            [str(sample_path(dataset_id))],
        )
        cursor = connection.execute(sql)
        columns = [description[0] for description in cursor.description]
        rows = [list(row) for row in cursor.fetchall()]
        return {"columns": columns, "rows": rows}
    finally:
        connection.close()


def _jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, float) and value != value:
        return None
    return value


_ROW_COUNT_COLUMNS = {
    "customers", "inspections", "observations", "people", "cases", "samples",
    "applicants", "permits", "contracts", "flights", "trips", "employees",
    "records", "postings", "crimes", "requests", "licenses", "flowers",
    "wines", "buildings", "failures", "orders",
}


def primary_number(columns: list[str], rows: list[list[Any]]) -> float | None:
    """Return the column that answers the question, not a helper row count.

    Aggregate rows produced by the corpus are ordered ``key, measure, [helpers]``
    where helpers are trailing row counts used for tie-breaking. The answering
    measure is therefore the last numeric column, unless that column is a known
    row-count helper and a measure precedes it.
    """
    if not rows:
        return None
    numeric = [
        (index, column)
        for index, column in enumerate(columns)
        if isinstance(rows[0][index], (int, float)) and not isinstance(rows[0][index], bool)
    ]
    for index, column in reversed(numeric):
        if len(numeric) > 1 and column.lower() in _ROW_COUNT_COLUMNS:
            continue
        return float(rows[0][index])
    if numeric:
        return float(rows[0][numeric[-1][0]])
    return None


def select_measure(columns: list[str], rows: list[list[Any]]) -> tuple[str | None, list[float]]:
    """Pick the metric column once, then read it from every result row."""
    if not rows:
        return None, []
    numeric = [
        (index, column)
        for index, column in enumerate(columns)
        if isinstance(rows[0][index], (int, float)) and not isinstance(rows[0][index], bool)
    ]
    chosen = None
    for index, column in reversed(numeric):
        if len(numeric) > 1 and column.lower() in _ROW_COUNT_COLUMNS:
            continue
        chosen = (index, column)
        break
    if chosen is None and numeric:
        chosen = numeric[-1]
    if chosen is None:
        return None, []
    index, column = chosen
    values = [float(row[index]) for row in rows if isinstance(row[index], (int, float))]
    return column, values


def build_results() -> dict[str, Any]:
    questions = {item["q_id"]: item for item in load_questions()["questions"]}
    key = load_key()["answers"]
    results: dict[str, Any] = {}
    failures: list[dict[str, Any]] = []
    for answer in key:
        q_id = answer["q_id"]
        question = questions[q_id]
        if answer.get("needs_clarification"):
            results[q_id] = {
                "q_id": q_id,
                "dataset_id": answer["dataset_id"],
                "answer_type": "clarification",
                "columns": [],
                "rows": [],
                "primary_number": None,
            }
            continue
        try:
            result = execute_sql(answer["dataset_id"], answer["sql"])
        except Exception as exc:  # noqa: BLE001 - surfaced in the report
            failures.append({"q_id": q_id, "error": str(exc)})
            continue
        number = primary_number(result["columns"], result["rows"])
        measure_column, measures = select_measure(result["columns"], result["rows"])
        result["rows"] = [[_jsonable(value) for value in row] for row in result["rows"]]
        results[q_id] = {
            "q_id": q_id,
            "dataset_id": answer["dataset_id"],
            "answer_type": answer["answer_type"],
            "columns": result["columns"],
            "rows": result["rows"],
            "primary_number": number,
            "measure_column": measure_column,
            "measures": measures,
        }
        if result["rows"] and number is None:
            failures.append({"q_id": q_id, "error": "no numeric measure in expected result"})
        if question.get("expected_row_count") is not None and answer["answer_type"] in {"rows", "row"}:
            if len(result["rows"]) != question["expected_row_count"]:
                failures.append(
                    {
                        "q_id": q_id,
                        "error": f"row count {len(result['rows'])} != declared {question['expected_row_count']}",
                    }
                )
    return {"results": results, "failures": failures}


def main() -> int:
    payload = build_results()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if payload["failures"]:
        for failure in payload["failures"]:
            print(f"FAIL {failure['q_id']}: {failure['error']}")
    print(f"{len(payload['results'])} ground-truth answers computed, {len(payload['failures'])} problem(s)")
    return 0 if not payload["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
