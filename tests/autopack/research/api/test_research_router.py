import pytest
from fastapi.testclient import TestClient
from autopack.main import app

client = TestClient(app)


def test_get_research_sessions():
    response = client.get("/api/research/sessions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_research_session():
    response = client.post(
        "/api/research/sessions",
        json={"topic": "AI Research", "description": "Exploring new AI techniques"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["topic"] == "AI Research"
    assert data["description"] == "Exploring new AI techniques"
    assert data["status"] == "active"


def test_get_specific_research_session():
    # First, create a session
    create_response = client.post(
        "/api/research/sessions",
        json={"topic": "AI Research", "description": "Exploring new AI techniques"},
    )
    session_id = create_response.json()["session_id"]

    # Now, retrieve the specific session
    response = client.get(f"/api/research/sessions/{session_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id


def test_get_nonexistent_research_session():
    response = client.get("/api/research/sessions/nonexistent")
    assert response.status_code == 404
    assert response.json() == {"detail": "Session not found"}


def test_create_research_session_invalid():
    response = client.post("/api/research/sessions", json={"topic": "", "description": ""})
    assert response.status_code == 422
    assert "value_error" in response.json()["detail"][0]["type"]


if __name__ == "__main__":
    pytest.main()
