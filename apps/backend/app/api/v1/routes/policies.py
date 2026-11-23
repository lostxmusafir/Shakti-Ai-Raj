from typing import List
from fastapi import APIRouter, Depends
from app.auth.dependencies import get_current_active_user
from app.models.user import User
from app.models.policy import Policy
from app.policies.service import policy_service
from app.core.exceptions import NotFoundError

router = APIRouter()

@router.get("", response_model=List[Policy])
async def list_policies(user: User = Depends(get_current_active_user)):
    return await policy_service.list_policies(unit_id=user.unit_id)

@router.get("/{policy_code}", response_model=Policy)
async def get_policy(policy_code: str, user: User = Depends(get_current_active_user)):
    policy = await policy_service.get_by_code(policy_code)
    if not policy:
        raise NotFoundError("Policy", policy_code)
    return policy
