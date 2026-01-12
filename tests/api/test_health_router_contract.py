"""Contract tests for health router.

These tests verify the health router behavior contract is preserved
during the extraction from main.py to api/routes/health.py (PR-API-3a).
"""

import os
from unittest.mock import MagicMock, patch


class TestRootEndpointContract:
    """Contract tests for the root endpoint."""

    def test_root_returns_service_info(self):
        """Contract: Root endpoint returns service name, version, description."""
        from autopack.api.routes.health import read_root

        result = read_root()

        assert result["service"] == "Autopack Supervisor"
        assert "version" in result
        assert result["description"] == "v7 autonomous build playbook orchestrator"


class TestHealthEndpointContract:
    """Contract tests for the health check endpoint."""

    def test_health_returns_required_fields(self):
        """Contract: Health check returns all required fields."""
        from autopack.api.routes.health import health_check

        # Mock DB session
        mock_db = MagicMock()
        mock_db.execute.return_value = None
        mock_db.query.return_value.limit.return_value.all.return_value = []

        with patch.dict(os.environ, {"TESTING": "1"}, clear=False):
            result = health_check(db=mock_db)

        # Required fields
        assert "status" in result
        assert "timestamp" in result
        assert "database_identity" in result
        assert "database" in result
        assert "qdrant" in result
        assert "kill_switches" in result
        assert "version" in result
        assert "service" in result
        assert "component" in result

    def test_health_returns_healthy_when_db_connected(self):
        """Contract: Status is 'healthy' when database is connected."""
        from autopack.api.routes.health import health_check

        mock_db = MagicMock()
        mock_db.execute.return_value = None
        mock_db.query.return_value.limit.return_value.all.return_value = []

        result = health_check(db=mock_db)

        assert result["status"] == "healthy"
        assert result["database"] == "connected"

    def test_health_returns_degraded_when_db_fails(self):
        """Contract: Status is 'degraded' when database check fails."""
        from autopack.api.routes.health import health_check

        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("Connection failed")

        result = health_check(db=mock_db)

        assert result["status"] == "degraded"
        assert "error:" in result["database"]

    def test_health_qdrant_disabled_when_not_configured(self):
        """Contract: Qdrant shows 'disabled' when QDRANT_HOST not set."""
        from autopack.api.routes.health import health_check

        mock_db = MagicMock()
        mock_db.execute.return_value = None
        mock_db.query.return_value.limit.return_value.all.return_value = []

        # Ensure QDRANT_HOST is not set
        env = {k: v for k, v in os.environ.items() if k != "QDRANT_HOST"}
        with patch.dict(os.environ, env, clear=True):
            result = health_check(db=mock_db)

        assert result["qdrant"] == "disabled"

    def test_health_includes_kill_switches(self):
        """Contract: Kill switches are reported in health response."""
        from autopack.api.routes.health import health_check

        mock_db = MagicMock()
        mock_db.execute.return_value = None
        mock_db.query.return_value.limit.return_value.all.return_value = []

        with patch.dict(
            os.environ,
            {"AUTOPACK_ENABLE_PHASE6_METRICS": "1", "AUTOPACK_ENABLE_CONSOLIDATED_METRICS": "0"},
            clear=False,
        ):
            result = health_check(db=mock_db)

        assert result["kill_switches"]["phase6_metrics"] is True
        assert result["kill_switches"]["consolidated_metrics"] is False


class TestDatabaseIdentityContract:
    """Contract tests for database identity hash."""

    def test_database_identity_is_12_chars(self):
        """Contract: Database identity hash is 12 characters."""
        from autopack.api.routes.health import _get_database_identity

        identity = _get_database_identity()

        assert len(identity) == 12
        assert identity.isalnum()

    def test_database_identity_masks_credentials(self):
        """Contract: Database identity masks credentials in URL."""
        from autopack.api.routes.health import _get_database_identity

        # Even with credentials in URL, the identity should work
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://user:secret@localhost/db"},
            clear=False,
        ):
            identity = _get_database_identity()

        # Should still return 12-char hash
        assert len(identity) == 12

    def test_database_identity_normalizes_paths(self):
        """Contract: Database identity normalizes path separators."""
        from autopack.api.routes.health import _get_database_identity

        # Windows-style path
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "sqlite:///C:\\path\\to\\db.sqlite"},
            clear=False,
        ):
            windows_identity = _get_database_identity()

        # Unix-style path (normalized)
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "sqlite:///C:/path/to/db.sqlite"},
            clear=False,
        ):
            unix_identity = _get_database_identity()

        # Both should produce the same identity
        assert windows_identity == unix_identity


class TestQdrantConnectionContract:
    """Contract tests for Qdrant connection check."""

    def test_qdrant_disabled_when_no_host(self):
        """Contract: Returns 'disabled' when QDRANT_HOST not set."""
        from autopack.api.routes.health import _check_qdrant_connection

        env = {k: v for k, v in os.environ.items() if k != "QDRANT_HOST"}
        with patch.dict(os.environ, env, clear=True):
            result = _check_qdrant_connection()

        assert result == "disabled"

    def test_qdrant_connected_on_success(self):
        """Contract: Returns 'connected' when healthz returns 200."""
        from autopack.api.routes.health import _check_qdrant_connection

        with patch.dict(os.environ, {"QDRANT_HOST": "http://localhost:6333"}, clear=False):
            # requests is imported inside the function, so patch the actual module
            import sys

            mock_requests = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_requests.get.return_value = mock_response

            with patch.dict(sys.modules, {"requests": mock_requests}):
                result = _check_qdrant_connection()

        assert result == "connected"

    def test_qdrant_unhealthy_on_non_200(self):
        """Contract: Returns unhealthy status when healthz returns non-200."""
        from autopack.api.routes.health import _check_qdrant_connection

        with patch.dict(os.environ, {"QDRANT_HOST": "http://localhost:6333"}, clear=False):
            import sys

            mock_requests = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_requests.get.return_value = mock_response

            with patch.dict(sys.modules, {"requests": mock_requests}):
                result = _check_qdrant_connection()

        assert "unhealthy" in result
        assert "503" in result

    def test_qdrant_error_on_exception(self):
        """Contract: Returns error message on connection exception."""
        from autopack.api.routes.health import _check_qdrant_connection

        with patch.dict(os.environ, {"QDRANT_HOST": "http://localhost:6333"}, clear=False):
            import sys

            mock_requests = MagicMock()
            mock_requests.get.side_effect = Exception("Connection refused")

            with patch.dict(sys.modules, {"requests": mock_requests}):
                result = _check_qdrant_connection()

        assert "error:" in result
