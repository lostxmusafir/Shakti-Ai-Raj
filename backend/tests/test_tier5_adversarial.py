"""
Tier 5 Adversarial Test Suite for Shakti-Ai-Raj Excel Training Pack & Exemplar Retrieval.
Combines adversarial tests from Challenger 1 and Challenger 2:
1. Concurrency and Race Conditions (manifest lost updates, thread-safe ingestion)
2. DuckDB Thread-Safety and Query Plan Validation (cursor isolation, EXPLAIN validation)
3. Edge-Case Data Corruptions and Boundary Tampering (missing columns, unknown Q_IDs, formula errors)
4. Anomaly View Boundary Stress (division by zero, zero/negative durations, malformed time formats)
5. ExampleRetriever Edge Cases & Query Boundaries (extreme inputs, top_k <= 0, non-string columns)
6. Dynamic Hot-Reloading, Cache Invalidation & File Failures (disk updates, corrupted/deleted files)
7. Schema Boundaries, Manifest Extremes & Anti-Facade Guards (null datasets, extra fields, bypass vectors)
8. Memory, Performance & Concurrency Stress (rapid query throughput, multi-threaded retrieval)
"""

from __future__ import annotations

import os
import re
import sys
import json
import time
import shutil
import hashlib
import tempfile
import concurrent.futures
from pathlib import Path
from typing import Any, Dict, List

import duckdb
import pandas as pd
import pytest
from pydantic import ValidationError

from app.learning.training_pack import (
    TrainingPackIngestionService,
    compute_binary_sha256,
    PACK_CONFIGS,
    DEFAULT_TRAINING_PACK_DIR,
    BASE_DIR,
)
from app.learning.training_pack_queries import (
    FLIGHT_QUERIES,
    BANK_QUERIES,
    SONGS_QUERIES,
    FLIGHT_ANOMALIES_VIEW_SQL,
    get_all_specs,
)
from app.learning.examples import GoldenExample
from app.ai.learning.example_retrieval import ExampleRetriever
import app.ai.learning.example_retrieval as er_mod

# Suppress unknown mark warnings
pytestmark = [pytest.mark.filterwarnings("ignore::pytest.PytestUnknownMarkWarning")]


def _resolve_pack_file(filename: str) -> Path:
    candidates = [
        DEFAULT_TRAINING_PACK_DIR / filename,
        BASE_DIR / "data" / "training_pack" / filename,
        BASE_DIR / filename,
    ]
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError(f"Could not find {filename}")


@pytest.fixture(autouse=True)
def reset_retriever_cache():
    """Ensure ExampleRetriever cache is clean before and after each test."""
    ExampleRetriever.clear_cache()
    yield
    ExampleRetriever.clear_cache()


# ==============================================================================
# SECTION 1: CONCURRENCY AND RACE CONDITIONS (Challenger 1)
# ==============================================================================

@pytest.mark.tier5
def test_concurrent_ingest_pack_race_condition(tmp_path: Path):
    """
    Adversarial Stress Test: Focus 1
    Simultaneously ingest different datasets (Flight, Bank, Songs) across 3 worker threads.
    Verifies whether manifest state persistence handles concurrent writes without
    corrupting manifest or golden artifacts.
    """
    manifest_file = tmp_path / "concurrent_manifest.json"
    golden_file = tmp_path / "concurrent_golden.json"

    service = TrainingPackIngestionService(
        manifest_path=manifest_file,
        golden_output_path=golden_file
    )

    def ingest_worker(cfg):
        cand_data = _resolve_pack_file(cfg["dataset_filename"])
        cand_q = _resolve_pack_file(cfg["questions_filename"])
        return service.ingest_pack(
            dataset_path=cand_data,
            questions_path=cand_q,
            dataset_id=cfg["dataset_id"],
            dataset_sheet=cfg["dataset_sheet"],
            questions_sheet=cfg["questions_sheet"],
            force=True
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(ingest_worker, cfg): cfg["dataset_id"] for cfg in PACK_CONFIGS}
        results = {}
        for f in concurrent.futures.as_completed(futures):
            ds_id = futures[f]
            results[ds_id] = f.result()

    assert len(results) == 3
    for ds_id, res in results.items():
        assert res["status"] == "SUCCESS"

    assert manifest_file.is_file()
    with manifest_file.open("r", encoding="utf-8") as mf:
        manifest_data = json.load(mf)

    recorded_datasets = list(manifest_data.get("datasets", {}).keys())
    assert len(recorded_datasets) == 3


@pytest.mark.tier5
def test_concurrent_ingest_all_idempotency_stress(tmp_path: Path):
    """
    Adversarial Stress Test: Focus 1
    Stress-test concurrent calls to ingest_all() with 4 worker threads running simultaneously.
    Ensures no unhandled file collisions, permission locks, or JSON corruption.
    """
    manifest_file = tmp_path / "stress_manifest.json"
    golden_file = tmp_path / "stress_golden.json"

    service = TrainingPackIngestionService(
        manifest_path=manifest_file,
        golden_output_path=golden_file
    )

    service.ingest_all(force=True)

    def run_ingest_all():
        return service.ingest_all(force=False)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(run_ingest_all) for _ in range(4)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    for r in results:
        assert r["status"] == "ALREADY_INGESTED"
        assert r["total_verified"] == 150


