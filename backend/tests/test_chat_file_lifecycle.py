import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.service import auth_service
from app.db.repository import BaseRepository
from app.main import app
from app.models.file import StoredFile
from app.storage.local import storage_service


async def _auth_headers(email: str, name: str):
    user = await auth_service.register(email, "Pass123!", name, role="employee", unit_id="lifecycle_unit")
    return user, {"Authorization": f"Bearer {auth_service.create_token_for_user(user)}"}


@pytest.mark.asyncio
async def test_chat_delete_cleans_messages_but_keeps_reusable_file():
    user, headers = await _auth_headers(f"owner_{uuid.uuid4().hex}@test.internal", "Lifecycle Owner")
    sample_path = os.path.abspath("data/samples/incidents.csv")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with open(sample_path, "rb") as sample:
            file_response = await ac.post(
                "/api/v1/files",
                files={"file": ("incidents.csv", sample, "text/csv")},
                headers=headers,
            )
        assert file_response.status_code == 200
        file_id = file_response.json()["id"]
        stored_file = await BaseRepository("files", StoredFile).get_by_id(file_id)
        assert stored_file is not None

        chat_response = await ac.post("/api/v1/chats", json={"title": "Lifecycle Chat"}, headers=headers)
        chat_id = chat_response.json()["id"]
        message_response = await ac.post(
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": "Count incidents", "file_ids": [file_id]},
            headers=headers,
        )
        assert message_response.status_code == 200

        delete_response = await ac.delete(f"/api/v1/chats/{chat_id}", headers=headers)
        assert delete_response.status_code == 200
        assert (await ac.get(f"/api/v1/chats/{chat_id}", headers=headers)).status_code == 404
        assert (await ac.get(f"/api/v1/files/{file_id}", headers=headers)).status_code == 200
        assert os.path.exists(storage_service.get_file_path(stored_file.storage_key)) is True


@pytest.mark.asyncio
async def test_chat_and_file_ownership_are_enforced():
    owner, owner_headers = await _auth_headers(f"owner_{uuid.uuid4().hex}@test.internal", "Owner")
    _, other_headers = await _auth_headers(f"other_{uuid.uuid4().hex}@test.internal", "Other")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        chat_id = (await ac.post("/api/v1/chats", json={}, headers=owner_headers)).json()["id"]
        assert (await ac.delete(f"/api/v1/chats/{chat_id}", headers=other_headers)).status_code == 403

        sample_path = os.path.abspath("data/samples/incidents.csv")
        with open(sample_path, "rb") as sample:
            file_id = (await ac.post(
                "/api/v1/files",
                files={"file": ("incidents.csv", sample, "text/csv")},
                headers=owner_headers,
            )).json()["id"]
        assert (await ac.delete(f"/api/v1/files/{file_id}", headers=other_headers)).status_code == 403

        assert (await ac.delete(f"/api/v1/chats/{chat_id}", headers=owner_headers)).status_code == 200
        assert (await ac.delete(f"/api/v1/files/{file_id}", headers=owner_headers)).status_code == 200
        assert (await ac.get(f"/api/v1/files/{file_id}", headers=owner_headers)).status_code == 404


@pytest.mark.asyncio
async def test_file_detach_only_removes_chat_reference():
    _, headers = await _auth_headers(f"detach_{uuid.uuid4().hex}@test.internal", "Detach Owner")
    sample_path = os.path.abspath("data/samples/incidents.csv")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with open(sample_path, "rb") as sample:
            file_response = await ac.post(
                "/api/v1/files",
                files={"file": ("incidents.csv", sample, "text/csv")},
                headers=headers,
            )
        file_id = file_response.json()["id"]
        chat_id = (await ac.post("/api/v1/chats", json={}, headers=headers)).json()["id"]
        await ac.post(
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": "Count incidents", "file_ids": [file_id]},
            headers=headers,
        )

        detach_response = await ac.delete(f"/api/v1/chats/{chat_id}/files/{file_id}", headers=headers)
        assert detach_response.status_code == 200
        assert (await ac.get(f"/api/v1/files/{file_id}", headers=headers)).status_code == 200
