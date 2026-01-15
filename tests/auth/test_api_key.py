"""Tests for API key authentication.

Phase 4: Simplified auth for multi-device access.
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from autopack.auth.api_key import generate_api_key, verify_api_key
from autopack.auth.models import APIKey


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


def test_api_key_creation(client: TestClient, db: Session):
    """Test creating an API key via the API."""
    response = client.post(
        "/api/auth/api-keys",
        json={
            "name": "Test Key",
            "description": "A test API key",
        },
    )

    assert response.status_code == 201
    data = response.json()

    assert data["name"] == "Test Key"
    assert data["description"] == "A test API key"
    assert "key" in data
    assert data["key"].startswith("autopack_")
    assert "id" in data
    assert "created_at" in data


def test_api_key_authentication(client: TestClient, db: Session):
    """Test that API key authentication works."""
    # Create an API key
    create_response = client.post(
        "/api/auth/api-keys",
        json={"name": "Auth Test Key"},
    )
    assert create_response.status_code == 201
    api_key = create_response.json()["key"]

    # Try to access protected endpoint without key
    response = client.get("/api/auth/api-keys")
    assert response.status_code == 401

    # Try with invalid key
    response = client.get(
        "/api/auth/api-keys",
        headers={"X-API-Key": "invalid_key"},
    )
    assert response.status_code == 403

    # Try with valid key
    response = client.get(
        "/api/auth/api-keys",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    keys = response.json()
    assert len(keys) >= 1
    assert any(k["name"] == "Auth Test Key" for k in keys)


def test_api_key_revocation(client: TestClient, db: Session):
    """Test revoking an API key."""
    # Create an API key
    create_response = client.post(
        "/api/auth/api-keys",
        json={"name": "Revoke Test Key"},
    )
    api_key = create_response.json()["key"]
    key_id = create_response.json()["id"]

    # Revoke the key
    response = client.delete(
        f"/api/auth/api-keys/{key_id}",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 204

    # Try to use the revoked key
    response = client.get(
        "/api/auth/api-keys",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 403  # Should be forbidden now


def test_api_key_last_used_tracking(client: TestClient, db: Session):
    """Test that last_used_at is updated when key is used."""
    # Create an API key
    create_response = client.post(
        "/api/auth/api-keys",
        json={"name": "Usage Tracking Key"},
    )
    api_key_str = create_response.json()["key"]
    key_id = create_response.json()["id"]

    # Check initial state (last_used_at should be None)
    key_model = db.query(APIKey).filter(APIKey.id == key_id).first()
    assert key_model.last_used_at is None

    # Use the key
    response = client.get(
        "/api/auth/api-keys",
        headers={"X-API-Key": api_key_str},
    )
    assert response.status_code == 200

    # Check that last_used_at was updated
    db.refresh(key_model)
    assert key_model.last_used_at is not None


def test_api_key_list_shows_metadata_only(client: TestClient, db: Session):
    """Test that listing keys doesn't expose the actual key values."""
    # Create a key
    create_response = client.post(
        "/api/auth/api-keys",
        json={"name": "Metadata Test Key"},
    )
    api_key = create_response.json()["key"]

    # List keys
    response = client.get(
        "/api/auth/api-keys",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200

    keys = response.json()
    # Check that no key values are exposed
    for key in keys:
        assert "key" not in key
        assert "key_hash" not in key
        assert "name" in key
        assert "is_active" in key
