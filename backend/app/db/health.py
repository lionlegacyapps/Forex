"""Read-only database connectivity checks.

These helpers never create, update, or delete data and never return
connection credentials.
"""

from __future__ import annotations

from sqlalchemy import text

from app.core.exceptions import DatabaseNotConfiguredError
from app.core.logging import get_logger
from app.db.session import get_engine

logger = get_logger(__name__)


def check_database_connection() -> bool:
    """Execute ``SELECT 1`` and return True on success.

    Raises:
        DatabaseNotConfiguredError: when DATABASE_URL is not set.
        Exception: on connectivity / auth / network failures (callers should
            treat the exception as opaque — do not expose it to clients).
    """
    engine = get_engine()
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True


def database_is_healthy() -> bool:
    """Return True when the database answers ``SELECT 1``, else False.

    Never raises; never exposes credentials. Logs only a generic failure line.
    """
    try:
        return check_database_connection()
    except DatabaseNotConfiguredError:
        logger.warning("Database health check skipped: DATABASE_URL not configured")
        return False
    except Exception:
        # Avoid logger.exception — SQLAlchemy errors can embed connection details.
        logger.error("Database health check failed")
        return False
