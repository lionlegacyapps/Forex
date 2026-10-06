"""Database health endpoint and connectivity helper tests."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import reset_db_state
from app.main import create_app


def test_health_database_unhealthy_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    reset_db_state()

    with TestClient(create_app()) as local_client:
        response = local_client.get("/health/database")
        assert response.status_code == 503
        assert response.json() == {"status": "unhealthy"}
        body = response.text.lower()
        assert "postgresql" not in body
        assert "password" not in body
        assert "supabase" not in body


def test_health_database_healthy_when_check_passes(client: TestClient) -> None:
    with patch("app.api.routes.health.database_is_healthy", return_value=True):
        response = client.get("/health/database")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_liveness_health_still_independent_of_database(client: TestClient) -> None:
    with patch("app.api.routes.health.database_is_healthy", return_value=False):
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
