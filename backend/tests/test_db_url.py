"""Tests for DATABASE_URL normalization (no live credentials)."""

import pytest

from app.db.url import normalize_database_url


def test_normalize_postgresql_to_psycopg() -> None:
    result = normalize_database_url("postgresql://user:pass@db.example.com:5432/postgres")
    assert result.startswith("postgresql+psycopg://")
    assert "sslmode=require" in result
    assert "user:pass@" in result  # credentials preserved, not logged by app code


def test_normalize_postgres_scheme() -> None:
    result = normalize_database_url("postgres://user:pass@db.example.com:5432/postgres")
    assert result.startswith("postgresql+psycopg://")
    assert "sslmode=require" in result


def test_normalize_idempotent_psycopg_scheme() -> None:
    url = "postgresql+psycopg://user:pass@db.example.com:5432/postgres?sslmode=require"
    assert normalize_database_url(url) == url


def test_normalize_preserves_existing_sslmode() -> None:
    url = "postgresql://user:pass@db.example.com:5432/postgres?sslmode=verify-full"
    result = normalize_database_url(url)
    assert "sslmode=verify-full" in result
    assert result.count("sslmode=") == 1


def test_normalize_skips_ssl_for_localhost() -> None:
    result = normalize_database_url("postgresql://user:pass@localhost:5432/postgres")
    assert "sslmode=" not in result


def test_normalize_rejects_empty() -> None:
    with pytest.raises(ValueError):
        normalize_database_url("   ")
