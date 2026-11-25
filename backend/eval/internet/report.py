"""Render the blind internet-data evaluation results as a Markdown report."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data" / "benchmark" / "internet"
REPORTS_DIR = ROOT / "data" / "benchmark" / "reports"


def _fmt(value: Any) -> str:
    if value is None:
        return "not measured"
    return f"{value:.2f}%"


def _table(rows: list[list[Any]], headers: list[str]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def render(planner_run: dict[str, Any] | None, reference_run: dict[str, Any] | None) -> str:
    manifest = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
    questions = json.loads((Path(__file__).resolve().parent / "questions.json").read_text(encoding="utf-8"))["questions"]
    key = json.loads((Path(__file__).resolve().parent / "ground_truth.json").read_text(encoding="utf-8"))["answers"]

    languages = Counter(item["language"] for item in questions)
    difficulties = Counter(item["difficulty"] for item in questions)
    conversations = {item["conversation_id"] for item in questions if item.get("conversation_id")}
    datasets_with_questions = {item["dataset_id"] for item in questions}
    ambiguous = [item for item in questions if item.get("needs_clarification")]
    null_sensitive = [item for item in planner_run["results"] if item["null_sensitive"]] if planner_run else []

    lines: list[str] = []
    lines.append("# Blind Public-Internet Dataset Evaluation")
    lines.append("")
    lines.append(f"Datasets loaded: **{manifest['dataset_count']} / 30**")
    lines.append("")
    lines.append(f"Human-style questions: **{len(questions)}** (minimum required 150)")
    lines.append("")
    lines.append(
        f"Datasets with questions: {len(datasets_with_questions)} / 30 · "
        f"Multi-turn conversations: {len(conversations)} (minimum 10) · "
        f"Ambiguous questions: {len(ambiguous)}"
    )
    lines.append("")
    lines.append("## Corpus composition")
    lines.append("")
    lines.append(_table([[k, v] for k, v in sorted(languages.items())], ["Language", "Questions"]))
    lines.append("")
    lines.append(_table([[k, v] for k, v in sorted(difficulties.items())], ["Difficulty", "Questions"]))
    lines.append("")
    lines.append("## Measured accuracy")
    lines.append("")
    if planner_run:
        planner = planner_run["summary"]
        rows = [[dimension, _fmt(value)] for dimension, value in planner["dimensions"].items()]
        lines.append(_table(rows, ["Dimension", "Planner mode"]))
        lines.append("")
        lines.append(
            f"Planner mode: **{planner_run['planner']['planner_mode']}** "
            f"({planner_run['planner']['provider_class']}). {planner_run['planner'].get('note', '')}"
        )
    if reference_run:
        reference = reference_run["summary"]
        lines.append("")
        lines.append(
            "Execution-layer reference mode (ground-truth SQL executed through the production "
            f"engine + verifier; {reference['total_questions']} executable questions):"
        )
        lines.append("")
        lines.append(_table([[d, _fmt(reference['dimensions'][d])] for d in reference["dimensions"]], ["Dimension", "Reference mode"]))
    lines.append("")
    lines.append("## Null, sparse and zero-heavy data")
    lines.append("")
    if planner_run:
        lines.append(
            f"Null-sensitive questions: **{planner_run['summary']['null_and_sparse']['total']}** · "
            f"numerical accuracy {_fmt(planner_run['summary']['null_and_sparse']['numerical_pct'])} · "
            f"execution {_fmt(planner_run['summary']['null_and_sparse']['execution_pct'])}"
        )
        lines.append("")
        lines.append(_table(
            [[item["q_id"], item["actual_measure"], item["expected_measure"],
              "yes" if item["dimensions"]["numerical_correctness"] else "no"] for item in null_sensitive],
            ["Question", "System value", "Expected value", "Correct"],
        ))
    lines.append("")
    lines.append("## Failure taxonomy")
    lines.append("")
    if planner_run:
        failures = planner_run["summary"]["failures"]
        lines.append(_table([[k, v] for k, v in sorted(failures.items(), key=lambda kv: -kv[1])], ["Failure type", "Count"]))
        lines.append("")
        lines.append(f"False verification passes: **{planner_run['summary']['false_verification_passes']}**")
    lines.append("")
    lines.append("## Per-dataset results (planner mode)")
    lines.append("")
    if planner_run:
        rows = []
        for dataset_id, stats in planner_run["summary"]["by_dataset"].items():
            rows.append([dataset_id, stats["total"], _fmt(stats["intent_pct"]), _fmt(stats["numerical_pct"])])
        lines.append(_table(rows, ["Dataset", "Questions", "Intent", "Numerical"]))
    lines.append("")
    lines.append("## Guardrails")
    lines.append("")
    if planner_run:
        integrity = planner_run["retrieval_integrity"]
        lines.append(f"- Blind questions found in the retrieval/golden store: **{integrity['blind_questions_found_in_retrieval']}**")
        lines.append(f"- Retrieval store size: {integrity['retrieval_store_size']}")
        lines.append(f"- production_code_changed_for_dataset: **{str(planner_run['production_code_changed_for_dataset']).lower()}**")
        independent = planner_run["independent_ground_truth_checks"]
        lines.append(f"- Independent Pandas recomputation of difficult/null cases: **{independent['matched']}/{independent['total']}** match")
    if reference_run:
        cte_failures = [
            item for item in reference_run["results"]
            if item.get("error") and "Unauthorized table reference" in item["error"]
        ]
        lines.append(
            f"- Reference-mode execution failures: **{len(cte_failures)}** — all are CTE (`WITH`) queries "
            "rejected by the production `SQLSanitizer`, which does not resolve CTE names to dataset aliases."
        )
    lines.append("")
    lines.append("## Datasets")
    lines.append("")
    lines.append(_table(
        [[item["test_id"], item["dataset_id"], item["source"], item["original_rows"], item["test_sample_rows"],
          item["license_or_terms"].split(";")[0]] for item in manifest["datasets"]],
        ["Test", "Dataset", "Source", "Original rows", "Sample rows", "License"],
    ))
    lines.append("")
    lines.append("## Answer key")
    lines.append("")
    lines.append(f"Sealed ground-truth answers: {len(key)} (stored separately from the questions; never given to the planner).")
    return "\n".join(lines) + "\n"


def main() -> int:
    planner_path = DATA_DIR / "blind_run_planner.json"
    reference_path = DATA_DIR / "blind_run_reference.json"
    planner = json.loads(planner_path.read_text(encoding="utf-8")) if planner_path.exists() else None
    reference = json.loads(reference_path.read_text(encoding="utf-8")) if reference_path.exists() else None
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    target = REPORTS_DIR / "internet_blind_eval.md"
    target.write_text(render(planner, reference), encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
