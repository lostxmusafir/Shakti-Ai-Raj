import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, AsyncGenerator
from app.core.exceptions import AppException
from app.db.repository import BaseRepository
from app.models.analysis import AnalysisRun
from app.models.file import StoredFile
from app.storage.local import storage_service
from app.ai.orchestration.context import AIContext
from app.ai.orchestration.state import AnalysisState
from app.ai.orchestration.intent import IntentClassifier
from app.ai.planning.schemas import AnalysisPlan, DatasetRef, AggregateOperation, Condition, JoinRule
from app.ai.planning.validator import PlanValidator
from app.analysis.execution.duckdb_engine import DuckDBEngine
from app.ai.verification.verifier import ResultVerifier
from app.policies.service import policy_service
from app.policies.evaluator import PolicyEvaluator
from app.audit.service import audit_service
from app.ai.providers.gemini_provider import get_ai_provider

logger = logging.getLogger(__name__)

# In-memory event queues for live SSE subscriptions
active_analysis_queues: Dict[str, asyncio.Queue] = {}

class AnalysisOrchestrator:
    def __init__(self):
        self.analysis_repo = BaseRepository("analysis_runs", AnalysisRun)
        self.file_repo = BaseRepository("files", StoredFile)
        self.ai_provider = get_ai_provider()

    async def _emit_event(self, analysis_id: str, event_type: str, data: Dict[str, Any]):
        if analysis_id in active_analysis_queues:
            await active_analysis_queues[analysis_id].put({
                "type": event_type,
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

    async def run(
        self,
        analysis_id: str,
        ctx: AIContext,
        question: str,
        file_ids: List[str]
    ) -> Dict[str, Any]:
        queue = asyncio.Queue()
        active_analysis_queues[analysis_id] = queue

        try:
            # 1. State: UNDERSTANDING
            await self.analysis_repo.update(analysis_id, {"status": AnalysisState.UNDERSTANDING.value})
            await self._emit_event(analysis_id, "analysis.status", {"status": AnalysisState.UNDERSTANDING.value})
            
            intent = IntentClassifier.classify(question, file_ids)
            await self.analysis_repo.update(analysis_id, {"intent": intent})

            # 2. State: RETRIEVING_CONTEXT
            await self.analysis_repo.update(analysis_id, {"status": AnalysisState.RETRIEVING_CONTEXT.value})
            await self._emit_event(analysis_id, "analysis.status", {"status": AnalysisState.RETRIEVING_CONTEXT.value})

            files_map: Dict[str, StoredFile] = {}
            file_paths_map: Dict[str, str] = {}
            for fid in file_ids:
                f_record = await self.file_repo.get_by_id(fid, unit_id=ctx.unit_id)
                if not f_record:
                    # check if super_admin
                    if ctx.role == "super_admin":
                        f_record = await self.file_repo.get_by_id(fid)
                if f_record:
                    files_map[fid] = f_record
                    file_paths_map[fid] = storage_service.get_file_path(f_record.storage_key)

            # Route based on intent
            if intent == "GENERAL_CHAT":
                response_text = await self._handle_general_chat(analysis_id, question)
                return await self._finalize_success(analysis_id, ctx, question, response_text)

            elif intent == "DATA_INSPECTION":
                response_text, result_data = await self._handle_data_inspection(analysis_id, files_map)
                return await self._finalize_success(analysis_id, ctx, question, response_text, result=result_data)

            elif intent == "POLICY_EVALUATION":
                response_text, result_data, prov = await self._handle_policy_evaluation(
                    analysis_id, ctx, question, files_map, file_paths_map
                )
                return await self._finalize_success(
                    analysis_id, ctx, question, response_text, result=result_data, provenance=prov
                )

            else:  # DATA_ANALYSIS or MULTI_FILE_ANALYSIS
                return await self._handle_data_analysis(
                    analysis_id, ctx, question, file_ids, files_map, file_paths_map, intent
                )

        except Exception as e:
            logger.error(f"Analysis failed: {str(e)}", exc_info=True)
            await self.analysis_repo.update(analysis_id, {
                "status": AnalysisState.FAILED.value,
                "error": str(e),
                "completed_at": datetime.now(timezone.utc)
            })
            await self._emit_event(analysis_id, "analysis.failed", {"error": str(e)})
            await audit_service.log_event(
                "analysis.failed",
                user_id=ctx.user_id,
                unit_id=ctx.unit_id,
                details={"analysis_id": analysis_id, "error": str(e)}
            )
            raise e
        finally:
            # Send completion marker to queue
            await queue.put(None)

    async def _handle_general_chat(self, analysis_id: str, question: str) -> str:
        await self._emit_event(analysis_id, "analysis.status", {"status": AnalysisState.GENERATING_ANSWER.value})
        messages = [{"role": "user", "content": question}]
        response = await self.ai_provider.generate(messages)
        await self._emit_event(analysis_id, "assistant.delta", {"delta": response})
        return response

    async def _handle_data_inspection(
        self,
        analysis_id: str,
        files_map: Dict[str, StoredFile]
    ) -> tuple[str, Dict[str, Any]]:
        await self._emit_event(analysis_id, "analysis.status", {"status": AnalysisState.GENERATING_ANSWER.value})
        summaries = []
        for fid, f in files_map.items():
            profile = f.schema_profile or {}
            rows = profile.get("row_count", 0)
            cols = [c["name"] for c in profile.get("columns", [])]
            summaries.append(f"**Dataset: {f.original_name}** ({rows:,} rows)\nColumns: {', '.join(cols)}")
        
        resp = "Here is the dataset schema inspection:\n\n" + "\n\n".join(summaries)
        await self._emit_event(analysis_id, "assistant.delta", {"delta": resp})
        return resp, {"type": "inspection", "files": list(files_map.keys())}

    async def _handle_policy_evaluation(
        self,
        analysis_id: str,
        ctx: AIContext,
        question: str,
        files_map: Dict[str, StoredFile],
        file_paths_map: Dict[str, str]
    ) -> tuple[str, Dict[str, Any], Dict[str, Any]]:
        # 1. State: PLANNING
        await self.analysis_repo.update(analysis_id, {"status": AnalysisState.PLANNING.value})
        await self._emit_event(analysis_id, "analysis.status", {"status": AnalysisState.PLANNING.value})

        # Find applicable policy
        policies = await policy_service.list_policies()
        target_policy = None
        for p in policies:
            if p.policy_code.lower() in question.lower() or p.department.lower() in question.lower() or any(w in question.lower() for w in ["email", "expense", "security"]):
                target_policy = p
                break
        if not target_policy and policies:
            target_policy = policies[0]

        if not target_policy:
            raise AppException("POLICY_NOT_FOUND", "No applicable company policy found.", status_code=404)

        # 2. State: EXECUTING
        await self.analysis_repo.update(analysis_id, {"status": AnalysisState.EXECUTING.value})
        await self._emit_event(analysis_id, "analysis.status", {"status": AnalysisState.EXECUTING.value})

        primary_fid = list(file_paths_map.keys())[0]
        eval_result = PolicyEvaluator.evaluate_file_against_policy(
            file_paths_map[primary_fid],
            target_policy
        )

        # 3. State: VERIFYING
        await self.analysis_repo.update(analysis_id, {"status": AnalysisState.VERIFYING.value})
        await self._emit_event(analysis_id, "analysis.status", {"status": AnalysisState.VERIFYING.value})

        total_violations = eval_result["total_violations"]
        explanation = (
            f"### Policy Evaluation Report: {target_policy.title} ({target_policy.policy_code} v{target_policy.version})\n\n"
            f"- **Department**: {target_policy.department}\n"
            f"- **Effective Date**: {target_policy.effective_from}\n"
            f"- **Violations Detected**: **{total_violations:,}**\n\n"
        )
        if total_violations > 0:
            explanation += f"Identified {len(eval_result['evidence_rows'])} offending rows in source file `{files_map[primary_fid].original_name}` (Rows: {eval_result['evidence_rows'][:10]})."
        else:
            explanation += "No policy violations detected across evaluated records."

        await self._emit_event(analysis_id, "assistant.delta", {"delta": explanation})

        provenance = {
            "policy_code": target_policy.policy_code,
            "policy_version": target_policy.version,
            "source_files": [primary_fid],
            "evidence_rows": eval_result["evidence_rows"]
        }
        return explanation, eval_result, provenance

    async def _handle_data_analysis(
        self,
        analysis_id: str,
        ctx: AIContext,
        question: str,
        file_ids: List[str],
        files_map: Dict[str, StoredFile],
        file_paths_map: Dict[str, str],
        intent: str
    ) -> Dict[str, Any]:
        # 1. State: PLANNING
        await self.analysis_repo.update(analysis_id, {"status": AnalysisState.PLANNING.value})
        await self._emit_event(analysis_id, "analysis.status", {"status": AnalysisState.PLANNING.value})

        # Construct deterministic AnalysisPlan
        datasets = [DatasetRef(file_id=fid, alias=f"ds_{idx+1}") for idx, fid in enumerate(file_ids)]
        
        # Smartly infer columns from first dataset's profile
        first_file = files_map[file_ids[0]]
        first_profile = first_file.schema_profile or {}
        available_cols = [c["name"] for c in first_profile.get("columns", [])]
        
        # Check for group_by or aggregation requests in user question
        group_cols = []
        for col in available_cols:
            if col.lower() in question.lower() and col.lower() not in ["id", "count", "total"]:
                group_cols.append(col)

        # Check for numeric aggregation target
        num_cols = [c["name"] for c in first_profile.get("columns", []) if c.get("inferred_type") in ["integer", "float"]]
        aggregations = []
        if any(w in question.lower() for w in ["sum", "total", "amount", "revenue"]) and num_cols:
            target_col = next((c for c in num_cols if c.lower() in question.lower()), num_cols[0])
            aggregations.append(AggregateOperation(function="sum", column=target_col, alias=f"total_{target_col}"))
        elif any(w in question.lower() for w in ["average", "avg", "mean"]) and num_cols:
            target_col = next((c for c in num_cols if c.lower() in question.lower()), num_cols[0])
            aggregations.append(AggregateOperation(function="avg", column=target_col, alias=f"avg_{target_col}"))
        else:
            aggregations.append(AggregateOperation(function="count", column="*", alias="record_count"))

        # Joins if multi-file
        joins = []
        if len(file_ids) > 1 and len(datasets) >= 2:
            second_file = files_map[file_ids[1]]
            second_profile = second_file.schema_profile or {}
            second_cols = [c["name"] for c in second_profile.get("columns", [])]
            # Find matching join key
            common_keys = [c for c in available_cols if c in second_cols]
            if common_keys:
                join_col = common_keys[0]
                joins.append(JoinRule(
                    left_dataset="ds_1",
                    right_dataset="ds_2",
                    left_column=join_col,
                    right_column=join_col,
                    join_type="inner"
                ))

        plan = AnalysisPlan(
            intent=intent,
            question=question,
            datasets=datasets,
            filters=[],
            group_by=group_cols[:2],
            aggregations=aggregations,
            joins=joins,
            limit=50
        )

        # 2. State: VALIDATING_PLAN
        await self.analysis_repo.update(analysis_id, {
            "status": AnalysisState.VALIDATING_PLAN.value,
            "plan": plan.model_dump()
        })
        await self._emit_event(analysis_id, "analysis.status", {"status": AnalysisState.VALIDATING_PLAN.value})

        validated_plan = PlanValidator.validate_plan(plan, files_map)

        # 3. State: EXECUTING
        await self.analysis_repo.update(analysis_id, {"status": AnalysisState.EXECUTING.value})
        await self._emit_event(analysis_id, "analysis.status", {"status": AnalysisState.EXECUTING.value})

        engine_result = DuckDBEngine.execute(validated_plan, files_map, file_paths_map)

        # 4. State: VERIFYING
        await self.analysis_repo.update(analysis_id, {"status": AnalysisState.VERIFYING.value})
        await self._emit_event(analysis_id, "analysis.status", {"status": AnalysisState.VERIFYING.value})

        verification = ResultVerifier.verify(validated_plan, engine_result, files_map)

        # 5. State: GENERATING_ANSWER
        await self.analysis_repo.update(analysis_id, {"status": AnalysisState.GENERATING_ANSWER.value})
        await self._emit_event(analysis_id, "analysis.status", {"status": AnalysisState.GENERATING_ANSWER.value})

        row_count = engine_result["row_count"]
        explanation = f"### Verified Analysis Results\n\nExecuted deterministic query via **DuckDB** in {engine_result['duration_ms']}ms.\n\n"
        explanation += f"- **Rows Analyzed/Returned**: {row_count:,}\n"
        explanation += f"- **Verification Status**: ✅ {verification['provenance']['verification_status'].upper()}\n\n"

        if row_count > 0:
            top_rows = engine_result["rows"][:5]
            explanation += f"Top Results Preview:\n\n"
            for r in top_rows:
                items = [f"**{k}**: {v}" for k, v in r.items()]
                explanation += f"- {', '.join(items)}\n"

        await self._emit_event(analysis_id, "assistant.delta", {"delta": explanation})

        return await self._finalize_success(
            analysis_id,
            ctx,
            question,
            explanation,
            result=engine_result,
            verification=verification,
            provenance=verification["provenance"]
        )

    async def _finalize_success(
        self,
        analysis_id: str,
        ctx: AIContext,
        question: str,
        explanation: str,
        result: Optional[Dict[str, Any]] = None,
        verification: Optional[Dict[str, Any]] = None,
        provenance: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        update_data = {
            "status": AnalysisState.COMPLETED.value,
            "result": result or {},
            "verification": verification or {},
            "provenance": provenance or {},
            "completed_at": datetime.now(timezone.utc)
        }
        await self.analysis_repo.update(analysis_id, update_data)
        await self._emit_event(analysis_id, "analysis.completed", {
            "analysis_id": analysis_id,
            "result": result,
            "provenance": provenance
        })
        await audit_service.log_event(
            "analysis.completed",
            user_id=ctx.user_id,
            unit_id=ctx.unit_id,
            details={"analysis_id": analysis_id, "question": question}
        )
        return {
            "analysis_id": analysis_id,
            "status": "completed",
            "explanation": explanation,
            "result": result,
            "verification": verification,
            "provenance": provenance
        }

orchestrator = AnalysisOrchestrator()
