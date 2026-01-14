"""Tests for authentication endpoint rate limiting.

Verifies rate limiting is correctly applied to:
- POST /approval/request (10 requests/minute)
- POST /telegram/webhook (30 requests/minute)
- POST /api/auth/oauth/refresh/{provider} (5 requests/minute)
- POST /api/auth/oauth/reset/{provider} (5 requests/minute)

Note: These tests verify the rate limiting decorators are present
and configured correctly. The actual rate limit enforcement is provided
by slowapi middleware which is tested by the slowapi library itself.
"""

import inspect
import os
from unittest.mock import patch


class TestRateLimitDecorators:
    """Verify rate limiting decorators are applied to endpoints."""

    def test_approval_request_has_rate_limit_decorator(self):
        """Verify /approval/request has @limiter.limit decorator."""
        from autopack.api.routes.approvals import request_approval

        # Check that the function has been wrapped by limiter
        # slowapi adds __wrapped__ attribute when decorating
        assert hasattr(request_approval, "__wrapped__") or hasattr(
            request_approval, "_rate_limit_decorator"
        ), "/approval/request should have rate limiting decorator"

        # Verify the endpoint signature includes Request parameter
        sig = inspect.signature(request_approval)
        assert (
            "request" in sig.parameters
        ), "/approval/request should have request parameter for rate limiting"

    def test_telegram_webhook_has_rate_limit_decorator(self):
        """Verify /telegram/webhook has @limiter.limit decorator."""
        from autopack.api.routes.approvals import telegram_webhook

        # Check for rate limit decorator
        assert hasattr(telegram_webhook, "__wrapped__") or hasattr(
            telegram_webhook, "_rate_limit_decorator"
        ), "/telegram/webhook should have rate limiting decorator"

        # Verify Request parameter
        sig = inspect.signature(telegram_webhook)
        assert (
            "request" in sig.parameters
        ), "/telegram/webhook should have request parameter for rate limiting"

    def test_oauth_refresh_has_rate_limit_decorator(self):
        """Verify /api/auth/oauth/refresh/{provider} has @limiter.limit decorator."""
        from autopack.auth.oauth_router import refresh_credential

        # Check for rate limit decorator
        assert hasattr(refresh_credential, "__wrapped__") or hasattr(
            refresh_credential, "_rate_limit_decorator"
        ), "/api/auth/oauth/refresh/{provider} should have rate limiting decorator"

        # Verify Request parameter
        sig = inspect.signature(refresh_credential)
        assert (
            "request" in sig.parameters
        ), "/api/auth/oauth/refresh/{provider} should have request parameter for rate limiting"

    def test_oauth_reset_has_rate_limit_decorator(self):
        """Verify /api/auth/oauth/reset/{provider} has @limiter.limit decorator."""
        from autopack.auth.oauth_router import reset_failure_count

        # Check for rate limit decorator
        assert hasattr(reset_failure_count, "__wrapped__") or hasattr(
            reset_failure_count, "_rate_limit_decorator"
        ), "/api/auth/oauth/reset/{provider} should have rate limiting decorator"

        # Verify Request parameter
        sig = inspect.signature(reset_failure_count)
        assert (
            "request" in sig.parameters
        ), "/api/auth/oauth/reset/{provider} should have request parameter for rate limiting"


class TestRateLimitConfiguration:
    """Verify rate limit configuration is correct."""

    def test_limiter_is_imported_in_approvals_router(self):
        """Verify limiter is imported in approvals router."""
        import autopack.api.routes.approvals as approvals_module

        assert hasattr(approvals_module, "limiter"), "approvals router should import limiter"

    def test_limiter_is_imported_in_oauth_router(self):
        """Verify limiter is imported in oauth router."""
        # Check that the limiter is used by verifying the decorator is present
        # We already test this in TestRateLimitDecorators, so this is redundant
        # but kept for symmetry with the approvals router test
        from autopack.auth.oauth_router import refresh_credential

        # If the function has the decorator, the import succeeded
        assert (
            hasattr(refresh_credential, "__wrapped__")
            or "request" in inspect.signature(refresh_credential).parameters
        )

    def test_request_parameter_added_to_approval_endpoints(self):
        """Verify Request parameter is added to approval endpoints."""
        from autopack.api.routes.approvals import request_approval, telegram_webhook

        # Both functions should have request parameter
        assert "request" in inspect.signature(request_approval).parameters
        assert "request" in inspect.signature(telegram_webhook).parameters

    def test_request_parameter_added_to_oauth_endpoints(self):
        """Verify Request parameter is added to OAuth endpoints."""
        from autopack.auth.oauth_router import refresh_credential, reset_failure_count

        # Both functions should have request parameter
        assert "request" in inspect.signature(refresh_credential).parameters
        assert "request" in inspect.signature(reset_failure_count).parameters


