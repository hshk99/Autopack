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


class TestBackgroundTaskMonitorContract:
    """Contract tests for BackgroundTaskMonitor (IMP-OPS-007)."""

    def test_monitor_record_run_resets_failure_count(self):
        """Contract: Recording a successful run resets failure count to zero."""
        from autopack.api.app import BackgroundTaskMonitor

        monitor = BackgroundTaskMonitor()
        monitor.record_failure("test_task")
        monitor.record_failure("test_task")
        assert monitor._failure_counts["test_task"] == 2

        monitor.record_run("test_task")
        assert monitor._failure_counts["test_task"] == 0

    def test_monitor_record_failure_increments_count(self):
        """Contract: Recording a failure increments the failure count."""
        from autopack.api.app import BackgroundTaskMonitor

        monitor = BackgroundTaskMonitor()
        assert monitor._failure_counts.get("test_task", 0) == 0

        monitor.record_failure("test_task")
        assert monitor._failure_counts["test_task"] == 1

        monitor.record_failure("test_task")
        assert monitor._failure_counts["test_task"] == 2

    def test_monitor_healthy_when_no_runs(self):
        """Contract: Task is healthy if it has never run (not yet expected)."""
        from autopack.api.app import BackgroundTaskMonitor

        monitor = BackgroundTaskMonitor()
        assert monitor.is_healthy("never_run_task") is True

    def test_monitor_unhealthy_when_too_many_failures(self):
        """Contract: Task is unhealthy when failure count exceeds threshold."""
        from autopack.api.app import BackgroundTaskMonitor

        monitor = BackgroundTaskMonitor(max_failures=3)
        monitor.record_failure("failing_task")
        monitor.record_failure("failing_task")
        assert monitor.is_healthy("failing_task") is True  # 2 failures, under threshold

        monitor.record_failure("failing_task")
        assert monitor.is_healthy("failing_task") is False  # 3 failures, at threshold

    def test_monitor_unhealthy_when_stale(self):
        """Contract: Task is unhealthy when last run exceeds max age."""
        from datetime import timedelta

        from autopack.api.app import BackgroundTaskMonitor

        monitor = BackgroundTaskMonitor(max_age_seconds=300)
        monitor.record_run("stale_task")

        # Manually set last run to be old
        from datetime import datetime, timezone

        monitor._last_run["stale_task"] = datetime.now(timezone.utc) - timedelta(seconds=400)

        assert monitor.is_healthy("stale_task") is False

    def test_monitor_healthy_when_recent_run(self):
        """Contract: Task is healthy when last run is within max age."""
        from autopack.api.app import BackgroundTaskMonitor

        monitor = BackgroundTaskMonitor(max_age_seconds=300)
        monitor.record_run("recent_task")

        assert monitor.is_healthy("recent_task") is True

    def test_monitor_get_task_status_returns_all_fields(self):
        """Contract: get_task_status returns all required fields."""
        from autopack.api.app import BackgroundTaskMonitor

        monitor = BackgroundTaskMonitor(max_age_seconds=300, max_failures=3)
        monitor.record_run("test_task")

        status = monitor.get_task_status("test_task")

        assert "healthy" in status
        assert "last_run" in status
        assert "age_seconds" in status
        assert "failure_count" in status
        assert "max_age_seconds" in status
        assert "max_failures" in status

    def test_monitor_get_all_status_includes_all_tasks(self):
        """Contract: get_all_status includes all tracked tasks."""
        from autopack.api.app import BackgroundTaskMonitor

        monitor = BackgroundTaskMonitor()
        monitor.record_run("task_a")
        monitor.record_failure("task_b")

        all_status = monitor.get_all_status()

        assert "task_a" in all_status
        assert "task_b" in all_status
        assert all_status["task_a"]["healthy"] is True
        assert all_status["task_b"]["failure_count"] == 1

    def test_monitor_is_all_healthy_returns_true_when_all_healthy(self):
        """Contract: is_all_healthy returns True when all tasks are healthy."""
        from autopack.api.app import BackgroundTaskMonitor

        monitor = BackgroundTaskMonitor()
        monitor.record_run("task_a")
        monitor.record_run("task_b")

        assert monitor.is_all_healthy() is True

    def test_monitor_is_all_healthy_returns_false_when_any_unhealthy(self):
        """Contract: is_all_healthy returns False when any task is unhealthy."""
        from autopack.api.app import BackgroundTaskMonitor

        monitor = BackgroundTaskMonitor(max_failures=2)
        monitor.record_run("healthy_task")
        monitor.record_failure("failing_task")
        monitor.record_failure("failing_task")

        assert monitor.is_all_healthy() is False


