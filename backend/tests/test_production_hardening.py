import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, settings
from app.core.exceptions import RateLimitError
from app.core.rate_limit import RateLimitRule, rate_limit_service
from app.db.mongodb import MongoDBManager
from app.auth.service import auth_service
from app.ai.orchestration.orchestrator import orchestrator
from app.main import app


def test_production_defaults_are_rejected():
    production = Settings(
        ENVIRONMENT="production",
        USE_MOCK_DB=True,
        MONGODB_URI="mongodb://localhost:27017",
        JWT_SECRET_KEY="dev-secret-key-change-in-production-universal-ai-analyst-2026",
        SEED_ADMIN_PASSWORD="AdminSecret123!",
        CORS_ORIGINS=["*"],
        RATE_LIMIT_ENABLED=False,
    )

    with pytest.raises(RuntimeError, match="Invalid production configuration"):
        production.validate_runtime()


def test_development_defaults_remain_allowed():
    Settings(ENVIRONMENT="development").validate_runtime()


@pytest.mark.asyncio
async def test_rate_limit_enforcement_in_mock_mode(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(MongoDBManager, "is_mock", True)
    rate_limit_service._local.clear()
    rule = RateLimitRule(limit=2, window_seconds=60)

    await rate_limit_service.enforce("test", "user-1", rule)
    await rate_limit_service.enforce("test", "user-1", rule)
    with pytest.raises(RateLimitError) as error:
        await rate_limit_service.enforce("test", "user-1", rule)

    assert error.value.status_code == 429
    assert error.value.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.asyncio
async def test_login_rate_limit_returns_standard_headers(monkeypatch):
    await auth_service.ensure_seed_admin()
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_LOGIN_PER_MINUTE", 1)
    monkeypatch.setattr(MongoDBManager, "is_mock", True)
    rate_limit_service._local.clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        first = await ac.post(
            "/api/v1/auth/login",
            json={"email": settings.SEED_ADMIN_EMAIL, "password": settings.SEED_ADMIN_PASSWORD},
        )
        second = await ac.post(
            "/api/v1/auth/login",
            json={"email": settings.SEED_ADMIN_EMAIL, "password": settings.SEED_ADMIN_PASSWORD},
        )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["x-ratelimit-limit"] == "1"
    assert second.headers["retry-after"]


@pytest.mark.asyncio
async def test_background_analysis_failure_is_persisted_without_leaking_details(monkeypatch):
    await auth_service.ensure_seed_admin()

    async def fail_run(*args, **kwargs):
        raise RuntimeError("private provider response")

    monkeypatch.setattr(orchestrator, "run", fail_run)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        login = await ac.post(
            "/api/v1/auth/login",
            json={"email": settings.SEED_ADMIN_EMAIL, "password": settings.SEED_ADMIN_PASSWORD},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        chat = await ac.post("/api/v1/chats", json={"title": "failure test"}, headers=headers)
        response = await ac.post(
            f"/api/v1/chats/{chat.json()['id']}/messages",
            json={"content": "trigger failure", "file_ids": []},
            headers=headers,
        )
        analysis_id = response.json()["analysis_id"]
        analysis = await ac.get(f"/api/v1/analysis/{analysis_id}", headers=headers)
        messages = await ac.get(f"/api/v1/chats/{chat.json()['id']}/messages", headers=headers)

    assert analysis.json()["status"] == "failed"
    assert analysis.json()["error"].startswith("Analysis failed. Reference: req_")
    assert "private provider response" not in analysis.text
    failures = [m for m in messages.json() if m.get("analysis_id") == analysis_id]
    assert len(failures) == 1
    assert "Please retry" in failures[0]["content"]
