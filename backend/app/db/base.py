"""SQLAlchemy declarative base."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for ORM models. Trading tables will be added in later phases."""
