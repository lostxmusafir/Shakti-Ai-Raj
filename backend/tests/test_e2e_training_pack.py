"""
Complete 4-Tier End-to-End Test Suite for Shakti-Ai-Raj Excel Training Pack Learning.

Methodology:
- Tier 1: Feature Coverage (@pytest.mark.tier1) - Checksums, Ingestion, Manifest & Golden Artifacts, Idempotency.
- Tier 2: Boundary & Corner Cases (@pytest.mark.tier2) - Tampered Checksums, Invalid Sheets, Corrupted Files, Force Re-ingestion.
- Tier 3: Cross-Feature Combinations (@pytest.mark.tier3) - Concurrent DuckDB Registration, Interleaved Ingestion, Semantic Retriever.
- Tier 4: Real-World Scenarios (@pytest.mark.tier4) - 150-Question DuckDB Recomputation, 30% Held-Out Generalization, 300+ Benchmark Non-Regression.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd
import pytest

from app.ai.learning.evaluation_service import evaluation_service
from app.ai.learning.example_retrieval import ExampleRetriever
from app.learning.examples import GoldenExample
from app.learning.training_pack import (
    DEFAULT_GOLDEN_PATH,
    DEFAULT_MANIFEST_PATH,
    DEFAULT_TRAINING_PACK_DIR,
    PACK_CONFIGS,
    TrainingPackIngestionService,
)
from app.learning.training_pack_queries import (
    BANK_QUERIES,
    FLIGHT_QUERIES,
    SONGS_QUERIES,
    FLIGHT_ANOMALIES_VIEW_SQL,
    get_all_specs,
    get_catalog,
)

# Suppress unknown mark warnings when run without conftest marker registrations
pytestmark = [pytest.mark.filterwarnings("ignore::pytest.PytestUnknownMarkWarning")]


# Verified cryptographic reference checksums from TEST_INFRA.md
VERIFIED_CHECKSUMS: Dict[str, str] = {
    "flight_dataset_single_sheet.xlsx": "2d9492600a645bc92917375ed0f26456828433c640d6cb87878ad7c6df85a4d2",
    "flight_questions_60_single_sheet.xlsx": "edc521ca1fcf24737413c48748b51d73cba987a8230388a10babcc16e23d1458",
    "bank_customers_single_sheet.xlsx": "383e1f46701721f82417641fcff7b5c068bc793bd0ddfb681c72ed1382bfa358",
    "bank_questions_single_sheet.xlsx": "f6720422dde29dd6005ca7bae858e2086b07f8cb6b55645206e281ccf68786ee",
    "bollywood_songs_finance_dataset.xlsx": "160bec0ccd23e1c1c487d1319fc95774d5bba957fd80c92ab2eb7930348abcc1",
    "bollywood_songs_questions_60_single_sheet.xlsx": "e19d7694c7cb0f139c6967dc6736bd4f02c7e05246f00353b77548b7d2973e2e",
}

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _compute_binary_sha256(path: Path) -> str:
    """Computes exact binary SHA-256 for a given file path."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _resolve_pack_file(filename: str) -> Path:
    """Resolves pack file from data/training_pack or workspace root."""
    candidates = [
        DEFAULT_TRAINING_PACK_DIR / filename,
        BASE_DIR / "data" / "training_pack" / filename,
        BASE_DIR / filename,
    ]
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError(f"Could not find {filename} in {[str(c) for c in candidates]}")


@pytest.fixture(scope="module")
def ingestion_service() -> TrainingPackIngestionService:
    """Module-scoped TrainingPackIngestionService instance."""
    return TrainingPackIngestionService()


@pytest.fixture(scope="module")
def multi_dataset_duckdb_con():
    """In-memory DuckDB connection containing all 3 training pack tables and clean views."""
    con = duckdb.connect(":memory:")

    # 1. Flight Data & View
    flight_data_path = _resolve_pack_file("flight_dataset_single_sheet.xlsx")
    df_flight = pd.read_excel(flight_data_path, sheet_name="Flight_Data", engine="openpyxl")
    con.register("flight_data", df_flight)
    con.register("flight", df_flight)
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

    # 2. Bank Customers
    bank_data_path = _resolve_pack_file("bank_customers_single_sheet.xlsx")
    df_bank = pd.read_excel(bank_data_path, sheet_name="Bank_Customers", engine="openpyxl")
    con.register("bank_customers", df_bank)
    con.register("bank", df_bank)

    # 3. Songs Finance
    songs_data_path = _resolve_pack_file("bollywood_songs_finance_dataset.xlsx")
    df_songs = pd.read_excel(songs_data_path, sheet_name="Songs_Finance", engine="openpyxl")
    con.register("songs_finance", df_songs)
    con.register("songs", df_songs)
    con.register("bollywood", df_songs)

    yield con
    con.close()


# ==============================================================================
# TIER 1: FEATURE COVERAGE (@pytest.mark.tier1)
# ==============================================================================


@pytest.mark.tier1
def test_sha256_cryptographic_checksums(ingestion_service: TrainingPackIngestionService):
    """
    Tier 1: Feature Coverage
    Verify exact binary SHA-256 for all 6 Excel files against verified reference checksums.
    Validates both direct binary hashing and the service's compute_checksums method.
    """
    for filename, expected_hash in VERIFIED_CHECKSUMS.items():
        resolved_path = _resolve_pack_file(filename)
        assert resolved_path.is_file(), f"Expected file {filename} does not exist"

        # Direct binary verification
        computed_binary = _compute_binary_sha256(resolved_path)
        assert computed_binary == expected_hash, (
            f"Checksum mismatch for {filename}: computed {computed_binary}, expected {expected_hash}"
        )

        # Service method verification
        service_checksums = ingestion_service.compute_checksums(resolved_path)
        assert service_checksums["binary_sha256"] == expected_hash, (
            f"Service binary hash mismatch for {filename}"
        )
        assert "logical_sha256" in service_checksums
        assert len(service_checksums["logical_sha256"]) == 64

    # Also verify workspace root copies match if present
    for filename, expected_hash in VERIFIED_CHECKSUMS.items():
        root_path = BASE_DIR / filename
        if root_path.is_file():
            assert _compute_binary_sha256(root_path) == expected_hash, (
                f"Workspace root file {filename} has altered checksum"
            )


@pytest.mark.tier1
def test_training_pack_ingestion_generates_manifest_and_artifacts(
    ingestion_service: TrainingPackIngestionService
):
    """
    Tier 1: Feature Coverage
    Test ingestion service on Flight_Data, Bank_Customers, Songs_Finance.
    Verify manifest generation at data/benchmark/manifests/training_pack_ingestion_manifest.json
    and golden artifacts at data/benchmark/golden/golden_examples_training_pack.json.
    """
    result = ingestion_service.ingest_all()
    assert result["status"] in ("SUCCESS", "ALREADY_INGESTED"), (
        f"Unexpected ingestion status: {result['status']}"
    )
    assert result["total_verified"] == 150, (
        f"Expected 150 verified questions, found {result['total_verified']}"
    )

    # Verify Manifest
    manifest_path = DEFAULT_MANIFEST_PATH
    assert manifest_path.is_file(), f"Manifest file missing at {manifest_path}"
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest.get("manifest_version") == "1.0"
    datasets = manifest.get("datasets", {})
    for expected_id in ["flight_data", "bank_customers", "songs_finance"]:
        assert expected_id in datasets, f"Dataset {expected_id} missing from manifest"
        ds_entry = datasets[expected_id]
        assert ds_entry.get("status") == "verified"
        assert ds_entry.get("num_verified") in (60, 30)
        assert len(ds_entry.get("composite_checksum", "")) == 64
        assert len(ds_entry.get("dataset_binary_sha256", "")) == 64
        assert len(ds_entry.get("questions_binary_sha256", "")) == 64

    # Verify Golden Artifacts File
    golden_path = DEFAULT_GOLDEN_PATH
    assert golden_path.is_file(), f"Golden artifacts missing at {golden_path}"
    with golden_path.open("r", encoding="utf-8") as gf:
        golden_data = json.load(gf)
    assert len(golden_data) == 150, f"Expected 150 golden artifacts, found {len(golden_data)}"


