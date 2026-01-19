"""Tests for IMP-OPS-004: Readiness probe endpoint.

Tests the /ready endpoint which differs from /health (liveness) by:
- Returns 503 until all initialization is complete
- Checks database schema, not just connectivity
- Verifies optional dependencies are ready or disabled
- Tracks application initialization state
"""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestInitializationState:
    """Tests for the initialization state tracking."""

    def test_initial_state_not_initialized(self):
        """State starts as not initialized."""
        from autopack.api.routes.health import _InitializationState

        state = _InitializationState()
        assert state.is_initialized() is False
        assert state.get_errors() == []

    def test_mark_initialized(self):
        """mark_initialized sets state to True."""
        from autopack.api.routes.health import _InitializationState

        state = _InitializationState()
        state.mark_initialized()
        assert state.is_initialized() is True

    def test_mark_failed_records_error(self):
        """mark_failed records error messages."""
        from autopack.api.routes.health import _InitializationState

        state = _InitializationState()
        state.mark_failed("Test error 1")
        state.mark_failed("Test error 2")

        errors = state.get_errors()
        assert len(errors) == 2
        assert "Test error 1" in errors
        assert "Test error 2" in errors

    def test_reset_clears_state(self):
        """reset() clears all state."""
        from autopack.api.routes.health import _InitializationState

        state = _InitializationState()
        state.mark_initialized()
        state.mark_failed("Test error")

        state.reset()

        assert state.is_initialized() is False
        assert state.get_errors() == []


class TestReadinessEndpointContract:
    """Contract tests for the readiness probe endpoint."""

    def setup_method(self):
        """Reset initialization state before each test."""
        from autopack.api.routes.health import reset_initialization_state

        reset_initialization_state()

    def test_ready_returns_503_before_initialization(self):
        """Readiness returns 503 when app not initialized."""
        from autopack.api.routes.health import readiness_check

        mock_db = MagicMock()
        mock_db.execute.return_value = None
        mock_db.query.return_value.limit.return_value.all.return_value = []

        # Mock schema check to pass
        with patch(
            "autopack.api.routes.health._check_schema_initialized",
            return_value={"ready": True, "details": "ok", "table_count": 10},
        ):
            result = readiness_check(db=mock_db)

        # Should be JSONResponse with 503
        assert hasattr(result, "status_code")
        assert result.status_code == 503

    def test_ready_returns_200_after_initialization(self):
        """Readiness returns 200 when fully initialized."""
        from autopack.api.routes.health import mark_app_initialized, readiness_check

        # Mark as initialized
        mark_app_initialized()

        mock_db = MagicMock()
        mock_db.execute.return_value = None
        mock_db.query.return_value.limit.return_value.all.return_value = []

        # Mock schema check to pass
        with patch(
            "autopack.api.routes.health._check_schema_initialized",
            return_value={"ready": True, "details": "ok", "table_count": 10},
        ):
            result = readiness_check(db=mock_db)

        # Should be dict (200 OK)
        assert isinstance(result, dict)
        assert result["ready"] is True
        assert result["status"] == "ready"

    def test_ready_returns_required_fields(self):
        """Readiness response includes all required fields."""
        from autopack.api.routes.health import mark_app_initialized, readiness_check

        mark_app_initialized()

        mock_db = MagicMock()
        mock_db.execute.return_value = None
        mock_db.query.return_value.limit.return_value.all.return_value = []

        with patch(
            "autopack.api.routes.health._check_schema_initialized",
            return_value={"ready": True, "details": "ok", "table_count": 10},
        ):
            result = readiness_check(db=mock_db)

        # Required fields
        assert "ready" in result
        assert "status" in result
        assert "timestamp" in result
        assert "checks" in result
        assert "version" in result
        assert "service" in result
        assert "component" in result

        # Required checks
        assert "initialization" in result["checks"]
        assert "schema" in result["checks"]
        assert "database" in result["checks"]
        assert "dependencies" in result["checks"]

    def test_ready_shows_initialization_errors(self):
        """Readiness shows initialization errors in response."""
        from autopack.api.routes.health import (
            mark_initialization_failed,
            readiness_check,
        )

        mark_initialization_failed("Database init failed")

        mock_db = MagicMock()
        mock_db.execute.return_value = None
        mock_db.query.return_value.limit.return_value.all.return_value = []

        with patch(
            "autopack.api.routes.health._check_schema_initialized",
            return_value={"ready": True, "details": "ok", "table_count": 10},
        ):
            result = readiness_check(db=mock_db)

        # Should return 503
        assert hasattr(result, "status_code")
        assert result.status_code == 503

        # Check response body contains errors
        import json

        body = json.loads(result.body)
        assert body["checks"]["initialization"]["errors"] is not None
        assert "Database init failed" in body["checks"]["initialization"]["errors"]


