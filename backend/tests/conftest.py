"""Shared pytest fixtures."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.session import reset_db_state
from app.db.target import DatabaseTargetKind, classify_database_url
from app.db.url import normalize_database_url
from app.main import create_app


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    get_settings.cache_clear()
    reset_db_state()
    application = create_app()
    with TestClient(application) as test_client:
        yield test_client
    get_settings.cache_clear()
    reset_db_state()


def _settings_database_url() -> str | None:
    """Resolve DATABASE_URL via application settings (``.env`` wins over shell)."""
    get_settings.cache_clear()
    settings = get_settings()
    if not settings.is_database_configured:
        return None
    assert settings.database_url is not None
    return normalize_database_url(settings.database_url)


@pytest.fixture(scope="session")
def db_engine() -> Generator[Engine, None, None]:
    """Engine for schema integration tests.

    Requires repository-root ``.env`` DATABASE_URL targeting Supabase.
    Refuses the accidental local ``trading_dev`` database.
    """
    url = _settings_database_url()
    if url is None:
        pytest.skip("DATABASE_URL not configured in repository-root .env")

    kind = classify_database_url(url)
    if kind == DatabaseTargetKind.LOCAL:
        pytest.skip(
            "DATABASE_URL points at a local database; schema tests require Supabase"
        )
    if kind != DatabaseTargetKind.SUPABASE:
        pytest.skip("DATABASE_URL target is not confidently Supabase; refusing schema tests")

    engine = create_engine(url, pool_pre_ping=True, future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def db_session(db_engine: Engine) -> Generator[Session, None, None]:
    """Transactional session rolled back after each test (no leftover rows)."""
    connection = db_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection, autoflush=False, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
