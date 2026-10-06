"""Database package — connection and session architecture."""

from app.db.base import Base
from app.db.health import check_database_connection, database_is_healthy
from app.db.session import get_db_session, get_engine, reset_db_state
from app.db.target import DatabaseTargetKind, classify_database_url, inspect_database_target
from app.db.url import normalize_database_url

__all__ = [
    "Base",
    "DatabaseTargetKind",
    "check_database_connection",
    "classify_database_url",
    "database_is_healthy",
    "get_db_session",
    "get_engine",
    "inspect_database_target",
    "normalize_database_url",
    "reset_db_state",
]
