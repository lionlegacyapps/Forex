"""FastAPI dependency providers."""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session


def settings_dependency() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(settings_dependency)]
SessionDep = Annotated[Session, Depends(get_db_session)]


def db_session_dependency() -> Generator[Session, None, None]:
    """Yield a DB session; only use once DATABASE_URL is configured."""
    yield from get_db_session()
