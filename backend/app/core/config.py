import os
from typing import List, Optional, Union, Literal
from pydantic import SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "SBK Quiz Analyzer API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"
    ENVIRONMENT: str = "development"  # development, staging, production, testing
    
    # Security
    INITIAL_ADMIN_PASSWORD: Optional[SecretStr] = None  # Required only before the bootstrap audit guard exists
    SECRET_KEY: str = "dev-secret-key-change-in-production-min-32-chars-sbk-quiz-analyzer-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12  # 12 hours for admin JWTs
    SESSION_EXPIRE_MINUTES: int = 60  # 1 hour for quiz player sessions
    
    # Firebase is the production identity and persistence provider.
    DATABASE_BACKEND: Literal["firestore", "sql"] = "firestore"
    FIREBASE_PROJECT_ID: str = "mcq-analyzer-16a47"
    FIREBASE_SERVICE_ACCOUNT_JSON: Optional[SecretStr] = None

    # SQL is retained for explicit local development and migration sources.
    DATABASE_URL: str = "sqlite:///./quizmaster.db"
    
    # Redis
    REDIS_URL: Union[str, None] = None
    RATE_LIMIT_ENABLED: bool = True

    # AI Configuration (Server-Side Only - Never Exposed to Client)
    GEMINI_API_KEY: Optional[str] = None
    AI_MODEL_NAME: str = "gemini-2.5-flash"
    MAX_DOCX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB limit
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
        "https://mcq-analyzer-weld.vercel.app",
        "https://mcq-analyzer-16a47.firebaseapp.com",
        "https://mcq-analyzer-16a47.web.app",
        "https://sbk-quiz-analyzer.firebaseapp.com",
        "https://sbk-quiz-analyzer.web.app",
    ]

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_database_url(cls, v: Optional[str], info: ValidationInfo) -> str:
        url = (v or "").strip()
        if info.data.get("DATABASE_BACKEND") == "sql" and os.environ.get("VERCEL") and (not url or url.lower().startswith("sqlite")):
            raise ValueError(
                "Vercel requires a persistent PostgreSQL DATABASE_URL. "
                "Connect a database in Vercel Storage, set DATABASE_URL, and redeploy. "
                "Temporary SQLite storage cannot retain quizzes across instances."
            )
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        return url or "sqlite:///./quizmaster.db"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return []

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
