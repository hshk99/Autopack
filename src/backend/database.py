"""
Database configuration and session management.
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from .config import settings


# Create database engine - use connection args appropriate for database type
_is_sqlite = settings.database_url.startswith("sqlite")
_engine_kwargs = {"pool_pre_ping": True}
if not _is_sqlite:
    _engine_kwargs.update({"pool_size": 10, "max_overflow": 20})
else:
    _engine_kwargs.update({"connect_args": {"check_same_thread": False}})

engine = create_engine(settings.database_url, **_engine_kwargs)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for getting database sessions.

    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