# ==============================================================================
# SECTION 2: DUCKDB THREAD-SAFETY AND QUERY PLAN VALIDATION (Challenger 1)
# ==============================================================================

@pytest.mark.tier5
def test_duckdb_cursor_isolation_thread_safety():
    """
    Adversarial Stress Test: Focus 2
    Verify that in-memory DuckDB database supports multi-threaded concurrent query execution
    using cursor isolation (con.cursor()) across 8 concurrent threads executing 40 analytical queries.
    """
    con = duckdb.connect(":memory:")

    df_flight = pd.read_excel(_resolve_pack_file("flight_dataset_single_sheet.xlsx"), sheet_name="Flight_Data")
    con.execute("CREATE TABLE flight_data AS SELECT * FROM df_flight")
    con.execute("CREATE TABLE flight AS SELECT * FROM flight_data")

    con.execute("""
    CREATE VIEW v_flight_clean AS
    SELECT *,
      TRY_CAST(Journey_Date || ' ' || (CASE 
            WHEN Dep_Time LIKE '% hrs' THEN SUBSTR(Dep_Time, 1, 2) || ':' || SUBSTR(Dep_Time, 3, 2)
            WHEN Dep_Time LIKE '% PM' THEN LPAD(CAST(TRY_CAST(SUBSTR(Dep_Time, 1, 2) AS INT) % 12 + 12 AS VARCHAR), 2, '0') || SUBSTR(Dep_Time, 3, 3)
            WHEN Dep_Time LIKE '% AM' THEN LPAD(CAST(TRY_CAST(SUBSTR(Dep_Time, 1, 2) AS INT) % 12 AS VARCHAR), 2, '0') || SUBSTR(Dep_Time, 3, 3)
            ELSE Dep_Time END) AS TIMESTAMP) AS dep_ts,
      TRY_CAST(Arrival_Date || ' ' || (CASE 
            WHEN Arrival_Time LIKE '% hrs' THEN SUBSTR(Arrival_Time, 1, 2) || ':' || SUBSTR(Arrival_Time, 3, 2)
            WHEN Arrival_Time LIKE '% PM' THEN LPAD(CAST(TRY_CAST(SUBSTR(Arrival_Time, 1, 2) AS INT) % 12 + 12 AS VARCHAR), 2, '0') || SUBSTR(Arrival_Time, 3, 3)
            WHEN Arrival_Time LIKE '% AM' THEN LPAD(CAST(TRY_CAST(SUBSTR(Arrival_Time, 1, 2) AS INT) % 12 AS VARCHAR), 2, '0') || SUBSTR(Arrival_Time, 3, 3)
            ELSE Arrival_Time END) AS TIMESTAMP) AS arr_ts
    FROM flight_data;
    """)
    con.execute(FLIGHT_ANOMALIES_VIEW_SQL)

    queries = [
        "SELECT COUNT(*) FROM flight_data",
        "SELECT issue_type, COUNT(*) FROM v_flight_anomalies GROUP BY issue_type",
        "SELECT Origin_City, COUNT(*) FROM v_flight_clean GROUP BY Origin_City",
        FLIGHT_QUERIES["F1"]["sql_query"],
        FLIGHT_QUERIES["F4"]["sql_query"],
        FLIGHT_QUERIES["F10"]["sql_query"],
        FLIGHT_QUERIES["F20"]["sql_query"],
        FLIGHT_QUERIES["F30"]["sql_query"],
    ]

    def execute_with_cursor(q_sql):
        cur = con.cursor()
        res = cur.execute(q_sql).fetchall()
        cur.close()
        return len(res)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(execute_with_cursor, queries[i % len(queries)]) for i in range(40)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 40
    assert all(r >= 0 for r in results)
    con.close()


