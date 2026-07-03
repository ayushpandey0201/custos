"""SQLAlchemy ORM models — single source of DB schema truth.

Alembic migrations in migrations/versions/ are generated from this file.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

