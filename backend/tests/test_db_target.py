"""Sanitized database-target classification tests (no live credentials)."""

from app.db.target import DatabaseTargetKind, classify_database_url


def test_classify_localhost_as_local() -> None:
    assert (
        classify_database_url("postgresql://u:p@127.0.0.1:5432/trading_dev")
        == DatabaseTargetKind.LOCAL
    )


def test_classify_supabase_host() -> None:
    assert (
        classify_database_url(
            "postgresql://u:p@db.abcdefghijkl.supabase.co:5432/postgres"
        )
        == DatabaseTargetKind.SUPABASE
    )


def test_classify_unknown_remote() -> None:
    assert (
        classify_database_url("postgresql://u:p@db.example.com:5432/postgres")
        == DatabaseTargetKind.UNKNOWN
    )
