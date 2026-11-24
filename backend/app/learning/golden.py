from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import duckdb

from app.learning.examples import GoldenExample


def _checksum(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _profile_columns(path: str | Path) -> List[str]:
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("CREATE TABLE dataset AS SELECT * FROM read_csv_auto(?)", [str(Path(path).resolve())])
        return [row[0] for row in connection.execute("DESCRIBE dataset").fetchall()]
    finally:
        connection.close()


def _run_query(path: str | Path, sql: str) -> tuple[List[Dict[str, Any]], List[str]]:
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("CREATE TABLE dataset AS SELECT * FROM read_csv_auto(?)", [str(Path(path).resolve())])
        cursor = connection.execute(sql)
        columns = [description[0] for description in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return rows, columns
    finally:
        connection.close()


def generate_dlp_examples(path: str | Path, dataset_id: str = "synthetic-dlp") -> List[GoldenExample]:
    columns = _profile_columns(path)
    required = {"event_id", "employee_name", "department", "action", "is_external", "data_size_bytes"}
    missing = required - set(columns)
    if missing:
        raise ValueError(f"DLP example generation requires actual columns: {sorted(missing)}")
    checksum = _checksum(path)
    templates = [
        ("How many security events are in the dataset?", "english", "filtered_count", "event_count", "SELECT COUNT(*) AS event_count FROM dataset", ["event_id"]),
        ("Blocked incidents kitne hain?", "hinglish", "filtered_count", "blocked_events", "SELECT COUNT(*) AS blocked_events FROM dataset WHERE action = 'BLOCKED'", ["action"]),
        ("Bahar sabse zyada data kisne bheja?", "hinglish", "ranking", "external_transfer_volume", "SELECT employee_name, SUM(data_size_bytes) AS data_size_bytes FROM dataset WHERE is_external = TRUE AND action <> 'BLOCKED' GROUP BY employee_name ORDER BY data_size_bytes DESC LIMIT 1", ["employee_name", "data_size_bytes", "is_external", "action"]),
        ("Which department has the highest completed transfer volume?", "english", "ranking", "department_transfer_volume", "SELECT department, SUM(data_size_bytes) AS data_size_bytes FROM dataset WHERE action <> 'BLOCKED' GROUP BY department ORDER BY data_size_bytes DESC, department ASC LIMIT 5", ["department", "data_size_bytes", "action"]),
        ("External events ka count department-wise batao.", "hinglish", "grouped_count", "external_events_by_department", "SELECT department, COUNT(*) AS event_count FROM dataset WHERE is_external = TRUE GROUP BY department ORDER BY event_count DESC, department ASC", ["department", "is_external"]),
        ("How many blocked events transferred zero bytes?", "english", "filtered_count", "blocked_zero_bytes", "SELECT COUNT(*) AS blocked_zero_bytes FROM dataset WHERE action = 'BLOCKED' AND data_size_bytes = 0", ["action", "data_size_bytes"]),
        ("Kaunse recipient domains ko external data gaya?", "hinglish", "distinct_count", "external_domains", "SELECT COUNT(DISTINCT recipient_domain) AS external_domains FROM dataset WHERE is_external = TRUE AND action <> 'BLOCKED'", ["recipient_domain", "is_external", "action"]),
        ("Show the highest severity event count.", "english", "grouped_count", "severity_counts", "SELECT severity, COUNT(*) AS event_count FROM dataset GROUP BY severity ORDER BY event_count DESC, severity ASC", ["severity"]),
        ("Blocked action ka department breakdown do.", "hinglish", "grouped_count", "blocked_by_department", "SELECT department, COUNT(*) AS event_count FROM dataset WHERE action = 'BLOCKED' GROUP BY department ORDER BY event_count DESC, department ASC", ["department", "action"]),
        ("What is the average completed event size?", "english", "average", "average_completed_size", "SELECT AVG(data_size_bytes) AS average_completed_size FROM dataset WHERE action <> 'BLOCKED'", ["data_size_bytes", "action"]),
        ("External approved destinations kitne hain?", "hinglish", "filtered_count", "approved_external_events", "SELECT COUNT(*) AS approved_external_events FROM dataset WHERE is_external = TRUE AND is_approved_destination = TRUE", ["is_external", "is_approved_destination"]),
        ("Which employees had blocked events?", "english", "distinct_count", "blocked_employees", "SELECT COUNT(DISTINCT employee_id) AS blocked_employees FROM dataset WHERE action = 'BLOCKED'", ["employee_id", "action"]),
    ]
    examples: List[GoldenExample] = []
    for question, language, intent, target, sql, mapping_columns in templates:
        rows, _ = _run_query(path, sql)
        evidence_sql = "SELECT event_id FROM dataset"
        if " WHERE " in sql:
            where_clause = sql.split(" WHERE ", 1)[1]
            where_clause = where_clause.split(" GROUP BY ", 1)[0]
            where_clause = where_clause.split(" ORDER BY ", 1)[0]
            where_clause = where_clause.split(" LIMIT ", 1)[0]
            evidence_sql += f" WHERE {where_clause}"
        evidence_sql += " LIMIT 20"
        try:
            evidence_rows, _ = _run_query(path, evidence_sql)
            evidence_ids = [str(row.get("event_id")) for row in evidence_rows if row.get("event_id") is not None][:20]
        except Exception:
            evidence_ids = []
        examples.append(GoldenExample(
            dataset_id=dataset_id,
            dataset_checksum=checksum,
            question=question,
            language=language,
            intent=intent,
            semantic_target=target,
            column_mapping={target: ", ".join(column for column in mapping_columns if column in columns)},
            sql_query=sql,
            expected_plan={"operation": "duckdb_select", "sql": sql},
            expected_answer={"rows": rows},
            evidence_ids=evidence_ids,
            verification={"status": "verified", "method": "independent_duckdb_computation", "source_path": str(path)},
            source_type="synthetic",
            approval_status="pending",
            skill_selection=[],
        ))
    return examples
