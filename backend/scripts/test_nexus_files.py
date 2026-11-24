"""Run the supplied NexusDynamics CSV and SQLite helper views read-only."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.ai.learning.semantic_mapping import SemanticMapper
from app.analysis.profiling.profiler import DataProfiler


def run(csv_path: Path, sql_path: Path) -> dict:
    connection = sqlite3.connect(":memory:")
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        quoted = ", ".join(f'"{column.replace(chr(34), chr(34) * 2)}" TEXT' for column in columns)
        connection.execute(f"CREATE TABLE incidents ({quoted})")
        placeholders = ",".join("?" for _ in columns)
        connection.executemany(
            f"INSERT INTO incidents VALUES ({placeholders})",
            ([row.get(column, "") or "" for column in columns] for row in reader),
        )
    connection.executescript(sql_path.read_text(encoding="utf-8"))

    checks = {
        "source_rows": connection.execute("SELECT COUNT(*) FROM incidents").fetchone()[0],
        "view_rows": connection.execute("SELECT COUNT(*) FROM v").fetchone()[0],
        "external_rows": connection.execute("SELECT COUNT(*) FROM v WHERE is_ext=1").fetchone()[0],
        "mixed_rows": connection.execute("SELECT COUNT(*) FROM v WHERE is_mixed=1").fetchone()[0],
        "blocked_rows": connection.execute("SELECT COUNT(*) FROM v WHERE action='Blocked'").fetchone()[0],
        "top_external_sender": connection.execute(
            "SELECT src, SUM(size_kb) AS total_size_kb FROM v "
            "WHERE is_ext=1 AND action <> 'Blocked' GROUP BY src "
            "ORDER BY total_size_kb DESC, src ASC LIMIT 1"
        ).fetchone(),
    }
    connection.close()

    profile = DataProfiler.profile_file(str(csv_path), csv_path.name)
    profiled_columns = [column["name"] for column in profile.get("columns", [])]
    external = SemanticMapper.resolve_semantics(
        "Bahar sabse zyada data kisne bheja?", profiled_columns, profile
    )
    blocked = SemanticMapper.resolve_semantics(
        "Blocked incidents kitne hain?", profiled_columns, profile
    )
    result = {
        "csv": str(csv_path.resolve()),
        "sql_helpers": str(sql_path.resolve()),
        "checks": checks,
        "profile": {"row_count": profile.get("row_count"), "columns": profiled_columns},
        "semantic_mapping": {
            "external_question": external.model_dump(),
            "blocked_question": blocked.model_dump(),
        },
        "verification_status": "passed",
    }
    if checks["source_rows"] != 5000 or checks["view_rows"] != 5000:
        raise AssertionError("Nexus source/view row count is not 5,000")
    if external.mapped_columns.get("entity") != "Source":
        raise AssertionError("Source semantic mapping failed")
    if blocked.suggested_filters[0]["value"] != "Blocked":
        raise AssertionError("Blocked value mapping failed")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=r"C:\Users\DREAM\Downloads\NexusDynamics_Incidents_5000.csv")
    parser.add_argument("--sql", default=r"C:\Users\DREAM\Downloads\NexusDynamics_Verification_Helpers.sql")
    parser.add_argument("--output", default="data/benchmark/reports/nexus_user_file_test.json")
    args = parser.parse_args()
    result = run(Path(args.csv), Path(args.sql))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, default=list) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, default=list))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
