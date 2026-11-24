from fastapi import APIRouter
from app.api.v1.routes import health, auth, chats, files, analysis, policies

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(chats.router, prefix="/chats", tags=["Chats"])
api_router.include_router(files.router, prefix="/files", tags=["Files"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["Analysis"])
api_router.include_router(policies.router, prefix="/policies", tags=["Policies"])
