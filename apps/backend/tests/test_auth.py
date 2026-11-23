import pytest
from app.auth.security import hash_password, verify_password, create_access_token, decode_access_token
from app.auth.service import AuthService
from app.models.user import User

@pytest.mark.asyncio
async def test_password_hashing():
    pwd = "SecretPassword123!"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword", hashed) is False

@pytest.mark.asyncio
async def test_jwt_token_flow():
    payload = {"sub": "user_123", "role": "employee", "unit_id": "unit_a"}
    token = create_access_token(payload)
    assert isinstance(token, str)
    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == "user_123"
    assert decoded["role"] == "employee"

@pytest.mark.asyncio
async def test_auth_service_registration_and_login():
    auth_svc = AuthService()
    email = "testuser@company.internal"
    pwd = "MySecurePassword"
    
    # Register
    user = await auth_svc.register(email, pwd, "Test User", role="employee", unit_id="unit_1")
    assert user.email == email
    assert user.role == "employee"

    # Authenticate
    auth_user = await auth_svc.authenticate(email, pwd)
    assert auth_user.id == user.id

    # Bad password
    with pytest.raises(Exception):
        await auth_svc.authenticate(email, "WrongPassword")
