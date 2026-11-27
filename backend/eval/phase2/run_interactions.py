"""Run the small Phase 2 human-in-the-loop safety corpus."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from app.ai.orchestration.ambiguity import AmbiguityDetector
from app.analysis.profiling.profiler import DataProfiler
from app.models.file import StoredFile


ROOT = Path(__file__).resolve().parents[3]
QUESTIONS = Path(__file__).with_name("interaction_questions.json")
REPORT = ROOT / "data/benchmark/reports/phase2_hitl_report.json"


def stored_file(path: str) -> StoredFile:
    profile = DataProfiler.profile_file(path, Path(path).name)
    return StoredFile(
        id="hitl_fixture",
        owner_user_id="phase2-benchmark",
        unit_id="default_unit",
        original_name=Path(path).name,
        content_type="text/csv",
        size_bytes=Path(path).stat().st_size,
        storage_key=Path(path).name,
        status="ready",
        schema_profile=profile,
    )


def main() -> int:
    fixture = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
    try:
        fixture.write(
            "id,Transaction Amount,Claim Amount,invoice_date,payment_date,Debit,Credit\n"
            "1,100,50,2026-10-01,2026-10-02,10,\n"
            "2,200,75,2026-10-05,2026-10-06,,20\n"
        )
        fixture.close()
        files = {"hitl_fixture": stored_file(fixture.name)}
        cases = json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
        passed = 0
        results = []
        for case in cases:
            interrupt = AmbiguityDetector.detect(case["question"], files)
            actual = interrupt.get("reason") if interrupt else None
            ok = actual == case["expected_reason"]
            print(f"{'PASS' if ok else 'FAIL'} {case['q_id']}: {actual}")
            results.append({
                "q_id": case["q_id"],
                "question": case["question"],
                "expected_reason": case["expected_reason"],
                "actual_reason": actual,
                "passed": ok,
            })
            passed += int(ok)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps({
            "corpus_version": "phase2-interactions-1.0",
            "model_training": False,
            "external_provider_called": False,
            "total": len(cases),
            "passed": passed,
            "failed": len(cases) - passed,
            "results": results,
        }, indent=2) + "\n", encoding="utf-8")
        print(f"Phase 2 HITL safety: {passed}/{len(cases)} passed")
        return 0 if passed == len(cases) else 1
    finally:
        try:
            os.unlink(fixture.name)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
