from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
    )

    DATABASE_URL: str
    ANTHROPIC_API_KEY: str = ""
    ENABLE_LIVE_AI_ANALYSIS: bool = False
    ENVIRONMENT: str = "development"
    # Comma-separated browser origins allowed for CORS (always used; never wildcard).
    # Local: http://localhost:3000,http://localhost:3001
    # Railway: https://getvigilapp.vercel.app
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    def cors_allow_origins(self) -> list[str]:
        """Parse explicit CORS origins from CORS_ORIGINS (no wildcard)."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
