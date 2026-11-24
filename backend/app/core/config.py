import os
from typing import List, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

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
    AI_PROVIDER: str = "mistral"  # mistral, gemini, mock
    AI_MODEL: str = "ministral-8b-latest"
    AI_API_KEY: str = ""

    # Mistral AI Provider Configuration
    # Credentials must be supplied through the environment or a secret manager.
    MISTRAL_API_KEYS: List[str] = []
    MISTRAL_BASE_URL: str = "https://api.mistral.ai/v1"
    MISTRAL_DEFAULT_MODEL: str = "ministral-8b-latest"
    MISTRAL_HIGHER_MODEL: str = "codestral-latest"
    MISTRAL_EMBEDDING_MODEL: str = "mistral-embed"

    @field_validator("MISTRAL_API_KEYS", mode="before")
    @classmethod
    def assemble_mistral_keys(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            return [k.strip() for k in v.split(",") if k.strip()]
        return v

    # Seed Admin
    SEED_ADMIN_EMAIL: str = "admin@company.internal"
    SEED_ADMIN_PASSWORD: str = "AdminSecret123!"
    SEED_ADMIN_NAME: str = "Super Administrator"

    # Feature Flags
    ENABLE_GENERIC_PLANNER: bool = False

settings = Settings()
