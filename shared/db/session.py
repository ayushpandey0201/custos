"""Engine/session factory and DB health check.

Defaults to SQLite so the entire stack runs on a laptop with no external
services; ``CUSTOS_DATABASE_URL`` points it at Postgres under docker-compose.
Nothing above this module knows which one it got.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from shared.config import defaults
from shared.db.models import Base

engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def init_engine(database_url: str | None = None) -> Engine:
    """Create (or replace) the process-wide engine and session factory.

    Explicitly rebinds even if an engine already exists. Callers that only want
    an engine to exist should use :func:`ensure_engine` instead.
    """
    global engine, SessionLocal

    url = database_url or defaults.DATABASE_URL
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        # SQLite's default single-thread check trips under FastAPI's threadpool.
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs.pop("pool_pre_ping")

    engine = create_engine(url, **kwargs)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return engine


def ensure_engine() -> Engine:
    """Return the current engine, creating a default one only if none exists.

    This is what service startup calls. An app factory must never discard an
    engine that was configured before it ran — doing so silently repoints the
    whole process at the default database, which is exactly the kind of failure
    that shows up as "no such table" in tests and as data written to the wrong
    place in production.
    """
    if engine is None:
        return init_engine()
    return engine


def create_all(database_url: str | None = None) -> Engine:
    """Create every table. Used by tests and the demo; production uses Alembic."""
    eng = init_engine(database_url) if database_url else ensure_engine()
    Base.metadata.create_all(eng)
    return eng


def get_sessionmaker() -> sessionmaker[Session]:
    if SessionLocal is None:
        init_engine()
    assert SessionLocal is not None
    return SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope. Commits on success, rolls back on any exception."""
    factory = get_sessionmaker()
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_scope() as db:
        yield db


def health_check() -> bool:
    """True when the database answers a trivial query.

    Never raises: this is called from the health endpoint, and a health check
    that can crash the process it is checking is worse than useless.
    """
    try:
        factory = get_sessionmaker()
        with factory() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
