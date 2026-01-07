"""Contract tests for OpenAPI strategy (BUILD-191).

Verifies:
1. Runtime OpenAPI is accessible and valid
2. No checked-in openapi.json exists (runtime-canonical strategy)
3. OpenAPI contains required metadata
"""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# Repository root for file existence checks
REPO_ROOT = Path(__file__).parent.parent.parent


@pytest.fixture
def api_client(tmp_path):
    """TestClient for OpenAPI verification."""
    # Use tmp_path for isolated test database
    test_db = tmp_path / "test_openapi.db"

    # Ensure clean environment for tests
    os.environ["TESTING"] = "1"
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"

    # Recreate database engine with test DATABASE_URL
    import autopack.database
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    autopack.database.engine = create_engine(
        f"sqlite:///{test_db}",
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"check_same_thread": False},
    )
    autopack.database.SessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=autopack.database.engine
    )

    # Initialize database with tables
    from autopack.database import init_db
    from unittest.mock import patch

    with patch("autopack.config.settings") as mock_settings:
        mock_settings.db_bootstrap_enabled = True
        init_db()

    from autopack.main import app

    return TestClient(app)


class TestOpenAPIRuntimeCanonical:
    """Test that OpenAPI is served at runtime (canonical)."""

    def test_openapi_json_accessible(self, api_client):
        """Test /openapi.json endpoint is accessible."""
        response = api_client.get("/openapi.json")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

    def test_openapi_has_required_metadata(self, api_client):
        """Test OpenAPI contains required metadata fields."""
        response = api_client.get("/openapi.json")
        assert response.status_code == 200

        schema = response.json()

        # Required OpenAPI 3.0 fields
        assert "openapi" in schema
        assert schema["openapi"].startswith("3.")

        # Info object with title and version
        assert "info" in schema
        assert "title" in schema["info"]
        assert "version" in schema["info"]
        assert schema["info"]["title"] == "Autopack Supervisor"

        # Must have paths defined
        assert "paths" in schema
        assert len(schema["paths"]) > 0

    def test_openapi_includes_health_endpoint(self, api_client):
        """Test OpenAPI includes the /health endpoint."""
        response = api_client.get("/openapi.json")
        schema = response.json()

        assert "/health" in schema["paths"]

    def test_openapi_includes_runs_endpoints(self, api_client):
        """Test OpenAPI includes run management endpoints."""
        response = api_client.get("/openapi.json")
        schema = response.json()

        # Key executor endpoints
        run_endpoints = [p for p in schema["paths"] if p.startswith("/runs")]
        assert len(run_endpoints) > 0, "Expected /runs/* endpoints in OpenAPI schema"

    def test_swagger_ui_accessible(self, api_client):
        """Test Swagger UI (/docs) is accessible."""
        response = api_client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_redoc_accessible(self, api_client):
        """Test ReDoc (/redoc) is accessible."""
        response = api_client.get("/redoc")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestOpenAPINotCheckedIn:
    """Test that OpenAPI is NOT checked into git (runtime-canonical strategy)."""

    def test_no_checked_in_openapi_json(self):
        """Verify no docs/api/openapi.json is committed.

        BUILD-191: OpenAPI is runtime-canonical. Checking in openapi.json
        would create "two truths" that can drift.
        """
        checked_in_openapi = REPO_ROOT / "docs" / "api" / "openapi.json"
        assert not checked_in_openapi.exists(), (
            f"Found checked-in {checked_in_openapi}. "
            "OpenAPI should be runtime-generated, not committed. "
            "See docs/api/OPENAPI_STRATEGY.md for the canonical strategy."
        )

    def test_no_checked_in_openapi_yaml(self):
        """Verify no docs/api/openapi.yaml is committed."""
        checked_in_openapi = REPO_ROOT / "docs" / "api" / "openapi.yaml"
        assert not checked_in_openapi.exists(), (
            f"Found checked-in {checked_in_openapi}. "
            "OpenAPI should be runtime-generated, not committed."
        )

    def test_openapi_strategy_doc_exists(self):
        """Verify the OpenAPI strategy documentation exists."""
        strategy_doc = REPO_ROOT / "docs" / "api" / "OPENAPI_STRATEGY.md"
        assert strategy_doc.exists(), (
            f"Missing {strategy_doc}. "
            "This document defines the runtime-canonical OpenAPI strategy."
        )


class TestOpenAPIVersionConsistency:
    """Test OpenAPI version matches package version."""

    def test_openapi_version_matches_package(self, api_client):
        """Test OpenAPI version matches autopack.__version__."""
        from autopack.version import __version__

        response = api_client.get("/openapi.json")
        schema = response.json()

        assert schema["info"]["version"] == __version__, (
            f"OpenAPI version ({schema['info']['version']}) "
            f"does not match package version ({__version__})"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
