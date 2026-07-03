"""Engine/session factory and DB health check."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = None
SessionLocal = None


def init_engine(database_url: str):
    global engine, SessionLocal
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(bind=engine)
    return engine


def health_check() -> bool:
    raise NotImplementedError

