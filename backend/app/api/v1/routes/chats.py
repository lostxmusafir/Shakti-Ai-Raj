import asyncio
from typing import List
from fastapi import APIRouter, Depends, BackgroundTasks
from app.auth.dependencies import get_current_active_user
from app.models.user import User
from app.models.chat import ChatSession
from app.models.message import ChatMessage
from app.models.analysis import AnalysisRun
from app.db.repository import BaseRepository
from app.core.exceptions import NotFoundError, ForbiddenError
from app.schemas.chat import (
    CreateChatRequest, ChatSessionResponse,
    SendMessageRequest, MessageResponse
)
from app.ai.orchestration.context import AIContext
from app.ai.orchestration.orchestrator import orchestrator
from app.audit.service import audit_service

router = APIRouter()
chat_repo = BaseRepository("chat_sessions", ChatSession)
message_repo = BaseRepository("chat_messages", ChatMessage)
analysis_repo = BaseRepository("analysis_runs", AnalysisRun)

@router.post("", response_model=ChatSessionResponse)
async def create_chat(
    req: CreateChatRequest,
    user: User = Depends(get_current_active_user)
):
    session = ChatSession(
        user_id=user.id,
        unit_id=user.unit_id,
        title=req.title or "New Analysis"
    )
    created = await chat_repo.create(session)
    await audit_service.log_event("chat.created", user_id=user.id, unit_id=user.unit_id, details={"chat_id": created.id})
    return ChatSessionResponse(
        id=created.id,
        user_id=created.user_id,
        unit_id=created.unit_id,
        title=created.title,
        created_at=created.created_at,
        updated_at=created.updated_at
    )

@router.get("", response_model=List[ChatSessionResponse])
async def list_chats(user: User = Depends(get_current_active_user)):
    query = {"user_id": user.id}
    sessions = await chat_repo.find_many(query, sort_by="updated_at", direction=-1)
    return [
        ChatSessionResponse(
            id=s.id,
            user_id=s.user_id,
            unit_id=s.unit_id,
            title=s.title,
            created_at=s.created_at,
            updated_at=s.updated_at
        )
        for s in sessions
    ]

@router.get("/{chat_id}", response_model=ChatSessionResponse)
async def get_chat(chat_id: str, user: User = Depends(get_current_active_user)):
    session = await chat_repo.get_by_id(chat_id)
    if not session:
        raise NotFoundError("Chat session", chat_id)
    
    can_access = False
    if user.role in ["tech_admin", "super_admin"]:
        can_access = True
    elif user.role == "unit_admin" and session.unit_id == user.unit_id:
        can_access = True
    elif session.user_id == user.id:
        can_access = True

    if not can_access:
        raise ForbiddenError("You cannot access this chat session.")

    return ChatSessionResponse(
        id=session.id,
        user_id=session.user_id,
        unit_id=session.unit_id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at
    )

@router.delete("/{chat_id}")
async def delete_chat(chat_id: str, user: User = Depends(get_current_active_user)):
    session = await chat_repo.get_by_id(chat_id)
    if not session:
        raise NotFoundError("Chat session", chat_id)
    
    can_delete = False
    if user.role in ["tech_admin", "super_admin"]:
        can_delete = True
    elif user.role == "unit_admin" and session.unit_id == user.unit_id:
        can_delete = True
    elif session.user_id == user.id:
        can_delete = True

    if not can_delete:
        raise ForbiddenError("You cannot delete this chat session.")

    await chat_repo.delete(chat_id)
    return {"status": "deleted", "id": chat_id}

@router.get("/{chat_id}/messages", response_model=List[MessageResponse])
async def list_messages(chat_id: str, user: User = Depends(get_current_active_user)):
    session = await chat_repo.get_by_id(chat_id)
    if not session:
        raise NotFoundError("Chat session", chat_id)
    
    can_access = False
    if user.role in ["tech_admin", "super_admin"]:
        can_access = True
    elif user.role == "unit_admin" and session.unit_id == user.unit_id:
        can_access = True
    elif session.user_id == user.id:
        can_access = True

    if not can_access:
        raise ForbiddenError("You cannot access messages for this chat session.")

    messages = await message_repo.find_many({"chat_id": chat_id}, sort_by="created_at", direction=1)
    return [
        MessageResponse(
            id=m.id,
            chat_id=m.chat_id,
            user_id=m.user_id,
            role=m.role,
            content=m.content,
            attachments=m.attachments,
            analysis_id=m.analysis_id,
            created_at=m.created_at,
            metadata=getattr(m, "metadata", {}) or {}
        )
        for m in messages
    ]

@router.post("/{chat_id}/messages")
async def send_message(
    chat_id: str,
    req: SendMessageRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_active_user)
):
    session = await chat_repo.get_by_id(chat_id)
    if not session:
        raise NotFoundError("Chat session", chat_id)
    if session.user_id != user.id and user.role != "super_admin":
        raise ForbiddenError()

    # 1. Save user message
    user_msg = ChatMessage(
        chat_id=chat_id,
        user_id=user.id,
        role="user",
        content=req.content,
        attachments=req.file_ids
    )
    saved_user_msg = await message_repo.create(user_msg)

    # 2. Create AnalysisRun record
    analysis = AnalysisRun(
        chat_id=chat_id,
        message_id=saved_user_msg.id,
        user_id=user.id,
        unit_id=user.unit_id,
        question=req.content,
        input_file_ids=req.file_ids,
        status="queued"
    )
    saved_analysis = await analysis_repo.create(analysis)

    # 3. Launch orchestration task
    ctx = AIContext(
        user_id=user.id,
        unit_id=user.unit_id or "default_unit",
        role=user.role,
        chat_id=chat_id,
        file_ids=req.file_ids
    )

    async def execute_and_save_assistant_reply():
        try:
            res = await orchestrator.run(
                analysis_id=saved_analysis.id,
                ctx=ctx,
                question=req.content,
                file_ids=req.file_ids
            )
            # Create assistant message in history with full metadata
            assistant_msg = ChatMessage(
                chat_id=chat_id,
                user_id=user.id,
                role="assistant",
                content=res["explanation"],
                attachments=req.file_ids,
                analysis_id=saved_analysis.id,
                metadata={
                    "result": res.get("result"),
                    "verification": res.get("verification"),
                    "provenance": res.get("provenance")
                }
            )
            await message_repo.create(assistant_msg)
        except Exception:
            pass

    background_tasks.add_task(execute_and_save_assistant_reply)

    return {
        "message_id": saved_user_msg.id,
        "analysis_id": saved_analysis.id,
        "status": "queued"
    }
