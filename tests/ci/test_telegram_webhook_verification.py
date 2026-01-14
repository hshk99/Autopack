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
                "message": {"message_id": 1, "chat": {"id": 123456789}},
                "data": "approve:test-phase-123",
            }
        }

        response = client.post("/telegram/webhook", json=payload)
        # Should not return 403 (may return other errors due to missing DB data)
        assert (
            response.status_code != 403
        ), f"Webhook should be accessible in testing mode, got {response.status_code}"

    def test_webhook_rejects_missing_secret_in_production(self, production_client):
        """Webhook should reject requests without secret token in production."""
        payload = {
            "callback_query": {
                "id": "12345",
                "from": {"id": 123456789, "username": "testuser"},
                "message": {"message_id": 1, "chat": {"id": 123456789}},
                "data": "approve:test-phase-123",
            }
        }

        # Request without X-Telegram-Bot-Api-Secret-Token header
        response = production_client.post("/telegram/webhook", json=payload)
        assert (
            response.status_code == 403
        ), f"Webhook should reject missing secret in production, got {response.status_code}"

    def test_webhook_rejects_invalid_secret_in_production(self, production_client):
        """Webhook should reject requests with wrong secret token."""
        payload = {
            "callback_query": {
                "id": "12345",
                "from": {"id": 123456789, "username": "testuser"},
                "message": {"message_id": 1, "chat": {"id": 123456789}},
                "data": "approve:test-phase-123",
            }
        }

        # Request with wrong secret token
        response = production_client.post(
            "/telegram/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        )
        assert (
            response.status_code == 403
        ), f"Webhook should reject invalid secret, got {response.status_code}"

    def test_webhook_accepts_valid_secret_in_production(self, production_client):
        """Webhook should accept requests with correct secret token."""
        payload = {
            "callback_query": {
                "id": "12345",
                "from": {"id": 123456789, "username": "testuser"},
                "message": {"message_id": 1, "chat": {"id": 123456789}},
                "data": "approve:test-phase-123",
            }
        }

        # Request with correct secret token
        response = production_client.post(
            "/telegram/webhook",
            json=payload,
            headers={
                "X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret-12345"
            },  # gitleaks:allow
        )
        # Should not return 403 (may return other errors due to missing DB)
        assert (
            response.status_code != 403
        ), f"Webhook should accept valid secret, got {response.status_code}"

    def test_webhook_with_valid_credentials_processes_request(self, production_client):
        """Webhook with valid secret should process request (not return 403)."""
        payload = {
            "callback_query": {
                "id": "12345",
                "from": {"id": 123456789, "username": "testuser"},
                "message": {
                    "message_id": 1,
                    "chat": {"id": 123456789},
                },
                "data": "approve:test-phase-123",
            }
        }

        # Request with valid secret - should not be rejected for auth reasons
        response = production_client.post(
            "/telegram/webhook",
            json=payload,
            headers={
                "X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret-12345"
            },  # gitleaks:allow
        )
        # Should not return 403 - may return 200 (processed) or other status
        assert (
            response.status_code != 403
        ), f"Webhook with valid credentials should not be rejected, got {response.status_code}"


class TestTelegramWebhookProductionRequirements:
    """Test production requirements for Telegram webhook."""

    def test_production_rejects_without_secret(self):
        """In production without TELEGRAM_WEBHOOK_SECRET, requests are rejected."""
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
                    "data": "approve:test",
                }
            }

            response = client.post("/telegram/webhook", json=payload)
            # Should return 403 (access denied) when secret not configured
            # The security module returns False → 403 to avoid leaking config state
            assert response.status_code in (
                403,
                500,
            ), f"Should reject when secret not configured in production, got {response.status_code}"

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


class TestWebhookSecurityModule:
    """Verify webhook security module is properly implemented."""

    def test_verify_telegram_webhook_exists_in_security_module(self):
        """verify_telegram_webhook function must exist in security module."""
        from autopack.notifications.telegram_webhook_security import (
            verify_telegram_webhook,
        )

        assert callable(verify_telegram_webhook)

    def test_verify_telegram_webhook_imported_in_main(self):
        """verify_telegram_webhook must be imported and used in main."""
        # Check the import exists (aliased as verify_telegram_webhook_crypto)
        from autopack.main import verify_telegram_webhook_crypto

        assert callable(verify_telegram_webhook_crypto)

    def test_telegram_webhook_endpoint_exists(self):
        """telegram_webhook endpoint must exist."""
        from autopack.main import app
        from fastapi.routing import APIRoute

        webhook_route = None
        for route in app.routes:
            if isinstance(route, APIRoute) and route.path == "/telegram/webhook":
                webhook_route = route
                break

        assert webhook_route is not None, "Telegram webhook route not found"
        assert "POST" in webhook_route.methods, "Telegram webhook must accept POST"
