"""Integration test fixtures and configuration."""

import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def mock_session_local(db_engine):
    """Mock SessionLocal to use the test database engine.

    This ensures PhaseStateManager and other components use the test database
    instead of creating their own connection to the global database.
    """
    from sqlalchemy.orm import sessionmaker
    from autopack import database

    # Create a sessionmaker bound to the test engine
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    # Patch the SessionLocal in the database module
    with patch.object(database, "SessionLocal", TestingSessionLocal):
        yield
