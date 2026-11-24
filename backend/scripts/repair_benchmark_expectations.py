"""Repair generated golden expectations from the checked-in source data.

This is intentionally deterministic: expected rows are taken from the same
DuckDB context used by the offline evaluator, with explicit tie-breakers.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ai.learning.evaluation_service import evaluation_service


GOLDEN = Path("data/benchmark/golden/golden_examples_300.json")


def _rows(connection, sql: str):
    cursor = connection.execute(sql)
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def main() -> int:
    examples = json.loads(GOLDEN.read_text(encoding="utf-8"))
    by_id = {example.get("example_id"): example for example in examples}
    connection = evaluation_service.setup_database_context()
    try:
        raj_domains_sql = (
            "SELECT dest, COUNT(*) AS cnt FROM v_rajcom "
            "WHERE severity='High' AND is_ext=1 GROUP BY dest "
            "ORDER BY cnt DESC, dest ASC LIMIT 3"
        )
        raj_sender_sql = (
            "SELECT src AS employee, COUNT(*) AS high_sev_cases FROM v_rajcom "
            "WHERE severity='High' GROUP BY src "
            "ORDER BY high_sev_cases DESC, employee ASC LIMIT 1"
        )
        expense_sql = (
            "SELECT claim_id, employee_id, category, amount FROM expenses "
            "WHERE (category='Meals' AND amount > 150.0) "
            "OR (category='Entertainment' AND amount > 500.0) "
            "OR (amount > 3000.0) ORDER BY amount DESC, claim_id ASC"
        )

        updates = {
            "gold-rajcom-0022": raj_domains_sql,
            "gold-rajcom-0032": raj_sender_sql,
            "gold-expens-0221": expense_sql,
        }
        for example_id, sql in updates.items():
            example = by_id[example_id]
            result_rows = _rows(connection, sql)
            example["sql_query"] = sql
            example["expected_answer"]["columns"] = list(result_rows[0]) if result_rows else []
            example["expected_answer"]["row_count"] = len(result_rows)
            example["expected_answer"]["rows"] = result_rows
            example["expected_answer"]["primary_metric"] = result_rows[0] if result_rows else {}

            if example_id == "gold-rajcom-0022":
                evidence_rows = _rows(
                    connection,
                    "SELECT id FROM v_rajcom WHERE severity='High' AND is_ext=1 "
                    "AND dest IN (SELECT dest FROM v_rajcom WHERE severity='High' AND is_ext=1 "
                    "GROUP BY dest ORDER BY COUNT(*) DESC, dest ASC LIMIT 3) ORDER BY id",
                )
            elif example_id == "gold-rajcom-0032":
                evidence_rows = _rows(
                    connection,
                    "SELECT id FROM v_rajcom WHERE severity='High' "
                    "AND src = (SELECT src FROM v_rajcom WHERE severity='High' GROUP BY src "
                    "ORDER BY COUNT(*) DESC, src ASC LIMIT 1) ORDER BY id",
                )
            else:
                evidence_rows = _rows(
                    connection,
                    "SELECT claim_id FROM expenses WHERE (category='Meals' AND amount > 150.0) "
                    "OR (category='Entertainment' AND amount > 500.0) OR (amount > 3000.0) "
                    "ORDER BY amount DESC, claim_id ASC",
                )
            evidence_key = "claim_id" if example_id == "gold-expens-0221" else "id"
            example["evidence_ids"] = [str(row[evidence_key]) for row in evidence_rows]
    finally:
        connection.close()

    GOLDEN.write_text(json.dumps(examples, indent=2) + "\n", encoding="utf-8")
    print("Repaired", ", ".join(updates))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
