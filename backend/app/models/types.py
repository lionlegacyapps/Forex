"""Reusable SQLAlchemy Enum column helper (non-native PostgreSQL enums)."""

from __future__ import annotations

from enum import Enum
from typing import TypeVar

from sqlalchemy import Enum as SAEnum

E = TypeVar("E", bound=Enum)


def str_enum_column(enum_cls: type[E], *, name: str) -> SAEnum:
    """VARCHAR-backed enum column with a CHECK constraint via SQLAlchemy."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )
