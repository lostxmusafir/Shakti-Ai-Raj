"""Structural and integrity tests for the blind public-internet evaluation.

These tests never download data and never call a model. They verify that the
corpus is complete, that the answer key is sealed and separate, and that the
stored ground-truth computation is reproducible and free of errors.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "backend"))

from eval.internet.catalog import CATALOG  # noqa: E402
EVAL_DIR = BASE / "backend" / "eval" / "internet"
DATA_DIR = BASE / "data" / "benchmark" / "internet"


def _load(name: str) -> dict:
    return json.loads((EVAL_DIR / name).read_text(encoding="utf-8"))


def test_catalog_has_thirty_unique_datasets_across_categories():
    assert len(CATALOG) == 30
    assert len({item.dataset_id for item in CATALOG}) == 30
    assert len({item.test_id for item in CATALOG}) == 30
    assert len({item.category for item in CATALOG}) >= 8
    for item in CATALOG:
        assert item.source_url.startswith("https://"), item.dataset_id
        assert item.license_or_terms, item.dataset_id


def test_questions_cover_every_dataset_and_minimum_volume():
    questions = _load("questions.json")["questions"]
    assert len(questions) >= 150
    dataset_ids = {item["dataset_id"] for item in questions}
    assert dataset_ids == {item.dataset_id for item in CATALOG}
    per_dataset = {}
    for item in questions:
        per_dataset[item["dataset_id"]] = per_dataset.get(item["dataset_id"], 0) + 1
    assert min(per_dataset.values()) >= 5


def test_questions_span_languages_and_difficulties():
    questions = _load("questions.json")["questions"]
    assert {item["language"] for item in questions} >= {"english", "hinglish", "hindi", "shorthand"}
    assert {item["difficulty"] for item in questions} >= {"simple", "medium", "hard", "ambiguous", "followup"}
    followups = [item for item in questions if item["difficulty"] == "followup"]
    conversations = {item["conversation_id"] for item in followups}
    assert len(conversations) >= 10
    for conversation in conversations:
        turns = [item for item in questions if item["conversation_id"] == conversation]
        assert len(turns) >= 3
        assert sorted(item["turn_index"] for item in turns) == list(range(1, len(turns) + 1))


def test_question_file_contains_no_answers_or_sql():
    questions = _load("questions.json")["questions"]
    for item in questions:
        assert "sql" not in item
        assert "expected_sql" not in item
        assert "answer" not in item


def test_answer_key_is_sealed_and_complete():
    questions = {item["q_id"] for item in _load("questions.json")["questions"]}
    key = _load("ground_truth.json")
    assert key.get("sealed") is True
    answers = {item["q_id"] for item in key["answers"]}
    assert answers == questions
    for answer in key["answers"]:
        if answer.get("needs_clarification"):
            assert answer["sql"] is None
        else:
            assert answer["sql"].strip().lower().startswith(("select", "with"))
            assert "data" in answer["sql"].lower()


@pytest.mark.skipif(not (DATA_DIR / "manifest.json").exists(), reason="datasets not acquired in this environment")
def test_manifest_records_provenance_for_all_datasets():
    manifest = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dataset_count"] == 30
    assert len(manifest["datasets"]) == 30
    required = {
        "test_id", "source", "dataset_name", "source_url", "license_or_terms",
        "download_timestamp", "sha256", "original_rows", "test_sample_rows",
        "columns", "sample_method", "random_seed",
    }
    for record in manifest["datasets"]:
        assert required <= set(record), record["dataset_id"]
        assert len(record["sha256"]) == 64
        assert record["random_seed"] == 42


@pytest.mark.skipif(not (DATA_DIR / "ground_truth_results.json").exists(), reason="ground truth not computed")
def test_ground_truth_computation_is_clean():
    payload = json.loads((DATA_DIR / "ground_truth_results.json").read_text(encoding="utf-8"))
    assert payload["failures"] == []
    assert len(payload["results"]) == 180


@pytest.mark.skipif(not (DATA_DIR / "samples").exists(), reason="dataset samples not present")
def test_independent_recomputation_matches_duckdb():
    from eval.internet.independent import run_independent_checks

    report = run_independent_checks()
    assert report["total"] >= 25
    assert report["matched"] == report["total"], [
        item for item in report["checks"] if item["status"] != "match"
    ]


@pytest.mark.skipif(not (DATA_DIR / "blind_run_planner.json").exists(), reason="blind run not executed")
def test_blind_run_has_no_retrieval_contamination_and_no_dataset_hacks():
    payload = json.loads((DATA_DIR / "blind_run_planner.json").read_text(encoding="utf-8"))
    assert payload["retrieval_integrity"]["blind_questions_found_in_retrieval"] == 0
    assert payload["production_code_changed_for_dataset"] is False
    assert payload["summary"]["total_questions"] == 180
