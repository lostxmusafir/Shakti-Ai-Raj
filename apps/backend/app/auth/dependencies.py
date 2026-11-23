from typing import List, Optional
from fastapi import Depends, Header, HTTPException, status
from app.core.exceptions import UnauthorizedError, ForbiddenError
from app.auth.security import decode_access_token
from app.db.repository import BaseRepository
from app.models.user import User

user_repo = BaseRepository("users", User)

async def get_current_user(authorization: Optional[str] = Header(None)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid Authorization header.")
    
    token = authorization.split(" ")[1]
    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        raise UnauthorizedError("Token is invalid or expired.")
    
    user = await user_repo.get_by_id(payload["sub"])
    if not user:
        raise UnauthorizedError("User record no longer exists.")
    if user.status != "active":
        raise ForbiddenError("Account is inactive.")
    
    return user

async def get_current_active_user(user: User = Depends(get_current_user)) -> User:
    return user

def require_roles(allowed_roles: List[str]):
    async def role_checker(user: User = Depends(get_current_active_user)) -> User:
        if user.role not in allowed_roles and user.role != "super_admin":
            raise ForbiddenError(f"Role '{user.role}' is not authorized for this operation. Required: {allowed_roles}")
        return user
    return role_checker