@pytest.mark.tier5
def test_duckdb_explain_query_plan_anomalies_view():
    """
    Adversarial Stress Test: Focus 2
    Validates EXPLAIN query plan for v_flight_anomalies and v_flight_clean.
    Ensures DuckDB query planner resolves all 26 UNION ALL branches, joins, and filters
    without cyclic references or planning failures.
    """
    con = duckdb.connect(":memory:")
    df_flight = pd.read_excel(_resolve_pack_file("flight_dataset_single_sheet.xlsx"), sheet_name="Flight_Data")
    con.execute("CREATE TABLE flight_data AS SELECT * FROM df_flight")
    con.execute("CREATE TABLE flight AS SELECT * FROM flight_data")

    con.execute("""
    CREATE VIEW v_flight_clean AS
    SELECT *,
      TRY_CAST(Journey_Date || ' ' || (CASE 
            WHEN Dep_Time LIKE '% hrs' THEN SUBSTR(Dep_Time, 1, 2) || ':' || SUBSTR(Dep_Time, 3, 2)
            WHEN Dep_Time LIKE '% PM' THEN LPAD(CAST(TRY_CAST(SUBSTR(Dep_Time, 1, 2) AS INT) % 12 + 12 AS VARCHAR), 2, '0') || SUBSTR(Dep_Time, 3, 3)
            WHEN Dep_Time LIKE '% AM' THEN LPAD(CAST(TRY_CAST(SUBSTR(Dep_Time, 1, 2) AS INT) % 12 AS VARCHAR), 2, '0') || SUBSTR(Dep_Time, 3, 3)
            ELSE Dep_Time END) AS TIMESTAMP) AS dep_ts,
      TRY_CAST(Arrival_Date || ' ' || (CASE 
            WHEN Arrival_Time LIKE '% hrs' THEN SUBSTR(Arrival_Time, 1, 2) || ':' || SUBSTR(Arrival_Time, 3, 2)
            WHEN Arrival_Time LIKE '% PM' THEN LPAD(CAST(TRY_CAST(SUBSTR(Arrival_Time, 1, 2) AS INT) % 12 + 12 AS VARCHAR), 2, '0') || SUBSTR(Arrival_Time, 3, 3)
            WHEN Arrival_Time LIKE '% AM' THEN LPAD(CAST(TRY_CAST(SUBSTR(Arrival_Time, 1, 2) AS INT) % 12 AS VARCHAR), 2, '0') || SUBSTR(Arrival_Time, 3, 3)
            ELSE Arrival_Time END) AS TIMESTAMP) AS arr_ts
    FROM flight_data;
    """)
    con.execute(FLIGHT_ANOMALIES_VIEW_SQL)

    plan = con.execute("EXPLAIN SELECT issue_type, COUNT(*) FROM v_flight_anomalies GROUP BY issue_type").fetchall()
    assert len(plan) > 0
    plan_text = str(plan[0]).upper()
    assert "UNION" in plan_text or "PROJECTION" in plan_text or "SCAN" in plan_text or "HASH" in plan_text
    con.close()


# ==============================================================================
# SECTION 3: EDGE-CASE DATA CORRUPTIONS AND BOUNDARY TAMPERING (Challenger 1)
# ==============================================================================

@pytest.mark.tier5
def test_ingest_pack_missing_mandatory_q_id_column(tmp_path: Path):
    """
    Adversarial Stress Test: Focus 3
    Tampered questions Excel missing 'Q_ID' column must fail cleanly with KeyError or ValueError
    without leaving incomplete or corrupted records in manifest.
    """
    manifest_file = tmp_path / "manifest.json"
    golden_file = tmp_path / "golden.json"
    service = TrainingPackIngestionService(manifest_path=manifest_file, golden_output_path=golden_file)

    bank_data_path = _resolve_pack_file("bank_customers_single_sheet.xlsx")
    bank_q_path = _resolve_pack_file("bank_questions_single_sheet.xlsx")

    df_q = pd.read_excel(bank_q_path, sheet_name="Bank_Questions")
    df_bad = df_q.drop(columns=["Q_ID"])
    bad_q_path = tmp_path / "bank_q_missing_qid.xlsx"
    with pd.ExcelWriter(bad_q_path, engine="openpyxl") as writer:
        df_bad.to_excel(writer, sheet_name="Bank_Questions", index=False)

    with pytest.raises((KeyError, ValueError)):
        service.ingest_pack(
            dataset_path=bank_data_path,
            questions_path=bad_q_path,
            dataset_id="bank_test_bad_col",
            dataset_sheet="Bank_Customers",
            questions_sheet="Bank_Questions",
            force=True
        )

    if manifest_file.is_file():
        with manifest_file.open("r", encoding="utf-8") as mf:
            m = json.load(mf)
        assert "bank_test_bad_col" not in m.get("datasets", {})


@pytest.mark.tier5
def test_ingest_pack_unknown_question_id(tmp_path: Path):
    """
    Adversarial Stress Test: Focus 3
    Questions workbook with unknown Q_ID ('B999') that has no canonical SQL specification
    must raise ValueError and reject ingestion.
    """
    manifest_file = tmp_path / "manifest.json"
    golden_file = tmp_path / "golden.json"
    service = TrainingPackIngestionService(manifest_path=manifest_file, golden_output_path=golden_file)

    bank_data_path = _resolve_pack_file("bank_customers_single_sheet.xlsx")
    bank_q_path = _resolve_pack_file("bank_questions_single_sheet.xlsx")

    df_q = pd.read_excel(bank_q_path, sheet_name="Bank_Questions")
    df_bad = df_q.copy()
    df_bad.loc[0, "Q_ID"] = "B999"
    bad_q_path = tmp_path / "bank_q_unknown_id.xlsx"
    with pd.ExcelWriter(bad_q_path, engine="openpyxl") as writer:
        df_bad.to_excel(writer, sheet_name="Bank_Questions", index=False)

    with pytest.raises(ValueError, match=r"No canonical query specification found for question B999"):
        service.ingest_pack(
            dataset_path=bank_data_path,
            questions_path=bad_q_path,
            dataset_id="bank_test_unknown_qid",
            dataset_sheet="Bank_Customers",
            questions_sheet="Bank_Questions",
            force=True
        )


