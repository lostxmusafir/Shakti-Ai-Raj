import uuid
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.exceptions import AppException
from app.db.mongodb import MongoDBManager
from app.auth.service import auth_service
from app.policies.service import policy_service
from app.api.v1.api import api_router
from app.ai.orchestration.orchestrator import orchestrator
from app.core.rate_limit import rate_limit_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("universal_ai_analyst")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Universal AI Analyst backend service...")
    settings.validate_runtime()
    await MongoDBManager.connect()
    await rate_limit_service.ensure_indexes()
    await auth_service.ensure_seed_admin()
    await policy_service.ensure_seed_policies()
    logger.info("Universal AI Analyst backend initialization complete.")
    try:
        yield
    finally:
        # Shutdown
        logger.info("Shutting down Universal AI Analyst backend service...")
        try:
            await orchestrator.workflow.close()
        finally:
            await MongoDBManager.disconnect()

app = FastAPI(
    title="Universal AI Analyst API",
    description="Internal, policy-aware AI data analyst with deterministic calculation engine",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Standardized Error Handler
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    request_id = request.headers.get("x-request-id", f"req_{uuid.uuid4().hex[:10]}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id,
                "details": exc.details
            }
        },
        headers=exc.headers,
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = request.headers.get("x-request-id", f"req_{uuid.uuid4().hex[:10]}")
    logger.error(f"Unhandled error for request {request_id}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected server error occurred.",
                "request_id": request_id
            }
        }
    )

# Include API Router
app.include_router(api_router, prefix="/api/v1")
