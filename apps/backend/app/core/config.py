import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ENVIRONMENT: str = "development"
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Database
    MONGODB_URI: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "universal_ai_analyst"
    USE_MOCK_DB: bool = True

    # Security
    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production-universal-ai-analyst-2026"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Storage
    STORAGE_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../data/uploads"))
    MAX_UPLOAD_SIZE_BYTES: int = 50 * 1024 * 1024  # 50MB

    # AI Provider
    AI_PROVIDER: str = "mock"  # mock, gemini, openai
    AI_MODEL: str = "gemini-2.5-flash"
    AI_API_KEY: str = ""

    # Seed Admin
    SEED_ADMIN_EMAIL: str = "admin@company.internal"
    SEED_ADMIN_PASSWORD: str = "AdminSecret123!"
    SEED_ADMIN_NAME: str = "Super Administrator"

settings = Settings()
