"""Shared pytest fixtures."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import reset_db_state
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
