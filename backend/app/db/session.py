"""Database engine and session factory.

Designed for Supabase PostgreSQL. The engine is created lazily so the API
can start during early development before DATABASE_URL is set.
"""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.exceptions import DatabaseNotConfiguredError
from app.core.logging import get_logger

logger = get_logger(__name__)

_SessionLocal: sessionmaker[Session] | None = None


@lru_cache
def get_engine() -> Engine:
    """Create (and cache) the SQLAlchemy engine, or raise if not configured."""
    settings = get_settings()
    if not settings.is_database_configured:
        raise DatabaseNotConfiguredError()

    assert settings.database_url is not None
    logger.info("Creating SQLAlchemy engine for configured DATABASE_URL")
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
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