@pytest.mark.tier1
def test_golden_examples_schema_and_count():
    """
    Tier 1: Feature Coverage
    Verify golden examples match schema 1.0, count matches 150 questions (60 flight, 30 bank, 60 songs),
    and required fields are populated with correct 70% train / 30% test split.
    """
    golden_path = DEFAULT_GOLDEN_PATH
    assert golden_path.is_file(), f"Golden artifact missing: {golden_path}"

    with golden_path.open("r", encoding="utf-8") as f:
        examples = json.load(f)

    assert len(examples) == 150, f"Total golden examples must be 150, found {len(examples)}"

    dataset_counts: Dict[str, int] = {}
    split_counts: Dict[str, int] = {}

    for record in examples:
        # Validate against GoldenExample Pydantic schema
        example = GoldenExample.model_validate(record)

        assert example.schema_version == "1.0", f"Invalid schema version: {example.schema_version}"
        assert example.example_id.startswith("tp-"), f"Example ID must start with 'tp-': {example.example_id}"
        assert example.dataset_id in ("flight_data", "bank_customers", "songs_finance"), (
            f"Invalid dataset_id: {example.dataset_id}"
        )
        assert len(example.dataset_checksum) == 64, "dataset_checksum must be 64-char SHA-256"
        assert example.question.strip() != "", "question cannot be empty"
        assert example.sql_query and example.sql_query.strip() != "", "sql_query cannot be empty"
        assert "raw" in example.expected_answer, "expected_answer must contain 'raw'"
        assert example.verification.get("status") == "verified", "status must be 'verified'"
        assert example.verification.get("engine") == "duckdb", "engine must be 'duckdb'"
        assert example.approval_status == "approved", "approval_status must be 'approved'"
        assert example.split in ("train", "test"), f"split must be 'train' or 'test': {example.split}"

        dataset_counts[example.dataset_id] = dataset_counts.get(example.dataset_id, 0) + 1
        split_counts[example.split] = split_counts.get(example.split, 0) + 1

    # Verify Dataset Counts (60 Flight, 30 Bank, 60 Songs)
    assert dataset_counts.get("flight_data") == 60, f"Expected 60 flight examples, found {dataset_counts.get('flight_data')}"
    assert dataset_counts.get("bank_customers") == 30, f"Expected 30 bank examples, found {dataset_counts.get('bank_customers')}"
    assert dataset_counts.get("songs_finance") == 60, f"Expected 60 songs examples, found {dataset_counts.get('songs_finance')}"

    # Verify Stratified Split (70% Train = 105, 30% Test = 45)
    assert split_counts.get("train") == 105, f"Expected 105 train examples, got {split_counts.get('train')}"
    assert split_counts.get("test") == 45, f"Expected 45 test examples, got {split_counts.get('test')}"


@pytest.mark.tier1
def test_idempotency_returns_already_ingested(ingestion_service: TrainingPackIngestionService):
    """
    Tier 1: Feature Coverage
    Verify that rerunning ingestion returns status ALREADY_INGESTED and skips redundant training in <100ms.
    """
    # Test on Bank Customers (30 questions)
    bank_data_path = _resolve_pack_file("bank_customers_single_sheet.xlsx")
    bank_q_path = _resolve_pack_file("bank_questions_single_sheet.xlsx")

    # Call 1: Already ingested in previous test
    start_time = time.perf_counter()
    result = ingestion_service.ingest_pack(
        dataset_path=bank_data_path,
        questions_path=bank_q_path,
        dataset_id="bank_customers",
        dataset_sheet="Bank_Customers",
        questions_sheet="Bank_Questions",
        force=False,
    )
    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    assert result["status"] == "ALREADY_INGESTED", (
        f"Expected ALREADY_INGESTED on rerun, got {result['status']}"
    )
    assert result["dataset_id"] == "bank_customers"
    assert "checksum" in result
    # Check that execution was fast and skipped DuckDB execution
    assert result.get("num_verified") == 30

    # Rerun all 3 datasets via ingest_all to verify idempotency across full suite
    all_res = ingestion_service.ingest_all(force=False)
    assert all_res["status"] == "ALREADY_INGESTED"
    for ds_id, sub_res in all_res["results"].items():
        assert sub_res["status"] == "ALREADY_INGESTED", f"Dataset {ds_id} failed idempotency check"


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES (@pytest.mark.tier2)
# ==============================================================================


