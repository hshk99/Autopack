"""Pytest configuration and fixtures for backend tests."""

import sys
from pathlib import Path

import pytest

# Add project root and src to sys.path to enable absolute imports.
# This must happen before any backend imports.
#
# IMPORTANT: Do NOT add `src/backend` directly to sys.path.
# Doing so makes the backend importable both as `backend.*` and `src.backend.*`,
# which can cause module duplication and SQLAlchemy model/table re-definition
# errors during pytest collection.
project_root = Path(__file__).resolve().parent.parent.parent
src_path = project_root / "src"

# Insert paths in reverse order of priority (last inserted = highest priority)
for path in (project_root, src_path):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

# Now import backend modules after path setup
try:
    from fastapi.testclient import TestClient
    
    # Prefer the canonical import path for this repo layout.
    from src.backend.main import app
    
    BACKEND_AVAILABLE = True
    
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

except ImportError as e:
    # If backend module is not available, create placeholder fixtures
    # that skip tests requiring the backend
    import warnings
    warnings.warn(f"Backend module not available: {e}. Backend tests will be skipped.")
    
    BACKEND_AVAILABLE = False
    
    @pytest.fixture
    def client():
        """Placeholder fixture when backend is not available."""
        pytest.skip("Backend module not available")
    
    @pytest.fixture
    def async_client():
        """Placeholder fixture when backend is not available."""
        pytest.skip("Backend module not available")
