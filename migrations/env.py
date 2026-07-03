"""Alembic environment — reads shared/db/models.py as schema source of truth."""

from alembic import context

from shared.db.models import Base

target_metadata = Base.metadata

