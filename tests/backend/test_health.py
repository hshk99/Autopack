"""Tests for health check endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    from src.backend.main import app
    return TestClient(app)


def test_health_check(client: TestClient) -> None:
    """Test the health check endpoint returns 200 OK."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data


def test_readiness_check(client: TestClient) -> None:
    """Test the readiness check endpoint returns 200 OK."""
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert "timestamp" in data


def test_root_endpoint(client: TestClient) -> None:
    """Test the root endpoint returns basic info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "version" in data


def test_api_docs_available(client: TestClient) -> None:
    """Test that API documentation is available."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
