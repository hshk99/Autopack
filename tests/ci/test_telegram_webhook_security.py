"""Telegram webhook security contract tests (PR7).

Ensures Telegram webhook endpoint has proper cryptographic verification:
1. Production mode requires secret token
2. Valid secret tokens are accepted
3. Invalid/missing tokens are rejected in production
4. Constant-time comparison is used (timing attack prevention)

Contract: Telegram webhook cannot be spoofed in production.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent


class TestWebhookSecurityModule:
    """Verify telegram_webhook_security module exists and works correctly."""

    def test_module_exists(self):
        """Webhook security module must exist."""
        security_module = (
            REPO_ROOT / "src" / "autopack" / "notifications" / "telegram_webhook_security.py"
        )
        assert security_module.exists(), (
            "telegram_webhook_security.py not found - "
            "PR7 requires webhook signature verification"
        )

    def test_module_is_importable(self):
        """Module must be importable without errors."""
        from autopack.notifications.telegram_webhook_security import (
            get_webhook_secret,
            is_verification_required,
            verify_secret_token,
            verify_telegram_webhook,
            get_verification_status,
        )

        # All functions should be callable
        assert callable(get_webhook_secret)
        assert callable(is_verification_required)
        assert callable(verify_secret_token)
        assert callable(verify_telegram_webhook)
        assert callable(get_verification_status)


class TestSecretTokenVerification:
    """Verify secret token verification logic."""

    def test_verify_with_matching_secret(self):
        """Valid token should pass verification."""
        from autopack.notifications.telegram_webhook_security import verify_secret_token

        with patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": "test-secret-12345"}):
            assert verify_secret_token("test-secret-12345") is True

    def test_verify_with_wrong_secret(self):
        """Invalid token should fail verification."""
        from autopack.notifications.telegram_webhook_security import verify_secret_token

        with patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": "test-secret-12345"}):
            assert verify_secret_token("wrong-secret") is False

    def test_verify_with_empty_token(self):
        """Empty token should fail verification."""
        from autopack.notifications.telegram_webhook_security import verify_secret_token

        with patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": "test-secret-12345"}):
            assert verify_secret_token("") is False
            assert verify_secret_token(None) is False

    def test_verify_without_configured_secret(self):
        """No configured secret should fail verification."""
        from autopack.notifications.telegram_webhook_security import verify_secret_token

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
            assert verify_secret_token("any-token") is False


class TestProductionRequirements:
    """Verify production mode security requirements."""

    def test_production_requires_verification(self):
        """Production mode should require verification."""
        from autopack.notifications.telegram_webhook_security import is_verification_required

        with patch.dict(os.environ, {"AUTOPACK_ENV": "production"}, clear=False):
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
            assert is_verification_required() is True

    def test_production_with_secret_requires_verification(self):
        """Production with secret should require verification."""
        from autopack.notifications.telegram_webhook_security import is_verification_required

        with patch.dict(
            os.environ,
            {"AUTOPACK_ENV": "production", "TELEGRAM_WEBHOOK_SECRET": "secret"},
        ):
            assert is_verification_required() is True

    def test_development_without_secret_no_requirement(self):
        """Development mode without secret should not require verification."""
        from autopack.notifications.telegram_webhook_security import is_verification_required

        with patch.dict(os.environ, {"AUTOPACK_ENV": "development"}, clear=False):
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
            assert is_verification_required() is False

    def test_development_with_secret_requires_verification(self):
        """Development with secret should require verification."""
        from autopack.notifications.telegram_webhook_security import is_verification_required

        with patch.dict(
            os.environ,
            {"AUTOPACK_ENV": "development", "TELEGRAM_WEBHOOK_SECRET": "secret"},
        ):
            assert is_verification_required() is True


class TestWebhookVerification:
    """Verify full webhook verification flow."""

    @pytest.mark.asyncio
    async def test_production_rejects_without_secret_config(self):
        """Production should reject if no secret is configured."""
        from autopack.notifications.telegram_webhook_security import verify_telegram_webhook

        mock_request = MagicMock()
        mock_request.headers.get.return_value = None

        with patch.dict(os.environ, {"AUTOPACK_ENV": "production"}, clear=False):
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
            result = await verify_telegram_webhook(mock_request)
            assert result is False

    @pytest.mark.asyncio
    async def test_production_rejects_invalid_token(self):
        """Production should reject invalid token."""
        from autopack.notifications.telegram_webhook_security import verify_telegram_webhook

        mock_request = MagicMock()
        mock_request.headers.get.return_value = "wrong-token"

        with patch.dict(
            os.environ,
            {"AUTOPACK_ENV": "production", "TELEGRAM_WEBHOOK_SECRET": "correct-token"},
        ):
            result = await verify_telegram_webhook(mock_request)
            assert result is False

    @pytest.mark.asyncio
    async def test_production_accepts_valid_token(self):
        """Production should accept valid token."""
        from autopack.notifications.telegram_webhook_security import verify_telegram_webhook

        mock_request = MagicMock()
        mock_request.headers.get.return_value = "correct-token"

        with patch.dict(
            os.environ,
            {"AUTOPACK_ENV": "production", "TELEGRAM_WEBHOOK_SECRET": "correct-token"},
        ):
            result = await verify_telegram_webhook(mock_request)
            assert result is True

    @pytest.mark.asyncio
    async def test_development_allows_without_token(self):
        """Development should allow requests without token (no secret configured)."""
        from autopack.notifications.telegram_webhook_security import verify_telegram_webhook

        mock_request = MagicMock()
        mock_request.headers.get.return_value = None

        with patch.dict(os.environ, {"AUTOPACK_ENV": "development"}, clear=False):
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
            result = await verify_telegram_webhook(mock_request)
            assert result is True


class TestTimingAttackPrevention:
    """Verify timing attack prevention measures."""

    def test_uses_hmac_compare_digest(self):
        """Verification should use constant-time comparison."""
        import inspect
        from autopack.notifications import telegram_webhook_security

        source = inspect.getsource(telegram_webhook_security)

        # Must use hmac.compare_digest for timing attack prevention
        assert "hmac.compare_digest" in source, (
            "Webhook verification must use hmac.compare_digest "
            "for constant-time comparison (timing attack prevention)"
        )


class TestMainIntegration:
    """Verify webhook verification is integrated into main.py."""

    def test_webhook_handler_calls_verification(self):
        """Webhook handler must call verify_telegram_webhook."""
        main_py = REPO_ROOT / "src" / "autopack" / "main.py"
        content = main_py.read_text(encoding="utf-8")

        # Must import and call verification
        assert (
            "verify_telegram_webhook" in content
        ), "main.py telegram_webhook handler must call verify_telegram_webhook"
        assert (
            "telegram_webhook_security" in content
        ), "main.py must import from telegram_webhook_security module"

    def test_webhook_handler_rejects_on_failure(self):
        """Webhook handler must raise HTTPException on verification failure."""
        main_py = REPO_ROOT / "src" / "autopack" / "main.py"
        content = main_py.read_text(encoding="utf-8")

        # Find the webhook handler section
        webhook_start = content.find('@app.post("/telegram/webhook")')
        assert webhook_start > 0, "Telegram webhook handler not found"

        webhook_section = content[webhook_start : webhook_start + 1500]

        # Must raise HTTPException on failure
        assert (
            "HTTPException" in webhook_section
        ), "Webhook handler must raise HTTPException on verification failure"
        assert (
            "403" in webhook_section
        ), "Webhook handler must return 403 status on verification failure"


class TestVerificationStatus:
    """Verify status helper for debugging/contract tests."""

    def test_get_verification_status_returns_dict(self):
        """get_verification_status should return status dict."""
        from autopack.notifications.telegram_webhook_security import get_verification_status

        status = get_verification_status()

        assert isinstance(status, dict)
        assert "secret_configured" in status
        assert "verification_required" in status
        assert "environment" in status

    def test_status_reflects_configuration(self):
        """Status should reflect current configuration."""
        from autopack.notifications.telegram_webhook_security import get_verification_status

        with patch.dict(
            os.environ,
            {"AUTOPACK_ENV": "production", "TELEGRAM_WEBHOOK_SECRET": "secret"},
        ):
            status = get_verification_status()
            assert status["secret_configured"] is True
            assert status["verification_required"] is True
            assert status["environment"] == "production"

        with patch.dict(os.environ, {"AUTOPACK_ENV": "development"}, clear=False):
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
            status = get_verification_status()
            assert status["secret_configured"] is False
            assert status["verification_required"] is False
            assert status["environment"] == "development"
