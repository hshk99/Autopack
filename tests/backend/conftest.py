"""Pytest configuration and fixtures for backend tests."""

import pytest
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture
def client() -> TestClient:
    """
    Create a test client for the FastAPI application.
    
    Returns:
        TestClient: Configured test client
    """
    return TestClient(app)


@pytest.fixture
def async_client():
    """Create an async test client for the FastAPI application."""
    from httpx import AsyncClient
    return AsyncClient(app=app, base_url="http://test")
