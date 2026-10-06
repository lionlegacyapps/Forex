"""Shared pytest fixtures."""

from collections.abc import Generator
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.session import reset_db_state
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


def _database_url() -> str | None:
    raw = os.environ.get("DATABASE_URL") or ""
    if not raw.strip():
        settings = get_settings()
        raw = settings.database_url or ""
    if not raw.strip():
        return None
    return normalize_database_url(raw)


@pytest.fixture(scope="session")
def db_engine() -> Generator[Engine, None, None]:
    url = _database_url()
    if url is None:
        pytest.skip("DATABASE_URL not configured — skipping schema DB tests")

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
