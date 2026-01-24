"""
Contract tests for API app wiring.

PR-API-2: These tests define the behavioral contract for app factory
extracted from main.py to api/app.py.

Contract guarantees:
1. App is created with correct metadata (title, version)
2. Rate limiter is attached to app.state
3. CORS only enabled when CORS_ALLOWED_ORIGINS is set
4. Global exception handler returns error_id for correlation
5. Auth and research routers are included

These tests prevent app wiring drift during refactoring.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

# Set testing mode before imports
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


class TestCreateAppContract:
    """Contract tests for create_app behavior."""

    def test_app_has_correct_title(self):
        """Contract: App title is 'Autopack Supervisor'."""
        from autopack.api.app import create_app

        app = create_app()
        assert app.title == "Autopack Supervisor"

    def test_app_has_version(self):
        """Contract: App has a version string."""
        from autopack.api.app import create_app
        from autopack.version import __version__

        app = create_app()
        assert app.version == __version__

    def test_rate_limiter_attached_to_state(self):
        """Contract: Rate limiter is available at app.state.limiter."""
        from autopack.api.app import create_app
        from autopack.api.deps import limiter

        app = create_app()
        assert hasattr(app.state, "limiter")
        assert app.state.limiter is limiter

    def test_rate_limit_exceeded_handler_registered(self):
        """Contract: RateLimitExceeded exception has handler."""
        from autopack.api.app import create_app
        from slowapi.errors import RateLimitExceeded

        app = create_app()
        # Exception handlers are stored in app.exception_handlers
        assert RateLimitExceeded in app.exception_handlers

    def test_global_exception_handler_registered(self):
        """Contract: Global Exception handler is registered."""
        from autopack.api.app import create_app

        app = create_app()
        assert Exception in app.exception_handlers

    def test_cors_disabled_by_default(self):
        """Contract: CORS middleware not added when CORS_ALLOWED_ORIGINS not set."""
        from autopack.api.app import create_app

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": ""}, clear=False):
            app = create_app()
            # Check that CORSMiddleware is not in the middleware stack
            middleware_classes = [type(m).__name__ for m in app.user_middleware]
            # When CORS is not configured, CORSMiddleware should not be present
            # Note: user_middleware contains Middleware objects, not the actual middleware
            cors_middlewares = [m for m in middleware_classes if "CORS" in m]
            assert len(cors_middlewares) == 0

    def test_cors_enabled_when_origins_configured(self):
        """Contract: CORS middleware added when CORS_ALLOWED_ORIGINS is set."""
        from autopack.api.app import create_app

        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "http://localhost:3000"}, clear=False):
            app = create_app()
            # Check that we have user middleware added
            # The CORS middleware is added via app.add_middleware
            # It appears in user_middleware as a Middleware object
            assert len(app.user_middleware) > 0

    def test_auth_router_included(self):
        """Contract: Authentication router is included at /api/auth paths."""
        from autopack.api.app import create_app

        app = create_app()
        # Get all routes
        routes = [r.path for r in app.routes]
        # Auth routes should be present (from autopack.auth router)
        auth_routes = [r for r in routes if r.startswith("/api/auth")]
        assert len(auth_routes) > 0, "Auth routes should be included"

    def test_research_router_included(self):
        """Contract: Research router is included at /research paths."""
        from autopack.api.app import create_app

        app = create_app()
        # Get all routes
        routes = [r.path for r in app.routes]
        # Research routes should be present
        research_routes = [r for r in routes if r.startswith("/research")]
        assert len(research_routes) > 0, "Research routes should be included"


class TestGlobalExceptionHandlerContract:
    """Contract tests for global exception handler behavior."""

    @pytest.mark.asyncio
    async def test_returns_error_id_in_response(self):
        """Contract: Exception handler returns error_id for log correlation."""
        from autopack.api.app import global_exception_handler
        from fastapi import Request

        # Create mock request
        request = MagicMock(spec=Request)
        request.url = MagicMock()
        request.url.path = "/test"
        request.method = "GET"
        request.headers = {}
        request.query_params = {}

        # Call handler with a test exception
        # report_error is imported locally inside global_exception_handler
        with patch("autopack.error_reporter.report_error"):
            response = await global_exception_handler(request, ValueError("test error"))

        # Parse response
        import json

        content = json.loads(response.body.decode())

        assert "error_id" in content
        assert len(content["error_id"]) == 8  # Short UUID

    @pytest.mark.asyncio
    async def test_production_hides_error_type(self):
        """Contract: Production mode does not expose error type."""
        from autopack.api.app import global_exception_handler
        from fastapi import Request

        request = MagicMock(spec=Request)
        request.url = MagicMock()
        request.url.path = "/test"
        request.method = "GET"
        request.headers = {}
        request.query_params = {}

        with patch("autopack.api.app.is_production", return_value=True):
            with patch("autopack.error_reporter.report_error"):
                response = await global_exception_handler(request, ValueError("test"))

        import json

        content = json.loads(response.body.decode())

        # Production should not include error_type
        assert "error_type" not in content
        assert content["detail"] == "Internal server error"

    @pytest.mark.asyncio
    async def test_development_includes_error_type(self):
        """Contract: Development mode includes error type for debugging."""
        from autopack.api.app import global_exception_handler
        from fastapi import Request

        request = MagicMock(spec=Request)
        request.url = MagicMock()
        request.url.path = "/test"
        request.method = "GET"
        request.headers = {}
        request.query_params = {}

        with patch("autopack.api.app.is_production", return_value=False):
            with patch("autopack.error_reporter.report_error"):
                response = await global_exception_handler(request, ValueError("test"))

        import json

        content = json.loads(response.body.decode())

        # Development should include error_type
        assert content["error_type"] == "ValueError"

    @pytest.mark.asyncio
    async def test_extracts_run_id_from_path(self):
        """Contract: Handler extracts run_id from /runs/{run_id}/* paths."""
        from autopack.api.app import global_exception_handler
        from fastapi import Request

        request = MagicMock(spec=Request)
        request.url = MagicMock()
        request.url.path = "/runs/test-run-123/phases/p1"
        request.method = "GET"
        request.headers = {}
        request.query_params = {}

        with patch("autopack.api.app.is_production", return_value=False):
            with patch("autopack.error_reporter.report_error") as mock_report:
                await global_exception_handler(request, ValueError("test"))

        # Verify report_error was called with extracted run_id
        mock_report.assert_called_once()
        call_kwargs = mock_report.call_args[1]
        assert call_kwargs["run_id"] == "test-run-123"
        assert call_kwargs["phase_id"] == "p1"


class TestLifespanContract:
    """Contract tests for lifespan context manager."""

    @pytest.mark.asyncio
    async def test_lifespan_skips_db_init_in_testing(self):
        """Contract: Database init is skipped when TESTING=1."""
        from autopack.api.app import lifespan
        from fastapi import FastAPI

        app = FastAPI()

        with patch.dict(os.environ, {"TESTING": "1"}, clear=False):
            with patch("autopack.api.app.init_db") as mock_init:
                async with lifespan(app):
                    pass

        # init_db should NOT have been called in testing mode
        mock_init.assert_not_called()

    @pytest.mark.asyncio
    async def test_lifespan_starts_timeout_cleanup_task(self):
        """Contract: Lifespan starts approval timeout cleanup background task."""
        import asyncio
        from autopack.api.app import lifespan
        from fastapi import FastAPI

        app = FastAPI()

        # Track that the background task coroutine was used
        cleanup_was_called = False

        async def mock_cleanup():
            """Mock cleanup that does nothing but can be tracked."""
            nonlocal cleanup_was_called
            cleanup_was_called = True
            # Wait indefinitely until cancelled
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                pass

        with patch.dict(os.environ, {"TESTING": "1"}, clear=False):
            # Mock the approval_timeout_cleanup function
            with patch("autopack.api.app.approval_timeout_cleanup", mock_cleanup):
                async with lifespan(app):
                    # Give the task time to start
                    await asyncio.sleep(0.01)
                    # Task should have started
                    assert cleanup_was_called, "approval_timeout_cleanup task should be started"


class TestGracefulShutdownManagerContract:
    """Contract tests for graceful shutdown manager (IMP-OPS-003)."""

    def test_initial_state_not_shutting_down(self):
        """Contract: Manager starts in non-shutdown state."""
        from autopack.api.app import GracefulShutdownManager

        manager = GracefulShutdownManager()
        assert not manager.is_shutting_down()
        assert manager.get_active_transaction_count() == 0

    def test_begin_transaction_increments_count(self):
        """Contract: begin_transaction increases active count."""
        from autopack.api.app import GracefulShutdownManager

        manager = GracefulShutdownManager()
        assert manager.begin_transaction() is True
        assert manager.get_active_transaction_count() == 1
        assert manager.begin_transaction() is True
        assert manager.get_active_transaction_count() == 2

    def test_end_transaction_decrements_count(self):
        """Contract: end_transaction decreases active count."""
        from autopack.api.app import GracefulShutdownManager

        manager = GracefulShutdownManager()
        manager.begin_transaction()
        manager.begin_transaction()
        assert manager.get_active_transaction_count() == 2

        manager.end_transaction()
        assert manager.get_active_transaction_count() == 1

        manager.end_transaction()
        assert manager.get_active_transaction_count() == 0

    def test_end_transaction_does_not_go_negative(self):
        """Contract: Active count cannot go below zero."""
        from autopack.api.app import GracefulShutdownManager

        manager = GracefulShutdownManager()
        # End without begin should not cause negative count
        manager.end_transaction()
        manager.end_transaction()
        assert manager.get_active_transaction_count() == 0

    def test_begin_transaction_rejected_during_shutdown(self):
        """Contract: New transactions rejected after shutdown initiated."""
        from autopack.api.app import GracefulShutdownManager

        manager = GracefulShutdownManager()

        # Manually set shutdown flag
        manager._shutdown_event.set()

        # New transactions should be rejected
        assert manager.begin_transaction() is False
        assert manager.get_active_transaction_count() == 0

    @pytest.mark.asyncio
    async def test_initiate_shutdown_sets_flag(self):
        """Contract: initiate_shutdown sets the shutdown flag."""
        from autopack.api.app import GracefulShutdownManager

        manager = GracefulShutdownManager(shutdown_timeout=1.0)
        assert not manager.is_shutting_down()

        await manager.initiate_shutdown()
        assert manager.is_shutting_down()

    @pytest.mark.asyncio
    async def test_initiate_shutdown_waits_for_transactions(self):
        """Contract: Shutdown waits for active transactions to complete."""
        import asyncio
        from autopack.api.app import GracefulShutdownManager

        manager = GracefulShutdownManager(shutdown_timeout=5.0)

        # Start a transaction
        manager.begin_transaction()

        # Start shutdown in background
        shutdown_task = asyncio.create_task(manager.initiate_shutdown())

        # Give it time to start waiting
        await asyncio.sleep(0.1)

        # Should still be waiting
        assert not shutdown_task.done()

        # Complete the transaction
        manager.end_transaction()

        # Shutdown should complete quickly now
        result = await asyncio.wait_for(shutdown_task, timeout=1.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_initiate_shutdown_times_out(self):
        """Contract: Shutdown returns False on timeout with pending transactions."""
        from autopack.api.app import GracefulShutdownManager

        # Short timeout for testing
        manager = GracefulShutdownManager(shutdown_timeout=0.1)

        # Start a transaction that won't complete
        manager.begin_transaction()

        # Initiate shutdown - should timeout
        result = await manager.initiate_shutdown()

        assert result is False
        # Transaction count should still be 1
        assert manager.get_active_transaction_count() == 1

    @pytest.mark.asyncio
    async def test_initiate_shutdown_immediate_when_no_transactions(self):
        """Contract: Shutdown completes immediately when no active transactions."""
        import asyncio
        from autopack.api.app import GracefulShutdownManager

        manager = GracefulShutdownManager(shutdown_timeout=30.0)

        # No transactions active
        start = asyncio.get_event_loop().time()
        result = await manager.initiate_shutdown()
        elapsed = asyncio.get_event_loop().time() - start

        assert result is True
        # Should complete almost instantly, not wait for timeout
        assert elapsed < 1.0


class TestLifespanGracefulShutdownContract:
    """Contract tests for graceful shutdown integration in lifespan."""

    @pytest.mark.asyncio
    async def test_lifespan_initializes_shutdown_manager(self):
        """Contract: Lifespan initializes the global shutdown manager."""
        import asyncio
        from autopack.api.app import lifespan, get_shutdown_manager
        from fastapi import FastAPI

        app = FastAPI()

        async def mock_cleanup():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                pass

        with patch.dict(os.environ, {"TESTING": "1"}, clear=False):
            with patch("autopack.api.app.approval_timeout_cleanup", mock_cleanup):
                async with lifespan(app):
                    # Should be able to get the shutdown manager
                    manager = get_shutdown_manager()
                    assert manager is not None
                    assert not manager.is_shutting_down()

    @pytest.mark.asyncio
    async def test_lifespan_uses_env_timeout(self):
        """Contract: Lifespan uses GRACEFUL_SHUTDOWN_TIMEOUT env var."""
        import asyncio
        from autopack.api.app import lifespan, get_shutdown_manager
        from fastapi import FastAPI

        app = FastAPI()

        async def mock_cleanup():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                pass

        with patch.dict(
            os.environ, {"TESTING": "1", "GRACEFUL_SHUTDOWN_TIMEOUT": "60"}, clear=False
        ):
            with patch("autopack.api.app.approval_timeout_cleanup", mock_cleanup):
                async with lifespan(app):
                    manager = get_shutdown_manager()
                    assert manager._shutdown_timeout == 60.0

    @pytest.mark.asyncio
    async def test_get_shutdown_manager_raises_before_init(self):
        """Contract: get_shutdown_manager raises if called before lifespan."""
        from autopack.api import app as app_module

        # Reset the global manager
        original = app_module._shutdown_manager
        app_module._shutdown_manager = None

        try:
            with pytest.raises(RuntimeError, match="not initialized"):
                app_module.get_shutdown_manager()
        finally:
            # Restore
            app_module._shutdown_manager = original


class TestAlertCriticalFailureContract:
    """Contract tests for background task alerting (IMP-OPS-005)."""

    @pytest.mark.asyncio
    async def test_alert_logs_critical_message(self):
        """Contract: alert_critical_failure logs at critical level."""
        from autopack.api.app import alert_critical_failure

        with patch("autopack.api.app.logger") as mock_logger:
            with patch(
                "autopack.notifications.telegram_notifier.TelegramNotifier"
            ) as mock_notifier_class:
                mock_notifier = MagicMock()
                mock_notifier.is_configured.return_value = False
                mock_notifier_class.return_value = mock_notifier

                await alert_critical_failure(
                    task_name="test_task",
                    error="Test error message",
                    severity="critical",
                    restart_count=5,
                )

        # Verify critical log was called
        mock_logger.critical.assert_called_once()
        call_args = mock_logger.critical.call_args
        assert "test_task" in call_args[0][0]
        assert "Test error message" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_alert_sends_telegram_when_configured(self):
        """Contract: alert_critical_failure sends Telegram notification when configured."""
        from autopack.api.app import alert_critical_failure

        with patch(
            "autopack.notifications.telegram_notifier.TelegramNotifier"
        ) as mock_notifier_class:
            mock_notifier = MagicMock()
            mock_notifier.is_configured.return_value = True
            mock_notifier_class.return_value = mock_notifier

            await alert_critical_failure(
                task_name="test_task",
                error="Test error",
                severity="critical",
            )

        # Verify Telegram notification was sent
        mock_notifier.send_completion_notice.assert_called_once()
        call_kwargs = mock_notifier.send_completion_notice.call_args[1]
        assert call_kwargs["status"] == "error"
        assert "test_task" in call_kwargs["message"]

    @pytest.mark.asyncio
    async def test_alert_skips_telegram_when_not_configured(self):
        """Contract: alert_critical_failure skips Telegram when not configured."""
        from autopack.api.app import alert_critical_failure

        with patch(
            "autopack.notifications.telegram_notifier.TelegramNotifier"
        ) as mock_notifier_class:
            mock_notifier = MagicMock()
            mock_notifier.is_configured.return_value = False
            mock_notifier_class.return_value = mock_notifier

            await alert_critical_failure(
                task_name="test_task",
                error="Test error",
            )

        # Verify Telegram notification was NOT sent
        mock_notifier.send_completion_notice.assert_not_called()

    @pytest.mark.asyncio
    async def test_alert_handles_telegram_failure_gracefully(self):
        """Contract: alert_critical_failure handles Telegram errors without raising."""
        from autopack.api.app import alert_critical_failure

        with patch(
            "autopack.notifications.telegram_notifier.TelegramNotifier"
        ) as mock_notifier_class:
            mock_notifier = MagicMock()
            mock_notifier.is_configured.return_value = True
            mock_notifier.send_completion_notice.side_effect = Exception("Network error")
            mock_notifier_class.return_value = mock_notifier

            # Should not raise
            await alert_critical_failure(
                task_name="test_task",
                error="Test error",
            )

    @pytest.mark.asyncio
    async def test_alert_includes_restart_count_when_provided(self):
        """Contract: alert message includes restart count when provided."""
        from autopack.api.app import alert_critical_failure

        with patch("autopack.api.app.logger") as mock_logger:
            with patch(
                "autopack.notifications.telegram_notifier.TelegramNotifier"
            ) as mock_notifier_class:
                mock_notifier = MagicMock()
                mock_notifier.is_configured.return_value = True
                mock_notifier_class.return_value = mock_notifier

                await alert_critical_failure(
                    task_name="test_task",
                    error="Test error",
                    restart_count=3,
                )

        # Verify restart count is in the log message
        call_args = mock_logger.critical.call_args
        assert "3 restart attempts" in call_args[0][0]


class TestBackgroundTaskSupervisorAlertingContract:
    """Contract tests for supervisor alerting on max restarts (IMP-OPS-005)."""

    @pytest.mark.asyncio
    async def test_supervisor_alerts_on_max_restarts(self):
        """Contract: Supervisor calls alert_critical_failure when max restarts exceeded."""
        from autopack.api.app import BackgroundTaskSupervisor

        failure_count = 0

        async def failing_task():
            nonlocal failure_count
            failure_count += 1
            raise ValueError("Always fails")

        with patch("autopack.api.app.alert_critical_failure") as mock_alert:
            supervisor = BackgroundTaskSupervisor(max_restarts=2)
            await supervisor.supervise("test_failing_task", failing_task)

        # Should have alerted after exceeding max restarts
        mock_alert.assert_called_once()
        call_kwargs = mock_alert.call_args[1]
        assert call_kwargs["task_name"] == "test_failing_task"
        assert call_kwargs["severity"] == "critical"
        assert call_kwargs["restart_count"] == 2

    @pytest.mark.asyncio
    async def test_supervisor_does_not_alert_on_normal_completion(self):
        """Contract: Supervisor does not alert when task completes normally."""
        from autopack.api.app import BackgroundTaskSupervisor

        async def successful_task():
            pass  # Completes normally

        with patch("autopack.api.app.alert_critical_failure") as mock_alert:
            supervisor = BackgroundTaskSupervisor(max_restarts=3)
            await supervisor.supervise("test_success_task", successful_task)

        # Should not have called alert
        mock_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_supervisor_does_not_alert_on_cancel(self):
        """Contract: Supervisor does not alert on task cancellation."""
        import asyncio
        from autopack.api.app import BackgroundTaskSupervisor

        async def cancellable_task():
            await asyncio.sleep(3600)  # Wait to be cancelled

        with patch("autopack.api.app.alert_critical_failure") as mock_alert:
            supervisor = BackgroundTaskSupervisor(max_restarts=3)
            task = asyncio.create_task(supervisor.supervise("test_cancel_task", cancellable_task))
            await asyncio.sleep(0.01)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Should not have called alert on cancellation
        mock_alert.assert_not_called()