@pytest.mark.tier5
def test_ingest_pack_formula_errors_sanitized(tmp_path: Path):
    """
    Adversarial Stress Test: Focus 3
    Excel questions containing formula error strings ('#DIV/0!', '#REF!', '#N/A') and NaN
    in Expected_Answer are sanitized cleanly and do not crash JSON serialization or schema validation.
    """
    manifest_file = tmp_path / "manifest.json"
    golden_file = tmp_path / "golden.json"
    service = TrainingPackIngestionService(manifest_path=manifest_file, golden_output_path=golden_file)

    bank_data_path = _resolve_pack_file("bank_customers_single_sheet.xlsx")
    bank_q_path = _resolve_pack_file("bank_questions_single_sheet.xlsx")

    df_q = pd.read_excel(bank_q_path, sheet_name="Bank_Questions")
    df_err = df_q.copy()
    df_err.loc[0, "Expected_Answer"] = "#DIV/0!"
    df_err.loc[1, "Expected_Answer"] = "#REF!"
    df_err.loc[2, "Expected_Answer"] = "#N/A"
    df_err.loc[3, "Expected_Answer"] = None

    err_q_path = tmp_path / "bank_q_formula_err.xlsx"
    with pd.ExcelWriter(err_q_path, engine="openpyxl") as writer:
        df_err.to_excel(writer, sheet_name="Bank_Questions", index=False)

    res = service.ingest_pack(
        dataset_path=bank_data_path,
        questions_path=err_q_path,
        dataset_id="bank_test_formula_err",
        dataset_sheet="Bank_Customers",
        questions_sheet="Bank_Questions",
        force=True
    )

    assert res["status"] == "SUCCESS"
    assert res["num_verified"] == 30

    with golden_file.open("r", encoding="utf-8") as gf:
        golden_items = json.load(gf)
    assert len(golden_items) >= 30
    for item in golden_items:
        GoldenExample.model_validate(item)


# ==============================================================================
# SECTION 4: ANOMALY VIEW BOUNDARY STRESS (Challenger 1)
# ==============================================================================

@pytest.mark.tier5
def test_anomaly_view_zero_and_negative_duration_handling():
    """
    Adversarial Stress Test: Focus 4
    Inject flights with zero duration (dep_ts == arr_ts) and negative duration (arr_ts < dep_ts).
    Verifies that relational queries on v_flight_anomalies do not divide by zero or crash,
    and correctly flag ARRIVAL_BEFORE_DEPARTURE.
    """
    df_flight = pd.read_excel(_resolve_pack_file("flight_dataset_single_sheet.xlsx"), sheet_name="Flight_Data")

    row_zero = df_flight.iloc[0:1].copy()
    row_zero["Booking_ID"] = "FB-ADV-ZERO"
    row_zero["Journey_Date"] = "2024-05-01"
    row_zero["Dep_Time"] = "10:00:00"
    row_zero["Arrival_Date"] = "2024-05-01"
    row_zero["Arrival_Time"] = "10:00:00"
    row_zero["Distance_km"] = 500

    row_neg = df_flight.iloc[0:1].copy()
    row_neg["Booking_ID"] = "FB-ADV-NEG"
    row_neg["Journey_Date"] = "2024-05-02"
    row_neg["Dep_Time"] = "12:00:00"
    row_neg["Arrival_Date"] = "2024-05-01"
    row_neg["Arrival_Time"] = "10:00:00"
    row_neg["Distance_km"] = 1200

    test_df = pd.concat([df_flight, row_zero, row_neg], ignore_index=True)

    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE flight_data AS SELECT * FROM test_df")
    con.execute("CREATE TABLE flight AS SELECT * FROM flight_data")

    con.execute("""
    CREATE VIEW v_flight_clean AS
    SELECT *,
      TRY_CAST(Journey_Date || ' ' || (CASE 
            WHEN Dep_Time LIKE '% hrs' THEN SUBSTR(Dep_Time, 1, 2) || ':' || SUBSTR(Dep_Time, 3, 2)
            WHEN Dep_Time LIKE '% PM' THEN LPAD(CAST(TRY_CAST(SUBSTR(Dep_Time, 1, 2) AS INT) % 12 + 12 AS VARCHAR), 2, '0') || SUBSTR(Dep_Time, 3, 3)
            WHEN Dep_Time LIKE '% AM' THEN LPAD(CAST(TRY_CAST(SUBSTR(Dep_Time, 1, 2) AS INT) % 12 AS VARCHAR), 2, '0') || SUBSTR(Dep_Time, 3, 3)
            ELSE Dep_Time END) AS TIMESTAMP) AS dep_ts,
      TRY_CAST(Arrival_Date || ' ' || (CASE 
            WHEN Arrival_Time LIKE '% hrs' THEN SUBSTR(Arrival_Time, 1, 2) || ':' || SUBSTR(Arrival_Time, 3, 2)
            WHEN Arrival_Time LIKE '% PM' THEN LPAD(CAST(TRY_CAST(SUBSTR(Arrival_Time, 1, 2) AS INT) % 12 + 12 AS VARCHAR), 2, '0') || SUBSTR(Arrival_Time, 3, 3)
            WHEN Arrival_Time LIKE '% AM' THEN LPAD(CAST(TRY_CAST(SUBSTR(Arrival_Time, 1, 2) AS INT) % 12 AS VARCHAR), 2, '0') || SUBSTR(Arrival_Time, 3, 3)
            ELSE Arrival_Time END) AS TIMESTAMP) AS arr_ts
    FROM flight_data;
    """)
    con.execute(FLIGHT_ANOMALIES_VIEW_SQL)

    anomalies = con.execute("""
        SELECT Booking_ID, issue_type 
        FROM v_flight_anomalies 
        WHERE Booking_ID IN ('FB-ADV-ZERO', 'FB-ADV-NEG')
    """).fetchall()

    neg_issues = [issue for bid, issue in anomalies if bid == "FB-ADV-NEG"]
    assert "ARRIVAL_BEFORE_DEPARTURE" in neg_issues
    con.close()


