"""Adapter that runs the production analysis pipeline without MongoDB.

The blind evaluation must not modify production code per dataset, so this module
drives the real objects the API uses: ``DataProfiler``, the orchestrator's
planning + fallback logic, ``PlanValidator``, ``DuckDBEngine`` and
``ResultVerifier``. Only the persistence layer is replaced with in-memory stubs,
because the evaluation VM has no Atlas cluster.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any

# The evaluation runs outside the API container, so point storage at the
# workspace and never touch an external database.
os.environ.setdefault("STORAGE_DIR", str(Path(__file__).resolve().parents[3] / "data" / "uploads"))
os.environ.setdefault("USE_MOCK_DB", "true")

from app.ai.learning.example_retrieval import ExampleRetriever
from app.ai.orchestration.context import AIContext
from app.ai.orchestration.intent import IntentClassifier
from app.ai.planning.schemas import AnalysisPlan, DatasetRef
from app.ai.planning.validator import PlanValidator
from app.ai.providers import get_ai_provider
from app.ai.providers.mock_provider import MockAIProvider
from app.ai.verification.verifier import ResultVerifier
from app.analysis.execution.duckdb_engine import DuckDBEngine
from app.analysis.profiling.profiler import DataProfiler
from app.models.file import StoredFile
import app.ai.orchestration.orchestrator as orchestrator_module
from app.ai.orchestration.orchestrator import AnalysisOrchestrator

FILE_ID = "eval-file-1"
ALIAS = "ds_1"


class _MemoryRepo:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}

    async def update(self, record_id: str, payload: dict[str, Any]) -> None:
        self.records.setdefault(record_id, {}).update(payload)

    async def get_by_id(self, record_id: str, unit_id: str | None = None):  # pragma: no cover - not used
        return None


class _NullAudit:
    async def log_event(self, *args: Any, **kwargs: Any) -> None:
        return None


def _llm_ready(provider: Any) -> bool:
    if isinstance(provider, MockAIProvider):
        return False
    keys = getattr(provider, "api_keys", None)
    if keys:
        return True
    return bool(getattr(provider, "api_key", ""))


def provider_description() -> dict[str, Any]:
    provider = get_ai_provider()
    ready = _llm_ready(provider)
    return {
        "provider_class": type(provider).__name__,
        "llm_available": ready,
        "planner_mode": "llm_planner" if ready else "deterministic_keyword_fallback",
        "note": (
            "No model credentials are configured in this environment, so the planner falls back "
            "to the production keyword planner. LLM planning was not exercised."
            if not ready
            else "A configured provider is available."
        ),
    }


class SystemUnderTest:
    """Runs one natural-language question against one dataset sample."""

    def __init__(self) -> None:
        self._profiles: dict[str, dict[str, Any]] = {}
        provider = get_ai_provider()
        self._provider = provider if _llm_ready(provider) else MockAIProvider()

    @property
    def provider_class(self) -> str:
        return type(self._provider).__name__

    # -- profiling ---------------------------------------------------------
    def profile(self, path: str, name: str) -> dict[str, Any]:
        cached = self._profiles.get(path)
        if cached is None:
            cached = DataProfiler.profile_file(path, name)
            self._profiles[path] = cached
        return cached

    def _file_record(self, path: str, name: str) -> StoredFile:
        profile = self.profile(path, name)
        return StoredFile(
            id=FILE_ID,
            owner_user_id="blind-eval",
            unit_id="default_unit",
            original_name=name,
            content_type="text/csv",
            size_bytes=os.path.getsize(path),
            storage_key=name,
            status="ready",
            schema_profile=profile,
        )

    # -- planner mode ------------------------------------------------------
    def run_question(self, path: str, name: str, question: str) -> dict[str, Any]:
        record = self._file_record(path, name)
        orchestrator = AnalysisOrchestrator.__new__(AnalysisOrchestrator)
        orchestrator.analysis_repo = _MemoryRepo()
        orchestrator.file_repo = _MemoryRepo()
        orchestrator.ai_provider = self._provider
        context = AIContext(user_id="blind-eval", unit_id="default_unit", role="super_admin", chat_id="blind-eval")
        intent = IntentClassifier.classify(question, [FILE_ID])
        original_audit = orchestrator_module.audit_service
        orchestrator_module.audit_service = _NullAudit()
        try:
            response = asyncio.run(
                orchestrator._handle_data_analysis(
                    "blind-analysis",
                    context,
                    question,
                    [FILE_ID],
                    {FILE_ID: record},
                    {FILE_ID: path},
                    intent,
                )
            )
        except Exception as exc:  # noqa: BLE001 - execution failures are scored, not hidden
            return {
                "intent": intent,
                "error": f"{type(exc).__name__}: {exc}",
                "stage": "pipeline",
                "answer": "",
                "plan": None,
                "result": None,
                "verification": None,
            }
        finally:
            orchestrator_module.audit_service = original_audit

        result = response.get("result") or {}
        return {
            "intent": intent,
            "error": None,
            "stage": "completed",
            "answer": response.get("explanation", ""),
            "plan": self._repository_plan(orchestrator),
            "result": result,
            "verification": response.get("verification"),
        }

    @staticmethod
    def _repository_plan(orchestrator: AnalysisOrchestrator) -> dict[str, Any] | None:
        record = orchestrator.analysis_repo.records.get("blind-analysis", {})
        plan = record.get("plan")
        return plan

    # -- engine / verifier reference mode ----------------------------------
    def run_reference_sql(self, path: str, name: str, question: str, sql: str) -> dict[str, Any]:
        record = self._file_record(path, name)
        engine_sql = re.sub(r"\bdata\b", f'"{ALIAS}"', sql)
        plan = AnalysisPlan(
            intent="DATA_ANALYSIS",
            question=question,
            datasets=[DatasetRef(file_id=FILE_ID, alias=ALIAS)],
            sql_query=engine_sql,
            limit=10000,
        )
        try:
            validated = PlanValidator.validate_plan(plan, {FILE_ID: record})
            result = DuckDBEngine.execute(validated, {FILE_ID: record}, {FILE_ID: path})
            verification = ResultVerifier.verify(validated, result, {FILE_ID: record})
        except Exception as exc:  # noqa: BLE001
            return {"error": f"{type(exc).__name__}: {exc}", "stage": "engine_reference", "result": None, "verification": None, "plan": plan.model_dump()}
        return {"error": None, "stage": "completed", "result": result, "verification": verification, "plan": plan.model_dump()}

    @staticmethod
    def retrieval_contamination_report() -> dict[str, Any]:
        """Blind-set integrity: confirm no corpus entry exists in retrieval."""
        import json
        from pathlib import Path

        corpus = json.loads((Path(__file__).resolve().parent / "questions.json").read_text(encoding="utf-8"))
        known = {example.get("question", "") for example in ExampleRetriever.load_examples()}
        overlaps = [item["q_id"] for item in corpus["questions"] if item["question"] in known]
        return {
            "retrieval_store_size": len(known),
            "blind_questions_found_in_retrieval": len(overlaps),
            "overlapping_question_ids": overlaps,
        }
