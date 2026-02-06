"""Tests for IMP-REL-001: Multi-channel notification fallback.

Tests the NotificationChain implementation with Telegram -> Email -> SMS fallback.
Ensures resilience against single point of failure in approval notifications.

Also includes IMP-REL-012 tests for Telegram retry logic with exponential backoff.
"""

from __future__ import annotations

import os
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from autopack.approvals.notification_chain import (
    EmailChannel,
    NotificationChain,
    NotificationChannel,
    SMSChannel,
    TelegramChannel,
    create_notification_chain,
)
from autopack.approvals.service import (
    ApprovalRequest,
    ApprovalResult,
    ApprovalTriggerReason,
    ChainedApprovalService,
)


@pytest.fixture
def sample_request() -> ApprovalRequest:
    """Create a sample approval request for testing."""
    return ApprovalRequest(
        request_id="test-req-001",
        run_id="test-run",
        phase_id="test-phase",
        trigger_reason=ApprovalTriggerReason.PIVOT_INTENTION_CHANGE,
        affected_pivots=["safety_risk"],
        description="Test approval request",
        diff_summary={"changed": ["test_field"]},
    )


@pytest.fixture
def mock_token(monkeypatch) -> str:
    """Provide isolated test token via monkeypatch.

    Generates a unique token for each test to ensure proper isolation
    and prevent accidental leakage of hardcoded tokens in CI artifacts.
    """
    test_token = "test-token-" + os.urandom(8).hex()
    monkeypatch.setenv("TEST_AUTH_TOKEN", test_token)
    return test_token


class MockChannel(NotificationChannel):
    """Mock notification channel for testing."""

    def __init__(self, name: str, enabled: bool = True, success: bool = True):
        self._name = name
        self._enabled = enabled
        self._success = success
        self.send_called = False
        self.last_request = None

    @property
    def name(self) -> str:
        return self._name

    def is_enabled(self) -> bool:
        return self._enabled

    def send(self, request: ApprovalRequest) -> ApprovalResult:
        self.send_called = True
        self.last_request = request
        return ApprovalResult(
            success=self._success,
            approved=None,
            error_reason=None if self._success else f"{self._name}_failed",
            evidence={"channel": self._name, "sent": self._success},
        )


class TestNotificationChain:
    """Tests for NotificationChain class."""

    def test_empty_chain_returns_failure(self, sample_request):
        """Empty chain should return failure."""
        chain = NotificationChain()
        result = chain.send(sample_request)

        assert result.success is False
        assert "No enabled notification channels" in result.error_details.get("chain", "")

    def test_single_channel_success(self, sample_request):
        """Single channel success should return success."""
        chain = NotificationChain()
        mock_channel = MockChannel("telegram", enabled=True, success=True)
        chain.add_channel(mock_channel)

        result = chain.send(sample_request)

        assert result.success is True
        assert result.successful_channel == "telegram"
        assert mock_channel.send_called is True

    def test_fallback_to_second_channel(self, sample_request):
        """Should fallback to second channel when first fails."""
        chain = NotificationChain()
        first_channel = MockChannel("telegram", enabled=True, success=False)
        second_channel = MockChannel("email", enabled=True, success=True)
        chain.add_channel(first_channel)
        chain.add_channel(second_channel)

        result = chain.send(sample_request)

        assert result.success is True
        assert result.successful_channel == "email"
        assert first_channel.send_called is True
        assert second_channel.send_called is True
        assert "telegram" in result.failed_channels

    def test_fallback_to_third_channel(self, sample_request):
        """Should fallback to third channel when first two fail."""
        chain = NotificationChain()
        first_channel = MockChannel("telegram", enabled=True, success=False)
        second_channel = MockChannel("email", enabled=True, success=False)
        third_channel = MockChannel("sms", enabled=True, success=True)
        chain.add_channel(first_channel)
        chain.add_channel(second_channel)
        chain.add_channel(third_channel)

        result = chain.send(sample_request)

        assert result.success is True
        assert result.successful_channel == "sms"
        assert result.failed_channels == ["telegram", "email"]

    def test_all_channels_fail(self, sample_request):
        """Should return failure when all channels fail."""
        chain = NotificationChain()
        chain.add_channel(MockChannel("telegram", enabled=True, success=False))
        chain.add_channel(MockChannel("email", enabled=True, success=False))
        chain.add_channel(MockChannel("sms", enabled=True, success=False))

        result = chain.send(sample_request)

        assert result.success is False
        assert result.successful_channel is None
        assert result.failed_channels == ["telegram", "email", "sms"]

    def test_disabled_channels_skipped(self, sample_request):
        """Disabled channels should not be added to chain."""
        chain = NotificationChain()
        disabled_channel = MockChannel("telegram", enabled=False, success=True)
        enabled_channel = MockChannel("email", enabled=True, success=True)
        chain.add_channel(disabled_channel)
        chain.add_channel(enabled_channel)

        assert chain.get_enabled_channels() == ["email"]

        result = chain.send(sample_request)

        assert result.success is True
        assert result.successful_channel == "email"
        assert disabled_channel.send_called is False

    def test_channel_exception_handled(self, sample_request):
        """Channel exceptions should be handled and fallback triggered."""
        chain = NotificationChain()

        class ExceptionChannel(NotificationChannel):
            @property
            def name(self) -> str:
                return "exception_channel"

            def is_enabled(self) -> bool:
                return True

            def send(self, request: ApprovalRequest) -> ApprovalResult:
                raise RuntimeError("Simulated channel failure")

        chain.add_channel(ExceptionChannel())
        chain.add_channel(MockChannel("email", enabled=True, success=True))

        result = chain.send(sample_request)

        assert result.success is True
        assert result.successful_channel == "email"
        assert "exception_channel" in result.failed_channels
        assert "Simulated channel failure" in result.error_details["exception_channel"]


