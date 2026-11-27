import asyncio
import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple

from pymongo import ReturnDocument

from app.core.config import settings
from app.core.exceptions import RateLimitError
from app.db.mongodb import MongoDBManager


@dataclass(frozen=True)
class RateLimitRule:
    limit: int
    window_seconds: int


class RateLimitService:
    def __init__(self) -> None:
        self._local: Dict[Tuple[str, int], int] = {}
        self._lock = asyncio.Lock()
        self._index_ready = False

    async def ensure_indexes(self) -> None:
        if self._index_ready or MongoDBManager.is_mock:
            return
        await MongoDBManager.get_collection("rate_limit_windows").create_index(
            "expires_at", expireAfterSeconds=0
        )
        self._index_ready = True

    async def check(self, scope: str, key: str, rule: RateLimitRule) -> tuple[bool, int, int]:
        now = int(time.time())
        window_start = now - (now % rule.window_seconds)

        if MongoDBManager.is_mock:
            async with self._lock:
                self._local = {
                    item: count for item, count in self._local.items()
                    if item[1] >= window_start
                }
                local_key = (f"{scope}:{key}", window_start)
                count = self._local.get(local_key, 0) + 1
                self._local[local_key] = count
                remaining = max(0, rule.limit - count)
                return count <= rule.limit, remaining, window_start + rule.window_seconds

        digest = hashlib.sha256(f"{scope}:{key}:{window_start}".encode()).hexdigest()
        collection = MongoDBManager.get_collection("rate_limit_windows")
        document = await collection.find_one_and_update(
            {"_id": digest},
            {
                "$inc": {"count": 1},
                "$setOnInsert": {
                    "scope": scope,
                    "window_start": window_start,
                    "expires_at": datetime.now(timezone.utc) + timedelta(seconds=rule.window_seconds),
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        count = int(document.get("count", 0))
        remaining = max(0, rule.limit - count)
        return count <= rule.limit, remaining, window_start + rule.window_seconds

    async def enforce(self, scope: str, key: str, rule: RateLimitRule) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        allowed, remaining, reset_at = await self.check(scope, key, rule)
        headers = {
            "X-RateLimit-Limit": str(rule.limit),
            "X-RateLimit-Remaining": str(remaining),
            "Retry-After": str(max(1, reset_at - int(time.time()))),
        }
        if not allowed:
            raise RateLimitError("Too many requests. Please retry later.", headers)


rate_limit_service = RateLimitService()
