"""
Unit and integration tests for Milestone 1:
Training Pack Ingestion, Idempotency, Canonical DuckDB Execution, and ExampleRetriever Integration.
"""
import time
import json
import re
from pathlib import Path
import pytest
import duckdb
import pandas as pd

from app.learning.training_pack import (
    TrainingPackIngestionService,
    compute_binary_sha256,
    DEFAULT_MANIFEST_PATH,
    DEFAULT_GOLDEN_PATH,
    PACK_CONFIGS
)
from app.learning.training_pack_queries import (
    FLIGHT_QUERIES,
    BANK_QUERIES,
    SONGS_QUERIES,
    FLIGHT_ANOMALIES_VIEW_SQL,
    get_flight_anomalies_view_sql,
    get_query_spec,
    get_all_specs
)
from app.ai.learning.example_retrieval import ExampleRetriever


def test_training_pack_checksum_computation():
    service = TrainingPackIngestionService()
    flight_file = Path("data/training_pack/flight_dataset_single_sheet.xlsx")
    assert flight_file.is_file()

    checksums = service.compute_checksums(flight_file)
    assert "binary_sha256" in checksums
    assert "logical_sha256" in checksums
    assert len(checksums["binary_sha256"]) == 64
    assert len(checksums["logical_sha256"]) == 64
    assert checksums["binary_sha256"] == "2d9492600a645bc92917375ed0f26456828433c640d6cb87878ad7c6df85a4d2"


def test_training_pack_ingestion_and_artifact_generation(tmp_path):
    manifest_file = tmp_path / "test_manifest.json"
    golden_file = tmp_path / "test_golden.json"

    service = TrainingPackIngestionService(
        manifest_path=manifest_file,
        golden_output_path=golden_file
    )

    res = service.ingest_all(force=True)
    assert res["status"] == "SUCCESS"
    assert res["total_verified"] == 150
    assert golden_file.is_file()
    assert manifest_file.is_file()

    with golden_file.open("r", encoding="utf-8") as f:
        examples = json.load(f)
    assert len(examples) == 150

    # Verify split: 70% train (105), 30% test (45)
    train_count = sum(1 for e in examples if e["split"] == "train")
    test_count = sum(1 for e in examples if e["split"] == "test")
    assert train_count == 105
    assert test_count == 45
    assert train_count / 150 == 0.70
    assert test_count / 150 == 0.30

    # Verify GoldenExample schema fields
    for ex in examples:
        assert ex["schema_version"] == "1.0"
        assert ex["approval_status"] == "approved"
        assert ex["verification"]["status"] == "verified"
        assert ex["verification"]["engine"] == "duckdb"
        assert ex["sql_query"] is not None and len(ex["sql_query"]) > 5
        assert "raw" in ex["expected_answer"]
        assert "columns" in ex["expected_answer"]
        assert "row_count" in ex["expected_answer"]


def test_training_pack_idempotency_under_100ms(tmp_path):
    manifest_file = tmp_path / "test_manifest.json"
    golden_file = tmp_path / "test_golden.json"

    service = TrainingPackIngestionService(
        manifest_path=manifest_file,
        golden_output_path=golden_file
    )

    # First run (fresh ingestion)
    res1 = service.ingest_all(force=True)
    assert res1["status"] == "SUCCESS"

    # Second run (strict idempotency check)
    t0 = time.perf_counter()
    res2 = service.ingest_all(force=False)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert res2["status"] == "ALREADY_INGESTED"
    assert res2["total_verified"] == 150
    assert elapsed_ms < 100.0, f"Expected idempotency response < 100ms, took {elapsed_ms:.2f}ms"

    for ds_id in ["flight_data", "bank_customers", "songs_finance"]:
        assert res2["results"][ds_id]["status"] == "ALREADY_INGESTED"


