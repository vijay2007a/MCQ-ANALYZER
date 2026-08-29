import os
from typing import List, Optional, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "SBK Quiz Analyzer API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"
    ENVIRONMENT: str = "development"  # development, staging, production, testing
    
    # Security
    SECRET_KEY: str = "dev-secret-key-change-in-production-min-32-chars-sbk-quiz-analyzer-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12  # 12 hours for admin JWTs
    SESSION_EXPIRE_MINUTES: int = 60  # 1 hour for quiz player sessions
    
    # Database
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
    ]

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
