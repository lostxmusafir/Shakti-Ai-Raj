import os
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ai.orchestration.ambiguity import AmbiguityDetector
from app.ai.orchestration.context import AIContext
from app.ai.orchestration.orchestrator import AnalysisOrchestrator
from app.ai.orchestration.langgraph_workflow import LangGraphAnalystWorkflow
from app.analysis.profiling.profiler import DataProfiler
from app.db.repository import BaseRepository
from app.models.analysis import AnalysisRun
from app.models.chat import ChatSession
from app.models.file import StoredFile
from app.models.user import User
from app.auth.security import create_access_token, hash_password as get_password_hash


@pytest.fixture
def multi_amount_csv(tmp_path):
    p = tmp_path / "multi_amount.csv"
    p.write_text(
        "id,Transaction Amount,Claim Amount,Invoice Amount,invoice_date,payment_date,created_date\n"
        "1,100,50,120,2026-10-01,2026-10-02,2026-10-01\n"
        "2,200,75,220,2026-10-05,2026-10-06,2026-10-05\n"
        "3,300,25,310,2026-10-10,2026-10-11,2026-10-10\n",
        encoding="utf-8",
    )
    return str(p)


@pytest.fixture
def mixed_records_csv(tmp_path):
    p = tmp_path / "mixed_records.csv"
    # >= 12 rows so RowFamilyDiscovery activates
    rows = [
        "ID,Record Type,Destination,Action,Debit,Credit,Amount,invoice_date,payment_date",
        "1,DLP Incident,ext@gmail.com,Blocked,,,,,",
        "2,DLP Incident,int@company.com,Permitted,,,,,",
        "3,DLP Incident,ext@yahoo.com,Blocked,,,,,",
        "4,DLP Incident,int@company.com,Permitted,,,,,",
        "5,DLP Incident,ext@partner.org,Blocked,,,,,",
        "6,DLP Incident,int@company.com,Permitted,,,,,",
        "7,Finance Transaction,,Blocked,500,0,500,2026-10-01,2026-10-02",
        "8,Finance Transaction,,Permitted,0,300,300,2026-10-02,2026-10-03",
        "9,Finance Transaction,,Blocked,250,0,250,2026-10-03,2026-10-04",
        "10,Finance Transaction,,Permitted,0,400,400,2026-10-04,2026-10-05",
        "11,Finance Transaction,,Blocked,100,0,100,2026-10-05,2026-10-06",
        "12,Finance Transaction,,Permitted,0,200,200,2026-10-06,2026-10-07",
    ]
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return str(p)


def _make_stored_file(file_id: str, path: str, unit_id: str = "unit_a") -> StoredFile:
    profile = DataProfiler.profile_file(path, os.path.basename(path))
    return StoredFile(
        id=file_id,
        owner_user_id="user_a",
        unit_id=unit_id,
        original_name=os.path.basename(path),
        content_type="text/csv",
        size_bytes=os.path.getsize(path),
        storage_key=os.path.basename(path),
        schema_profile=profile,
    )


@pytest.mark.asyncio
async def test_01_high_confidence_query_does_not_interrupt(multi_amount_csv, tmp_path):
    f = _make_stored_file("f1", multi_amount_csv)
    orch = AnalysisOrchestrator()
    wf = LangGraphAnalystWorkflow(orch, db_path=str(tmp_path / "ckpt1.sqlite"))
    out = await wf.start(
        {
            "analysis_id": "run_1",
            "thread_id": "chat_1:run_1",
            "user_id": "user_a",
            "unit_id": "unit_a",
            "role": "super_admin",
            "question": "Total records kitne hain?",
            "resolved_question": "Total records kitne hain?",
            "file_ids": ["f1"],
            "intent": "DATA_ANALYSIS",
            "resolved_bindings": [],
            "cancelled": False,
        },
        files_map={"f1": f},
        file_paths_map={"f1": multi_amount_csv},
    )
    assert out["status"] == "completed"
    assert out["state"]["engine_result"]["rows"][0]


@pytest.mark.asyncio
async def test_02_03_04_ambiguous_metric_interrupts_resumes_and_binds(multi_amount_csv, tmp_path):
    f = _make_stored_file("f2", multi_amount_csv)
    orch = AnalysisOrchestrator()
    wf = LangGraphAnalystWorkflow(orch, db_path=str(tmp_path / "ckpt2.sqlite"))

    out1 = await wf.start(
        {
            "analysis_id": "run_2",
            "thread_id": "chat_2:run_2",
            "user_id": "user_a",
            "unit_id": "unit_a",
            "role": "super_admin",
            "question": "Amount kitna hai?",
            "resolved_question": "Amount kitna hai?",
            "file_ids": ["f2"],
            "intent": "DATA_ANALYSIS",
            "resolved_bindings": [],
            "cancelled": False,
        },
        files_map={"f2": f},
        file_paths_map={"f2": multi_amount_csv},
    )
    assert out1["status"] == "interrupted"
    intr = out1["interrupt"]
    assert intr["type"] == "choice"
    assert intr["reason"] == "AMBIGUOUS_METRIC"
    assert len(intr["options"]) == 3

    out2 = await wf.resume(
        "chat_2:run_2",
        "claim_amount",
        files_map={"f2": f},
        file_paths_map={"f2": multi_amount_csv},
    )
    assert out2["status"] == "completed"
    bindings = out2["state"]["plan_dict"]["resolved_bindings"]
    assert any(b["resolved_by"] == "user" and b["binding"] == "Claim Amount" for b in bindings)
    prov_bindings = out2["state"]["verification"]["provenance"]["resolved_bindings"]
    assert any(b["binding"] == "Claim Amount" for b in prov_bindings)