class TestSchemaCheck:
    """Tests for database schema initialization check."""

    def test_schema_check_passes_with_required_tables(self):
        """Schema check passes when required tables exist."""
        from autopack.api.routes.health import _check_schema_initialized

        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = [
            "runs",
            "phases",
            "events",
            "users",
        ]

        with patch("autopack.api.routes.health.inspect", return_value=mock_inspector):
            result = _check_schema_initialized()

        assert result["ready"] is True
        assert result["table_count"] == 4

    def test_schema_check_fails_when_tables_missing(self):
        """Schema check fails when required tables are missing."""
        from autopack.api.routes.health import _check_schema_initialized

        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["users", "other"]

        with patch("autopack.api.routes.health.inspect", return_value=mock_inspector):
            result = _check_schema_initialized()

        assert result["ready"] is False
        assert "missing required tables" in result["details"]

    def test_schema_check_handles_exception(self):
        """Schema check returns error on exception."""
        from autopack.api.routes.health import _check_schema_initialized

        with patch(
            "autopack.api.routes.health.inspect",
            side_effect=Exception("DB connection failed"),
        ):
            result = _check_schema_initialized()

        assert result["ready"] is False
        assert "schema check failed" in result["details"]


class TestDatabaseReadyCheck:
    """Tests for database readiness check."""

    def test_database_ready_when_queryable(self):
        """Database is ready when queries succeed."""
        from autopack.api.routes.health import _check_database_ready

        mock_db = MagicMock()
        mock_db.execute.return_value = None
        mock_db.query.return_value.limit.return_value.all.return_value = []

        result = _check_database_ready(mock_db)

        assert result["ready"] is True
        assert "connected" in result["details"]

    def test_database_not_ready_on_error(self):
        """Database is not ready when queries fail."""
        from autopack.api.routes.health import _check_database_ready

        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("Connection refused")

        result = _check_database_ready(mock_db)

        assert result["ready"] is False
        assert "database error" in result["details"]


class TestDependenciesCheck:
    """Tests for optional dependencies readiness check."""

    def test_qdrant_disabled_when_not_configured(self):
        """Qdrant shows ready=True when disabled (no QDRANT_HOST)."""
        from autopack.api.routes.health import _check_dependencies_ready

        env = {k: v for k, v in os.environ.items() if k != "QDRANT_HOST"}
        with patch.dict(os.environ, env, clear=True):
            result = _check_dependencies_ready()

        assert result["qdrant"]["ready"] is True
        assert "disabled" in result["qdrant"]["details"]

    def test_qdrant_ready_when_connected(self):
        """Qdrant shows ready=True when connected."""
        from autopack.api.routes.health import _check_dependencies_ready

        with patch.dict(os.environ, {"QDRANT_HOST": "http://localhost:6333"}):
            with patch(
                "autopack.api.routes.health._check_qdrant_connection",
                return_value="connected",
            ):
                result = _check_dependencies_ready()

        assert result["qdrant"]["ready"] is True
        assert result["qdrant"]["details"] == "connected"

    def test_qdrant_not_ready_on_error(self):
        """Qdrant shows ready=False when connection fails."""
        from autopack.api.routes.health import _check_dependencies_ready

        with patch.dict(os.environ, {"QDRANT_HOST": "http://localhost:6333"}):
            with patch(
                "autopack.api.routes.health._check_qdrant_connection",
                return_value="error: connection refused",
            ):
                result = _check_dependencies_ready()

        assert result["qdrant"]["ready"] is False


class TestLifespanIntegration:
    """Tests for lifespan integration with readiness state."""

    def setup_method(self):
        """Reset initialization state before each test."""
        from autopack.api.routes.health import reset_initialization_state

        reset_initialization_state()

    @pytest.mark.asyncio
    async def test_lifespan_marks_initialized(self):
        """Lifespan context manager marks app as initialized."""
        from autopack.api.routes.health import _init_state

        # Verify not initialized before lifespan
        assert _init_state.is_initialized() is False

        # Import and run lifespan (mocking dependencies)
        from autopack.api.app import lifespan

        mock_app = MagicMock()

        with patch("autopack.api.app.get_api_key", return_value="test-key"):
            with patch("autopack.api.app.init_db"):
                with patch("autopack.api.app.approval_timeout_cleanup"):
                    with patch.dict(os.environ, {"TESTING": "0"}):
                        async with lifespan(mock_app):
                            # Inside lifespan, should be initialized
                            assert _init_state.is_initialized() is True

    @pytest.mark.asyncio
    async def test_lifespan_records_db_init_failure(self):
        """Lifespan records DB init failure."""
        from autopack.api.routes.health import _init_state

        from autopack.api.app import lifespan

        mock_app = MagicMock()

        with patch("autopack.api.app.get_api_key", return_value="test-key"):
            with patch(
                "autopack.api.app.init_db",
                side_effect=Exception("Schema missing"),
            ):
                with patch.dict(os.environ, {"TESTING": "0"}):
                    with pytest.raises(Exception, match="Schema missing"):
                        async with lifespan(mock_app):
                            pass

        # Should have recorded the error
        errors = _init_state.get_errors()
        assert len(errors) == 1
        assert "Database initialization failed" in errors[0]
