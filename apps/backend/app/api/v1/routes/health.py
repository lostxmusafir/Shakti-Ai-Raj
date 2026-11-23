from fastapi import APIRouter
from app.db.mongodb import MongoDBManager

router = APIRouter()

@router.get("/health")
async def health_check():
    mongo_ok = await MongoDBManager.ping()
    return {
        "status": "healthy" if mongo_ok else "degraded",
        "database": {
            "connected": mongo_ok,
            "engine": "mongodb_atlas" if not MongoDBManager.is_mock else "mock_in_memory"
        },
        "services": {
            "analysis_engine": "duckdb_polars",
            "orchestration": "active"
        }
    }
