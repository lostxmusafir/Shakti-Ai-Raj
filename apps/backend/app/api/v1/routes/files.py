import os
from typing import List
from fastapi import APIRouter, Depends, UploadFile, File
from app.auth.dependencies import get_current_active_user
from app.models.user import User
from app.models.file import StoredFile
from app.db.repository import BaseRepository
from app.core.exceptions import NotFoundError, ForbiddenError, AppException
from app.storage.local import storage_service
from app.analysis.profiling.profiler import DataProfiler
from app.schemas.file import FileResponse
from app.audit.service import audit_service

router = APIRouter()
file_repo = BaseRepository("files", StoredFile)

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

@router.post("", response_model=FileResponse)
async def upload_file(
    file: UploadFile = File(...),
    user: User = Depends(get_current_active_user)
):
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise AppException("UNSUPPORTED_FILE_TYPE", f"File extension '{ext}' is not supported. Supported: {list(ALLOWED_EXTENSIONS)}", status_code=400)

    content = await file.read()
    storage_key = await storage_service.save_file(filename, content)
    file_path = storage_service.get_file_path(storage_key)

    # Profile the data schema
    try:
        profile = DataProfiler.profile_file(file_path, filename)
        status = "ready"
    except Exception as e:
        profile = {"error": str(e)}
        status = "error"

    stored_file = StoredFile(
        owner_user_id=user.id,
        unit_id=user.unit_id,
        original_name=filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        storage_key=storage_key,
        status=status,
        schema_profile=profile
    )
    saved = await file_repo.create(stored_file)
    await audit_service.log_event("file.upload", user_id=user.id, unit_id=user.unit_id, details={"file_id": saved.id, "name": filename})

    return FileResponse(
        id=saved.id,
        original_name=saved.original_name,
        content_type=saved.content_type,
        size_bytes=saved.size_bytes,
        status=saved.status,
        schema_profile=saved.schema_profile,
        created_at=saved.created_at
    )

@router.get("", response_model=List[FileResponse])
async def list_files(user: User = Depends(get_current_active_user)):
    query = {"owner_user_id": user.id} if user.role != "super_admin" else {}
    files = await file_repo.find_many(query, sort_by="created_at", direction=-1)
    return [
        FileResponse(
            id=f.id,
            original_name=f.original_name,
            content_type=f.content_type,
            size_bytes=f.size_bytes,
            status=f.status,
            schema_profile=f.schema_profile,
            created_at=f.created_at
        )
        for f in files
    ]

@router.get("/{file_id}", response_model=FileResponse)
async def get_file(file_id: str, user: User = Depends(get_current_active_user)):
    record = await file_repo.get_by_id(file_id)
    if not record:
        raise NotFoundError("File", file_id)
    if record.owner_user_id != user.id and user.role != "super_admin":
        raise ForbiddenError("You cannot access this file.")
    return FileResponse(
        id=record.id,
        original_name=record.original_name,
        content_type=record.content_type,
        size_bytes=record.size_bytes,
        status=record.status,
        schema_profile=record.schema_profile,
        created_at=record.created_at
    )

@router.delete("/{file_id}")
async def delete_file(file_id: str, user: User = Depends(get_current_active_user)):
    record = await file_repo.get_by_id(file_id)
    if not record:
        raise NotFoundError("File", file_id)
    if record.owner_user_id != user.id and user.role != "super_admin":
        raise ForbiddenError("You cannot delete this file.")
    
    storage_service.delete_file(record.storage_key)
    await file_repo.delete(file_id)
    await audit_service.log_event("file.delete", user_id=user.id, unit_id=user.unit_id, details={"file_id": file_id})
    return {"status": "deleted", "id": file_id}
