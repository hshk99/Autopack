"""IMP-SEC-006: Require webhook secret in production.

This test module verifies that TELEGRAM_WEBHOOK_SECRET is required in production mode.
Without this requirement, webhooks can be spoofed by attackers who discover the endpoint.

Security contract:
- Production mode MUST reject webhook requests if TELEGRAM_WEBHOOK_SECRET is not configured
- Production mode MUST reject webhook requests with invalid/missing secret token
- Development mode MAY allow requests without validation (for local testing)

The implementation in telegram_webhook_security.py handles this by:
1. Checking AUTOPACK_ENV environment variable
2. Returning False (→ 403) when in production without a configured secret
3. Logging an error to alert operators of misconfiguration
"""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestIMPSEC006WebhookSecretRequired:
    """IMP-SEC-006: Verify webhook secret is required in production."""

    @pytest.mark.asyncio
    async def test_production_rejects_when_secret_not_configured(self):
        """Production MUST reject webhooks if TELEGRAM_WEBHOOK_SECRET not set.

        This prevents webhook spoofing attacks where attackers send fake
        Telegram callbacks to trigger unauthorized actions.
        """
        from autopack.notifications.telegram_webhook_security import \
            verify_telegram_webhook

        mock_request = MagicMock()
        mock_request.headers.get.return_value = None

        with patch.dict(os.environ, {"AUTOPACK_ENV": "production"}, clear=False):
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)

            result = await verify_telegram_webhook(mock_request)

            # MUST return False to trigger 403 in handler
            assert result is False, (
                "IMP-SEC-006: Production mode must reject webhooks "
                "when TELEGRAM_WEBHOOK_SECRET is not configured"
            )

    @pytest.mark.asyncio
    async def test_production_rejects_invalid_secret_token(self):
        """Production MUST reject webhooks with wrong secret token.

        Even if secret is configured, requests with invalid tokens must be rejected.
        """
        from autopack.notifications.telegram_webhook_security import \
            verify_telegram_webhook

        mock_request = MagicMock()
        mock_request.headers.get.return_value = "attacker-supplied-token"

        with patch.dict(
            os.environ,
            {
                "AUTOPACK_ENV": "production",
                "TELEGRAM_WEBHOOK_SECRET": "real-secret-token",  # gitleaks:allow
            },
        ):
            result = await verify_telegram_webhook(mock_request)

            assert (
                result is False
            ), "IMP-SEC-006: Production mode must reject webhooks with invalid secret token"

    @pytest.mark.asyncio
    async def test_production_accepts_valid_secret_token(self):
        """Production MUST accept webhooks with correct secret token."""
        from autopack.notifications.telegram_webhook_security import \
            verify_telegram_webhook

        mock_request = MagicMock()
        mock_request.headers.get.return_value = "correct-secret-token"

        with patch.dict(
            os.environ,
            {
                "AUTOPACK_ENV": "production",
                "TELEGRAM_WEBHOOK_SECRET": "correct-secret-token",  # gitleaks:allow
            },
        ):
            result = await verify_telegram_webhook(mock_request)

            assert (
                result is True
            ), "IMP-SEC-006: Production mode must accept webhooks with valid secret token"

    @pytest.mark.asyncio
    async def test_development_allows_without_secret_configured(self):
        """Development mode allows webhooks without secret for local testing."""
        from autopack.notifications.telegram_webhook_security import \
            verify_telegram_webhook

        mock_request = MagicMock()
        mock_request.headers.get.return_value = None

        with patch.dict(os.environ, {"AUTOPACK_ENV": "development"}, clear=False):
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)

            result = await verify_telegram_webhook(mock_request)

            assert result is True, (
                "Development mode should allow webhooks without secret "
                "for local testing convenience"
            )

    def test_error_logged_when_production_secret_missing(self, caplog):
        """Production must log error when secret is missing."""
        import asyncio

        from autopack.notifications.telegram_webhook_security import \
            verify_telegram_webhook

        mock_request = MagicMock()
        mock_request.headers.get.return_value = None

        with patch.dict(os.environ, {"AUTOPACK_ENV": "production"}, clear=False):
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)

            with caplog.at_level("ERROR"):
                asyncio.get_event_loop().run_until_complete(verify_telegram_webhook(mock_request))

            # Should log error about missing secret
            assert any(
                "TELEGRAM_WEBHOOK_SECRET" in record.message for record in caplog.records
            ), "IMP-SEC-006: Must log error when production secret is missing"


class TestWebhookSecretConfiguration:
    """Test webhook secret configuration helpers."""

    def test_is_verification_required_in_production(self):
        """Production always requires verification."""
        from autopack.notifications.telegram_webhook_security import \
            is_verification_required

        with patch.dict(os.environ, {"AUTOPACK_ENV": "production"}, clear=False):
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)

            assert is_verification_required() is True, (
                "IMP-SEC-006: Verification must be required in production "
                "even if secret is not configured"
            )

    def test_is_verification_required_when_secret_set(self):
        """Verification required when secret is configured (any environment)."""
        from autopack.notifications.telegram_webhook_security import \
            is_verification_required

        with patch.dict(
            os.environ,
            {"AUTOPACK_ENV": "development", "TELEGRAM_WEBHOOK_SECRET": "secret"},
        ):
            assert (
                is_verification_required() is True
            ), "Verification should be required when secret is configured"

    def test_verification_not_required_dev_no_secret(self):
        """Development without secret does not require verification."""
        from autopack.notifications.telegram_webhook_security import \
            is_verification_required

        with patch.dict(os.environ, {"AUTOPACK_ENV": "development"}, clear=False):
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)

            assert (
                is_verification_required() is False
            ), "Development mode without secret should not require verification"
