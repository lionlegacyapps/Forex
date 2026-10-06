"""Centralized environment-based configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Environment variable names match field names in uppercase
    (e.g. ``database_url`` ← ``DATABASE_URL``).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
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
