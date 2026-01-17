"""Tests for API key endpoint authentication.

IMP-SEC-001: Verify that create_api_key endpoint requires authentication.
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
