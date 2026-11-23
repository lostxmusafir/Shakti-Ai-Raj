from fastapi import APIRouter, Depends
from app.auth.service import auth_service
from app.auth.dependencies import get_current_active_user
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.audit.service import audit_service

router = APIRouter()

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    user = await auth_service.authenticate(req.email, req.password)
    token = auth_service.create_token_for_user(user)
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

@router.post("/register", response_model=UserResponse)
async def register(req: RegisterRequest):
    user = await auth_service.register(
        email=req.email,
        password=req.password,
        name=req.name,
        role=req.role or "employee",
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