class TestTelegramChannel:
    """Tests for TelegramChannel."""

    def test_not_enabled_without_config(self):
        """TelegramChannel should not be enabled without config."""
        with patch.dict("os.environ", {}, clear=True):
            channel = TelegramChannel()
            assert channel.is_enabled() is False

    def test_enabled_with_config(self, mock_token):
        """TelegramChannel should be enabled with proper config."""
        with patch.dict(
            "os.environ",
            {"TELEGRAM_BOT_TOKEN": mock_token, "TELEGRAM_CHAT_ID": "12345"},
        ):
            channel = TelegramChannel()
            assert channel.is_enabled() is True

    def test_send_returns_error_when_not_configured(self, sample_request, isolated_env):
        """Send should return error when not configured."""
        channel = TelegramChannel(bot_token=None, chat_id=None)
        result = channel.send(sample_request)

        assert result.success is False
        assert result.error_reason == "telegram_not_configured"


class TestEmailChannel:
    """Tests for EmailChannel."""

    def test_not_enabled_by_default(self):
        """EmailChannel should not be enabled by default."""
        with patch.dict("os.environ", {}, clear=True):
            channel = EmailChannel()
            assert channel.is_enabled() is False

    def test_enabled_with_full_config(self):
        """EmailChannel should be enabled with full configuration."""
        with patch.dict(
            "os.environ",
            {
                "AUTOPACK_NOTIFICATION_EMAIL_ENABLED": "true",
                "AUTOPACK_NOTIFICATION_EMAIL_HOST": "smtp.test.com",
                "AUTOPACK_NOTIFICATION_EMAIL_USER": "user",
                "AUTOPACK_NOTIFICATION_EMAIL_PASSWORD": "pass",
                "AUTOPACK_NOTIFICATION_EMAIL_FROM": "from@test.com",
                "AUTOPACK_NOTIFICATION_EMAIL_TO": "to@test.com",
            },
        ):
            channel = EmailChannel()
            assert channel.is_enabled() is True

    def test_not_enabled_without_explicit_flag(self):
        """EmailChannel requires explicit enable flag."""
        with patch.dict(
            "os.environ",
            {
                "AUTOPACK_NOTIFICATION_EMAIL_HOST": "smtp.test.com",
                "AUTOPACK_NOTIFICATION_EMAIL_USER": "user",
                "AUTOPACK_NOTIFICATION_EMAIL_PASSWORD": "pass",
                "AUTOPACK_NOTIFICATION_EMAIL_FROM": "from@test.com",
                "AUTOPACK_NOTIFICATION_EMAIL_TO": "to@test.com",
            },
        ):
            channel = EmailChannel()
            assert channel.is_enabled() is False

    def test_send_returns_error_when_not_configured(self, sample_request, isolated_env):
        """Send should return error when not configured."""
        channel = EmailChannel()
        result = channel.send(sample_request)

        assert result.success is False
        assert result.error_reason == "email_not_configured"