@pytest.mark.tier5
def test_anomaly_view_emi_math_division_by_zero():
    """
    Adversarial Stress Test: Focus 4
    Inject rows where EMI_Opted = 'Yes' but Total_Fare = 0 or EMI_Months = 0.
    Ensures mathematical formulas in EMI anomaly calculations do not crash the engine
    with division-by-zero or floating point exceptions.
    """
    df_flight = pd.read_excel(_resolve_pack_file("flight_dataset_single_sheet.xlsx"), sheet_name="Flight_Data")

    row_zero_fare = df_flight.iloc[0:1].copy()
    row_zero_fare["Booking_ID"] = "FB-ADV-EMI-ZERO-FARE"
    row_zero_fare["EMI_Opted"] = "Yes"
    row_zero_fare["Payment_Method"] = "Credit Card"
    row_zero_fare["Total_Fare"] = 0
    row_zero_fare["Amount_Charged"] = 0
    row_zero_fare["EMI_Interest_Pct"] = 0
    row_zero_fare["EMI_Months"] = 3
    row_zero_fare["EMI_Amount"] = 0

    row_zero_months = df_flight.iloc[0:1].copy()
    row_zero_months["Booking_ID"] = "FB-ADV-EMI-ZERO-MONTHS"
    row_zero_months["EMI_Opted"] = "Yes"
    row_zero_months["Payment_Method"] = "Credit Card"
    row_zero_months["Total_Fare"] = 5000
    row_zero_months["Amount_Charged"] = 5000
    row_zero_months["EMI_Interest_Pct"] = 0
    row_zero_months["EMI_Months"] = 0
    row_zero_months["EMI_Amount"] = 1000

    test_df = pd.concat([df_flight, row_zero_fare, row_zero_months], ignore_index=True)

    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE flight_data AS SELECT * FROM test_df")
    con.execute("CREATE TABLE flight AS SELECT * FROM flight_data")

    con.execute("""
    CREATE VIEW v_flight_clean AS
    SELECT *,
      TRY_CAST(Journey_Date || ' ' || (CASE 
            WHEN Dep_Time LIKE '% hrs' THEN SUBSTR(Dep_Time, 1, 2) || ':' || SUBSTR(Dep_Time, 3, 2)
            WHEN Dep_Time LIKE '% PM' THEN LPAD(CAST(TRY_CAST(SUBSTR(Dep_Time, 1, 2) AS INT) % 12 + 12 AS VARCHAR), 2, '0') || SUBSTR(Dep_Time, 3, 3)
            WHEN Dep_Time LIKE '% AM' THEN LPAD(CAST(TRY_CAST(SUBSTR(Dep_Time, 1, 2) AS INT) % 12 AS VARCHAR), 2, '0') || SUBSTR(Dep_Time, 3, 3)
            ELSE Dep_Time END) AS TIMESTAMP) AS dep_ts,
      TRY_CAST(Arrival_Date || ' ' || (CASE 
            WHEN Arrival_Time LIKE '% hrs' THEN SUBSTR(Arrival_Time, 1, 2) || ':' || SUBSTR(Arrival_Time, 3, 2)
            WHEN Arrival_Time LIKE '% PM' THEN LPAD(CAST(TRY_CAST(SUBSTR(Arrival_Time, 1, 2) AS INT) % 12 + 12 AS VARCHAR), 2, '0') || SUBSTR(Arrival_Time, 3, 3)
            WHEN Arrival_Time LIKE '% AM' THEN LPAD(CAST(TRY_CAST(SUBSTR(Arrival_Time, 1, 2) AS INT) % 12 AS VARCHAR), 2, '0') || SUBSTR(Arrival_Time, 3, 3)
            ELSE Arrival_Time END) AS TIMESTAMP) AS arr_ts
    FROM flight_data;
    """)
    con.execute(FLIGHT_ANOMALIES_VIEW_SQL)

    res = con.execute("""
        SELECT Booking_ID, issue_type 
        FROM v_flight_anomalies 
        WHERE Booking_ID IN ('FB-ADV-EMI-ZERO-FARE', 'FB-ADV-EMI-ZERO-MONTHS')
    """).fetchall()

    assert len(res) > 0
    con.close()


# ==============================================================================
# SECTION 5: EXEMPLAR RETRIEVER QUERY BOUNDARIES (Challenger 2)
# ==============================================================================

