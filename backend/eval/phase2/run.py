"""Run the Phase 2 benchmark slice without a model or production imports."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

from contract import expand_questions


ROOT = Path(__file__).resolve().parents[3]
QUESTIONS = Path(__file__).with_name("questions.json")
GROUND_TRUTH = Path(__file__).with_name("ground_truth.json")
REPORT = ROOT / "data/benchmark/reports/phase2_curated_report.json"


def register(con: duckdb.DuckDBPyConnection, dataset_id: str) -> None:
    if dataset_id == "microsoft-financial-sample":
        con.execute("CREATE OR REPLACE TABLE data AS SELECT * FROM read_xlsx(?)", [str(ROOT / "data/benchmark/public/Financial_Sample.xlsx")])
    elif dataset_id == "nexus-dynamics-incidents":
        con.execute("CREATE OR REPLACE TABLE data AS SELECT * FROM read_csv_auto(?)", [str(ROOT / "data/benchmark/public/NexusDynamics_Incidents_5000.csv")])
    elif dataset_id == "hr-employees":
        con.execute("CREATE OR REPLACE TABLE data AS SELECT * FROM read_csv_auto(?)", [str(ROOT / "data/benchmark/synthetic/hr/employees.csv")])
    elif dataset_id == "hr-payroll":
        con.execute("CREATE OR REPLACE TABLE data AS SELECT * FROM read_csv_auto(?)", [str(ROOT / "data/benchmark/synthetic/hr/payroll_summary.csv")])
    elif dataset_id == "hr-employees-payroll":
        con.execute("CREATE OR REPLACE TABLE employees AS SELECT * FROM read_csv_auto(?)", [str(ROOT / "data/benchmark/synthetic/hr/employees.csv")])
        con.execute("CREATE OR REPLACE TABLE payroll AS SELECT * FROM read_csv_auto(?)", [str(ROOT / "data/benchmark/synthetic/hr/payroll_summary.csv")])
    else:
        raise ValueError(f"Unknown benchmark dataset: {dataset_id}")


def main() -> int:
    questions = expand_questions(json.loads(QUESTIONS.read_text(encoding="utf-8")))
    answers = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    if not answers.get("sealed"):
        raise ValueError("Ground truth must be sealed")
    by_id = {item["q_id"]: item for item in answers["answers"]}
    base_ids = {item["base_q_id"] for item in questions}
    if set(by_id) != base_ids:
        raise ValueError("Question and answer keys do not match base corpus")

    con = duckdb.connect(":memory:")
    passed = 0
    results = []
    try:
        for question in questions:
            answer = by_id[question["base_q_id"]]
            register(con, question["dataset_id"])
            result = con.execute(answer["sql"]).fetchall()
            columns = [item[0] for item in con.description]
            if columns != answer["expected_columns"]:
                raise AssertionError(f"{question['q_id']}: columns {columns} != {answer['expected_columns']}")
            if len(result) != question["expected_row_count"]:
                raise AssertionError(f"{question['q_id']}: rows {len(result)} != {question['expected_row_count']}")
            print(f"PASS {question['q_id']}: {dict(zip(columns, result[0])) if result else '[]'}")
            results.append({
                "q_id": question["q_id"],
                "base_q_id": question["base_q_id"],
                "dataset_id": question["dataset_id"],
                "language": question["language"],
                "columns": columns,
                "rows": result,
                "passed": True,
            })
            passed += 1
    finally:
        con.close()
    report = {
        "phase": 2,
        "corpus_version": json.loads(QUESTIONS.read_text(encoding="utf-8")).get("corpus_version"),
        "model_training": False,
        "external_provider_called": False,
        "runner_changed_production_code": False,
        "total": len(questions),
        "passed": passed,
        "failed": len(questions) - passed,
        "results": results,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Phase 2 deterministic ground truth: {passed}/{len(questions)} passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
