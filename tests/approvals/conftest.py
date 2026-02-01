"""Fixtures for approval service tests.

Provides proper environment isolation and test infrastructure to prevent
timing-sensitive failures and ensure deterministic test execution.

Fixes IMP-TRIGGER-001: Ensures proper fixture setup for async and webhook
callback testing.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from autopack.approvals.service import ApprovalRequest, ApprovalTriggerReason


@pytest.fixture
def isolated_env(monkeypatch):
    """Provide isolated test environment.

    Clears all AUTOPACK_* and CI environment variables to prevent
    test pollution and ensure each test starts with clean state.

    Yields:
        monkeypatch fixture for test use
    """
    # Clear all AUTOPACK_* variables
    for key in list(os.environ.keys()):
        if key.startswith("AUTOPACK_") or key in ["CI", "GITHUB_ACTIONS", "GITLAB_CI"]:
            monkeypatch.delenv(key, raising=False)

    yield monkeypatch


@pytest.fixture
def sample_approval_request() -> ApprovalRequest:
    """Create a sample approval request for testing.

    Returns:
        ApprovalRequest for use in tests
    """
    return ApprovalRequest(
        request_id="req-test-001",
        run_id="test-run-123",
        phase_id="phase-test",
        trigger_reason=ApprovalTriggerReason.PIVOT_INTENTION_CHANGE,
        affected_pivots=["safety_risk"],
        description="Test approval request",
        diff_summary={"changed": ["test_field"]},
    )


@pytest.fixture
def mock_telegram_api():
    """Mock Telegram API responses.

    Provides deterministic API responses without making actual network calls.
    Prevents timeout and network errors that can cause flaky tests.

    Yields:
        dict: Mock Telegram API responses
    """
    responses = {
        "success": {"ok": True, "result": {"message_id": 12345, "chat": {"id": 123}}},
        "failure": {"ok": False, "description": "Bad Request: message text is empty"},
    }

    with patch("urllib.request.urlopen") as mock_urlopen:
        # Create mock response
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(responses["success"]).encode()
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False

        mock_urlopen.return_value = mock_response
        yield responses


@pytest.fixture
def mock_notification_channels():
    """Mock all notification channels.

    Provides isolated mocking for Telegram, Email, and SMS channels
    to prevent intermittent failures from network timeouts or rate limits.

    Yields:
        dict: Mock patches for each channel
    """
    patches = {}

    # Mock Telegram channel
    telegram_patch = patch(
        "autopack.approvals.notification_chain.TelegramChannel._send_telegram_request"
    )
    patches["telegram"] = telegram_patch.start()
    patches["telegram"].return_value = {"ok": True, "result": {"message_id": 1}}

    # Mock Email channel
    email_patch = patch("smtplib.SMTP")
    patches["email"] = email_patch.start()
    mock_smtp = MagicMock()
    patches["email"].return_value.__enter__.return_value = mock_smtp

    # Mock SMS Twilio channel
    twilio_patch = patch("urllib.request.urlopen")
    patches["twilio"] = twilio_patch.start()
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"sid": "SM123"}).encode()
    patches["twilio"].return_value.__enter__.return_value = mock_response

    yield patches

    # Cleanup
    for patch_obj in patches.values():
        patch_obj.stop()


@pytest.fixture
def ci_environment(monkeypatch):
    """Simulate CI environment.

    Sets up environment variables to make tests believe they're running in CI.
    Useful for testing CI-specific behavior (e.g., disabling Telegram).

    Yields:
        monkeypatch: Fixture for further env manipulation in test
    """
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    yield monkeypatch


@pytest.fixture
def no_ci_environment(monkeypatch):
    """Simulate local development environment.

    Ensures CI variables are cleared to test local behavior.

    Yields:
        monkeypatch: Fixture for further env manipulation in test
    """
    for var in ["CI", "GITHUB_ACTIONS", "GITLAB_CI", "JENKINS_URL"]:
        monkeypatch.delenv(var, raising=False)
    yield monkeypatch


@pytest.fixture
def telegram_configured(monkeypatch):
    """Configure Telegram service with test credentials.

    Provides isolated test credentials without leaking sensitive data
    in test output.

    Yields:
        dict: Configuration dictionary
    """
    config = {
        "bot_token": "test-bot-token-123456",
        "chat_id": "test-chat-id-789",
    }
    monkeypatch.setenv("AUTOPACK_TELEGRAM_ENABLED", "true")
    monkeypatch.setenv("AUTOPACK_TELEGRAM_BOT_TOKEN", config["bot_token"])
    monkeypatch.setenv("AUTOPACK_TELEGRAM_CHAT_ID", config["chat_id"])
    yield config


@pytest.fixture
def telegram_misconfigured(monkeypatch):
    """Create misconfigured Telegram setup.

    Tests error handling when configuration is incomplete.

    Yields:
        monkeypatch: Fixture for further env manipulation
    """
    # Enable but with missing credentials
    monkeypatch.setenv("AUTOPACK_TELEGRAM_ENABLED", "true")
    monkeypatch.delenv("AUTOPACK_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("AUTOPACK_TELEGRAM_CHAT_ID", raising=False)
    yield monkeypatch
