import asyncio
import os
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.config import settings
from app.auth.service import auth_service
from app.policies.service import policy_service

@pytest.mark.asyncio
async def test_full_e2e_analyst_pipeline():
    await auth_service.ensure_seed_admin()
    await policy_service.ensure_seed_policies()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Login
        login_resp = await ac.post("/api/v1/auth/login", json={
            "email": settings.SEED_ADMIN_EMAIL,
            "password": settings.SEED_ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Upload incidents.csv
        sample_path = os.path.abspath("data/samples/incidents.csv")
        with open(sample_path, "rb") as f:
            file_resp = await ac.post(
                "/api/v1/files",
                files={"file": ("incidents.csv", f, "text/csv")},
                headers=headers
            )
        assert file_resp.status_code == 200, file_resp.text
        file_id = file_resp.json()["id"]
        assert file_resp.json()["status"] == "ready"
        assert file_resp.json()["schema_profile"]["row_count"] == 12

        # 3. Create chat session
        chat_resp = await ac.post("/api/v1/chats", json={"title": "E2E Test Session"}, headers=headers)
        chat_id = chat_resp.json()["id"]

        # 4. Send analytical query
        msg_resp = await ac.post(
            f"/api/v1/chats/{chat_id}/messages",
            json={
                "content": "Show total resolution_hours grouped by department where severity is Critical",
                "file_ids": [file_id]
            },
            headers=headers
        )
        assert msg_resp.status_code == 200
        analysis_id = msg_resp.json()["analysis_id"]

        # 5. Wait for background execution to complete
        for _ in range(20):
            ana_resp = await ac.get(f"/api/v1/analysis/{analysis_id}", headers=headers)
            if ana_resp.json()["status"] == "completed":
                break
            await asyncio.sleep(0.1)

        completed_ana = ana_resp.json()
        assert completed_ana["status"] == "completed"
        assert completed_ana["result"] is not None
        assert completed_ana["result"]["engine"] == "duckdb"
        assert completed_ana["verification"]["passed"] is True
        assert "provenance" in completed_ana
        assert file_id in completed_ana["provenance"]["source_files"]

        # 6. Upload email_logs.csv and evaluate policy
        email_sample_path = os.path.abspath("data/samples/email_logs.csv")
        with open(email_sample_path, "rb") as f:
            email_file_resp = await ac.post(
                "/api/v1/files",
                files={"file": ("email_logs.csv", f, "text/csv")},
                headers=headers
            )
        email_file_id = email_file_resp.json()["id"]

        policy_msg_resp = await ac.post(
            f"/api/v1/chats/{chat_id}/messages",
            json={
                "content": "Evaluate this dataset against our email security policy for violations",
                "file_ids": [email_file_id]
            },
            headers=headers
        )
        policy_analysis_id = policy_msg_resp.json()["analysis_id"]

        for _ in range(20):
            p_ana_resp = await ac.get(f"/api/v1/analysis/{policy_analysis_id}", headers=headers)
            if p_ana_resp.json()["status"] == "completed":
                break
            await asyncio.sleep(0.1)

        policy_completed = p_ana_resp.json()
        assert policy_completed["status"] == "completed"
        assert policy_completed["result"]["total_violations"] == 3
        assert policy_completed["result"]["evidence_rows"] == [2, 4, 7]
        assert policy_completed["provenance"]["policy_code"] == "SEC-EMAIL-001"