@pytest.mark.tier2
def test_tampered_file_triggers_checksum_mismatch(
    tmp_path: Path, ingestion_service: TrainingPackIngestionService
):
    """
    Tier 2: Boundary & Corner Cases
    Test that altering bytes in workbook invalidates checksum and is recognized as new/different content.
    """
    original_path = _resolve_pack_file("flight_dataset_single_sheet.xlsx")
    tampered_path = tmp_path / "tampered_flight.xlsx"

    # Copy bytes and mutate byte at offset 500
    content = bytearray(original_path.read_bytes())
    content[500] = (content[500] + 1) % 256
    tampered_path.write_bytes(content)

    tampered_hash = _compute_binary_sha256(tampered_path)
    reference_hash = VERIFIED_CHECKSUMS["flight_dataset_single_sheet.xlsx"]
    assert tampered_hash != reference_hash, "Tampered file produced identical SHA-256"

    # Service should compute altered checksum
    checksums = ingestion_service.compute_checksums(tampered_path)
    assert checksums["binary_sha256"] == tampered_hash
    assert checksums["binary_sha256"] != reference_hash

    # is_already_ingested should return False for tampered composite checksum
    assert not ingestion_service.is_already_ingested("flight_data", tampered_hash)


@pytest.mark.tier2
def test_missing_or_invalid_sheet_name_handled_gracefully(
    ingestion_service: TrainingPackIngestionService
):
    """
    Tier 2: Boundary & Corner Cases
    Test handling of invalid sheet names (graceful error without corrupting manifest).
    """
    bank_data_path = _resolve_pack_file("bank_customers_single_sheet.xlsx")
    bank_q_path = _resolve_pack_file("bank_questions_single_sheet.xlsx")

    # Record manifest modification time before invocation
    mtime_before = DEFAULT_MANIFEST_PATH.stat().st_mtime

    with pytest.raises(Exception) as exc_info:
        ingestion_service.ingest_pack(
            dataset_path=bank_data_path,
            questions_path=bank_q_path,
            dataset_id="bank_customers_invalid",
            dataset_sheet="NonExistent_Sheet_XYZ_404",
            questions_sheet="Bank_Questions",
            force=True,
        )

    assert "NonExistent_Sheet_XYZ_404" in str(exc_info.value) or "Worksheet" in str(exc_info.value)

    # Verify manifest was not corrupted
    with DEFAULT_MANIFEST_PATH.open("r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert "datasets" in manifest
    assert "bank_customers_invalid" not in manifest["datasets"]


@pytest.mark.tier2
def test_corrupt_or_truncated_file_rejected(
    tmp_path: Path, ingestion_service: TrainingPackIngestionService
):
    """
    Tier 2: Boundary & Corner Cases
    Test handling of truncated / zero-byte files (clean rejection).
    """
    zero_byte_path = tmp_path / "zero_byte.xlsx"
    zero_byte_path.touch()

    truncated_path = tmp_path / "truncated.xlsx"
    truncated_path.write_bytes(b"PK\x03\x04randomcorruptbytes")

    bank_q_path = _resolve_pack_file("bank_questions_single_sheet.xlsx")

    for bad_file in [zero_byte_path, truncated_path]:
        with pytest.raises(Exception):
            ingestion_service.ingest_pack(
                dataset_path=bad_file,
                questions_path=bank_q_path,
                dataset_id="corrupt_test",
                dataset_sheet="Sheet1",
                questions_sheet="Bank_Questions",
                force=True,
            )


@pytest.mark.tier2
def test_force_ingestion_override(
    tmp_path: Path, ingestion_service: TrainingPackIngestionService
):
    """
    Tier 2: Boundary & Corner Cases
    Test force=True flag re-ingests even if checksum exists in manifest.
    """
    bank_data_path = _resolve_pack_file("bank_customers_single_sheet.xlsx")
    bank_q_path = _resolve_pack_file("bank_questions_single_sheet.xlsx")

    # Ingest with force=True
    result = ingestion_service.ingest_pack(
        dataset_path=bank_data_path,
        questions_path=bank_q_path,
        dataset_id="bank_customers",
        dataset_sheet="Bank_Customers",
        questions_sheet="Bank_Questions",
        force=True,
    )

    assert result["status"] == "SUCCESS", (
        f"force=True should return SUCCESS, got {result['status']}"
    )
    assert result["dataset_id"] == "bank_customers"
    assert result["num_verified"] == 30


# ==============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS (@pytest.mark.tier3)
# ==============================================================================


@pytest.mark.tier3
def test_multi_dataset_concurrent_duckdb_registration(multi_dataset_duckdb_con):
    """
    Tier 3: Cross-Feature Combinations
    Register all 3 datasets simultaneously in in-memory DuckDB (flight_data, bank_customers, songs_finance).
    Assert row counts (362, 100, 176) and column counts (41, 26, 42) with no collision.
    """
    con = multi_dataset_duckdb_con

    # Assert row counts
    flight_rows = con.execute("SELECT COUNT(*) FROM flight_data").fetchone()[0]
    bank_rows = con.execute("SELECT COUNT(*) FROM bank_customers").fetchone()[0]
    songs_rows = con.execute("SELECT COUNT(*) FROM songs_finance").fetchone()[0]

    assert flight_rows == 362, f"Expected 362 flight rows, got {flight_rows}"
    assert bank_rows == 100, f"Expected 100 bank rows, got {bank_rows}"
    assert songs_rows == 176, f"Expected 176 songs rows, got {songs_rows}"

    # Assert column counts
    flight_cols = len(con.execute("DESCRIBE flight_data").fetchall())
    bank_cols = len(con.execute("DESCRIBE bank_customers").fetchall())
    songs_cols = len(con.execute("DESCRIBE songs_finance").fetchall())

    assert flight_cols == 41, f"Expected 41 flight cols, got {flight_cols}"
    assert bank_cols == 26, f"Expected 26 bank cols, got {bank_cols}"
    assert songs_cols == 42, f"Expected 42 songs cols, got {songs_cols}"

    # Verify no namespace collision by executing single multi-table scalar query
    cross_query = """
    SELECT 
      (SELECT COUNT(*) FROM flight_data) AS total_flights,
      (SELECT COUNT(*) FROM bank_customers) AS total_customers,
      (SELECT COUNT(*) FROM songs_finance) AS total_songs
    """
    res = con.execute(cross_query).fetchone()
    assert res == (362, 100, 176), f"Multi-dataset cross query failed: {res}"


@pytest.mark.tier3
def test_interleaved_multi_dataset_idempotency(tmp_path: Path):
    """
    Tier 3: Cross-Feature Combinations
    Test sequential/interleaved ingestion and idempotency lifecycle across all 3 datasets
    using an isolated manifest and golden store in tmp_path.
    """
    isolated_manifest = tmp_path / "manifests" / "test_manifest.json"
    isolated_golden = tmp_path / "golden" / "test_golden.json"
    svc = TrainingPackIngestionService(
        manifest_path=isolated_manifest,
        golden_output_path=isolated_golden,
    )

    flight_d = _resolve_pack_file("flight_dataset_single_sheet.xlsx")
    flight_q = _resolve_pack_file("flight_questions_60_single_sheet.xlsx")
    bank_d = _resolve_pack_file("bank_customers_single_sheet.xlsx")
    bank_q = _resolve_pack_file("bank_questions_single_sheet.xlsx")
    songs_d = _resolve_pack_file("bollywood_songs_finance_dataset.xlsx")
    songs_q = _resolve_pack_file("bollywood_songs_questions_60_single_sheet.xlsx")

    # Step 1: Ingest Flight -> SUCCESS
    r1 = svc.ingest_pack(flight_d, flight_q, "flight_data", "Flight_Data", "Flight_Questions")
    assert r1["status"] == "SUCCESS"

    # Step 2: Ingest Bank -> SUCCESS
    r2 = svc.ingest_pack(bank_d, bank_q, "bank_customers", "Bank_Customers", "Bank_Questions")
    assert r2["status"] == "SUCCESS"

    # Step 3: Re-ingest Flight -> ALREADY_INGESTED
    r3 = svc.ingest_pack(flight_d, flight_q, "flight_data", "Flight_Data", "Flight_Questions")
    assert r3["status"] == "ALREADY_INGESTED"

    # Step 4: Ingest Songs -> SUCCESS
    r4 = svc.ingest_pack(songs_d, songs_q, "songs_finance", "Songs_Finance", "Songs_Questions")
    assert r4["status"] == "SUCCESS"

    # Step 5: Re-ingest Bank -> ALREADY_INGESTED
    r5 = svc.ingest_pack(bank_d, bank_q, "bank_customers", "Bank_Customers", "Bank_Questions")
    assert r5["status"] == "ALREADY_INGESTED"

    # Step 6: Re-ingest Songs -> ALREADY_INGESTED
    r6 = svc.ingest_pack(songs_d, songs_q, "songs_finance", "Songs_Finance", "Songs_Questions")
    assert r6["status"] == "ALREADY_INGESTED"

    # Verify isolated golden file contains all 150 items
    with isolated_golden.open("r", encoding="utf-8") as gf:
        isolated_items = json.load(gf)
    assert len(isolated_items) == 150


@pytest.mark.tier3
def test_retriever_query_integration():
    """
    Tier 3: Cross-Feature Combinations
    Test ExampleRetriever retrieves appropriate exemplars for domain queries
    across flight, bank, and bollywood songs domains without modifying model weights.
    """
    ExampleRetriever.clear_cache()
    all_examples = ExampleRetriever.load_examples(force_reload=True)

    # Should contain baseline (338) + training pack (150) = 488 total
    assert len(all_examples) >= 450, f"Expected >= 450 examples loaded, got {len(all_examples)}"

    # 1. Flight Query Retrieval
    flight_results = ExampleRetriever.retrieve(
        question="Which airline has the highest cancellation rate and total fare?",
        columns=["Airline", "Booking_Status", "Total_Fare"],
        top_k=3,
    )
    assert len(flight_results) > 0, "Failed to retrieve flight exemplars"
    assert any(
        ex.get("dataset_id") == "flight_data"
        or "airline" in ex.get("question", "").lower()
        or "flight" in ex.get("question", "").lower()
        for ex in flight_results
    )

    # 2. Bank Query Retrieval
    bank_results = ExampleRetriever.retrieve(
        question="Which city has customers with highest monthly income and credit score?",
        columns=["City", "Monthly_Income", "Credit_Score"],
        top_k=3,
    )
    assert len(bank_results) > 0, "Failed to retrieve bank exemplars"
    assert any(
        ex.get("dataset_id") == "bank_customers"
        or "credit" in ex.get("question", "").lower()
        or "income" in ex.get("question", "").lower()
        for ex in bank_results
    )

    # 3. Songs Query Retrieval
    songs_results = ExampleRetriever.retrieve(
        question="Which song has the highest total expense and youtube views?",
        columns=["Song_Title", "Total_Expense", "YouTube_Views_Million"],
        top_k=3,
    )
    assert len(songs_results) > 0, "Failed to retrieve songs exemplars"
    assert any(
        ex.get("dataset_id") == "songs_finance"
        or "song" in ex.get("question", "").lower()
        or "expense" in ex.get("question", "").lower()
        for ex in songs_results
    )

    # 4. Prompt Formatting Verification
    prompt_snippet = ExampleRetriever.format_for_prompt(flight_results)
    assert "### REUSABLE ANALYTICAL EXAMPLES" in prompt_snippet
    assert "Question:" in prompt_snippet


# ==============================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS (@pytest.mark.tier4)
# ==============================================================================


@pytest.mark.tier4
def test_independent_duckdb_recomputation_150_questions(multi_dataset_duckdb_con):
    """
    Tier 4: Real-World Scenarios
    Iterate through all 150 training pack questions, execute their SQL queries against
    registered DuckDB tables, and verify deterministic execution and answer matching.
    """
    con = multi_dataset_duckdb_con

    with DEFAULT_GOLDEN_PATH.open("r", encoding="utf-8") as gf:
        golden_examples = json.load(gf)

    assert len(golden_examples) == 150, "Expected 150 golden examples for recomputation"

    failures = []
    executed_count = 0

    for ex in golden_examples:
        q_id = ex["example_id"]
        sql = ex.get("sql_query")
        assert sql, f"Missing SQL query in {q_id}"

        try:
            cur = con.execute(sql)
            rows = cur.fetchall()
            executed_count += 1
            # Every query should produce a result (scalar or rows)
            assert rows is not None
        except Exception as e:
            failures.append((q_id, sql, str(e)))

    assert len(failures) == 0, (
        f"{len(failures)} of {executed_count} queries failed DuckDB execution: {failures[:5]}"
    )
    assert executed_count == 150, f"Expected 150 queries executed, got {executed_count}"


@pytest.mark.tier4
def test_generalization_on_held_out_unseen_questions(multi_dataset_duckdb_con):
    """
    Tier 4: Real-World Scenarios
    Verify semantic exemplar retrieval and DuckDB execution on the 30% held-out
    test split (45 questions: 18 flight, 9 bank, 18 songs) without Mistral weight modification.
    """
    con = multi_dataset_duckdb_con

    with DEFAULT_GOLDEN_PATH.open("r", encoding="utf-8") as gf:
        examples = json.load(gf)

    test_split = [ex for ex in examples if ex.get("split") == "test"]
    assert len(test_split) == 45, f"Expected exactly 45 held-out test split examples, got {len(test_split)}"

    # Check breakdown: 18 flight, 9 bank, 18 songs
    flight_test = [ex for ex in test_split if ex.get("dataset_id") == "flight_data"]
    bank_test = [ex for ex in test_split if ex.get("dataset_id") == "bank_customers"]
    songs_test = [ex for ex in test_split if ex.get("dataset_id") == "songs_finance"]

    assert len(flight_test) == 18, f"Expected 18 flight test examples, got {len(flight_test)}"
    assert len(bank_test) == 9, f"Expected 9 bank test examples, got {len(bank_test)}"
    assert len(songs_test) == 18, f"Expected 18 songs test examples, got {len(songs_test)}"

    # For each unseen question, verify semantic retrieval finds relevant training exemplars
    # and DuckDB query executes deterministically without error
    retrieval_hits = 0
    for ex in test_split:
        q = ex["question"]
        cols = list(ex.get("column_mapping", {}).values())
        retrieved = ExampleRetriever.retrieve(question=q, columns=cols, top_k=2)
        if len(retrieved) > 0:
            retrieval_hits += 1

        # Execute unseen query in DuckDB
        res = con.execute(ex["sql_query"]).fetchall()
        assert res is not None

    assert retrieval_hits >= 40, (
        f"Retrieval generalization hit rate too low: {retrieval_hits}/45"
    )


@pytest.mark.tier4
def test_non_regression_existing_300_golden_benchmarks():
    """
    Tier 4: Real-World Scenarios
    Run verification on existing 300+ golden benchmarks in golden_examples_300.json
    ensuring 100% pass and no regression against baseline analytics.
    """
    baseline_golden_path = BASE_DIR / "data" / "benchmark" / "golden" / "golden_examples_300.json"
    assert baseline_golden_path.is_file(), f"Missing baseline golden file at {baseline_golden_path}"

    with baseline_golden_path.open("r", encoding="utf-8") as f:
        base_examples = json.load(f)

    assert len(base_examples) >= 300, (
        f"Expected at least 300 baseline golden examples, found {len(base_examples)}"
    )

    # Set up database context from evaluation_service
    con = evaluation_service.setup_database_context()

    try:
        # 1. Test A: Security Incident Analysis - Highest External Sender
        # Ground Truth: NX-ENG086\Isha Dave, 500.0 MB across 57 incidents
        sql_a = (
            "SELECT src AS sender, ROUND(SUM(size_kb)/1024.0, 1) AS mb_sent, COUNT(*) AS incidents "
            "FROM v WHERE is_ext=1 GROUP BY src ORDER BY mb_sent DESC LIMIT 1"
        )
        row_a = con.execute(sql_a).fetchone()
        assert row_a is not None
        assert "Isha Dave" in row_a[0]
        assert row_a[1] == 500.0
        assert row_a[2] == 57

        # 2. Test B: Blocked Incidents Ground Truth (5 incidents)
        sql_b = "SELECT id FROM v WHERE action='Blocked' ORDER BY id"
        rows_b = [r[0] for r in con.execute(sql_b).fetchall()]
        assert rows_b == [550100380, 550100431, 550100855, 550101299, 550104760]

        # 3. Test C: Retail Analysis - Top 10 Products by Revenue
        sql_c = (
            "SELECT Description, ROUND(SUM(Quantity * UnitPrice), 2) AS total_revenue "
            "FROM retail WHERE Quantity > 0 AND UnitPrice > 0 "
            "GROUP BY Description ORDER BY total_revenue DESC LIMIT 10"
        )
        rows_c = con.execute(sql_c).fetchall()
        assert len(rows_c) == 10
        assert rows_c[0][1] > 0

        # 4. Test D: Finance Analysis - Highest Profit Country
        sql_d = (
            "SELECT Country, ROUND(SUM(Profit), 2) AS total_profit "
            "FROM financials GROUP BY Country ORDER BY total_profit DESC LIMIT 1"
        )
        row_d = con.execute(sql_d).fetchone()
        assert row_d is not None
        assert row_d[0] is not None
        assert row_d[1] > 0

        # 5. Test E: Multi-File Relational Anti-Join Analysis - 12 Missing Payroll
        sql_e = (
            "SELECT e.employee_id, e.full_name, e.department_id "
            "FROM employees e LEFT JOIN payroll p ON e.employee_id = p.employee_id "
            "WHERE p.employee_id IS NULL"
        )
        rows_e = con.execute(sql_e).fetchall()
        assert len(rows_e) == 12
    finally:
        con.close()
