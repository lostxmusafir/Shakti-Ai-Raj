import os
import pytest
from app.core.config import settings
from app.models.file import StoredFile
from app.models.analysis import AnalysisRun
from app.ai.orchestration.context import AIContext
from app.ai.orchestration.orchestrator import orchestrator
from app.analysis.profiling.profiler import DataProfiler
from app.db.repository import BaseRepository
from app.storage.local import storage_service

@pytest.mark.asyncio
async def test_nexus_dynamics_10_qa_benchmark(tmp_path, monkeypatch):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    ckpt_db = tmp_path / "nexus_checkpoints.sqlite"

    await orchestrator.workflow.close()
    monkeypatch.setattr(settings, "STORAGE_DIR", str(uploads_dir))
    monkeypatch.setattr(storage_service, "base_dir", os.path.abspath(str(uploads_dir)))
    monkeypatch.setattr(orchestrator.workflow, "_db_path", str(ckpt_db))

    file_repo = BaseRepository("files", StoredFile)
    analysis_repo = BaseRepository("analysis_runs", AnalysisRun)
    
    csv_path = os.path.abspath("data/samples/NexusDynamics_Incidents_5000.csv")
    assert os.path.exists(csv_path), "NexusDynamics_Incidents_5000.csv must exist in data/samples/"
    
    # Profile file
    profile = DataProfiler.profile_file(csv_path, "NexusDynamics_Incidents_5000.csv")
    assert profile["row_count"] == 5000
    
    with open(csv_path, "rb") as f:
        storage_key = await storage_service.save_file("NexusDynamics_Incidents_5000.csv", f.read())

    # Register file in repository
    stored_file = StoredFile(
        id="nexus_5000_test_file",
        owner_user_id="test_admin",
        unit_id="test_unit",
        original_name="NexusDynamics_Incidents_5000.csv",
        storage_key=storage_key,
        size_bytes=os.path.getsize(csv_path),
        content_type="text/csv",
        status="ready",
        schema_profile=profile
    )
    await file_repo.create(stored_file)
    
    ctx = AIContext(
        user_id="test_admin",
        unit_id="test_unit",
        role="super_admin",
        chat_id="test_chat",
        file_ids=[stored_file.id]
    )

    qa_test_cases = [
        {
            "q": "Total kitne incidents hain, total data kitna (GB), aur kitne me external recipient hai?",
            "check": lambda res: (
                res["result"]["rows"][0]["total_incidents"] == 5000 and
                float(res["result"]["rows"][0]["total_gb"]) == 15.88 and
                res["result"]["rows"][0]["external_incidents"] == 1158
            ),
            "expected_tokens": ["5,000", "15.88", "1,158"]
        },
        {
            "q": "Internal vs external split kya hai (incidents aur external MB)?",
            "check": lambda res: (
                len(res["result"]["rows"]) == 2 and
                res["result"]["rows"][0]["incidents"] == 3842 and
                res["result"]["rows"][1]["incidents"] == 1158 and
                float(res["result"]["rows"][1]["data_mb"]) == 4297.3
            ),
            "expected_tokens": ["3,842", "1,158", "4,297.3"]
        },
        {
            "q": "Bahar sabse zyada data kisne bheja",
            "check": lambda res: (
                "Isha Dave" in res["result"]["rows"][0]["sender"] and
                float(res["result"]["rows"][0]["mb_sent"]) == 500.0 and
                res["result"]["rows"][0]["incidents"] == 57
            ),
            "expected_tokens": ["Isha Dave", "500"]
        },
        {
            "q": "Personal Gmail par kya gaya aur kitna MB?",
            "check": lambda res: (
                res["result"]["rows"][0]["incidents"] == 244 and
                float(res["result"]["rows"][0]["data_mb"]) == 968.9
            ),
            "expected_tokens": ["244", "968.9"]
        },
        {
            "q": "Kitne incidents Blocked hue? Unke Incident IDs batao.",
            "check": lambda res: (
                len(res["result"]["rows"]) == 5 and
                [r["id"] for r in res["result"]["rows"]] == [550100380, 550100431, 550100855, 550101299, 550104760]
            ),
            "expected_tokens": ["550100380", "550100431"]
        },
        {
            "q": "Sabse bada external transfer kaunsa hai (ID, sender, file, size)?",
            "check": lambda res: (
                res["result"]["rows"][0]["id"] == 550102592 and
                "Chirag Mishra" in res["result"]["rows"][0]["sender"] and
                float(res["result"]["rows"][0]["size_kb"]) == 25000.0
            ),
            "expected_tokens": ["550102592", "Chirag Mishra"]
        },
        {
            "q": "Password files external gayi",
            "check": lambda res: res["result"]["rows"][0]["password_files_external"] == 64,
            "expected_tokens": ["64"]
        },
        {
            "q": "CAD blueprints external me kitne gaye aur kitna MB?",
            "check": lambda res: (
                res["result"]["rows"][0]["cad_incidents"] == 124 and
                float(res["result"]["rows"][0]["data_mb"]) == 1180.9
            ),
            "expected_tokens": ["124", "1,180.9"]
        },
        {
            "q": "Din ka peak hour kaunsa hai?",
            "check": lambda res: (
                res["result"]["rows"][0]["peak_hour"] == 11 and
                res["result"]["rows"][0]["incident_count"] == 649
            ),
            "expected_tokens": ["11", "649"]
        },
        {
            "q": "High severity ke kitne incidents personal webmail par gaye?",
            "check": lambda res: res["result"]["rows"][0]["high_severity_personal"] == 272,
            "expected_tokens": ["272"]
        }
    ]

    try:
        for idx, tc in enumerate(qa_test_cases, start=1):
            analysis_run = AnalysisRun(
                chat_id="test_chat",
                message_id=f"msg_q{idx}",
                user_id="test_admin",
                unit_id="test_unit",
                question=tc["q"],
                input_file_ids=[stored_file.id],
                status="queued"
            )
            saved_run = await analysis_repo.create(analysis_run)

            res = await orchestrator.run(
                analysis_id=saved_run.id,
                ctx=ctx,
                question=tc["q"],
                file_ids=[stored_file.id]
            )

            assert res["status"] == "completed", f"Q{idx} failed to complete: {res}"
            assert tc["check"](res), f"Q{idx} failed verification: {res['result']['rows']}"
            for token in tc["expected_tokens"]:
                token_alt = token.replace(",", "")
                assert token in res["explanation"] or token_alt in res["explanation"], f"Q{idx} explanation missing expected token '{token}': {res['explanation']}"
            print(f"✅ Q{idx} Passed: {tc['q']} -> {res['result']['rows']}")
    finally:
        await orchestrator.workflow.close()
