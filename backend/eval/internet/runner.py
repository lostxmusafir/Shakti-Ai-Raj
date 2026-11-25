"""Blind internet-data evaluation runner.

Modes
-----
``planner``
    Each natural-language question is sent through the production planning and
    analysis pipeline. This is the primary generalisation measurement.
``reference``
    Each hand-written ground-truth SQL is executed through the production
    DuckDB engine + verifier. This checks that the deterministic execution layer
    is portable across all 30 unseen schemas. It is not an NLU measurement.

Neither mode writes anything into the golden/retrieval store.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ground_truth import RESULTS_PATH, load_key, load_questions, sample_path
from .independent import run_independent_checks
from .scoring import score_question
from .system_under_test import SystemUnderTest, provider_description

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data" / "benchmark" / "internet"
REPORT_DIR = ROOT / "data" / "benchmark" / "reports"
DIMENSIONS = [
    "intent_understanding",
    "schema_mapping",
    "filter_accuracy",
    "aggregation_accuracy",
    "result_shape_accuracy",
    "sql_execution",
    "numerical_correctness",
    "semantic_verification",
    "answer_relevance",
    "human_readability",
]


def _pct(part: int, total: int) -> float:
    return round(100.0 * part / total, 2) if total else 0.0


def _summarise(scored: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(scored)
    dimensions = {}
    measured_counts = {}
    for dimension in DIMENSIONS:
        measured = [item for item in scored if item["dimensions"].get(dimension) is not None]
        dimensions[dimension] = _pct(sum(1 for item in measured if item["dimensions"].get(dimension)), len(measured)) if measured else None
        measured_counts[dimension] = len(measured)
    failures = Counter(failure for item in scored for failure in item["failures"])
    by_language: dict[str, dict[str, Any]] = defaultdict(lambda: {"total": 0, "numerical": 0})
    by_difficulty: dict[str, dict[str, Any]] = defaultdict(lambda: {"total": 0, "numerical": 0})
    by_dataset: dict[str, dict[str, Any]] = defaultdict(lambda: {"total": 0, "numerical": 0, "intent": 0})
    for item in scored:
        for bucket, key in ((by_language, item["language"]), (by_difficulty, item["difficulty"]), (by_dataset, item["dataset_id"])):
            bucket[key]["total"] += 1
            bucket[key]["numerical"] += int(item["dimensions"]["numerical_correctness"])
            if bucket is by_dataset:
                bucket[key]["intent"] += int(item["dimensions"]["intent_understanding"])
    null_items = [item for item in scored if item["null_sensitive"]]
    followups = [item for item in scored if item["followup"]]
    return {
        "total_questions": total,
        "dimensions": dimensions,
        "dimensions_measured": measured_counts,
        "failures": dict(failures),
        "false_verification_passes": sum(1 for item in scored if "FALSE_VERIFICATION_PASS" in item["failures"]),
        "by_language": {
            key: {**value, "numerical_pct": _pct(value["numerical"], value["total"])}
            for key, value in sorted(by_language.items())
        },
        "by_difficulty": {
            key: {**value, "numerical_pct": _pct(value["numerical"], value["total"])}
            for key, value in sorted(by_difficulty.items())
        },
        "by_dataset": {
            key: {
                **value,
                "numerical_pct": _pct(value["numerical"], value["total"]),
                "intent_pct": _pct(value["intent"], value["total"]),
            }
            for key, value in sorted(by_dataset.items())
        },
        "null_and_sparse": {
            "total": len(null_items),
            "numerical_pct": _pct(sum(1 for item in null_items if item["dimensions"]["numerical_correctness"]), len(null_items)),
            "execution_pct": _pct(sum(1 for item in null_items if item["dimensions"]["sql_execution"]), len(null_items)),
        },
        "followups": {
            "total": len(followups),
            "numerical_pct": _pct(sum(1 for item in followups if item["dimensions"]["numerical_correctness"]), len(followups)),
            "context_failures": sum(1 for item in followups if "FOLLOWUP_CONTEXT_ERROR" in item["failures"]),
        },
    }


def run(mode: str, limit: int | None = None) -> dict[str, Any]:
    questions = load_questions()["questions"]
    answers = {item["q_id"]: item for item in load_key()["answers"]}
    expected_results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))["results"]
    manifest = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
    dataset_sources = {item["dataset_id"]: item["source"] for item in manifest["datasets"]}

    system = SystemUnderTest()
    scored: list[dict[str, Any]] = []
    skipped = 0
    selected = questions[:limit] if limit else questions
    for index, question in enumerate(selected, start=1):
        path = str(sample_path(question["dataset_id"]))
        answer = answers[question["q_id"]]
        if mode == "reference" and not answer.get("sql"):
            # Clarification questions have no executable reference SQL; the
            # reference mode measures the execution layer, not clarification.
            skipped += 1
            continue
        expected = expected_results[question["q_id"]]
        if mode == "reference":
            actual = system.run_reference_sql(path, f"{question['dataset_id']}.csv", question["question"], answer["sql"])
        else:
            actual = system.run_question(path, f"{question['dataset_id']}.csv", question["question"])
        item = score_question(question, expected, actual, mode=mode)
        item["expected_answer"] = {"columns": expected.get("columns"), "rows": expected.get("rows")}
        item["answer_text"] = (actual.get("answer") or "")[:1500]
        scored.append(item)
        if index % 20 == 0:
            print(f"  {index}/{len(selected)} questions scored")

    summary = _summarise(scored)
    payload = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": mode,
        "skipped_non_executable": skipped,
        "planner": {**provider_description(), "effective_provider_class": system.provider_class},
        "dataset_sources": dataset_sources,
        "production_code_changed_for_dataset": False,
        "dataset_cases": [
            {
                "test_id": item["test_id"],
                "dataset_id": item["dataset_id"],
                "production_code_changed_for_dataset": False,
            }
            for item in manifest["datasets"]
        ],
        "retrieval_integrity": system.retrieval_contamination_report(),
        "independent_ground_truth_checks": run_independent_checks(),
        "summary": summary,
        "results": scored,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    target = DATA_DIR / f"blind_run_{mode}.json"
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def print_summary(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    print(f"\nmode={payload['mode']} planner={payload['planner']['planner_mode']} questions={summary['total_questions']}")
    for dimension, value in summary["dimensions"].items():
        print(f"  {dimension:24s} " + ("not measured" if value is None else f"{value:6.2f}%"))
    print(f"  false verification passes: {summary['false_verification_passes']}")
    print(f"  null/sparse numerical: {summary['null_and_sparse']['numerical_pct']}% of {summary['null_and_sparse']['total']}")
    print(f"  follow-up numerical: {summary['followups']['numerical_pct']}% of {summary['followups']['total']}")
    if summary["failures"]:
        print("  failures:", summary["failures"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["planner", "reference"], default="planner")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    payload = run(args.mode, args.limit)
    print_summary(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
