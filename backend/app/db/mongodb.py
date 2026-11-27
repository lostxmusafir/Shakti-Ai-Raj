import logging
import json
import os
import uuid
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

logger = logging.getLogger(__name__)

class MockAsyncCollection:
    """Thread-safe, async in-memory collection replicating Motor API for tests and offline dev."""
    def __init__(self, name: str, on_change=None):
        self.name = name
        self.docs: Dict[str, Dict[str, Any]] = {}
        self._on_change = on_change

    def _changed(self):
        if self._on_change:
            self._on_change()

    async def insert_one(self, document: Dict[str, Any]):
        doc = dict(document)
        if "_id" not in doc or not doc["_id"]:
            doc["_id"] = uuid.uuid4().hex
        elif not isinstance(doc["_id"], str):
            doc["_id"] = str(doc["_id"])
        self.docs[doc["_id"]] = doc
        self._changed()
        
        class InsertResult:
            def __init__(self, inserted_id):
                self.inserted_id = inserted_id
        return InsertResult(doc["_id"])

    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for doc in self.docs.values():
            match = True
            for k, v in query.items():
                if k == "_id" and not isinstance(v, str):
                    v = str(v)
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                return dict(doc)
        return None

    def find(self, query: Optional[Dict[str, Any]] = None):
        query = query or {}
        matches = []
        for doc in self.docs.values():
            match = True
            for k, v in query.items():
                if k == "_id" and not isinstance(v, str):
                    v = str(v)
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                matches.append(dict(doc))

        class AsyncCursor:
            def __init__(self, items):
                self.items = items

            def sort(self, field: str, direction: int = 1):
                reverse = direction < 0
                self.items.sort(key=lambda x: str(x.get(field, "")), reverse=reverse)
                return self

            def limit(self, count: int):
                self.items = self.items[:count]
                return self

            async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
                if length is not None:
                    return self.items[:length]
                return list(self.items)

            def __aiter__(self):
                self._iter = iter(self.items)
                return self

            async def __anext__(self):
                try:
                    return next(self._iter)
                except StopIteration:
                    raise StopAsyncIteration

        return AsyncCursor(matches)

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any]):
        doc = await self.find_one(query)
        if doc:
            doc_id = doc["_id"]
            if "$set" in update:
                for k, v in update["$set"].items():
                    self.docs[doc_id][k] = v
            else:
                for k, v in update.items():
                    self.docs[doc_id][k] = v
            self._changed()
        class UpdateResult:
            modified_count = 1 if doc else 0
        return UpdateResult()

    async def delete_one(self, query: Dict[str, Any]):
        doc = await self.find_one(query)
        deleted = 0
        if doc:
            del self.docs[doc["_id"]]
            deleted = 1
            self._changed()
        class DeleteResult:
            deleted_count = deleted
        return DeleteResult()

    async def count_documents(self, query: Optional[Dict[str, Any]] = None) -> int:
        cursor = self.find(query)
        res = await cursor.to_list()
        return len(res)

class MockAsyncDatabase:
    def __init__(self):
        self.collections: Dict[str, MockAsyncCollection] = {}

    def get_collection(self, name: str) -> MockAsyncCollection:
        if name not in self.collections:
            self.collections[name] = MockAsyncCollection(name)
        return self.collections[name]

    def __getitem__(self, name: str) -> MockAsyncCollection:
        return self.get_collection(name)

    async def command(self, cmd: str):
        if cmd == "ping":
            return {"ok": 1.0}
        return {"ok": 1.0}


class PersistentMockAsyncDatabase(MockAsyncDatabase):
    """Small JSON-backed local adapter for offline development.

    It intentionally preserves the existing collection API. MongoDB remains the
    production adapter; this class only makes the local mock survive restarts.
    """

    def __init__(self, path: str):
        super().__init__()
        self.path = os.path.abspath(path)
        self._load()

    def get_collection(self, name: str) -> MockAsyncCollection:
        if name not in self.collections:
            self.collections[name] = MockAsyncCollection(name, on_change=self._persist)
        return self.collections[name]

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            for name, documents in payload.get("collections", {}).items():
                collection = MockAsyncCollection(name, on_change=self._persist)
                if isinstance(documents, list):
                    collection.docs = {
                        str(doc["_id"]): doc
                        for doc in documents
                        if isinstance(doc, dict) and doc.get("_id")
                    }
                self.collections[name] = collection
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Could not load local database %s: %s", self.path, exc)

    def _persist(self):
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        payload = {
            "version": 1,
            "collections": {
                name: list(collection.docs.values())
                for name, collection in self.collections.items()
            },
        }
        temporary = f"{self.path}.{uuid.uuid4().hex}.tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, default=str)
            os.replace(temporary, self.path)
        except OSError as exc:
            logger.warning("Could not persist local database %s: %s", self.path, exc)
            try:
                if os.path.exists(temporary):
                    os.remove(temporary)
            except OSError:
                pass

class MongoDBManager:
    client: Optional[Any] = None
    db: Optional[Any] = None
    is_mock: bool = False
    is_persistent: bool = False

    @classmethod
    async def connect(cls):
        if settings.USE_MOCK_DB:
            database_cls = PersistentMockAsyncDatabase if settings.PERSIST_LOCAL_DB else MockAsyncDatabase
            logger.info(
                "Initializing %s Mock MongoDB manager.",
                "persistent local" if settings.PERSIST_LOCAL_DB else "in-memory",
            )
            cls.client = None
            cls.db = database_cls(settings.LOCAL_DB_PATH) if settings.PERSIST_LOCAL_DB else database_cls()
            cls.is_mock = True
            cls.is_persistent = settings.PERSIST_LOCAL_DB
            return

        try:
            logger.info(f"Connecting to MongoDB Atlas at {settings.MONGODB_URI}...")
            cls.client = AsyncIOMotorClient(
                settings.MONGODB_URI,
                serverSelectionTimeoutMS=2000
            )
            cls.db = cls.client[settings.DATABASE_NAME]
            # Verify connectivity with ping
            await cls.client.admin.command('ping')
            cls.is_mock = False
            cls.is_persistent = False
            logger.info("Successfully connected to MongoDB Atlas.")
        except Exception as e:
            if settings.ENVIRONMENT.lower() == "production":
                logger.error("Could not connect to the production MongoDB instance.", exc_info=True)
                raise RuntimeError("Production MongoDB connection failed.") from e
            logger.warning(f"Could not connect to live MongoDB: {e}. Falling back to in-memory Mock MongoDB.")
            cls.client = None
            cls.db = MockAsyncDatabase()
            cls.is_mock = True
            cls.is_persistent = False

    @classmethod
    async def disconnect(cls):
        if cls.client:
            cls.client.close()
            logger.info("MongoDB connection closed.")

    @classmethod
    def get_collection(cls, name: str):
        if cls.db is None:
            cls.db = PersistentMockAsyncDatabase(settings.LOCAL_DB_PATH) if settings.PERSIST_LOCAL_DB else MockAsyncDatabase()
            cls.is_mock = True
            cls.is_persistent = settings.PERSIST_LOCAL_DB
        return cls.db[name]

    @classmethod
    async def ping(cls) -> bool:
        if cls.is_mock:
            return True
        if cls.client:
            try:
                await cls.client.admin.command('ping')
                return True
            except Exception:
                return False
        return False
