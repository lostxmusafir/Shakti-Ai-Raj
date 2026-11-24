import uuid
from typing import TypeVar, Generic, Type, Optional, List, Dict, Any
from pydantic import BaseModel
from app.db.mongodb import MongoDBManager

T = TypeVar("T", bound=BaseModel)

class BaseRepository(Generic[T]):
    def __init__(self, collection_name: str, model_cls: Type[T]):
        self.collection_name = collection_name
        self.model_cls = model_cls

    @property
    def collection(self):
        return MongoDBManager.get_collection(self.collection_name)

    async def create(self, item: T) -> T:
        data = item.model_dump(mode="json")
        if not data.get("id"):
            data["id"] = uuid.uuid4().hex
        data["_id"] = data["id"]
        
        await self.collection.insert_one(data)
        return self.model_cls(**data)

    async def get_by_id(self, item_id: str, unit_id: Optional[str] = None) -> Optional[T]:
        query: Dict[str, Any] = {"_id": item_id}
        if unit_id and unit_id != "global":
            query["unit_id"] = unit_id
            
        doc = await self.collection.find_one(query)
        if not doc:
            return None
        doc["id"] = str(doc.get("_id", doc.get("id", "")))
        return self.model_cls(**doc)

    async def find_one(self, query: Dict[str, Any]) -> Optional[T]:
        doc = await self.collection.find_one(query)
        if not doc:
            return None
        doc["id"] = str(doc.get("_id", doc.get("id", "")))
        return self.model_cls(**doc)

    async def find_many(
        self,
        query: Dict[str, Any],
        sort_by: str = "created_at",
        direction: int = -1,
        limit: int = 100
    ) -> List[T]:
        cursor = self.collection.find(query).sort(sort_by, direction).limit(limit)
        items = []
        async for doc in cursor:
            doc["id"] = str(doc.get("_id", doc.get("id", "")))
            items.append(self.model_cls(**doc))
        return items

    async def update(self, item_id: str, updates: Dict[str, Any]) -> Optional[T]:
        await self.collection.update_one({"_id": item_id}, {"$set": updates})
        return await self.get_by_id(item_id)

    async def delete(self, item_id: str, unit_id: Optional[str] = None) -> bool:
        query: Dict[str, Any] = {"_id": item_id}
        if unit_id and unit_id != "global":
            query["unit_id"] = unit_id
            
        result = await self.collection.delete_one(query)
        return bool(result.deleted_count > 0)

    async def delete_many(self, query: Dict[str, Any]) -> int:
        result = await self.collection.delete_many(query)
        return int(result.deleted_count)

    async def count(self, query: Optional[Dict[str, Any]] = None) -> int:
        return await self.collection.count_documents(query or {})