class TestBackgroundTaskHealthEndpointContract:
    """Contract tests for /health/tasks endpoint (IMP-OPS-007)."""

    def test_health_tasks_returns_required_fields(self):
        """Contract: /health/tasks returns all required fields."""
        from autopack.api.routes.health import background_task_health

        with patch("autopack.api.routes.health._check_background_tasks") as mock_check:
            mock_check.return_value = {"status": "healthy", "tasks": {}}
            result = background_task_health()

        assert "status" in result
        assert "tasks" in result
        assert "timestamp" in result

    def test_health_tasks_returns_initializing_when_monitor_not_ready(self):
        """Contract: Returns 'initializing' status when monitor not initialized."""
        from autopack.api.routes.health import _check_background_tasks

        with patch("autopack.api.app.get_task_monitor") as mock_get:
            mock_get.side_effect = RuntimeError("Task monitor not initialized")
            result = _check_background_tasks()

        assert result["status"] == "initializing"
        assert result["tasks"] == {}

    def test_health_tasks_returns_healthy_when_all_tasks_healthy(self):
        """Contract: Returns 'healthy' status when all tasks are healthy."""
        from autopack.api.routes.health import _check_background_tasks

        mock_monitor = MagicMock()
        mock_monitor.get_all_status.return_value = {"task1": {"healthy": True}}
        mock_monitor.is_all_healthy.return_value = True

        with patch("autopack.api.app.get_task_monitor") as mock_get:
            mock_get.return_value = mock_monitor
            result = _check_background_tasks()

        assert result["status"] == "healthy"

    def test_health_tasks_returns_degraded_when_task_unhealthy(self):
        """Contract: Returns 'degraded' status when any task is unhealthy."""
        from autopack.api.routes.health import _check_background_tasks

        mock_monitor = MagicMock()
        mock_monitor.get_all_status.return_value = {"task1": {"healthy": False}}
        mock_monitor.is_all_healthy.return_value = False

        with patch("autopack.api.app.get_task_monitor") as mock_get:
            mock_get.return_value = mock_monitor
            result = _check_background_tasks()

        assert result["status"] == "degraded"


class TestHealthEndpointBackgroundTasksContract:
    """Contract tests for background task inclusion in /health endpoint (IMP-OPS-007)."""

    def test_health_includes_background_tasks(self):
        """Contract: /health endpoint includes background_tasks field."""
        from autopack.api.routes.health import health_check

        mock_db = MagicMock()
        mock_db.execute.return_value = None
        mock_db.query.return_value.limit.return_value.all.return_value = []

        with patch("autopack.api.routes.health._check_background_tasks") as mock_check:
            mock_check.return_value = {"status": "healthy", "tasks": {}}
            result = health_check(db=mock_db)

        assert "background_tasks" in result

    def test_health_degraded_when_background_tasks_degraded(self):
        """Contract: /health returns degraded when background tasks are degraded."""
        from autopack.api.routes.health import health_check

        mock_db = MagicMock()
        mock_db.execute.return_value = None
        mock_db.query.return_value.limit.return_value.all.return_value = []

        with patch("autopack.api.routes.health._check_background_tasks") as mock_check:
            mock_check.return_value = {"status": "degraded", "tasks": {"task1": {"healthy": False}}}
            result = health_check(db=mock_db)

        assert result["status"] == "degraded"
        assert result["background_tasks"]["status"] == "degraded"

    def test_health_healthy_when_background_tasks_healthy(self):
        """Contract: /health returns healthy when background tasks are healthy."""
        from autopack.api.routes.health import health_check

        mock_db = MagicMock()
        mock_db.execute.return_value = None
        mock_db.query.return_value.limit.return_value.all.return_value = []

        with patch("autopack.api.routes.health._check_background_tasks") as mock_check:
            mock_check.return_value = {"status": "healthy", "tasks": {"task1": {"healthy": True}}}
            result = health_check(db=mock_db)

        assert result["status"] == "healthy"
        assert result["background_tasks"]["status"] == "healthy"
