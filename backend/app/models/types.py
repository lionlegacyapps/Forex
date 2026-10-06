"""Reusable SQLAlchemy Enum column helper (non-native PostgreSQL enums)."""

from __future__ import annotations

from enum import Enum
from typing import TypeVar

from sqlalchemy import Enum as SAEnum

E = TypeVar("E", bound=Enum)


def str_enum_column(enum_cls: type[E], *, name: str) -> SAEnum:
    """VARCHAR-backed enum column with ORM validation.

    PostgreSQL CHECK constraints for allowed values are owned by Alembic
    migrations (ck_*_status / ck_*_trading_mode / etc.) so constraint names
    stay stable and explicit.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=False,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )
