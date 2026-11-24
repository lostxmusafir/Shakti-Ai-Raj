"""Audit benchmark provenance and golden-example completeness."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit(manifest_path: str | Path, golden_path: str | Path) -> Dict[str, Any]:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    examples = json.loads(Path(golden_path).read_text(encoding="utf-8"))
    datasets: List[Dict[str, Any]] = []
    for dataset in manifest.get("datasets", []):
        path = Path(dataset["file_path"])
        exists = path.is_file()
        checksum_ok = exists and sha256(path) == dataset.get("checksum_sha256")
        datasets.append({
            "source_name": dataset.get("source_name"),
            "dataset_id": dataset.get("dataset_id", dataset.get("source_name")),
            "exists": exists,
            "checksum_ok": checksum_ok,
            "row_count": dataset.get("row_count"),
            "column_count": dataset.get("column_count"),
            "approval_status": dataset.get("approval_status"),
        })
    required = {"example_id", "dataset_id", "dataset_checksum", "question", "language", "intent", "column_mapping", "expected_plan", "expected_answer", "verification", "source_type", "approval_status", "split"}
    complete = [example for example in examples if required <= set(example)]
    verified = [example for example in complete if example.get("verification", {}).get("status") == "verified"]
    approved = [example for example in complete if example.get("approval_status") == "approved"]
    return {
        "dataset_count": len(datasets),
        "datasets": datasets,
        "golden_example_count": len(examples),
        "complete_example_count": len(complete),
        "verified_example_count": len(verified),
        "approved_example_count": len(approved),
        "split_counts": {split: sum(example.get("split") == split for example in approved) for split in ("train", "val", "test")},
        "source_type_counts": {source: sum(example.get("source_type") == source for example in approved) for source in ("public", "synthetic", "private_tenant")},
        "evidence_coverage": sum(bool(example.get("evidence_ids")) for example in approved) / len(approved) if approved else 0.0,
        "missing_evidence_examples": [example.get("example_id") for example in approved if not example.get("evidence_ids")][:20],
        "all_dataset_files_present": all(dataset["exists"] for dataset in datasets),
        "all_dataset_checksums_valid": all(dataset["checksum_ok"] for dataset in datasets),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/benchmark/manifests/dataset_manifest.json")
    parser.add_argument("--golden", default="data/benchmark/golden/golden_examples_300.json")
    parser.add_argument("--output", default="data/benchmark/reports/benchmark_audit.json")
    args = parser.parse_args()
    report = audit(args.manifest, args.golden)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["all_dataset_files_present"] and report["all_dataset_checksums_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
