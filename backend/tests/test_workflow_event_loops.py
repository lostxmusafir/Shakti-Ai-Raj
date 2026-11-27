import asyncio
import os
from unittest.mock import patch
import httpx

from app.ai.orchestration.langgraph_workflow import LangGraphAnalystWorkflow
from app.ai.orchestration.orchestrator import AnalysisOrchestrator
from app.ai.providers import gemini_provider
from app.ai.providers.gemini_provider import get_ai_provider_for_tier
from app.ai.providers.mistral_provider import MistralAIProvider
from app.ai.providers.mock_provider import MockAIProvider
from app.ai.providers.zhipu_provider import ZhipuAIProvider
from app.analysis.profiling.profiler import DataProfiler
from app.core.config import settings
from app.models.file import StoredFile


def _make_stored_file(file_id: str, path: str) -> StoredFile:
    name = os.path.basename(path)
    profile = DataProfiler.profile_file(path, name)
    return StoredFile(
        id=file_id,
        owner_user_id="user_loop",
        unit_id="unit_loop",
        original_name=name,
        content_type="text/csv",
        size_bytes=os.path.getsize(path),
        storage_key=file_id,
        schema_profile=profile,
    )


def test_langgraph_workflow_runs_across_multiple_event_loops(tmp_path, monkeypatch):
    csv_path = tmp_path / "simple.csv"
    csv_path.write_text("id,amount\n1,10\n2,20\n", encoding="utf-8")
    stored_file = _make_stored_file("f_loop_1", str(csv_path))

    orch = AnalysisOrchestrator()
    mock_ai = MockAIProvider()
    monkeypatch.setattr(orch, "ai_provider", mock_ai)
    monkeypatch.setattr("app.ai.orchestration.orchestrator.get_ai_provider_for_tier", lambda ai_tier=None: mock_ai)

    wf = LangGraphAnalystWorkflow(orch, db_path=str(tmp_path / "wf_loops.sqlite"))

    def _base_state(run_id: str, question: str) -> dict:
        return {
            "analysis_id": run_id,
            "thread_id": f"thread:{run_id}",
            "user_id": "user_loop",
            "unit_id": "unit_loop",
            "role": "super_admin",
            "question": question,
            "resolved_question": question,
            "file_ids": [stored_file.id],
            "intent": "DATA_ANALYSIS",
            "resolved_bindings": [],
            "cancelled": False,
        }

    out1 = asyncio.run(
        wf.start(
            _base_state("run_1", "Total records kitne hain?"),
            files_map={stored_file.id: stored_file},
            file_paths_map={stored_file.id: str(csv_path)},
        )
    )
    assert out1["status"] == "completed"
    assert out1["state"]["engine_result"]["rows"]
    loop1 = wf._loop
    assert loop1 is not None

    out2 = asyncio.run(
        wf.start(
            _base_state("run_2", "Total records kitne hain?"),
            files_map={stored_file.id: stored_file},
            file_paths_map={stored_file.id: str(csv_path)},
        )
    )
    assert out2["status"] == "completed"
    assert out2["state"]["engine_result"]["rows"]
    assert wf._loop is not None
    assert wf._loop is not loop1

    asyncio.run(wf.close())
    assert wf._graph is None
    assert wf._conn is None
    assert wf._loop is None

    out3 = asyncio.run(
        wf.start(
            _base_state("run_3", "Total records kitne hain?"),
            files_map={stored_file.id: stored_file},
            file_paths_map={stored_file.id: str(csv_path)},
        )
    )
    assert out3["status"] == "completed"
    asyncio.run(wf.close())


