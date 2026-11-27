from fastapi import APIRouter
from app.db.mongodb import MongoDBManager
from app.core.config import settings

router = APIRouter()

@router.get("/health")
async def health_check():
    mongo_ok = await MongoDBManager.ping()
    return {
        "status": "healthy" if mongo_ok else "degraded",
        "database": {
            "connected": mongo_ok,
            "engine": (
                "mongodb_atlas"
                if not MongoDBManager.is_mock
                else "mock_persistent_file" if MongoDBManager.is_persistent else "mock_in_memory"
            )
        },
        "services": {
            "analysis_engine": "duckdb_polars",
            "orchestration": "active",
            "ai_provider": settings.AI_PROVIDER
        }
    }