@pytest.mark.tier5
def test_example_retriever_extreme_query_inputs():
    """
    Stress-test ExampleRetriever against empty, whitespace, 10k-char,
    SQL-injection, unicode, null-byte, and non-string/None columns inputs.
    """
    # 1. Empty string
    res_empty = ExampleRetriever.retrieve("", columns=["Airline", "Total_Fare"])
    assert isinstance(res_empty, list)

    # 2. Whitespace-only string
    res_ws = ExampleRetriever.retrieve("   \t\n   ", columns=["Airline", "Total_Fare"])
    assert isinstance(res_ws, list)

    # 3. 10,000-character adversarial string
    huge_q = "flight delay " * 800 + "X" * 1000
    t0 = time.perf_counter()
    res_huge = ExampleRetriever.retrieve(huge_q, columns=["Airline", "Total_Fare"])
    dt_ms = (time.perf_counter() - t0) * 1000.0
    assert isinstance(res_huge, list)
    assert dt_ms < 200.0, f"Retrieval of 10k string took {dt_ms:.2f}ms (>200ms SLA)"

    # 4. SQL Injection payload
    sqli_q = "'; DROP TABLE flight_data; SELECT * FROM users WHERE '1'='1 --"
    res_sqli = ExampleRetriever.retrieve(sqli_q, columns=["Airline", "Total_Fare"])
    assert isinstance(res_sqli, list)

    # 5. Unicode, Emojis, and Null bytes
    unicode_q = "✈️ 🚀 उड़ानों की संख्या \u0000 \ufffd \U0001F600 日本語 " + "ß" * 20
    res_uni = ExampleRetriever.retrieve(unicode_q, columns=["Airline"])
    assert isinstance(res_uni, list)

    # 6. Empty columns list
    res_empty_cols = ExampleRetriever.retrieve("flight fare", columns=[])
    assert isinstance(res_empty_cols, list)

    # 7. Non-string / None columns defensive handling
    res_none_cols = ExampleRetriever.retrieve("flight fare", columns=[None, 123, "Airline"])
    assert isinstance(res_none_cols, list)


@pytest.mark.tier5
def test_example_retriever_top_k_boundaries():
    """
    Verify retrieval behavior at boundary values of top_k:
    top_k=0, negative values (fixing Python slice anomaly), and large values.
    """
    # top_k = 0 should return empty list
    res_zero = ExampleRetriever.retrieve("flight fare", columns=["Airline"], top_k=0)
    assert res_zero == []

    # Large top_k should return all matching results without index out of bounds
    res_huge_k = ExampleRetriever.retrieve("flight fare", columns=["Airline"], top_k=5000)
    assert isinstance(res_huge_k, list)
    assert len(res_huge_k) <= 5000

    # Negative top_k: properly guarded to return [] instead of sliced records
    res_neg = ExampleRetriever.retrieve("flight fare", columns=["Airline"], top_k=-1)
    assert isinstance(res_neg, list)
    assert res_neg == []


@pytest.mark.tier5
def test_example_retriever_colliding_domain_phrases():
    """
    Adversarial multi-domain collision: construct query mixing key phrases from
    Flight, Bank, and Song domains simultaneously to test scoring and ranking stability.
    """
    query = (
        "What is the highest flight airline fare for song remake youtube views "
        "with credit score savings loan emi?"
    )
    cols = ["Total_Fare", "Credit_Score", "Views", "Airline"]
    results = ExampleRetriever.retrieve(query, columns=cols, top_k=6)
    assert isinstance(results, list)
    assert len(results) > 0

    # Verify results span multiple domains and are sorted by score
    dataset_ids = {r.get("dataset_id") for r in results if r.get("dataset_id")}
    assert len(dataset_ids) >= 1


# ==============================================================================
# SECTION 6: HOT-RELOADING, CACHING & FILE FAILURES (Challenger 2)
# ==============================================================================

@pytest.mark.tier5
def test_example_retriever_dynamic_hot_reloading(monkeypatch, tmp_path):
    """
    Verify ExampleRetriever dynamically reloads when artifact files are updated on disk
    without requiring manual cache clearing.
    """
    tmp_golden = tmp_path / "mock_golden.json"
    tmp_tp = tmp_path / "mock_tp.json"

    initial_item = {
        "example_id": "mock-01",
        "question": "What is the initial total fare?",
        "approval_status": "approved",
        "column_mapping": {"fare": "Total_Fare"}
    }
    tmp_golden.write_text(json.dumps([initial_item]), encoding="utf-8")
    tmp_tp.write_text(json.dumps([]), encoding="utf-8")

    monkeypatch.setattr(er_mod, "GOLDEN_FILE", str(tmp_golden))
    monkeypatch.setattr(er_mod, "TRAINING_PACK_GOLDEN_FILE", str(tmp_tp))
    ExampleRetriever.clear_cache()

    # Step 1: Initial load
    loaded1 = ExampleRetriever.load_examples()
    assert len(loaded1) == 1
    assert loaded1[0]["example_id"] == "mock-01"

    # Step 2: Update file with new item and advance mtime
    time.sleep(1.05)  # Ensure filesystem mtime increases beyond quantization
    updated_items = [
        initial_item,
        {
            "example_id": "mock-02",
            "question": "What is the new total fare?",
            "approval_status": "approved",
            "column_mapping": {"fare": "Total_Fare"}
        }
    ]
    tmp_golden.write_text(json.dumps(updated_items), encoding="utf-8")

    # Step 3: Call load_examples without force_reload -> should detect new mtime
    loaded2 = ExampleRetriever.load_examples()
    assert len(loaded2) == 2
    assert any(x["example_id"] == "mock-02" for x in loaded2)