def test_langgraph_workflow_interrupt_and_resume_across_loops(tmp_path, monkeypatch):
    csv_path = tmp_path / "multi_amount.csv"
    csv_path.write_text(
        "id,Transaction Amount,Claim Amount\n"
        "1,100,50\n"
        "2,200,75\n",
        encoding="utf-8",
    )
    stored_file = _make_stored_file("f_loop_hitl", str(csv_path))

    orch = AnalysisOrchestrator()
    mock_ai = MockAIProvider()
    monkeypatch.setattr(orch, "ai_provider", mock_ai)
    monkeypatch.setattr("app.ai.orchestration.orchestrator.get_ai_provider_for_tier", lambda ai_tier=None: mock_ai)

    wf = LangGraphAnalystWorkflow(orch, db_path=str(tmp_path / "wf_hitl_loops.sqlite"))
    thread_id = "thread:hitl_cross_loop"

    out1 = asyncio.run(
        wf.start(
            {
                "analysis_id": "run_hitl_1",
                "thread_id": thread_id,
                "user_id": "user_loop",
                "unit_id": "unit_loop",
                "role": "super_admin",
                "question": "Amount kitna hai?",
                "resolved_question": "Amount kitna hai?",
                "file_ids": [stored_file.id],
                "intent": "DATA_ANALYSIS",
                "resolved_bindings": [],
                "cancelled": False,
            },
            files_map={stored_file.id: stored_file},
            file_paths_map={stored_file.id: str(csv_path)},
        )
    )
    assert out1["status"] == "interrupted"
    assert out1["interrupt"]["reason"] == "AMBIGUOUS_METRIC"

    out2 = asyncio.run(
        wf.resume(
            thread_id,
            "claim_amount",
            files_map={stored_file.id: stored_file},
            file_paths_map={stored_file.id: str(csv_path)},
        )
    )
    assert out2["status"] == "completed"
    assert out2["state"]["engine_result"]["rows"]

    asyncio.run(wf.close())


def test_mistral_and_zhipu_providers_across_multiple_event_loops(monkeypatch):
    mistral = MistralAIProvider(api_keys=["k1", "k2", "k3"])
    zhipu = ZhipuAIProvider(api_keys=["z1", "z2"])

    monkeypatch.setattr(gemini_provider, "_TIER_PROVIDERS", {})
    monkeypatch.setattr(settings, "MISTRAL_API_KEYS", ["mk1", "mk2"])
    monkeypatch.setattr(settings, "ZHIPU_API_KEYS", ["zk1", "zk2"])

    tier_low = get_ai_provider_for_tier("low")
    tier_pro = get_ai_provider_for_tier("pro")
    assert isinstance(tier_low, ZhipuAIProvider)
    assert isinstance(tier_pro, ZhipuAIProvider)

    async def contend_keys(provider, count: int):
        return await asyncio.gather(*(provider.get_next_key() for _ in range(count)))

    # Loop 1: contend asyncio.Lock via asyncio.gather (binds lock to Loop 1 if unkeyed)
    l1_m = asyncio.run(contend_keys(mistral, 10))
    l1_z = asyncio.run(contend_keys(zhipu, 10))
    l1_low = asyncio.run(contend_keys(tier_low, 6))
    l1_pro = asyncio.run(contend_keys(tier_pro, 6))
    assert len(l1_m) == 10 and set(l1_m) == {"k1", "k2", "k3"}
    assert len(l1_z) == 10 and set(l1_z) == {"z1", "z2"}
    assert len(l1_low) == 6 and set(l1_low) == {"zk1", "zk2"}
    assert len(l1_pro) == 6 and set(l1_pro) == {"zk1", "zk2"}

    # Loop 2: contend locks again and run generate() against mocked HTTP transport
    def mock_post(url, json=None, headers=None, **kwargs):
        req = httpx.Request("POST", url)
        return httpx.Response(200, request=req, json={"choices": [{"message": {"content": "ok"}}]})

    async def loop2_work():
        r_m = await contend_keys(mistral, 10)
        r_z = await contend_keys(zhipu, 10)
        r_low = await contend_keys(tier_low, 6)
        r_pro = await contend_keys(tier_pro, 6)
        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            g_m = await mistral.generate([{"role": "user", "content": "ping"}])
            g_z = await zhipu.generate([{"role": "user", "content": "ping"}])
            g_low = await tier_low.generate([{"role": "user", "content": "ping"}])
            g_pro = await tier_pro.generate([{"role": "user", "content": "ping"}])
        return r_m, r_z, r_low, r_pro, g_m, g_z, g_low, g_pro

    r_m, r_z, r_low, r_pro, g_m, g_z, g_low, g_pro = asyncio.run(loop2_work())
    assert len(r_m) == 10 and r_m[0] == "k2"
    assert len(r_z) == 10 and r_z[0] == "z1"
    assert len(r_low) == 6 and set(r_low) == {"zk1", "zk2"}
    assert len(r_pro) == 6
    assert g_m == g_z == g_low == g_pro == "ok"
