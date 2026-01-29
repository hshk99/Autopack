"""Tests for API key authentication.

Phase 4: Simplified auth for multi-device access.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from autopack.auth.api_key import generate_api_key, get_api_key_from_db, verify_api_key
from autopack.auth.models import APIKey
from autopack.database import Base, engine, get_db


@pytest.fixture
def test_db():
    """Create a test database session."""
    # Create tables
    Base.metadata.create_all(bind=engine)

    # Create session
    session = next(get_db())

    yield session

    # Cleanup
    session.rollback()
    session.close()


def test_generate_api_key():
    """Test API key generation."""
    plain_key, hashed_key = generate_api_key()

    # Check format
    assert plain_key.startswith("autopack_")
    assert len(plain_key) > 20  # Should be reasonably long
    assert len(hashed_key) == 64  # SHA256 hex = 64 characters

    # Verify the key
    assert verify_api_key(plain_key, hashed_key)

    # Wrong key should not verify
    assert not verify_api_key("wrong_key", hashed_key)


def test_api_key_database_storage(test_db: Session):
    """Test storing and retrieving API keys from database."""
    plain_key, hashed_key = generate_api_key()

    # Create API key in database
    api_key = APIKey(
        name="Test Key",
        key_hash=hashed_key,
        description="A test API key",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(api_key)
    test_db.commit()
    test_db.refresh(api_key)

    # Verify it was stored
    assert api_key.id is not None
    assert api_key.name == "Test Key"
    assert api_key.key_hash == hashed_key
    assert api_key.is_active is True

    # Verify we can retrieve it
    retrieved = get_api_key_from_db(test_db, plain_key)
    assert retrieved is not None
    assert retrieved.id == api_key.id
    assert retrieved.name == "Test Key"


def test_api_key_authentication_with_db(test_db: Session):
    """Test that API key authentication works with database."""
    plain_key, hashed_key = generate_api_key()

    # Create active API key
    api_key = APIKey(
        name="Auth Test Key",
        key_hash=hashed_key,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(api_key)
    test_db.commit()

    # Valid key should authenticate
    result = get_api_key_from_db(test_db, plain_key)
    assert result is not None
    assert result.name == "Auth Test Key"

    # Invalid key should not authenticate
    result = get_api_key_from_db(test_db, "invalid_key")
    assert result is None

    # Inactive key should not authenticate
    api_key.is_active = False
    test_db.commit()
    result = get_api_key_from_db(test_db, plain_key)
    assert result is None


def test_api_key_last_used_tracking(test_db: Session):
    """Test that last_used_at is updated when key is used."""
    plain_key, hashed_key = generate_api_key()

    # Create API key
    api_key = APIKey(
        name="Usage Tracking Key",
        key_hash=hashed_key,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        last_used_at=None,
    )
    test_db.add(api_key)
    test_db.commit()

    # Initially last_used_at should be None
    assert api_key.last_used_at is None

    # Use the key
    result = get_api_key_from_db(test_db, plain_key)
    assert result is not None

    # Check that last_used_at was updated
    test_db.refresh(api_key)
    assert api_key.last_used_at is not None