@pytest.mark.asyncio
async def test_05_reload_restores_pending_interrupt_from_sqlite(multi_amount_csv, tmp_path):
    db_path = str(tmp_path / "ckpt_reload.sqlite")
    f = _make_stored_file("f3", multi_amount_csv)
    orch = AnalysisOrchestrator()

    wf1 = LangGraphAnalystWorkflow(orch, db_path=db_path)
    out1 = await wf1.start(
        {
            "analysis_id": "run_3",
            "thread_id": "chat_3:run_3",
            "user_id": "user_a",
            "unit_id": "unit_a",
            "role": "super_admin",
            "question": "Amount kitna hai?",
            "resolved_question": "Amount kitna hai?",
            "file_ids": ["f3"],
            "intent": "DATA_ANALYSIS",
            "resolved_bindings": [],
            "cancelled": False,
        },
        files_map={"f3": f},
        file_paths_map={"f3": multi_amount_csv},
    )
    assert out1["status"] == "interrupted"

    # Simulate server/page reload with fresh workflow instance reading same SQLite checkpointer
    wf2 = LangGraphAnalystWorkflow(orch, db_path=db_path)
    pending = await wf2.get_pending_interrupt("chat_3:run_3")
    assert pending is not None
    assert pending["reason"] == "AMBIGUOUS_METRIC"

    out2 = await wf2.resume(
        "chat_3:run_3",
        "transaction_amount",
        files_map={"f3": f},
        file_paths_map={"f3": multi_amount_csv},
    )
    assert out2["status"] == "completed"


@pytest.mark.asyncio
async def test_06_07_08_11_security_idempotency_invalid_option_and_cancel(multi_amount_csv):
    client = TestClient(app)
    user_repo = BaseRepository("users", User)
    chat_repo = BaseRepository("chat_sessions", ChatSession)
    run_repo = BaseRepository("analysis_runs", AnalysisRun)

    await user_repo.create(User(
        id="u_owner", email="owner@test.local", name="Owner",
        hashed_password=get_password_hash("Pass123!"), role="analyst", unit_id="unit_1"
    ))
    await user_repo.create(User(
        id="u_other", email="other@test.local", name="Other",
        hashed_password=get_password_hash("Pass123!"), role="analyst", unit_id="unit_2"
    ))

    tok_other = create_access_token({"sub": "u_other", "role": "analyst", "unit_id": "unit_2"})
    tok_owner = create_access_token({"sub": "u_owner", "role": "analyst", "unit_id": "unit_1"})

    await chat_repo.create(ChatSession(id="c_sec", user_id="u_owner", unit_id="unit_1", title="Sec Test"))
    intr_payload = {
        "interrupt_id": "intr_abc123",
        "type": "choice",
        "reason": "AMBIGUOUS_METRIC",
        "question": "Which amount?",
        "options": [{"id": "claim_amount", "label": "Claim Amount", "value": "Claim Amount"}],
        "context": {"concept": "metric"},
    }
    await run_repo.create(AnalysisRun(
        id="r_sec", chat_id="c_sec", message_id="m_1", user_id="u_owner", unit_id="unit_1",
        status="interrupted", thread_id="c_sec:r_sec", question="Amount kitna hai?",
        pending_interrupt=intr_payload,
    ))

    # 6. Wrong user cannot resume (403)
    res_403 = client.post(
        "/api/v1/analysis/r_sec/resume",
        headers={"Authorization": f"Bearer {tok_other}"},
        json={"interrupt_id": "intr_abc123", "response": "claim_amount"},
    )
    assert res_403.status_code == 403

    # 8. Invalid option rejected (400)
    res_400 = client.post(
        "/api/v1/analysis/r_sec/resume",
        headers={"Authorization": f"Bearer {tok_owner}"},
        json={"interrupt_id": "intr_abc123", "response": "nonexistent_option"},
    )
    assert res_400.status_code == 400

    # 7. Duplicate resume idempotency when interrupt_id already consumed
    await run_repo.update("r_sec", {"consumed_interrupt_ids": ["intr_abc123"], "status": "completed", "result": {"row_count": 1}})
    res_idem = client.post(
        "/api/v1/analysis/r_sec/resume",
        headers={"Authorization": f"Bearer {tok_owner}"},
        json={"interrupt_id": "intr_abc123", "response": "claim_amount"},
    )
    assert res_idem.status_code == 200
    assert res_idem.json()["idempotent_replay"] is True

    # 11. Cancellation while pending
    await run_repo.create(AnalysisRun(
        id="r_can", chat_id="c_sec", message_id="m_2", user_id="u_owner", unit_id="unit_1",
        status="interrupted", thread_id="c_sec:r_can", question="Amount?",
        pending_interrupt=intr_payload,
    ))
    res_can = client.post(
        "/api/v1/analysis/r_can/cancel",
        headers={"Authorization": f"Bearer {tok_owner}"},
    )
    assert res_can.status_code == 200
    assert res_can.json()["status"] == "cancelled"