def test_all_150_canonical_queries_execute_in_duckdb():
    con = duckdb.connect(":memory:")

    df_f = pd.read_excel("data/training_pack/flight_dataset_single_sheet.xlsx", sheet_name="Flight_Data")
    df_b = pd.read_excel("data/training_pack/bank_customers_single_sheet.xlsx", sheet_name="Bank_Customers")
    df_s = pd.read_excel("data/training_pack/bollywood_songs_finance_dataset.xlsx", sheet_name="Songs_Finance")

    con.register("flight_data", df_f)
    con.register("flight", df_f)
    con.register("bank_customers", df_b)
    con.register("bank", df_b)
    con.register("songs_finance", df_s)
    con.register("songs", df_s)
    con.register("bollywood", df_s)

    con.execute("""
    CREATE VIEW v_flight_clean AS
    SELECT *,
      CAST(Journey_Date || ' ' || (CASE 
            WHEN Dep_Time LIKE '% hrs' THEN SUBSTR(Dep_Time, 1, 2) || ':' || SUBSTR(Dep_Time, 3, 2)
            WHEN Dep_Time LIKE '% PM' THEN LPAD(CAST(CAST(SUBSTR(Dep_Time, 1, 2) AS INT) % 12 + 12 AS VARCHAR), 2, '0') || SUBSTR(Dep_Time, 3, 3)
            WHEN Dep_Time LIKE '% AM' THEN LPAD(CAST(CAST(SUBSTR(Dep_Time, 1, 2) AS INT) % 12 AS VARCHAR), 2, '0') || SUBSTR(Dep_Time, 3, 3)
            ELSE Dep_Time END) AS TIMESTAMP) AS dep_ts,
      CAST(Arrival_Date || ' ' || (CASE 
            WHEN Arrival_Time LIKE '% hrs' THEN SUBSTR(Arrival_Time, 1, 2) || ':' || SUBSTR(Arrival_Time, 3, 2)
            WHEN Arrival_Time LIKE '% PM' THEN LPAD(CAST(CAST(SUBSTR(Arrival_Time, 1, 2) AS INT) % 12 + 12 AS VARCHAR), 2, '0') || SUBSTR(Arrival_Time, 3, 3)
            WHEN Arrival_Time LIKE '% AM' THEN LPAD(CAST(CAST(SUBSTR(Arrival_Time, 1, 2) AS INT) % 12 AS VARCHAR), 2, '0') || SUBSTR(Arrival_Time, 3, 3)
            ELSE Arrival_Time END) AS TIMESTAMP) AS arr_ts
    FROM flight_data;
    """)

    con.execute(FLIGHT_ANOMALIES_VIEW_SQL)

    dataset_specs = [
        ("Flight", FLIGHT_QUERIES, ["flight_data", "flight", "v_flight_clean", "v_flight_anomalies"]),
        ("Bank", BANK_QUERIES, ["bank_customers", "bank"]),
        ("Songs", SONGS_QUERIES, ["songs_finance", "songs", "bollywood"]),
    ]

    for domain_name, queries, valid_tables in dataset_specs:
        table_pattern = r"\b(" + "|".join(valid_tables) + r")\b"
        
        for q_id, spec in queries.items():
            sql = spec["sql_query"]

            # Assertion 1: Mandatory FROM clause
            assert re.search(r"\bFROM\b", sql, re.IGNORECASE) is not None, (
                f"[{domain_name} {q_id}] Query has no FROM clause! Facade constant queries are prohibited."
            )

            # Assertion 2: Must reference registered domain tables or views
            assert re.search(table_pattern, sql, re.IGNORECASE) is not None, (
                f"[{domain_name} {q_id}] Query does not reference any valid table/view: {valid_tables}."
            )

            # Assertion 3: Prohibit static UNION branches without FROM
            if re.search(r"\bUNION\b", sql, re.IGNORECASE):
                branches = re.split(r"\bUNION\s+(?:ALL\s+|DISTINCT\s+)?", sql, flags=re.IGNORECASE)
                for b_idx, branch in enumerate(branches, start=1):
                    assert re.search(r"\bFROM\b", branch, re.IGNORECASE) is not None, (
                        f"[{domain_name} {q_id}] UNION branch {b_idx} has no FROM clause! Static union cascades are prohibited."
                    )

            # Assertion 4: Prohibit manual/hardcoded primary key ID lists in IN clauses
            id_in_match = re.search(r"\bIN\s*\(\s*'(?:FB\d+|CUST\d+|BS\d+|TXN\d+)'", sql, re.IGNORECASE)
            assert id_in_match is None, (
                f"[{domain_name} {q_id}] Query hardcodes record IDs in an IN clause ({id_in_match.group(0)}...) instead of relational computation!"
            )

            # Assertion 5: DuckDB physical execution plan check (no Dummy Scan)
            plan_rows = con.execute(f"EXPLAIN {sql}").fetchall()
            plan_str = "\n".join(str(r[1]) for r in plan_rows)
            assert "Dummy Scan" not in plan_str, (
                f"[{domain_name} {q_id}] Execution plan contains Dummy Scan! Real table data scanning is mandatory."
            )

            # Assertion 6: Execution returns non-empty result
            res = con.execute(sql).fetchall()
            assert len(res) > 0, f"[{domain_name} {q_id}] Query returned 0 rows."

    con.close()


def test_example_retriever_integration_with_training_pack():
    # Ingest if not present
    service = TrainingPackIngestionService()
    service.ingest_all(force=False)

    ExampleRetriever.clear_cache()
    all_examples = ExampleRetriever.load_examples()

    # Must contain both 300+ golden base examples and 150 training pack examples
    assert len(all_examples) >= 450

    # 1. Flight domain query retrieval
    flight_results = ExampleRetriever.retrieve(
        question="Which airline has the highest average fare?",
        columns=["Airline", "Total_Fare"],
        top_k=2
    )
    assert len(flight_results) > 0
    assert any("flight" in ex.get("dataset_id", "") or "tp-flight" in ex.get("example_id", "") for ex in flight_results)

    # 2. Bank domain query retrieval
    bank_results = ExampleRetriever.retrieve(
        question="What is the average credit score of customers?",
        columns=["Credit_Score", "Customer_ID"],
        top_k=2
    )
    assert len(bank_results) > 0
    assert any("bank" in ex.get("dataset_id", "") or "tp-bank" in ex.get("example_id", "") for ex in bank_results)

    # 3. Bollywood Songs domain query retrieval
    song_results = ExampleRetriever.retrieve(
        question="Which music label earned the most revenue from songs?",
        columns=["Music_Label", "Total_Income"],
        top_k=2
    )
    assert len(song_results) > 0
    assert any("song" in ex.get("dataset_id", "") or "tp-song" in ex.get("example_id", "") for ex in song_results)
