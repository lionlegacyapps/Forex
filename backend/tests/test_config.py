"""Configuration loading tests."""

import os

import pytest

from app.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_default_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "APP_NAME",
        "APP_ENV",
        "LOG_LEVEL",
        "API_HOST",
        "API_PORT",
        "DATABASE_URL",
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.app_name == "algo-trading-backend"
    assert settings.app_env == "development"
    assert settings.api_port == 8000
    assert settings.is_database_configured is False


def test_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "test-platform")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("API_PORT", "9000")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@host:5432/db")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")

    get_settings.cache_clear()
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.app_name == "test-platform"
    assert settings.app_env == "test"
    assert settings.log_level == "DEBUG"
    assert settings.api_port == 9000
    assert settings.is_database_configured is True
    assert settings.supabase_url == "https://example.supabase.co"


def test_empty_database_url_is_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "   ")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.is_database_configured is False


def test_app_starts_without_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "DATABASE_URL",
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert os.getenv("DATABASE_URL") in (None, "")
