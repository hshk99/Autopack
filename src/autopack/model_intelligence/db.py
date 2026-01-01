"""Database session helpers and migration utilities for model intelligence.

Production safety: Requires explicit DATABASE_URL for all mutation operations.
"""

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def get_database_url() -> str:
    """Get DATABASE_URL from environment.

    Raises:
        ValueError: If DATABASE_URL is not set (production safety requirement).
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError(
            "DATABASE_URL environment variable not set. "
            "Model intelligence operations require explicit database configuration."
        )
    return db_url


def create_model_intelligence_engine() -> Engine:
    """Create a SQLAlchemy engine for model intelligence operations.

    Returns:
        SQLAlchemy Engine instance.

    Raises:
        ValueError: If DATABASE_URL is not set.
    """
    db_url = get_database_url()
    return create_engine(db_url)


@contextmanager
def get_model_intelligence_session() -> Generator[Session, None, None]:
    """Context manager for model intelligence database sessions.

    Usage:
        with get_model_intelligence_session() as session:
            # perform operations
            session.commit()

    Yields:
        SQLAlchemy Session instance.

    Raises:
        ValueError: If DATABASE_URL is not set.
    """
    engine = create_model_intelligence_engine()
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