class TestSMSChannel:
    """Tests for SMSChannel."""

    def test_not_enabled_by_default(self):
        """SMSChannel should not be enabled by default."""
        with patch.dict("os.environ", {}, clear=True):
            channel = SMSChannel()
            assert channel.is_enabled() is False

    def test_enabled_with_twilio_config(self):
        """SMSChannel should be enabled with Twilio configuration."""
        with patch.dict(
            "os.environ",
            {
                "AUTOPACK_NOTIFICATION_SMS_ENABLED": "true",
                "AUTOPACK_NOTIFICATION_SMS_PROVIDER": "twilio",
                "AUTOPACK_NOTIFICATION_SMS_ACCOUNT_SID": "ACtest",
                "AUTOPACK_NOTIFICATION_SMS_AUTH_TOKEN": "token",
                "AUTOPACK_NOTIFICATION_SMS_FROM_NUMBER": "+1234567890",
                "AUTOPACK_NOTIFICATION_SMS_TO_NUMBER": "+0987654321",
            },
        ):
            channel = SMSChannel()
            assert channel.is_enabled() is True

    def test_send_returns_error_when_not_configured(self, sample_request, isolated_env):
        """Send should return error when not configured."""
        channel = SMSChannel()
        result = channel.send(sample_request)

        assert result.success is False
        assert result.error_reason == "sms_not_configured"


class TestChainedApprovalService:
    """Tests for ChainedApprovalService."""

    def test_is_enabled_with_telegram(self, mock_token):
        """Service should be enabled when Telegram is configured."""
        with patch.dict(
            "os.environ",
            {"TELEGRAM_BOT_TOKEN": mock_token, "TELEGRAM_CHAT_ID": "12345"},
        ):
            service = ChainedApprovalService()
            assert service.is_enabled() is True
            assert "telegram" in service.get_enabled_channels()

    def test_is_not_enabled_without_channels(self):
        """Service should not be enabled without any channels."""
        with patch.dict("os.environ", {}, clear=True):
            service = ChainedApprovalService()
            assert service.is_enabled() is False

    def test_request_approval_with_no_channels(self, sample_request):
        """Request should fail when no channels configured."""
        with patch.dict("os.environ", {}, clear=True):
            service = ChainedApprovalService()
            result = service.request_approval(sample_request)

            assert result.success is False
            assert result.error_reason == "no_channels_configured"


class TestCreateNotificationChain:
    """Tests for create_notification_chain factory."""

    def test_creates_chain_with_telegram_only(self, mock_token):
        """Factory should create chain with Telegram when configured."""
        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_BOT_TOKEN": mock_token,
                "TELEGRAM_CHAT_ID": "12345",
            },
            clear=True,
        ):
            chain = create_notification_chain()
            enabled = chain.get_enabled_channels()

            assert "telegram" in enabled
            assert "email" not in enabled
            assert "sms" not in enabled

    def test_creates_chain_with_multiple_channels(self, mock_token):
        """Factory should create chain with all configured channels."""
        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_BOT_TOKEN": mock_token,
                "TELEGRAM_CHAT_ID": "12345",
                "AUTOPACK_NOTIFICATION_EMAIL_ENABLED": "true",
                "AUTOPACK_NOTIFICATION_EMAIL_HOST": "smtp.test.com",
                "AUTOPACK_NOTIFICATION_EMAIL_USER": "user",
                "AUTOPACK_NOTIFICATION_EMAIL_PASSWORD": "pass",
                "AUTOPACK_NOTIFICATION_EMAIL_FROM": "from@test.com",
                "AUTOPACK_NOTIFICATION_EMAIL_TO": "to@test.com",
            },
        ):
            chain = create_notification_chain()
            enabled = chain.get_enabled_channels()

            assert "telegram" in enabled
            assert "email" in enabled

    def test_empty_chain_when_nothing_configured(self):
        """Factory should create empty chain when nothing configured."""
        with patch.dict("os.environ", {}, clear=True):
            chain = create_notification_chain()
            enabled = chain.get_enabled_channels()

            assert enabled == []


