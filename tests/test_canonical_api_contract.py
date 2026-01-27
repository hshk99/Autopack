"""Contract tests for canonical Autopack API.

BUILD-146 P12 API Consolidation - Phase 5 (Complete):
These tests ensure the canonical server (autopack.main:app) provides all
required endpoints with auth migrated to autopack.auth namespace.

Test coverage:
1. Run lifecycle endpoints (executor needs)
2. Enhanced health check (DB identity + kill switches)
3. Dashboard endpoints
4. Consolidated metrics endpoint (with kill switch)
5. Auth endpoints at /api/auth/* (migrated from backend.api.auth)
6. Kill switches default to OFF
"""

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def canonical_client(tmp_path):
    """TestClient for canonical server (autopack.main:app)."""
    # Use tmp_path for isolated test database
    test_db = tmp_path / "test_canonical.db"

    # Ensure clean environment for tests
    os.environ["TESTING"] = "1"
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"

    # Ensure kill switches are OFF by default
    os.environ.pop("AUTOPACK_ENABLE_CONSOLIDATED_METRICS", None)
    os.environ.pop("AUTOPACK_ENABLE_PHASE6_METRICS", None)

    # Recreate database engine with test DATABASE_URL
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import autopack.database

    autopack.database.engine = create_engine(
        f"sqlite:///{test_db}",
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"check_same_thread": False},  # Allow multi-threading for tests
    )
    autopack.database.SessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=autopack.database.engine
    )

    # Initialize database with tables
    from unittest.mock import patch

    from autopack.database import init_db

    # Enable bootstrap mode to allow table creation on empty DB
    with patch("autopack.config.settings") as mock_settings:
        mock_settings.db_bootstrap_enabled = True
        init_db()

    from autopack.main import app

    client = TestClient(app)

    yield client

    # Cleanup happens automatically with tmp_path


class TestCanonicalServerContract:
    """Test that canonical server provides all required endpoints."""

    def test_health_endpoint_enhanced(self, canonical_client):
        """Test /health endpoint has enhanced fields (BUILD-146 P12)."""
        response = canonical_client.get("/health")

        assert response.status_code == 200
        data = response.json()

        # Required fields from BUILD-146 P12 enhancement
        assert "status" in data
        assert "timestamp" in data
        assert "database_identity" in data
        assert "database" in data
        assert "qdrant" in data
        assert "kill_switches" in data
        assert "version" in data
        assert "service" in data
        assert "component" in data

        # DB should be connected in test mode
        assert data["database"] == "connected"

        # Qdrant should be disabled (not configured)
        assert data["qdrant"] == "disabled"

        # Kill switches should exist and be OFF by default
        assert isinstance(data["kill_switches"], dict)
        assert "phase6_metrics" in data["kill_switches"]
        assert "consolidated_metrics" in data["kill_switches"]
        assert data["kill_switches"]["phase6_metrics"] is False
        assert data["kill_switches"]["consolidated_metrics"] is False

    def test_run_lifecycle_endpoints_exist(self, canonical_client):
        """Test that run lifecycle endpoints exist (executor needs)."""
        # These endpoints are required by the autonomous executor

        # GET /runs/{run_id} - should return 404 for non-existent run
        response = canonical_client.get("/runs/test-run-id")
        assert response.status_code in [404, 503]  # 404 or 503 (DB issue)

        # POST /runs/start - should return 400 (missing auth) or work
        response = canonical_client.post(
            "/runs/start", json={"run": {"run_id": "test"}, "tiers": [], "phases": []}
        )
        # Should either work (201) or require validation (400/422)
        assert response.status_code in [201, 400, 422]

    def test_dashboard_endpoints_exist(self, canonical_client):
        """Test that dashboard endpoints exist."""
        # GET /dashboard/usage
        response = canonical_client.get("/dashboard/usage")
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert "models" in data

        # GET /dashboard/models
        response = canonical_client.get("/dashboard/models")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_consolidated_metrics_kill_switch_default_off(self, canonical_client):
        """Test that consolidated metrics endpoint has kill switch OFF by default."""
        # Ensure kill switch is not set
        os.environ.pop("AUTOPACK_ENABLE_CONSOLIDATED_METRICS", None)

        response = canonical_client.get("/dashboard/runs/test-run/consolidated-metrics")

        # Should return 503 (service unavailable) when kill switch is OFF
        assert response.status_code == 503
        assert "Consolidated metrics disabled" in response.json()["detail"]
        assert "AUTOPACK_ENABLE_CONSOLIDATED_METRICS=1" in response.json()["detail"]

    def test_consolidated_metrics_kill_switch_enabled(self, canonical_client):
        """Test that consolidated metrics work when kill switch is ON."""
        # Enable kill switch
        os.environ["AUTOPACK_ENABLE_CONSOLIDATED_METRICS"] = "1"

        # Reload app to pick up env change
        from autopack.main import app

        client = TestClient(app)

        response = client.get("/dashboard/runs/test-run/consolidated-metrics")

        # Should return 404 (run not found) instead of 503 (disabled)
        assert response.status_code == 404
        assert "Run not found" in response.json()["detail"]

        # Clean up
        os.environ.pop("AUTOPACK_ENABLE_CONSOLIDATED_METRICS", None)

    def test_consolidated_metrics_pagination_validation(self, canonical_client):
        """Test that consolidated metrics enforces pagination limits."""
        # Enable kill switch for this test
        os.environ["AUTOPACK_ENABLE_CONSOLIDATED_METRICS"] = "1"

        # Reload app
        from autopack.main import app

        client = TestClient(app)

        # Test limit validation (max 10000)
        response = client.get("/dashboard/runs/test-run/consolidated-metrics?limit=20000")
        assert response.status_code == 400
        assert "cannot exceed 10000" in response.json()["detail"]

        # Test offset validation (cannot be negative)
        response = client.get("/dashboard/runs/test-run/consolidated-metrics?offset=-1")
        assert response.status_code == 400
        assert "cannot be negative" in response.json()["detail"]

        # Clean up
        os.environ.pop("AUTOPACK_ENABLE_CONSOLIDATED_METRICS", None)

    def test_auth_endpoints_exist(self, canonical_client):
        """Test that auth endpoints exist at SOT paths (/api/auth/...)."""
        # POST /api/auth/login - should return 400/422 (missing credentials)
        response = canonical_client.post("/api/auth/login")
        assert response.status_code in [400, 422]

        # GET /api/auth/.well-known/jwks.json - should return JWKS (SOT path)
        response = canonical_client.get("/api/auth/.well-known/jwks.json")
        # Should work or return error based on config
        assert response.status_code in [200, 404, 500]

        # GET /api/auth/key-status - should return key status (SOT endpoint)
        response = canonical_client.get("/api/auth/key-status")
        assert response.status_code == 200
        data = response.json()
        assert "keys_loaded" in data or "status" in data

    def test_approval_endpoints_exist(self, canonical_client):
        """Test that approval workflow endpoints exist."""
        # GET /approval/pending
        response = canonical_client.get("/approval/pending")
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "requests" in data


