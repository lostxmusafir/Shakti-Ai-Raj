import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.config import settings
from app.auth.service import auth_service
from app.policies.service import policy_service

@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ["healthy", "degraded"]
        assert "database" in data
        assert "analysis_engine" in data["services"]

@pytest.mark.asyncio
async def test_auth_login_and_me():
    await auth_service.ensure_seed_admin()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Login with seed admin
        login_resp = await ac.post("/api/v1/auth/login", json={
            "email": settings.SEED_ADMIN_EMAIL,
            "password": settings.SEED_ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, login_resp.text
        auth_data = login_resp.json()
        assert "access_token" in auth_data
        token = auth_data["access_token"]
        assert auth_data["user"]["role"] == "super_admin"

        # Verify /me endpoint
        me_resp = await ac.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == settings.SEED_ADMIN_EMAIL

@pytest.mark.asyncio
async def test_chats_and_messages_flow():
    await auth_service.ensure_seed_admin()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Login
        login_resp = await ac.post("/api/v1/auth/login", json={
            "email": settings.SEED_ADMIN_EMAIL,
            "password": settings.SEED_ADMIN_PASSWORD
        })
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create chat
        chat_resp = await ac.post("/api/v1/chats", json={"title": "Q1 Security Audit"}, headers=headers)
        assert chat_resp.status_code == 200
        chat_id = chat_resp.json()["id"]

        # Send message
        msg_resp = await ac.post(
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": "Hello, how does the policy verification work?", "file_ids": []},
            headers=headers
        )
        assert msg_resp.status_code == 200
        assert "analysis_id" in msg_resp.json()
        assert msg_resp.json()["status"] == "queued"
