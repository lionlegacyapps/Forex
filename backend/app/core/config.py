"""Centralized environment-based configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py → repository root (where .env.example lives)
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve_env_file() -> Path | None:
    """Prefer the repository-root ``.env``, then a CWD ``.env`` if present."""
    candidates = (_REPO_ROOT / ".env", Path.cwd() / ".env")
    for path in candidates:
        if path.is_file():
            return path
    return None


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Environment variable names match field names in uppercase
    (e.g. ``database_url`` ← ``DATABASE_URL``).
    Process environment variables always take precedence over ``.env``.
    """

    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "algo-trading-backend"
    app_env: str = "development"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Optional during early development — app must start without DB credentials.
    database_url: str | None = None

    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None

    @property
    def is_database_configured(self) -> bool:
        """Return True when a non-empty DATABASE_URL is present."""
        return bool(self.database_url and self.database_url.strip())


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (dependency-injection friendly)."""
    return Settings()
