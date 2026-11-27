import os
from typing import List, Any, Annotated
from pydantic_settings import BaseSettings, SettingsConfigDict, NoDecode
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
    AI_PROVIDER: str = "zhipu"  # zhipu, mistral, gemini, mock
    AI_MODEL: str = "ministral-8b-latest"
    AI_API_KEY: str = ""

    # Mistral AI Provider Configuration
    # Credentials must be supplied through the environment or a secret manager.
    MISTRAL_API_KEYS: Annotated[List[str], NoDecode] = []
    MISTRAL_BASE_URL: str = "https://api.mistral.ai/v1"
    MISTRAL_DEFAULT_MODEL: str = "ministral-3b-latest"
    MISTRAL_HIGHER_MODEL: str = "ministral-3b-latest"
    MISTRAL_EMBEDDING_MODEL: str = "mistral-embed"

    # Zhipu AI (GLM) Provider Configuration
    ZHIPU_API_KEYS: Annotated[List[str], NoDecode] = []
    ZHIPU_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    ZHIPU_DEFAULT_MODEL: str = "glm-4.5-flash"

    @field_validator("MISTRAL_API_KEYS", "ZHIPU_API_KEYS", mode="before")
    @classmethod
    def assemble_api_keys(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            return [k.strip() for k in v.split(",") if k.strip()]
        return v

    # Seed Admin
    SEED_ADMIN_EMAIL: str = "admin@company.internal"
    SEED_ADMIN_PASSWORD: str = "AdminSecret123!"
    SEED_ADMIN_NAME: str = "Super Administrator"

    # Feature Flags
    ENABLE_GENERIC_PLANNER: bool = False
    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 5
    RATE_LIMIT_UPLOADS_PER_HOUR: int = 10
    RATE_LIMIT_ANALYSES_PER_HOUR: int = 30

    def validate_runtime(self) -> None:
        """Reject unsafe production defaults before the service accepts traffic."""
        if self.ENVIRONMENT.lower() != "production":
            return

        errors = []
        if self.USE_MOCK_DB:
            errors.append("USE_MOCK_DB must be false")
        if not self.MONGODB_URI or self.MONGODB_URI == "mongodb://localhost:27017":
            errors.append("MONGODB_URI must point to the production database")
        if len(self.JWT_SECRET_KEY) < 32 or self.JWT_SECRET_KEY == "dev-secret-key-change-in-production-universal-ai-analyst-2026":
            errors.append("JWT_SECRET_KEY must be a non-default value of at least 32 characters")
        if not self.SEED_ADMIN_PASSWORD or self.SEED_ADMIN_PASSWORD == "AdminSecret123!":
            errors.append("SEED_ADMIN_PASSWORD must be explicitly configured")
        if not self.CORS_ORIGINS or "*" in self.CORS_ORIGINS:
            errors.append("CORS_ORIGINS must contain explicit trusted origins")
        if not self.RATE_LIMIT_ENABLED:
            errors.append("RATE_LIMIT_ENABLED must be true")
        if errors:
            raise RuntimeError("Invalid production configuration: " + "; ".join(errors))

settings = Settings()