def test_09_free_text_validation():
    payload = {
        "interrupt_id": "intr_ft",
        "type": "free_text",
        "reason": "AMBIGUOUS_DOMAIN",
        "question": "Which company domain?",
        "options": [],
        "context": {"concept": "internal_domain"},
    }
    valid = AmbiguityDetector.validate_resume_response(payload, "raj.com")
    assert valid["binding"] == "raj.com"
    with pytest.raises(ValueError):
        AmbiguityDetector.validate_resume_response(payload, "")
    with pytest.raises(ValueError):
        AmbiguityDetector.validate_resume_response(payload, "raj.com; DROP TABLE users")


@pytest.mark.asyncio
async def test_10_12_sequential_interrupts_and_no_duplicate_execution(multi_amount_csv, tmp_path):
    f = _make_stored_file("f_seq", multi_amount_csv)
    orch = AnalysisOrchestrator()
    exec_calls = 0
    orig_exec = orch._format_executive_answer

    async def tracked_format(*args, **kwargs):
        nonlocal exec_calls
        exec_calls += 1
        return await orig_exec(*args, **kwargs)

    orch._format_executive_answer = tracked_format
    wf = LangGraphAnalystWorkflow(orch, db_path=str(tmp_path / "ckpt_seq.sqlite"))

    # Question has BOTH ambiguous metric ("Amount") AND ambiguous date ("Last month")
    out1 = await wf.start(
        {
            "analysis_id": "run_seq",
            "thread_id": "chat_seq:run_seq",
            "user_id": "user_a",
            "unit_id": "unit_a",
            "role": "super_admin",
            "question": "Last month ka amount kitna hai?",
            "resolved_question": "Last month ka amount kitna hai?",
            "file_ids": ["f_seq"],
            "intent": "DATA_ANALYSIS",
            "resolved_bindings": [],
            "cancelled": False,
        },
        files_map={"f_seq": f},
        file_paths_map={"f_seq": multi_amount_csv},
    )
    assert out1["status"] == "interrupted"
    assert out1["interrupt"]["reason"] == "AMBIGUOUS_METRIC"
    assert exec_calls == 0  # No execution before interrupt!

    out2 = await wf.resume("chat_seq:run_seq", "claim_amount", files_map={"f_seq": f}, file_paths_map={"f_seq": multi_amount_csv})
    assert out2["status"] == "interrupted"
    assert out2["interrupt"]["reason"] == "AMBIGUOUS_DATE"
    assert exec_calls == 0

    out3 = await wf.resume("chat_seq:run_seq", "invoice_date", files_map={"f_seq": f}, file_paths_map={"f_seq": multi_amount_csv})
    assert out3["status"] == "completed"
    assert exec_calls == 1  # Executed exactly once!


def test_mixed_data_cases_A_B_C_D(multi_amount_csv, mixed_records_csv):
    f_multi = _make_stored_file("f_m", multi_amount_csv)
    f_mixed = _make_stored_file("f_mix", mixed_records_csv)

    # Test A: Multiple valid amount columns -> interrupts
    intr_a = AmbiguityDetector.detect("Amount kitna hai?", {"f_m": f_multi})
    assert intr_a is not None and intr_a["reason"] == "AMBIGUOUS_METRIC"

    # Test B: Debit aur credit entries alag alag kitni hain? -> NO interrupt
    intr_b = AmbiguityDetector.detect("Debit aur credit entries alag alag kitni hain?", {"f_mix": f_mixed})
    assert intr_b is None

    # Test C: External emails kitne hain? -> NO unnecessary interrupt
    intr_c = AmbiguityDetector.detect("External emails kitne hain?", {"f_mix": f_mixed})
    assert intr_c is None

    # Test D: Ambiguous date field -> interrupts
    intr_d = AmbiguityDetector.detect("Last month ka revenue batao", {"f_m": f_multi})
    assert intr_d is not None and intr_d["reason"] == "AMBIGUOUS_DATE"
