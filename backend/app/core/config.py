"""Centralized environment-based configuration.

Development source of truth for secrets is the repository-root ``.env`` file
(see ``.env.example``). That file is gitignored.

Precedence (deterministic for local development)
----------------------------------------------
1. Explicit constructor kwargs (tests)
2. Repository-root ``.env`` (and CWD ``.env`` if used as fallback path)
3. Process environment variables
4. Field defaults

This means a stale shell ``DATABASE_URL`` (for example pointing at
``127.0.0.1/trading_dev``) cannot override a value defined in ``.env``.
If ``.env`` sets ``DATABASE_URL`` to empty, the database is treated as
unconfigured even when the shell still exports an old URL.

Persistent development data belongs in Supabase PostgreSQL — not a local
Docker/Postgres container.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

# backend/app/core/config.py → repository root (where .env.example lives)
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve_env_file() -> Path | None:
    """Prefer the repository-root ``.env``, then a CWD ``.env`` if present."""
    candidates = (_REPO_ROOT / ".env", Path.cwd() / ".env")
    for path in candidates:
        if path.is_file():
            return path
    return None


def env_file_path() -> Path:
    """Absolute path of the expected development ``.env`` file."""
    return _REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded from ``.env`` then the process environment."""

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

    # Optional until `.env` is filled — API still starts without DB credentials.
    database_url: str | None = None

    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Dotenv before process env so repo-root `.env` wins over stale shell exports.
        return init_settings, dotenv_settings, env_settings, file_secret_settings

    @property
    def is_database_configured(self) -> bool:
        """Return True when a non-empty DATABASE_URL is present."""
        return bool(self.database_url and self.database_url.strip())


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (dependency-injection friendly)."""
    return Settings()
