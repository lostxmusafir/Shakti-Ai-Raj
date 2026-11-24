from typing import Optional
from pydantic import BaseModel, EmailStr

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: Optional[str] = "employee"
    unit_id: Optional[str] = "default_unit"

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    unit_id: Optional[str] = None
    status: str

class RoleGrantRequest(BaseModel):
    user_id: str
    new_role: str
    reason: str
