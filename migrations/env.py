"""Alembic environment.

Targets ``shared.db.models.Base.metadata`` so that migrations are generated
from the ORM rather than hand-written — the models file is the single source of
schema truth and this keeps it that way.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from shared.config import defaults
from shared.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The URL comes from the same environment variable the services read, so a
# migration can never be applied to a different database than the one the
# gateway is talking to.
config.set_main_option("sqlalchemy.url", os.getenv("CUSTOS_DATABASE_URL", defaults.DATABASE_URL))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite cannot ALTER most columns in place; batch mode rebuilds the
        # table instead, so the same migration script runs on SQLite and
        # Postgres alike.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
