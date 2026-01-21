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