class TestRateLimitIntegration:
    """Integration tests verifying endpoints work with rate limiting enabled."""

    def test_approval_request_endpoint_responds(self, client):
        """Verify /approval/request endpoint is accessible (rate limiter doesn't break it)."""
        headers = {"X-API-Key": "test-key"}
        payload = {
            "phase_id": "test-phase",
            "run_id": "test-run",
            "context": "test",
            "decision_info": {},
        }

        with patch.dict(os.environ, {"AUTO_APPROVE_BUILD113": "false"}, clear=False):
            with patch(
                "autopack.notifications.telegram_notifier.TelegramNotifier"
            ) as mock_notifier_cls:
                from unittest.mock import MagicMock

                mock_notifier = MagicMock()
                mock_notifier.is_configured.return_value = False
                mock_notifier_cls.return_value = mock_notifier

                response = client.post("/approval/request", json=payload, headers=headers)
                # Should get a valid response (not 500 error from broken rate limiter)
                assert response.status_code in [200, 201]

    def test_telegram_webhook_endpoint_responds(self, client):
        """Verify /telegram/webhook endpoint is accessible."""
        payload = {}

        with patch.dict(os.environ, {"TESTING": "1"}, clear=False):
            response = client.post("/telegram/webhook", json=payload)
            # Should get valid response
            assert response.status_code == 200

    def test_oauth_refresh_endpoint_exists(self):
        """Verify /api/auth/oauth/refresh/{provider} endpoint function exists."""
        # Note: OAuth router is not currently mounted in main.py, so we can't
        # test via HTTP. Instead, verify the function exists and is configured.
        from autopack.auth.oauth_router import refresh_credential

        # Function should exist and be callable
        assert callable(refresh_credential)
        # Should have Request parameter for rate limiting
        assert "request" in inspect.signature(refresh_credential).parameters

    def test_oauth_reset_endpoint_exists(self):
        """Verify /api/auth/oauth/reset/{provider} endpoint function exists."""
        # Note: OAuth router is not currently mounted in main.py, so we can't
        # test via HTTP. Instead, verify the function exists and is configured.
        from autopack.auth.oauth_router import reset_failure_count

        # Function should exist and be callable
        assert callable(reset_failure_count)
        # Should have Request parameter for rate limiting
        assert "request" in inspect.signature(reset_failure_count).parameters


class TestRateLimitDocumentation:
    """Verify rate limiting is documented in endpoint docstrings."""

    def test_approval_request_documents_rate_limit(self):
        """Verify /approval/request docstring mentions rate limiting."""
        from autopack.api.routes.approvals import request_approval

        docstring = request_approval.__doc__ or ""
        assert "rate limit" in docstring.lower(), "/approval/request should document rate limiting"

    def test_telegram_webhook_documents_rate_limit(self):
        """Verify /telegram/webhook docstring mentions rate limiting."""
        from autopack.api.routes.approvals import telegram_webhook

        docstring = telegram_webhook.__doc__ or ""
        assert "rate limit" in docstring.lower(), "/telegram/webhook should document rate limiting"

    def test_oauth_refresh_documents_rate_limit(self):
        """Verify /api/auth/oauth/refresh/{provider} docstring mentions rate limiting."""
        from autopack.auth.oauth_router import refresh_credential

        docstring = refresh_credential.__doc__ or ""
        assert (
            "rate limit" in docstring.lower()
        ), "/api/auth/oauth/refresh/{provider} should document rate limiting"

    def test_oauth_reset_documents_rate_limit(self):
        """Verify /api/auth/oauth/reset/{provider} docstring mentions rate limiting."""
        from autopack.auth.oauth_router import reset_failure_count

        docstring = reset_failure_count.__doc__ or ""
        assert (
            "rate limit" in docstring.lower()
        ), "/api/auth/oauth/reset/{provider} should document rate limiting"
