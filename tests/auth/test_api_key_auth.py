"""Tests for API key endpoint authentication.

IMP-SEC-001: Verify that create_api_key endpoint requires authentication.
IMP-SEC-004: Verify ownership-based access control for API keys.
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from autopack.auth.api_key import generate_api_key
from autopack.auth.models import APIKey


def test_create_api_key_requires_auth(client: TestClient):
    """Verify create_api_key returns 401 without auth."""
    # Clear TESTING env to test real auth behavior
    import os

    saved_testing = os.environ.pop("TESTING", None)
    try:
        response = client.post("/api/auth/api-keys", json={"name": "test"})
        assert response.status_code == 401
    finally:
        if saved_testing:
            os.environ["TESTING"] = saved_testing


def test_create_api_key_works_with_auth(client: TestClient, db_session):
    """Verify create_api_key works with authentication."""
    # Create a valid API key in the database for authentication
    plain_key, hashed_key = generate_api_key()
    auth_key = APIKey(
        name="Auth Key",
        key_hash=hashed_key,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(auth_key)
    db_session.commit()

    # Make request with valid API key
    response = client.post(
        "/api/auth/api-keys",
        json={"name": "new-key"},
        headers={"X-API-Key": plain_key},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "new-key"
    assert "key" in data  # Should return the plain key


def test_create_api_key_rejects_invalid_key(client: TestClient):
    """Verify create_api_key rejects invalid API key."""
    import os

    saved_testing = os.environ.pop("TESTING", None)
    try:
        response = client.post(
            "/api/auth/api-keys",
            json={"name": "test"},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code in [401, 403]  # Either unauthorized or forbidden
    finally:
        if saved_testing:
            os.environ["TESTING"] = saved_testing


# IMP-SEC-004: Ownership-based access control tests


def test_list_api_keys_only_shows_owned_keys(client: TestClient, db_session):
    """IMP-SEC-004: Verify list only returns keys owned by current key."""
    # Create two separate API keys (neither owns the other)
    plain_key1, hashed_key1 = generate_api_key()
    key1 = APIKey(
        name="Key 1",
        key_hash=hashed_key1,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        created_by_key_id=None,  # Root key, no owner
    )
    db_session.add(key1)
    db_session.commit()
    db_session.refresh(key1)

    plain_key2, hashed_key2 = generate_api_key()
    key2 = APIKey(
        name="Key 2",
        key_hash=hashed_key2,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        created_by_key_id=None,  # Root key, no owner
    )
    db_session.add(key2)
    db_session.commit()

    # Key 1 should only see itself
    response = client.get("/api/auth/api-keys", headers={"X-API-Key": plain_key1})
    assert response.status_code == 200
    keys = response.json()
    assert len(keys) == 1
    assert keys[0]["name"] == "Key 1"


def test_list_api_keys_shows_created_keys(client: TestClient, db_session):
    """IMP-SEC-004: Verify list returns keys created by current key."""
    # Create parent key
    plain_key_parent, hashed_key_parent = generate_api_key()
    parent_key = APIKey(
        name="Parent Key",
        key_hash=hashed_key_parent,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(parent_key)
    db_session.commit()
    db_session.refresh(parent_key)

    # Create child key owned by parent
    plain_key_child, hashed_key_child = generate_api_key()
    child_key = APIKey(
        name="Child Key",
        key_hash=hashed_key_child,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        created_by_key_id=parent_key.id,
    )
    db_session.add(child_key)
    db_session.commit()

    # Parent should see both itself and child
    response = client.get("/api/auth/api-keys", headers={"X-API-Key": plain_key_parent})
    assert response.status_code == 200
    keys = response.json()
    assert len(keys) == 2
    key_names = {k["name"] for k in keys}
    assert "Parent Key" in key_names
    assert "Child Key" in key_names


def test_revoke_api_key_ownership_check(client: TestClient, db_session):
    """IMP-SEC-004: Verify users cannot revoke keys they don't own."""
    import os

    saved_testing = os.environ.pop("TESTING", None)
    try:
        # Create two unrelated keys
        plain_key1, hashed_key1 = generate_api_key()
        key1 = APIKey(
            name="Key 1",
            key_hash=hashed_key1,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(key1)
        db_session.commit()
        db_session.refresh(key1)

        plain_key2, hashed_key2 = generate_api_key()
        key2 = APIKey(
            name="Key 2",
            key_hash=hashed_key2,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(key2)
        db_session.commit()
        db_session.refresh(key2)

        # Key 1 tries to revoke Key 2 - should fail
        response = client.delete(
            f"/api/auth/api-keys/{key2.id}",
            headers={"X-API-Key": plain_key1},
        )
        assert response.status_code == 403
        assert "own" in response.json()["detail"].lower()
    finally:
        if saved_testing:
            os.environ["TESTING"] = saved_testing


def test_revoke_own_created_key(client: TestClient, db_session):
    """IMP-SEC-004: Verify users can revoke keys they created."""
    # Create parent key
    plain_key_parent, hashed_key_parent = generate_api_key()
    parent_key = APIKey(
        name="Parent Key",
        key_hash=hashed_key_parent,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(parent_key)
    db_session.commit()
    db_session.refresh(parent_key)

    # Create child key owned by parent
    plain_key_child, hashed_key_child = generate_api_key()
    child_key = APIKey(
        name="Child Key",
        key_hash=hashed_key_child,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        created_by_key_id=parent_key.id,
    )
    db_session.add(child_key)
    db_session.commit()
    db_session.refresh(child_key)

    # Parent should be able to revoke child
    response = client.delete(
        f"/api/auth/api-keys/{child_key.id}",
        headers={"X-API-Key": plain_key_parent},
    )
    assert response.status_code == 204

    # Verify child is now inactive
    db_session.refresh(child_key)
    assert child_key.is_active is False


def test_created_key_has_owner_set(client: TestClient, db_session):
    """IMP-SEC-004: Verify new keys have created_by_key_id set."""
    # Create a parent key
    plain_key, hashed_key = generate_api_key()
    parent_key = APIKey(
        name="Parent Key",
        key_hash=hashed_key,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(parent_key)
    db_session.commit()
    db_session.refresh(parent_key)

    # Create a new key via the API
    response = client.post(
        "/api/auth/api-keys",
        json={"name": "Child Key"},
        headers={"X-API-Key": plain_key},
    )
    assert response.status_code == 201
    new_key_id = response.json()["id"]

    # Verify the new key has the parent as owner
    new_key = db_session.query(APIKey).filter(APIKey.id == new_key_id).first()
    assert new_key.created_by_key_id == parent_key.id
