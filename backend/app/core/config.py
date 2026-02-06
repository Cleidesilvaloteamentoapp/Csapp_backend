
"""Application settings loaded from environment variables."""

import json
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration with Pydantic v2 validation."""

    # App
    APP_NAME: str = "CSApp Backend"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Supabase
    SUPABASE_URL: str
    SUPABASE_PUBLISHABLE_KEY: str
    SUPABASE_SECRET_KEY: str
    SUPABASE_JWT_SECRET: str  # JSON string with ES256 JWK

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Asaas
    ASAAS_API_KEY: str = ""
    ASAAS_ENVIRONMENT: str = "sandbox"
    ASAAS_BASE_URL: str = "https://sandbox.asaas.com/api/v3"

    # Email
    EMAIL_PROVIDER: str = "resend"
    RESEND_API_KEY: str = ""
    SMTP_FROM_EMAIL: str = "noreply@example.com"
    SMTP_FROM_NAME: str = "CSApp"

    # WhatsApp
    WHATSAPP_PROVIDER: str = "twilio"
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_NUMBER: str = ""

    # Storage
    SUPABASE_STORAGE_BUCKET: str = "documents"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        """Parse CORS origins from JSON string or list."""
        if isinstance(v, str):
            return json.loads(v)
        return v

    @property
    def supabase_jwt_jwk(self) -> dict:
        """Parse the Supabase JWT secret as JWK dict."""
        return json.loads(self.SUPABASE_JWT_SECRET)

    @property
    def database_url_sync(self) -> str:
        """Return sync database URL for Alembic."""
        return self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


settings = Settings()
