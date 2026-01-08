"""Telegram webhook cryptographic verification tests (PR3 - P1-SEC-TELEGRAM-001).

Contract tests ensuring:
1. Webhook requests without valid secret token are rejected in production
2. Webhook requests with valid secret token are accepted
3. Callbacks from unauthorized chats are rejected
4. Testing mode bypasses verification for local development

Security contract: Webhook cannot be abused if endpoint is reachable.
"""

import os
import pytest
from fastapi.testclient import TestClient


class TestTelegramWebhookVerification:
    """Contract tests for Telegram webhook security."""

    @pytest.fixture
    def client(self):
        """Create test client with TESTING mode enabled."""
        os.environ["TESTING"] = "1"
        from autopack.main import app
        return TestClient(app, raise_server_exceptions=False)

    @pytest.fixture
    def production_client(self):
        """Create test client in production mode."""
        # Clear testing mode
        old_testing = os.environ.pop("TESTING", None)
        old_env = os.environ.get("AUTOPACK_ENV")
        old_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
        old_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

        os.environ["AUTOPACK_ENV"] = "production"
        os.environ["TELEGRAM_WEBHOOK_SECRET"] = "test-webhook-secret-12345"  # gitleaks:allow
        os.environ["TELEGRAM_CHAT_ID"] = "123456789"

        from autopack.main import app
        client = TestClient(app, raise_server_exceptions=False)

        yield client

        # Restore environment
        if old_testing:
            os.environ["TESTING"] = old_testing
        if old_env:
            os.environ["AUTOPACK_ENV"] = old_env
        else:
            os.environ.pop("AUTOPACK_ENV", None)
        if old_secret:
            os.environ["TELEGRAM_WEBHOOK_SECRET"] = old_secret
        else:
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
        if old_chat_id:
            os.environ["TELEGRAM_CHAT_ID"] = old_chat_id
        else:
            os.environ.pop("TELEGRAM_CHAT_ID", None)

    def test_webhook_accessible_in_testing_mode(self, client):
        """Webhook should be accessible in testing mode without secret."""
        # Valid callback query structure
        payload = {
            "callback_query": {
                "id": "12345",
                "from": {"id": 123456789, "username": "testuser"},
                "message": {
                    "message_id": 1,
                    "chat": {"id": 123456789}
                },
                "data": "approve:test-phase-123"
            }
        }

        response = client.post("/telegram/webhook", json=payload)
        # Should not return 403 (may return other errors due to missing DB data)
        assert response.status_code != 403, (
            f"Webhook should be accessible in testing mode, got {response.status_code}"
        )

    def test_webhook_rejects_missing_secret_in_production(self, production_client):
        """Webhook should reject requests without secret token in production."""
        payload = {
            "callback_query": {
                "id": "12345",
                "from": {"id": 123456789, "username": "testuser"},
                "message": {"message_id": 1, "chat": {"id": 123456789}},
                "data": "approve:test-phase-123"
            }
        }

        # Request without X-Telegram-Bot-Api-Secret-Token header
        response = production_client.post("/telegram/webhook", json=payload)
        assert response.status_code == 403, (
            f"Webhook should reject missing secret in production, got {response.status_code}"
        )

    def test_webhook_rejects_invalid_secret_in_production(self, production_client):
        """Webhook should reject requests with wrong secret token."""
        payload = {
            "callback_query": {
                "id": "12345",
                "from": {"id": 123456789, "username": "testuser"},
                "message": {"message_id": 1, "chat": {"id": 123456789}},
                "data": "approve:test-phase-123"
            }
        }

        # Request with wrong secret token
        response = production_client.post(
            "/telegram/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"}
        )
        assert response.status_code == 403, (
            f"Webhook should reject invalid secret, got {response.status_code}"
        )

    def test_webhook_accepts_valid_secret_in_production(self, production_client):
        """Webhook should accept requests with correct secret token."""
        payload = {
            "callback_query": {
                "id": "12345",
                "from": {"id": 123456789, "username": "testuser"},
                "message": {"message_id": 1, "chat": {"id": 123456789}},
                "data": "approve:test-phase-123"
            }
        }

        # Request with correct secret token
        response = production_client.post(
            "/telegram/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret-12345"}  # gitleaks:allow
        )
        # Should not return 403 (may return other errors due to missing DB)
        assert response.status_code != 403, (
            f"Webhook should accept valid secret, got {response.status_code}"
        )

    def test_webhook_rejects_unauthorized_chat(self, production_client):
        """Webhook should reject callbacks from unauthorized chat IDs."""
        payload = {
            "callback_query": {
                "id": "12345",
                "from": {"id": 999999999, "username": "attacker"},
                "message": {
                    "message_id": 1,
                    "chat": {"id": 999999999}  # Different from authorized 123456789
                },
                "data": "approve:test-phase-123"
            }
        }

        # Request with valid secret but unauthorized chat
        response = production_client.post(
            "/telegram/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret-12345"}  # gitleaks:allow
        )
        assert response.status_code == 403, (
            f"Webhook should reject unauthorized chat, got {response.status_code}"
        )