class TestGetApprovalServiceWithChain:
    """Tests for get_approval_service with chain support."""

    def test_returns_chained_service_when_channels_available(self, mock_token):
        """Should return ChainedApprovalService when channels configured."""
        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_BOT_TOKEN": mock_token,
                "TELEGRAM_CHAT_ID": "12345",
            },
            clear=True,
        ):
            from autopack.approvals.service import get_approval_service

            service = get_approval_service(use_chain=True)
            assert isinstance(service, ChainedApprovalService)

    def test_falls_back_to_legacy_telegram_service(self):
        """Should fall back to TelegramApprovalService when use_chain=False."""
        with patch.dict(
            "os.environ",
            {
                "AUTOPACK_TELEGRAM_ENABLED": "true",
                "AUTOPACK_TELEGRAM_BOT_TOKEN": "test-token",
                "AUTOPACK_TELEGRAM_CHAT_ID": "12345",
            },
            clear=True,
        ):
            from autopack.approvals.service import get_approval_service
            from autopack.approvals.telegram import TelegramApprovalService

            service = get_approval_service(use_chain=False)
            assert isinstance(service, TelegramApprovalService)

    def test_returns_noop_in_ci(self, mock_token):
        """Should return NoopApprovalService in CI environment."""
        with patch.dict(
            "os.environ",
            {
                "CI": "true",
                "TELEGRAM_BOT_TOKEN": mock_token,
                "TELEGRAM_CHAT_ID": "12345",
            },
        ):
            from autopack.approvals.service import NoopApprovalService, get_approval_service

            service = get_approval_service()
            assert isinstance(service, NoopApprovalService)


class TestTelegramChannelRetry:
    """Tests for IMP-REL-012: Telegram retry logic with exponential backoff."""

    def test_retry_on_url_error(self, sample_request, mock_token):
        """Should retry on URLError and succeed after recovery."""
        channel = TelegramChannel(bot_token=mock_token, chat_id="12345")

        # Create a mock that fails twice then succeeds
        call_count = 0

        def mock_urlopen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise urllib.error.URLError("Network unreachable")
            # Return successful response on third try
            mock_response = MagicMock()
            mock_response.read.return_value = b'{"ok": true}'
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            result = channel.send(sample_request)

        assert result.success is True
        assert call_count == 3  # Two failures + one success

    def test_retry_on_timeout_error(self, sample_request, mock_token):
        """Should retry on TimeoutError and succeed after recovery."""
        channel = TelegramChannel(bot_token=mock_token, chat_id="12345")

        call_count = 0

        def mock_urlopen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("Connection timed out")
            mock_response = MagicMock()
            mock_response.read.return_value = b'{"ok": true}'
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            result = channel.send(sample_request)

        assert result.success is True
        assert call_count == 2  # One failure + one success

    def test_retry_exhausted_returns_failure(self, sample_request, mock_token):
        """Should return failure after all retries are exhausted."""
        channel = TelegramChannel(bot_token=mock_token, chat_id="12345")

        call_count = 0

        def mock_urlopen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise urllib.error.URLError("Network unreachable")

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            result = channel.send(sample_request)

        assert result.success is False
        assert result.error_reason == "telegram_exception"
        assert call_count == 3  # All 3 attempts made

    def test_no_retry_on_api_error(self, sample_request, mock_token):
        """Should not retry on non-network API errors."""
        channel = TelegramChannel(bot_token=mock_token, chat_id="12345")

        call_count = 0

        def mock_urlopen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            mock_response.read.return_value = b'{"ok": false, "error": "Bad Request"}'
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            result = channel.send(sample_request)

        assert result.success is False
        assert result.error_reason == "telegram_api_error"
        assert call_count == 1  # No retries on API error

    def test_retry_on_os_error(self, sample_request, mock_token):
        """Should retry on OSError (e.g., connection reset)."""
        channel = TelegramChannel(bot_token=mock_token, chat_id="12345")

        call_count = 0

        def mock_urlopen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise OSError("Connection reset by peer")
            mock_response = MagicMock()
            mock_response.read.return_value = b'{"ok": true}'
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            result = channel.send(sample_request)

        assert result.success is True
        assert call_count == 2


class TestTelegramApprovalServiceRetry:
    """Tests for IMP-REL-012: TelegramApprovalService retry logic."""

    def test_retry_on_network_failure(self, sample_request, mock_token):
        """Should retry on network failure and succeed after recovery."""
        from autopack.approvals.telegram import TelegramApprovalService

        service = TelegramApprovalService(bot_token=mock_token, chat_id="12345")

        call_count = 0

        def mock_urlopen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise urllib.error.URLError("Network unreachable")
            mock_response = MagicMock()
            mock_response.read.return_value = b'{"ok": true}'
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            result = service.request_approval(sample_request)

        assert result.success is True
        assert call_count == 3

    def test_retry_exhausted_returns_failure(self, sample_request, mock_token):
        """Should return failure after all retries are exhausted."""
        from autopack.approvals.telegram import TelegramApprovalService

        service = TelegramApprovalService(bot_token=mock_token, chat_id="12345")

        call_count = 0

        def mock_urlopen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise urllib.error.URLError("Network unreachable")

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            result = service.request_approval(sample_request)

        assert result.success is False
        assert call_count == 3  # All 3 attempts made
