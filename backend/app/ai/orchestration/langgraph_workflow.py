import os
import logging
from typing import Any, Dict, List, Optional, TypedDict

import aiosqlite
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.ai.learning.semantic_mapping import SemanticMapper
from app.ai.orchestration.ambiguity import AmbiguityDetector
from app.ai.orchestration.intent import IntentClassifier
from app.ai.orchestration.state import AnalysisState
from app.ai.planning.schemas import AnalysisPlan
from app.ai.planning.validator import PlanValidator
from app.ai.verification.verifier import ResultVerifier
from app.analysis.execution.duckdb_engine import DuckDBEngine
from app.models.file import StoredFile

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
DEFAULT_CHECKPOINT_DB = os.path.join(BASE_DIR, "data", "langgraph_checkpoints.sqlite")


class AnalystGraphState(TypedDict, total=False):
    analysis_id: str
    thread_id: str
    user_id: str
    unit_id: str
    role: str
    question: str
    resolved_question: str
    file_ids: List[str]
    intent: str
    ai_tier: str
    record_family: Optional[str]
    resolved_bindings: List[Dict[str, Any]]
    cancelled: bool
    plan_dict: Dict[str, Any]
    engine_result: Dict[str, Any]
    verification: Dict[str, Any]
    explanation: str


class LangGraphAnalystWorkflow:
    """
    Persistent LangGraph orchestration wrapper around Universal AI Analyst's
    existing deterministic services (IntentClassifier, SemanticMapper,
    AmbiguityDetector, Orchestrator planner, PlanValidator, DuckDBEngine, ResultVerifier).
    """

    def __init__(self, orchestrator_ref: Any, checkpointer: Optional[Any] = None, db_path: Optional[str] = None):
        self.orchestrator = orchestrator_ref
        self._external_checkpointer = checkpointer
        self._db_path = db_path or DEFAULT_CHECKPOINT_DB
        self._conn: Optional[aiosqlite.Connection] = None
        self._checkpointer: Optional[Any] = checkpointer
        self._graph = None
        # Pure in-memory context cache keyed by thread_id for file metadata during graph runs;
        # reloaded from DB on resume if server restarted.
        self._runtime_cache: Dict[str, Dict[str, Any]] = {}

    async def _ensure_graph(self):
        if self._graph is not None:
            return self._graph

        if self._checkpointer is None:
            os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
            self._conn = await aiosqlite.connect(self._db_path)
            self._checkpointer = AsyncSqliteSaver(self._conn)
            await self._checkpointer.setup()

        builder = StateGraph(AnalystGraphState)
        builder.add_node("understand_question", self._node_understand_question)
        builder.add_node("inspect_schema", self._node_inspect_schema)
        builder.add_node("resolve_record_family", self._node_resolve_record_family)
        builder.add_node("resolve_semantics", self._node_resolve_semantics)
        builder.add_node("maybe_interrupt", self._node_maybe_interrupt)
        builder.add_node("build_plan", self._node_build_plan)
        builder.add_node("validate_plan", self._node_validate_plan)
        builder.add_node("execute_plan", self._node_execute_plan)
        builder.add_node("verify_result", self._node_verify_result)
        builder.add_node("generate_answer", self._node_generate_answer)

        builder.add_edge(START, "understand_question")
        builder.add_edge("understand_question", "inspect_schema")
        builder.add_edge("inspect_schema", "resolve_record_family")
        builder.add_edge("resolve_record_family", "resolve_semantics")
        builder.add_edge("resolve_semantics", "maybe_interrupt")

        builder.add_conditional_edges(
            "maybe_interrupt",
            self._route_after_interrupt,
            {
                "cancelled": END,
                "check_again": "maybe_interrupt",
                "proceed": "build_plan",
            },
        )

        builder.add_edge("build_plan", "validate_plan")
        builder.add_edge("validate_plan", "execute_plan")
        builder.add_edge("execute_plan", "verify_result")
        builder.add_edge("verify_result", "generate_answer")
        builder.add_edge("generate_answer", END)

        self._graph = builder.compile(checkpointer=self._checkpointer)
        return self._graph

    async def _load_files_for_state(self, state: AnalystGraphState):
        thread_id = state["thread_id"]
        cached = self._runtime_cache.get(thread_id)
        if cached:
            return cached["files_map"], cached["file_paths_map"]
        files_map, file_paths_map = await self.orchestrator._load_authorized_files(
            state.get("file_ids", []),
            state.get("unit_id", "default_unit"),
            state.get("role", "employee"),
        )
        self._runtime_cache[thread_id] = {
            "files_map": files_map,
            "file_paths_map": file_paths_map,
        }
        return files_map, file_paths_map

    async def _node_understand_question(self, state: AnalystGraphState) -> Dict[str, Any]:
        # Pure & idempotent
        await self.orchestrator._emit_status(state["analysis_id"], AnalysisState.UNDERSTANDING.value)
        intent = IntentClassifier.classify(state["question"], state.get("file_ids", []))
        return {"intent": intent}

    async def _node_inspect_schema(self, state: AnalystGraphState) -> Dict[str, Any]:
        # Pure read-only load
        await self.orchestrator._emit_status(state["analysis_id"], AnalysisState.RETRIEVING_CONTEXT.value)
        await self._load_files_for_state(state)
        return {}

    async def _node_resolve_record_family(self, state: AnalystGraphState) -> Dict[str, Any]:
        files_map, _ = await self._load_files_for_state(state)
        if not files_map:
            return {"record_family": None}
        first_profile = next(iter(files_map.values())).schema_profile or {}
        if not first_profile.get("is_mixed"):
            return {"record_family": None}
        cols = [c["name"] for c in first_profile.get("columns", [])]
        sem = SemanticMapper.resolve_semantics(state["question"], cols, first_profile)
        return {"record_family": sem.record_family}

    async def _node_resolve_semantics(self, state: AnalystGraphState) -> Dict[str, Any]:
        bindings = state.get("resolved_bindings") or []
        resolved_q = AmbiguityDetector.apply_bindings_to_question(state["question"], bindings)
        return {"resolved_question": resolved_q}

    async def _node_maybe_interrupt(self, state: AnalystGraphState) -> Dict[str, Any]:
        files_map, _ = await self._load_files_for_state(state)
        bindings = list(state.get("resolved_bindings") or [])
        payload = AmbiguityDetector.detect(state["question"], files_map, bindings)
        if payload is None:
            return {}

        # Official LangGraph interrupt() — pauses graph and persists checkpoint
        user_response = interrupt(payload)

        # On resume, LangGraph re-runs this node from the top and returns user_response here
        binding = AmbiguityDetector.validate_resume_response(payload, user_response)
        if payload.get("reason") == "HIGH_IMPACT_APPROVAL" and binding.get("option_id") == "cancel":
            return {"cancelled": True, "resolved_bindings": bindings + [binding]}

        new_bindings = bindings + [binding]
        resolved_q = AmbiguityDetector.apply_bindings_to_question(state["question"], new_bindings)
        return {
            "resolved_bindings": new_bindings,
            "resolved_question": resolved_q,
            "record_family": binding.get("binding") if binding.get("concept") == "record_family" else state.get("record_family"),
        }

    def _route_after_interrupt(self, state: AnalystGraphState) -> str:
        if state.get("cancelled"):
            return "cancelled"
        # Check if another sequential ambiguity remains
        cached = self._runtime_cache.get(state["thread_id"], {})
        files_map = cached.get("files_map", {})
        next_payload = AmbiguityDetector.detect(
            state["question"], files_map, state.get("resolved_bindings") or []
        )
        if next_payload is not None:
            return "check_again"
        return "proceed"

    async def _node_build_plan(self, state: AnalystGraphState) -> Dict[str, Any]:
        await self.orchestrator._emit_status(state["analysis_id"], AnalysisState.PLANNING.value)
        files_map, _ = await self._load_files_for_state(state)
        effective_q = state.get("resolved_question") or state["question"]
        plan = await self.orchestrator._plan_with_ai(
            effective_q,
            state.get("file_ids", []),
            files_map,
            state.get("intent", "DATA_ANALYSIS"),
            ai_tier=state.get("ai_tier", "low"),
        )
        bindings = state.get("resolved_bindings") or []
        if bindings:
            plan.resolved_bindings = bindings
            for b in bindings:
                if b.get("concept") == "record_family" and b.get("binding"):
                    plan.record_family = b["binding"]
        return {"plan_dict": plan.model_dump()}

    async def _node_validate_plan(self, state: AnalystGraphState) -> Dict[str, Any]:
        await self.orchestrator._emit_status(state["analysis_id"], AnalysisState.VALIDATING_PLAN.value)
        files_map, _ = await self._load_files_for_state(state)
        plan = AnalysisPlan(**state["plan_dict"])
        validated = PlanValidator.validate_plan(plan, files_map)
        return {"plan_dict": validated.model_dump()}

    async def _node_execute_plan(self, state: AnalystGraphState) -> Dict[str, Any]:
        await self.orchestrator._emit_status(state["analysis_id"], AnalysisState.EXECUTING.value)
        files_map, file_paths_map = await self._load_files_for_state(state)
        plan = AnalysisPlan(**state["plan_dict"])
        result = DuckDBEngine.execute(plan, files_map, file_paths_map)
        return {"engine_result": result}

    async def _node_verify_result(self, state: AnalystGraphState) -> Dict[str, Any]:
        await self.orchestrator._emit_status(state["analysis_id"], AnalysisState.VERIFYING.value)
        files_map, _ = await self._load_files_for_state(state)
        plan = AnalysisPlan(**state["plan_dict"])
        verification = ResultVerifier.verify(
            plan,
            state["engine_result"],
            files_map,
            user_unit_id=state.get("unit_id"),
            user_role=state.get("role", "employee"),
        )
        return {"verification": verification}

    async def _node_generate_answer(self, state: AnalystGraphState) -> Dict[str, Any]:
        await self.orchestrator._emit_status(state["analysis_id"], AnalysisState.GENERATING_ANSWER.value)
        plan = AnalysisPlan(**state["plan_dict"])
        explanation = await self.orchestrator._format_executive_answer(
            state["question"],
            plan,
            state["engine_result"],
            state["verification"],
            ai_tier=state.get("ai_tier", "low"),
        )
        return {"explanation": explanation}

    async def start(
        self,
        initial_state: AnalystGraphState,
        files_map: Optional[Dict[str, StoredFile]] = None,
        file_paths_map: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        graph = await self._ensure_graph()
        thread_id = initial_state["thread_id"]
        if files_map is not None and file_paths_map is not None:
            self._runtime_cache[thread_id] = {
                "files_map": files_map,
                "file_paths_map": file_paths_map,
            }
        config = {"configurable": {"thread_id": thread_id}}
        out = await graph.ainvoke(initial_state, config=config)
        return self._format_output(out)

    async def resume(
        self,
        thread_id: str,
        user_response: Any,
        files_map: Optional[Dict[str, StoredFile]] = None,
        file_paths_map: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        graph = await self._ensure_graph()
        if files_map is not None and file_paths_map is not None:
            self._runtime_cache[thread_id] = {
                "files_map": files_map,
                "file_paths_map": file_paths_map,
            }
        config = {"configurable": {"thread_id": thread_id}}
        out = await graph.ainvoke(Command(resume=user_response), config=config)
        return self._format_output(out)

    async def get_pending_interrupt(self, thread_id: str) -> Optional[Dict[str, Any]]:
        graph = await self._ensure_graph()
        config = {"configurable": {"thread_id": thread_id}}
        snap = await graph.aget_state(config)
        if snap and getattr(snap, "interrupts", None):
            intr = snap.interrupts[0]
            return getattr(intr, "value", intr)
        return None

    @staticmethod
    def _format_output(out: Dict[str, Any]) -> Dict[str, Any]:
        if "__interrupt__" in out and out["__interrupt__"]:
            intr = out["__interrupt__"][0]
            payload = getattr(intr, "value", intr)
            return {
                "status": AnalysisState.INTERRUPTED.value,
                "interrupt": payload,
                "state": out,
            }
        if out.get("cancelled"):
            return {
                "status": AnalysisState.CANCELLED.value,
                "state": out,
            }
        return {
            "status": AnalysisState.COMPLETED.value,
            "state": out,
        }
