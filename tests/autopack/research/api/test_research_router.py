"""Tests for Research API router endpoints.

Note: These tests require RESEARCH_API_MODE=full or AUTOPACK_ENV=development
to access the research endpoints. The router is mounted at /research prefix.
"""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from autopack.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def enable_full_mode():
    """Enable full mode for all tests in this module."""
    with patch.dict(os.environ, {"AUTOPACK_ENV": "development"}):
        yield


def test_get_research_sessions():
    """Test GET /research/sessions returns list of sessions."""
    response = client.get("/research/sessions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_research_session():
    """Test POST /research/sessions creates a new session."""
    response = client.post(
        "/research/sessions",
        json={"topic": "AI Research", "description": "Exploring new AI techniques"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["topic"] == "AI Research"
    assert data["description"] == "Exploring new AI techniques"
    assert data["status"] == "active"


def test_get_specific_research_session():
    """Test GET /research/sessions/{id} retrieves a specific session."""
    # First, create a session
    create_response = client.post(
        "/research/sessions",
        json={"topic": "AI Research", "description": "Exploring new AI techniques"},
    )
    session_id = create_response.json()["session_id"]

    # Now, retrieve the specific session
    response = client.get(f"/research/sessions/{session_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id


def test_get_nonexistent_research_session():
    """Test GET /research/sessions/{id} returns 404 for unknown session."""
    response = client.get("/research/sessions/nonexistent")
    assert response.status_code == 404
    assert response.json() == {"detail": "Session not found"}


def test_create_research_session_invalid():
    """Test POST /research/sessions rejects invalid input."""
    response = client.post("/research/sessions", json={"topic": "", "description": ""})
    assert response.status_code == 422
    # Pydantic v2 uses 'string_too_short' instead of 'value_error'
    detail = response.json()["detail"]
    assert any(
        "string_too_short" in d.get("type", "") or "value_error" in d.get("type", "")
        for d in detail
    )


def test_get_api_mode():
    """Test GET /research/mode returns current mode configuration."""
    response = client.get("/research/mode")
    assert response.status_code == 200
    data = response.json()
    assert "mode" in data
    assert "bootstrap_endpoints_enabled" in data
    assert "full_endpoints_enabled" in data
    assert "safety_gates" in data


if __name__ == "__main__":
    pytest.main()
