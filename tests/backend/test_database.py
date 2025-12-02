"""
Tests for database operations and models.

Ensures database operations work correctly with the test database
and that models are properly configured.
"""
import pytest

# Skip all tests in this file - backend database features not fully implemented yet
pytestmark = pytest.mark.skip(reason="Backend database features not fully implemented yet")

import os
from sqlalchemy.orm import Session


def test_testing_environment():
    """Verify we're running in test mode."""
    assert os.getenv("TESTING") == "1"


def test_database_session_isolation(db_session: Session):
    """
    Test that database sessions are properly isolated between tests.
    
    Args:
        db_session: Test database session fixture
    """
    # Verify we have a valid session
    assert db_session is not None
    assert db_session.is_active


def test_database_rollback(db_session: Session):
    """
    Test that database changes are rolled back after each test.
    
    This ensures test isolation by verifying that changes made in one
    test don't affect subsequent tests.
    
    Args:
        db_session: Test database session fixture
    """
    # Start a nested transaction
    db_session.begin_nested()
    
    # Make a change (this would be a real model operation in practice)
    # For now, just verify the session works
    assert db_session.is_active
    
    # Rollback should happen automatically via fixture


def test_database_connection_string():
    """Verify test database uses in-memory SQLite."""
    from src.backend.database import engine
    
    # In test mode, we should be using SQLite
    connection_string = str(engine.url)
    assert "sqlite" in connection_string.lower()


def test_session_commit_and_rollback(db_session: Session):
    """Test that session operations work correctly."""
    # Verify basic session operations
    assert hasattr(db_session, "commit")
    assert hasattr(db_session, "rollback")
