import json
import asyncio
from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse
from app.auth.dependencies import get_current_active_user
from app.models.user import User
from app.models.analysis import AnalysisRun
from app.db.repository import BaseRepository
from app.core.exceptions import NotFoundError, ForbiddenError
from app.schemas.analysis import AnalysisResponse
from app.ai.orchestration.orchestrator import active_analysis_queues

router = APIRouter()
analysis_repo = BaseRepository("analysis_runs", AnalysisRun)

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
        intent=run.intent,
        question=run.question,
        plan=run.plan,
        result=run.result,
        verification=run.verification,
        provenance=run.provenance,
        created_at=run.created_at,
        completed_at=run.completed_at
    )

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
            # Check if run already finished
            run = await analysis_repo.get_by_id(analysis_id)
            if run:
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