class TestKillSwitchDefaults:
    """Test that all kill switches default to OFF."""

    def test_phase6_metrics_kill_switch_default_off(self):
        """Test that AUTOPACK_ENABLE_PHASE6_METRICS defaults to OFF."""
        # Ensure not set in environment
        os.environ.pop("AUTOPACK_ENABLE_PHASE6_METRICS", None)

        # Import fresh to pick up env state
        from autopack.main import app

        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["kill_switches"]["phase6_metrics"] is False

    def test_consolidated_metrics_kill_switch_default_off(self):
        """Test that AUTOPACK_ENABLE_CONSOLIDATED_METRICS defaults to OFF."""
        # Ensure not set in environment
        os.environ.pop("AUTOPACK_ENABLE_CONSOLIDATED_METRICS", None)

        from autopack.main import app

        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["kill_switches"]["consolidated_metrics"] is False


class TestDatabaseIdentityHash:
    """Test database identity hash for drift detection."""

    def test_database_identity_hash_format(self, canonical_client):
        """Test that database_identity is a 12-character hash."""
        response = canonical_client.get("/health")
        assert response.status_code == 200

        data = response.json()
        db_identity = data["database_identity"]

        # Should be a 12-character hex string
        assert isinstance(db_identity, str)
        assert len(db_identity) == 12
        assert all(c in "0123456789abcdef" for c in db_identity)

    def test_database_identity_masks_credentials(self, canonical_client):
        """Test that database identity hash masks credentials."""
        # Set a DB URL with credentials
        os.environ["DATABASE_URL"] = "postgresql://user:password@localhost/testdb"

        from autopack.main import app

        client = TestClient(app)

        response = client.get("/health")

        # Even with credentials in URL, response should not leak them
        # (identity hash should be different from raw URL hash)
        assert "password" not in response.text
        assert "user:password" not in response.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