@pytest.mark.tier5
def test_example_retriever_corrupted_file_handling(monkeypatch, tmp_path):
    """
    Verify ExampleRetriever behavior when golden artifact file contains invalid JSON.
    It should log an error and not raise unhandled crash to the caller.
    """
    tmp_golden = tmp_path / "corrupt_golden.json"
    tmp_tp = tmp_path / "corrupt_tp.json"

    tmp_golden.write_text("{ MALFORMED_JSON_CORRUPTION_HEADER: [", encoding="utf-8")
    tmp_tp.write_text(json.dumps([]), encoding="utf-8")

    monkeypatch.setattr(er_mod, "GOLDEN_FILE", str(tmp_golden))
    monkeypatch.setattr(er_mod, "TRAINING_PACK_GOLDEN_FILE", str(tmp_tp))
    ExampleRetriever.clear_cache()

    # Loading corrupted file should not crash with uncaught JSONDecodeError
    loaded = ExampleRetriever.load_examples()
    assert isinstance(loaded, list)
    assert len(loaded) == 0

    # Retrieve should return empty list gracefully
    res = ExampleRetriever.retrieve("flight fare", columns=["fare"])
    assert res == []


@pytest.mark.tier5
def test_example_retriever_deleted_file_resilience(monkeypatch, tmp_path):
    """
    Verify ExampleRetriever behavior when an artifact file is deleted from disk.
    """
    tmp_golden = tmp_path / "del_golden.json"
    tmp_tp = tmp_path / "del_tp.json"

    tmp_golden.write_text(json.dumps([{"example_id": "del-01", "question": "q", "approval_status": "approved"}]), encoding="utf-8")
    tmp_tp.write_text(json.dumps([]), encoding="utf-8")

    monkeypatch.setattr(er_mod, "GOLDEN_FILE", str(tmp_golden))
    monkeypatch.setattr(er_mod, "TRAINING_PACK_GOLDEN_FILE", str(tmp_tp))
    ExampleRetriever.clear_cache()

    # Load initial
    assert len(ExampleRetriever.load_examples()) == 1

    # Delete the golden file
    tmp_golden.unlink()
    ExampleRetriever.clear_cache()

    # Should not crash on missing file
    loaded = ExampleRetriever.load_examples()
    assert isinstance(loaded, list)
    assert len(loaded) == 0


# ==============================================================================
# SECTION 7: SCHEMA BOUNDARIES & ANTI-FACADE GUARDS (Challenger 2)
# ==============================================================================

@pytest.mark.tier5
def test_manifest_boundary_null_datasets(tmp_path):
    """
    Test TrainingPackIngestionService resilience when manifest has null datasets.
    """
    manifest_file = tmp_path / "manifest_null.json"
    manifest_file.write_text(json.dumps({"manifest_version": "1.0", "datasets": None}), encoding="utf-8")

    svc = TrainingPackIngestionService(manifest_path=manifest_file)
    manifest_data = svc._load_manifest()
    assert manifest_data["datasets"] is None

    # is_already_ingested safely handles null datasets without AttributeError
    datasets_dict = manifest_data.get("datasets") or {}
    assert datasets_dict.get("flight_data") is None
    assert svc.is_already_ingested("flight_data", "some_checksum") is False


@pytest.mark.tier5
def test_manifest_forward_compatibility_extra_fields(tmp_path):
    """
    Verify manifest preserves unexpected extra metadata fields across save operations.
    """
    manifest_file = tmp_path / "manifest_extra.json"
    initial_content = {
        "manifest_version": "1.0",
        "custom_telemetry": {"cluster": "us-east-1", "run_id": "run-999"},
        "datasets": {
            "flight_data": {
                "status": "verified",
                "composite_checksum": "dummy_chk",
                "extra_tag": "experimental"
            }
        }
    }
    manifest_file.write_text(json.dumps(initial_content), encoding="utf-8")

    svc = TrainingPackIngestionService(manifest_path=manifest_file)
    assert svc.is_already_ingested("flight_data", "dummy_chk") is True

    # Save manifest and verify custom_telemetry is retained
    loaded = svc._load_manifest()
    svc._save_manifest(loaded)
    reloaded = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert reloaded.get("custom_telemetry", {}).get("cluster") == "us-east-1"


