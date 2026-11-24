from typing import List, Optional
from fastapi import Depends, Header, Request, HTTPException, status
from app.core.exceptions import UnauthorizedError, ForbiddenError
from app.auth.security import decode_access_token
from app.db.repository import BaseRepository
from app.models.user import User

user_repo = BaseRepository("users", User)

ROLE_HIERARCHY = {
    "tech_admin": 4,
    "super_admin": 3,
    "unit_admin": 2,
    "employee": 1,
}

async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None)
) -> User:
    token: Optional[str] = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    elif "access_token" in request.cookies:
        token = request.cookies.get("access_token")

    if not token:
        raise UnauthorizedError("Missing or invalid authentication credentials.")
    
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
    """
    Enforces authoritative role hierarchy per Master Plan §2:
    TECH_ADMIN > SUPER_ADMIN > UNIT_ADMIN > EMPLOYEE
    Only TECH_ADMIN satisfies TECH_ADMIN requirements.
    SUPER_ADMIN cannot satisfy TECH_ADMIN requirements (e.g., admin role grants).
    """
    async def role_checker(user: User = Depends(get_current_active_user)) -> User:
        user_level = ROLE_HIERARCHY.get(user.role, 0)
        
        # If specific role list is provided, calculate if user role qualifies
        is_authorized = False
        if "tech_admin" in allowed_roles:
            is_authorized = (user.role == "tech_admin")
        else:
            min_required_level = min([ROLE_HIERARCHY.get(r, 99) for r in allowed_roles])
            is_authorized = (user_level >= min_required_level)

        if not is_authorized:
            raise ForbiddenError(
                f"Role '{user.role}' is not authorized for this operation. Required: {allowed_roles}"
            )
        return user
    return role_checker
