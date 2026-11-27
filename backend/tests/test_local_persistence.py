import json

import pytest

from app.core.config import settings
from app.db.mongodb import MongoDBManager


@pytest.mark.asyncio
async def test_persistent_local_database_survives_manager_restart(tmp_path):
    original_persist = settings.PERSIST_LOCAL_DB
    original_path = settings.LOCAL_DB_PATH
    try:
        settings.PERSIST_LOCAL_DB = True
        settings.LOCAL_DB_PATH = str(tmp_path / "local-db.json")

        MongoDBManager.db = None
        MongoDBManager.client = None
        await MongoDBManager.connect()
        await MongoDBManager.get_collection("checks").insert_one({"_id": "one", "value": 42})
        await MongoDBManager.disconnect()

        MongoDBManager.db = None
        MongoDBManager.client = None
        await MongoDBManager.connect()
        saved = await MongoDBManager.get_collection("checks").find_one({"_id": "one"})

        assert saved == {"_id": "one", "value": 42}
        assert MongoDBManager.is_mock is True
        assert MongoDBManager.is_persistent is True
        assert json.loads((tmp_path / "local-db.json").read_text(encoding="utf-8"))["version"] == 1
    finally:
        MongoDBManager.db = None
        MongoDBManager.client = None
        MongoDBManager.is_mock = False
        MongoDBManager.is_persistent = False
        settings.PERSIST_LOCAL_DB = original_persist
        settings.LOCAL_DB_PATH = original_path
