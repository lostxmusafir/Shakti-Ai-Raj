import json
import asyncio
from typing import Any, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from app.auth.dependencies import get_current_active_user
from app.models.user import User
from app.models.analysis import AnalysisRun
from app.models.message import ChatMessage
from app.db.repository import BaseRepository
from app.core.exceptions import NotFoundError, ForbiddenError
from app.schemas.analysis import AnalysisResponse
from app.ai.orchestration.context import AIContext
from app.ai.orchestration.orchestrator import active_analysis_queues, orchestrator
from app.ai.learning.feedback_service import FeedbackRequest, FeedbackSubmission, feedback_service

router = APIRouter()
analysis_repo = BaseRepository("analysis_runs", AnalysisRun)
message_repo = BaseRepository("chat_messages", ChatMessage)


class ResumeAnalysisRequest(BaseModel):
    interrupt_id: Optional[str] = None
    response: Any

@router.get("/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(analysis_id: str, user: User = Depends(get_current_active_user)):
    run = await analysis_repo.get_by_id(analysis_id)
    if not run:
        raise NotFoundError("Analysis run", analysis_id)
    if run.user_id != user.id and user.role != "super_admin":
        raise ForbiddenError()

    return AnalysisResponse(
        id=run.id,
        chat_id=run.chat_id,
        message_id=run.message_id,
        user_id=run.user_id,
        status=run.status,
        thread_id=run.thread_id,
        intent=run.intent,
        question=run.question,
        plan=run.plan,
        pending_interrupt=run.pending_interrupt,
        resolved_bindings=run.resolved_bindings,
        result=run.result,
        verification=run.verification,
        provenance=run.provenance,
        error=run.error,
        created_at=run.created_at,
        completed_at=run.completed_at
    )


@router.post("/{analysis_id}/resume")
async def resume_analysis(
    analysis_id: str,
    req: ResumeAnalysisRequest,
    user: User = Depends(get_current_active_user),
):
    run = await analysis_repo.get_by_id(analysis_id)
    if not run:
        raise NotFoundError("Analysis run", analysis_id)
    if (run.user_id != user.id or (run.unit_id and user.unit_id and run.unit_id != user.unit_id)) and user.role != "super_admin":
        raise ForbiddenError("You do not have permission to resume this analysis.")

    ctx = AIContext(
        user_id=user.id,
        unit_id=user.unit_id or "default_unit",
        role=user.role,
        chat_id=run.chat_id,
        file_ids=run.input_file_ids,
    )
    res = await orchestrator.resume_analysis(analysis_id, ctx, req.interrupt_id, req.response)
    if res.get("status") == "completed" and not res.get("idempotent_replay"):
        existing_msgs = await message_repo.find_many({"analysis_id": analysis_id, "role": "assistant"})
        if not existing_msgs:
            assistant_msg = ChatMessage(
                chat_id=run.chat_id,
                user_id=user.id,
                role="assistant",
                content=res["explanation"],
                attachments=run.input_file_ids,
                analysis_id=analysis_id,
                metadata={
                    "result": res.get("result"),
                    "verification": res.get("verification"),
                    "provenance": res.get("provenance"),
                },
            )
            await message_repo.create(assistant_msg)
    return res


@router.post("/{analysis_id}/cancel")
async def cancel_analysis(
    analysis_id: str,
    user: User = Depends(get_current_active_user),
):
    run = await analysis_repo.get_by_id(analysis_id)
    if not run:
        raise NotFoundError("Analysis run", analysis_id)
    if (run.user_id != user.id or (run.unit_id and user.unit_id and run.unit_id != user.unit_id)) and user.role != "super_admin":
        raise ForbiddenError("You do not have permission to cancel this analysis.")
    return await orchestrator.cancel_analysis(analysis_id)


@router.post("/{analysis_id}/feedback")
async def submit_analysis_feedback(
    analysis_id: str,
    request: FeedbackRequest,
    user: User = Depends(get_current_active_user),
):
    run = await analysis_repo.get_by_id(analysis_id)
    if not run:
        raise NotFoundError("Analysis run", analysis_id)
    if run.user_id != user.id and user.role not in {"super_admin", "tech_admin"}:
        raise ForbiddenError()
    correction_sql = request.correction_sql or (request.correction or {}).get("sql")
    submission = FeedbackSubmission(
        analysis_id=run.id,
        user_id=user.id,
        unit_id=user.unit_id,
        user_role=user.role,
        question=run.question,
        category=request.category,
        comment=request.comment,
        correction_sql=correction_sql,
        dataset_path=request.dataset_path,
        approved_by=user.id if user.role in {"unit_admin", "super_admin", "tech_admin"} else None,
    )
    feedback = await feedback_service.record_feedback_async(submission)
    return feedback.model_dump(mode="json")

@router.get("/{analysis_id}/events")
async def stream_analysis_events(analysis_id: str, request: Request):
    async def event_generator():
        # Wait up to 3 seconds for queue to be initialized if run just created
        for _ in range(30):
            if analysis_id in active_analysis_queues:
                break
            await asyncio.sleep(0.1)

        queue = active_analysis_queues.get(analysis_id)
        if not queue:
            # Check if run already finished or interrupted
            run = await analysis_repo.get_by_id(analysis_id)
            if run and run.status == "interrupted":
                yield {
                    "event": "analysis.interrupted",
                    "data": json.dumps({
                        "analysis_id": run.id,
                        "thread_id": run.thread_id,
                        "interrupt": run.pending_interrupt,
                    })
                }
            elif run and run.status == "cancelled":
                yield {
                    "event": "analysis.cancelled",
                    "data": json.dumps({"analysis_id": run.id})
                }
            elif run:
                yield {
                    "event": "analysis.completed",
                    "data": json.dumps({"status": run.status, "result": run.result})
                }
            return

        while True:
            if await request.is_disconnected():
                break

            try:
                event = await asyncio.wait_for(queue.get(), timeout=20.0)
                if event is None:  # End of stream sentinel
                    break
                
                yield {
                    "event": event["type"],
                    "data": json.dumps(event["data"])
                }
            except asyncio.TimeoutError:
                # Keepalive heartbeat
                yield {
                    "event": "ping",
                    "data": json.dumps({"timestamp": "keepalive"})
                }

    return EventSourceResponse(event_generator())