class TestTelegramWebhookProductionRequirements:
    """Test production requirements for Telegram webhook."""

    def test_production_requires_secret_configured(self):
        """In production, TELEGRAM_WEBHOOK_SECRET must be configured."""
        # Clear relevant env vars
        old_testing = os.environ.pop("TESTING", None)
        old_env = os.environ.get("AUTOPACK_ENV")
        old_secret = os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)

        os.environ["AUTOPACK_ENV"] = "production"
        # Note: NOT setting TELEGRAM_WEBHOOK_SECRET

        try:
            from autopack.main import app
            client = TestClient(app, raise_server_exceptions=False)

            payload = {
                "callback_query": {
                    "id": "12345",
                    "from": {"id": 123456789},
                    "message": {"message_id": 1, "chat": {"id": 123456789}},
                    "data": "approve:test"
                }
            }

            response = client.post("/telegram/webhook", json=payload)
            # Should return 500 (misconfiguration) since secret is required but not set
            assert response.status_code == 500, (
                f"Should return 500 when secret not configured in production, got {response.status_code}"
            )
            assert "TELEGRAM_WEBHOOK_SECRET" in response.text

        finally:
            # Restore
            if old_testing:
                os.environ["TESTING"] = old_testing
            if old_env:
                os.environ["AUTOPACK_ENV"] = old_env
            else:
                os.environ.pop("AUTOPACK_ENV", None)
            if old_secret:
                os.environ["TELEGRAM_WEBHOOK_SECRET"] = old_secret


class TestWebhookSecurityDocumentation:
    """Verify webhook security is properly documented."""

    def test_verify_telegram_webhook_exists(self):
        """verify_telegram_webhook function must exist."""
        from autopack.main import verify_telegram_webhook
        assert callable(verify_telegram_webhook)

    def test_telegram_webhook_has_security_dependency(self):
        """telegram_webhook endpoint must have security dependency."""
        from autopack.main import app
        from fastapi.routing import APIRoute

        webhook_route = None
        for route in app.routes:
            if isinstance(route, APIRoute) and route.path == "/telegram/webhook":
                webhook_route = route
                break

        assert webhook_route is not None, "Telegram webhook route not found"

        # Check dependencies include our verification
        dep_names = []
        for dep in webhook_route.dependencies:
            if hasattr(dep, 'dependency'):
                dep_names.append(str(dep.dependency))

        for dep in webhook_route.dependant.dependencies:
            if hasattr(dep, 'call'):
                dep_names.append(str(dep.call))

        # At least one dependency should mention telegram verification
        has_telegram_dep = any('telegram' in d.lower() for d in dep_names)
        assert has_telegram_dep, (
            f"Telegram webhook should have verification dependency. Found: {dep_names}"
        )