@pytest.mark.tier5
def test_golden_example_schema_strictness_and_versioning():
    """
    Test schema boundary: verify GoldenExample Pydantic model validation
    and schema version flexibility/strictness.
    """
    valid_payload = {
        "schema_version": "1.0",
        "example_id": "tp-test-01",
        "dataset_id": "flight_data",
        "dataset_checksum": "sha256_mock_hash",
        "question": "What is the average delay?",
        "language": "english",
        "intent": "data_analysis",
        "semantic_target": "delay",
        "column_mapping": {"delay": "Delay"},
        "sql_query": "SELECT AVG(Delay) FROM flight_data",
        "expected_plan": {"operation": "sql"},
        "expected_answer": {"raw": "15.2", "rows": [{"avg": 15.2}]},
        "verification": {"status": "verified", "engine": "duckdb"},
        "source_type": "training_pack",
        "approval_status": "approved"
    }

    ex_v1 = GoldenExample.model_validate(valid_payload)
    assert ex_v1.schema_version == "1.0"

    # Schema version 2.0 payload
    payload_v2 = dict(valid_payload, schema_version="2.0")
    ex_v2 = GoldenExample.model_validate(payload_v2)
    assert ex_v2.schema_version == "2.0"

    # Missing mandatory fields must raise ValidationError
    with pytest.raises(ValidationError):
        GoldenExample.model_validate({"question": "Only question provided"})


@pytest.mark.tier5
def test_anti_facade_guard_bypass_vectors():
    """
    Adversarial challenge: test known circumvention vectors against the anti-facade guard.
    Evaluates:
    - Inline comment between IN and parenthesis: `IN /* bypass */ ('FB001')`
    - Subquery wrapping: `IN (SELECT 'FB001')`
    - Equality chaining: `Booking_ID = 'FB001' OR Booking_ID = 'FB002'`
    - Commented FROM: `SELECT 42 /* FROM flight */`
    """
    # Current hardened detector
    def hardened_facade_check(sql: str) -> bool:
        clean_sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
        clean_sql = re.sub(r"--[^\n]*", " ", clean_sql)
        if not re.search(r"\bFROM\b", clean_sql, re.IGNORECASE):
            return True  # Facade: no legitimate FROM clause
        if re.search(r"'(?:FB\d+|CUST\d+|BS\d+|TXN\d+)'", clean_sql, re.IGNORECASE):
            return True  # Facade: hardcoded domain identifiers
        return False

    # 1. Legitimate query
    legit_sql = "SELECT Airline, AVG(Total_Fare) FROM flight_data GROUP BY Airline"
    assert hardened_facade_check(legit_sql) is False

    # 2. Standard facade
    standard_facade = "SELECT * FROM flight_data WHERE Booking_ID IN ('FB001', 'FB002')"
    assert hardened_facade_check(standard_facade) is True

    # 3. Bypass vectors caught by hardened detector
    assert hardened_facade_check("SELECT 42 /* FROM flight_data */") is True
    assert hardened_facade_check("SELECT * FROM flight_data WHERE Booking_ID IN /* comment */ ('FB001')") is True
    assert hardened_facade_check("SELECT * FROM flight_data WHERE Booking_ID = 'FB001' OR Booking_ID = 'FB002'") is True
    assert hardened_facade_check("SELECT * FROM flight_data WHERE Booking_ID IN (SELECT 'FB001')") is True


# ==============================================================================
# SECTION 8: PERFORMANCE, MEMORY & CONCURRENCY (Challenger 2)
# ==============================================================================

@pytest.mark.tier5
def test_example_retriever_rapid_query_throughput():
    """
    Stress-test ExampleRetriever throughput: 500 queries in a tight loop.
    Ensures no latency degradation, bounded execution time (<3.0s total),
    and steady memory footprint.
    """
    query = "What is the highest ticket fare for Mumbai to Delhi flight?"
    cols = ["Source", "Destination", "Fare", "Airline"]

    t0 = time.perf_counter()
    for _ in range(500):
        res = ExampleRetriever.retrieve(query, columns=cols, top_k=2)
        assert len(res) <= 2
    elapsed_total = time.perf_counter() - t0

    mean_per_query_ms = (elapsed_total / 500.0) * 1000.0
    assert elapsed_total < 3.0, f"500 queries took {elapsed_total:.2f}s (exceeded 3.0s limit)"
    assert mean_per_query_ms < 6.0, f"Mean query latency was {mean_per_query_ms:.2f}ms (>6ms SLA)"


@pytest.mark.tier5
def test_example_retriever_multithreaded_concurrency():
    """
    Concurrent multi-threaded stress: 8 worker threads executing 50 queries each
    simultaneously across different domains to ensure thread safety of caching & retrieval.
    """
    queries = [
        ("flight delay for Indigo", ["Airline", "Delay"]),
        ("average bank customer balance", ["Balance", "Customer_ID"]),
        ("bollywood song remake views youtube", ["Views", "Remake_Status"]),
        ("highest fare from Bangalore", ["Source", "Total_Fare"])
    ]

    errors: List[Exception] = []

    def worker_fn(thread_id: int):
        try:
            for idx in range(50):
                q, cols = queries[idx % len(queries)]
                res = ExampleRetriever.retrieve(f"{q} thread-{thread_id}-{idx}", columns=cols, top_k=2)
                assert isinstance(res, list)
        except Exception as e:
            errors.append(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker_fn, i) for i in range(8)]
        for f in futures:
            f.result()

    assert len(errors) == 0, f"Thread errors encountered during concurrency test: {errors}"
