"""Audit Phase 2 provenance, separation, and benchmark leakage boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from contract import expand_questions


ROOT = Path(__file__).resolve().parents[3]
QUESTIONS = Path(__file__).with_name("questions.json")
GROUND_TRUTH = Path(__file__).with_name("ground_truth.json")
MANIFEST = Path(__file__).with_name("phase2_manifest.json")


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def audit() -> dict[str, Any]:
    question_payload = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    questions = expand_questions(question_payload)
    answer_payload = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    answers = answer_payload.get("answers", [])
    answer_ids = {item.get("q_id") for item in answers}
    base_ids = {item.get("base_q_id") for item in questions}
    forbidden_question_keys = {"sql", "expected_answer", "expected_value", "answer"}
    questions_clean = all(not (forbidden_question_keys & set(item)) for item in questions)

    datasets = []
    for item in json.loads(MANIFEST.read_text(encoding="utf-8"))["datasets"]:
        path = ROOT / item["path"]
        exists = path.is_file()
        actual = checksum(path) if exists else None
        datasets.append({
            "dataset_id": item["dataset_id"],
            "path": item["path"],
            "exists": exists,
            "checksum_ok": exists and actual == item["checksum_sha256"].lower(),
            "approval_status": item.get("approval_status"),
        })

    return {
        "corpus_version": question_payload.get("corpus_version"),
        "question_count": len(questions),
        "base_question_count": len(base_ids),
        "unique_question_ids": len({item["q_id"] for item in questions}) == len(questions),
        "answers_separate": question_payload.get("answers_separate") is True,
        "ground_truth_sealed": answer_payload.get("sealed") is True,
        "question_file_has_no_answers": questions_clean,
        "answer_keys_cover_base_questions": answer_ids == base_ids,
        "datasets": datasets,
        "all_datasets_present": all(item["exists"] for item in datasets),
        "all_checksums_valid": all(item["checksum_ok"] for item in datasets),
        "external_provider_called": False,
        "model_training": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/benchmark/reports/phase2_curation_audit.json")
    args = parser.parse_args()
    report = audit()
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    required = (
        report["unique_question_ids"]
        and report["answers_separate"]
        and report["ground_truth_sealed"]
        and report["question_file_has_no_answers"]
        and report["answer_keys_cover_base_questions"]
        and report["all_datasets_present"]
        and report["all_checksums_valid"]
    )
    return 0 if required else 1


if __name__ == "__main__":
    raise SystemExit(main())
