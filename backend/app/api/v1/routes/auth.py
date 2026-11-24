import uuid
from fastapi import APIRouter, Depends, Response
from app.auth.service import auth_service
from app.auth.dependencies import get_current_active_user, require_roles
from app.models.user import User
from app.schemas.auth import (
    LoginRequest, RegisterRequest, TokenResponse, UserResponse, RoleGrantRequest
)
from app.core.exceptions import ForbiddenError, NotFoundError
from app.audit.service import audit_service
from app.db.repository import BaseRepository

router = APIRouter()
user_repo = BaseRepository("users", User)

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, response: Response):
    user = await auth_service.authenticate(req.email, req.password)
    token = auth_service.create_token_for_user(user)
    csrf_token = uuid.uuid4().hex

    # Set secure HttpOnly session cookie
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=86400,
    )
    # Set CSRF cookie readable by frontend client
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        samesite="lax",
        path="/",
        max_age=86400,
    )

    await audit_service.log_event("auth.login", user_id=user.id, unit_id=user.unit_id)
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            unit_id=user.unit_id,
            status=user.status
        )
    )

@router.post("/logout")
async def logout(response: Response, user: User = Depends(get_current_active_user)):
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="csrf_token", path="/")
    await audit_service.log_event("auth.logout", user_id=user.id, unit_id=user.unit_id)
    return {"status": "success", "message": "Logged out successfully."}

@router.post("/register", response_model=UserResponse)
async def register(req: RegisterRequest):
    # Enforce least privilege: public registration cannot elevate to admin
    if req.role and req.role != "employee":
        raise ForbiddenError("Self-registration for privileged roles is forbidden. Only tech_admin may assign administrative roles.")

    user = await auth_service.register(
        email=req.email,
        password=req.password,
        name=req.name,
        role="employee",
        unit_id=req.unit_id or "default_unit"
    )
    await audit_service.log_event("auth.register", user_id=user.id, unit_id=user.unit_id)
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        unit_id=user.unit_id,
        status=user.status
    )

@router.post("/admin/role-grants", response_model=UserResponse)
async def grant_role(
    req: RoleGrantRequest,
    current_user: User = Depends(require_roles(["tech_admin"]))
):
    """
    Master Plan §2.1 & §9.2:
    Only TECH_ADMIN may create, grant, revoke or manage UNIT_ADMIN and SUPER_ADMIN accounts.
    SUPER_ADMIN cannot create, promote or manage administrative accounts.
    """
    valid_roles = {"employee", "unit_admin", "super_admin", "tech_admin"}
    if req.new_role not in valid_roles:
        raise ForbiddenError(f"Invalid role '{req.new_role}'. Must be one of {valid_roles}")

    target_user = await user_repo.get_by_id(req.user_id)
    if not target_user:
        raise NotFoundError("User", req.user_id)

    old_role = target_user.role
    await user_repo.update(req.user_id, {"role": req.new_role})
    updated_user = await user_repo.get_by_id(req.user_id)

    await audit_service.log_event(
        "admin.role_grant",
        user_id=current_user.id,
        unit_id=current_user.unit_id,
        details={
            "subject_user_id": req.user_id,
            "old_role": old_role,
            "new_role": req.new_role,
            "reason": req.reason,
            "approved_by": current_user.email,
        }
    )

    return UserResponse(
        id=updated_user.id,
        email=updated_user.email,
        name=updated_user.name,
        role=updated_user.role,
        unit_id=updated_user.unit_id,
        status=updated_user.status
    )

@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_active_user)):
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        unit_id=user.unit_id,
        status=user.status
    )
