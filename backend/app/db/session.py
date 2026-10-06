"""Database engine and session factory.

Designed for Supabase PostgreSQL. The engine is created lazily so the API
can start during early development before DATABASE_URL is set.
"""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.exceptions import DatabaseNotConfiguredError
from app.core.logging import get_logger
from app.db.url import normalize_database_url

logger = get_logger(__name__)

_SessionLocal: sessionmaker[Session] | None = None


def _configured_database_url() -> str:
    """Return the normalized DATABASE_URL or raise if unset.

    The raw URL is never logged.
    """
    settings = get_settings()
    if not settings.is_database_configured:
        raise DatabaseNotConfiguredError()
    assert settings.database_url is not None
    return normalize_database_url(settings.database_url)


@lru_cache
def get_engine() -> Engine:
    """Create (and cache) the SQLAlchemy engine, or raise if not configured."""
    url = _configured_database_url()
    # Do not log the URL — it contains credentials.
    logger.info(
        "Creating SQLAlchemy engine (driver=psycopg, pool_pre_ping=on)"
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=300,
        pool_timeout=30,
        future=True,
    )


def get_session_factory() -> sessionmaker[Session]:
    """Return a session factory bound to the configured engine."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            class_=Session,
        )
    return _SessionLocal


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI-compatible session dependency."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def reset_db_state() -> None:
    """Clear cached engine/session factory (useful in tests)."""
    global _SessionLocal
    _SessionLocal = None
    get_engine.cache_clear()
