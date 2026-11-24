import json

from backend.scripts.audit_benchmark import audit


def test_benchmark_audit_reports_metadata_gaps(tmp_path):
    dataset = tmp_path / "dataset.csv"
    dataset.write_text("a\n1\n", encoding="utf-8")
    import hashlib
    checksum = hashlib.sha256(dataset.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"datasets": [{"source_name": "fixture", "file_path": str(dataset), "checksum_sha256": checksum}]}), encoding="utf-8")
    golden = tmp_path / "golden.json"
    golden.write_text(json.dumps([{
        "example_id": "e1", "dataset_id": "d", "dataset_checksum": checksum,
        "question": "count", "language": "english", "intent": "count", "column_mapping": {},
        "expected_plan": {}, "expected_answer": {}, "verification": {"status": "verified"},
        "source_type": "synthetic", "approval_status": "approved", "split": "test", "evidence_ids": [],
    }]), encoding="utf-8")
    report = audit(manifest, golden)
    assert report["all_dataset_checksums_valid"] is True
    assert report["approved_example_count"] == 1
    assert report["evidence_coverage"] == 0.0
