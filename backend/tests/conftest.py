import inspect
import os
from pathlib import Path

import pytest_asyncio

from app.ai.orchestration.langgraph_workflow import LangGraphAnalystWorkflow
from app.ai.orchestration.orchestrator import orchestrator


# Keep relative fixture references stable when pytest is invoked from backend/ or repo root.
os.chdir(Path(__file__).resolve().parents[2])


@pytest_asyncio.fixture(autouse=True, loop_scope="function")
async def isolate_global_langgraph_checkpoints(request, tmp_path):
    if not inspect.iscoroutinefunction(request.function):
        yield
        return

    orchestrator.workflow = LangGraphAnalystWorkflow(
        orchestrator,
        db_path=str(tmp_path / "langgraph_checkpoints.sqlite"),
    )
    try:
        yield
    finally:
        await orchestrator.workflow.aclose()
        orchestrator.workflow = LangGraphAnalystWorkflow(orchestrator)
