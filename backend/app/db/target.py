"""Safe identification of the intended development database target.

Never logs or returns credentials, usernames, passwords, or full URLs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

from app.core.exceptions import ConfigurationError
from app.db.url import normalize_database_url


class DatabaseTargetKind(StrEnum):
    SUPABASE = "supabase"
    LOCAL = "local"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DatabaseTargetInfo:
    """Sanitized metadata only — safe to print."""

    kind: DatabaseTargetKind
    is_postgres: bool
    has_supabase_auth_schema: bool
    database_name_is_trading_dev: bool


def classify_database_url(url: str) -> DatabaseTargetKind:
    """Classify a URL without exposing its contents."""
    normalized = normalize_database_url(url)
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").lower()
    db_name = (parsed.path or "").lstrip("/").split("/")[0].lower()

    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return DatabaseTargetKind.LOCAL
    if "supabase" in host:
        return DatabaseTargetKind.SUPABASE
    if db_name == "trading_dev":
        return DatabaseTargetKind.LOCAL
    return DatabaseTargetKind.UNKNOWN


def inspect_database_target(url: str) -> DatabaseTargetInfo:
    """Connect and collect non-secret signals about the target database."""
    kind = classify_database_url(url)
    normalized = normalize_database_url(url)
    parsed = urlparse(normalized)
    db_name = (parsed.path or "").lstrip("/").split("/")[0].lower()

    engine = create_engine(normalized, pool_pre_ping=True, future=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            is_postgres = connection.execute(text("SELECT version()")).scalar()
            is_postgres_bool = bool(is_postgres) and "PostgreSQL" in str(is_postgres)
            has_auth = bool(
                connection.execute(
                    text(
                        "SELECT EXISTS ("
                        "  SELECT 1 FROM information_schema.schemata "
                        "  WHERE schema_name = 'auth'"
                        ")"
                    )
                ).scalar()
            )
    finally:
        engine.dispose()

    # Prefer live signals when host classification is ambiguous.
    if kind == DatabaseTargetKind.UNKNOWN and has_auth and is_postgres_bool:
        kind = DatabaseTargetKind.SUPABASE
    if kind == DatabaseTargetKind.LOCAL:
        pass
    elif has_auth and is_postgres_bool and "supabase" in (parsed.hostname or "").lower():
        kind = DatabaseTargetKind.SUPABASE

    return DatabaseTargetInfo(
        kind=kind,
        is_postgres=is_postgres_bool,
        has_supabase_auth_schema=has_auth,
        database_name_is_trading_dev=(db_name == "trading_dev"),
    )


def require_supabase_target(url: str) -> DatabaseTargetInfo:
    """Raise if the URL does not confidently resolve to Supabase PostgreSQL."""
    info = inspect_database_target(url)
    if info.kind != DatabaseTargetKind.SUPABASE:
        raise ConfigurationError(
            "Refusing to proceed: DATABASE_URL does not target Supabase PostgreSQL. "
            "Set DATABASE_URL in the repository-root .env to your Supabase connection "
            "string (not local 127.0.0.1/trading_dev)."
        )
    if info.database_name_is_trading_dev:
        raise ConfigurationError(
            "Refusing to proceed: DATABASE_URL appears to target trading_dev, "
            "which is the local accidental database — not Supabase."
        )
    if not info.is_postgres:
        raise ConfigurationError(
            "Refusing to proceed: target database did not identify as PostgreSQL."
        )
    return info
