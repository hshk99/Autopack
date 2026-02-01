"""Tests for ModelValidationNotifier (IMP-NOTIFY-001)."""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from autopack.notifications.model_validation_notifier import ModelValidationNotifier
from autopack.research.model_validator import (
    BenchmarkScore,
    HardwareCompatibility,
    HardwareRequirement,
    InferenceMetrics,
    ModelMetadata,
    ModelType,
)


@pytest.fixture
def notifier():
    """Create notifier with mocked credentials."""
    return ModelValidationNotifier(
        bot_token="test_bot_token",
        chat_id="123456",
        callback_url="http://localhost:8001/webhook",
    )


@pytest.fixture
def sample_model() -> ModelMetadata:
    """Create a sample model for testing."""
    return ModelMetadata(
        name="Test Model",
        provider="Test Provider",
        model_type=ModelType.REASONING,
        release_date="2024-01",
        context_window=4096,
        description="A test model",
        benchmarks={
            "mmlu": BenchmarkScore("mmlu", 85.0, source="test"),
            "humaneval": BenchmarkScore("humaneval", 75.0, source="test"),
        },
        inference_metrics=InferenceMetrics(
            time_to_first_token_ms=100,
            tokens_per_second=50,
            memory_bf16_gb=10,
        ),
        reasoning_score=80.0,
        hardware_options=[
            HardwareCompatibility(
                hardware_type=HardwareRequirement.DATACENTER_GPU,
                min_vram_gb=16,
                recommended_vram_gb=24,
            )
        ],
        community_sentiment="good",
        community_stars=4.0,
        community_feedback_count=50,
        deployment_success_rate=0.95,
        validation_confidence="high",
    )


class TestModelValidationNotifier:
    """Test ModelValidationNotifier functionality."""

    def test_initialization(self):
        """Test notifier initialization."""
        notifier = ModelValidationNotifier(
            bot_token="test_token",
            chat_id="123",
        )
        assert notifier.bot_token == "test_token"
        assert notifier.chat_id == "123"
        assert notifier.is_configured()

    def test_initialization_from_env(self, monkeypatch):
        """Test notifier initialization from environment variables."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env_token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "789")

        notifier = ModelValidationNotifier()
        assert notifier.bot_token == "env_token"
        assert notifier.chat_id == "789"
        assert notifier.is_configured()

    def test_is_configured_false_without_credentials(self):
        """Test is_configured returns False without credentials."""
        notifier = ModelValidationNotifier(bot_token=None, chat_id=None)
        assert not notifier.is_configured()

    def test_is_configured_false_without_bot_token(self):
        """Test is_configured returns False without bot token."""
        notifier = ModelValidationNotifier(bot_token=None, chat_id="123")
        assert not notifier.is_configured()

    def test_is_configured_false_without_chat_id(self):
        """Test is_configured returns False without chat ID."""
        notifier = ModelValidationNotifier(bot_token="token", chat_id=None)
        assert not notifier.is_configured()

    def test_send_model_validation_report_not_configured(self):
        """Test sending report when not configured."""
        notifier = ModelValidationNotifier(bot_token=None, chat_id=None)
        model = ModelMetadata(
            name="Test",
            provider="Test",
            model_type=ModelType.GENERAL,
            release_date="2024-01",
            context_window=4096,
        )

        result = notifier.send_model_validation_report(model, "req-001")

        assert not result["success"]
        assert result["error"] == "telegram_not_configured"

    @patch("autopack.notifications.model_validation_notifier.requests.post")
    def test_send_model_validation_report_success(self, mock_post, notifier, sample_model):
        """Test successful model validation report sending."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 12345}}
        mock_post.return_value = mock_response

        result = notifier.send_model_validation_report(sample_model, "req-001")

        assert result["success"]
        assert result["message_id"] == 12345
        assert result["model_name"] == "Test Model"
        assert result["request_id"] == "req-001"
        mock_post.assert_called_once()

    @patch("autopack.notifications.model_validation_notifier.requests.post")
    def test_send_model_validation_report_api_error(self, mock_post, notifier, sample_model):
        """Test API error response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": False, "description": "Chat not found"}
        mock_post.return_value = mock_response

        result = notifier.send_model_validation_report(sample_model, "req-001")

        assert not result["success"]
        assert result["error"] == "telegram_api_error"

    @patch("autopack.notifications.model_validation_notifier.requests.post")
    def test_send_model_validation_report_http_error(self, mock_post, notifier, sample_model):
        """Test HTTP error response."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_post.return_value = mock_response

        result = notifier.send_model_validation_report(sample_model, "req-001")

        assert not result["success"]
        assert "401" in result["error"]

    @patch("autopack.notifications.model_validation_notifier.requests.post")
    def test_send_model_validation_report_exception(self, mock_post, notifier, sample_model):
        """Test exception handling."""
        mock_post.side_effect = Exception("Network error")

        result = notifier.send_model_validation_report(sample_model, "req-001")

        assert not result["success"]
        assert result["error"] == "exception"

    @patch("autopack.notifications.model_validation_notifier.requests.post")
    def test_send_approval_decision_ack_approved(self, mock_post, notifier):
        """Test sending approval acknowledgment."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = notifier.send_approval_decision_ack("req-001", "approved", "Test Model")

        assert result is True
        mock_post.assert_called_once()

    @patch("autopack.notifications.model_validation_notifier.requests.post")
    def test_send_approval_decision_ack_rejected(self, mock_post, notifier):
        """Test sending rejection acknowledgment."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = notifier.send_approval_decision_ack("req-001", "rejected", "Test Model")

        assert result is True
        call_args = mock_post.call_args
        assert "REJECTED" in call_args.kwargs["json"]["text"]

    def test_send_approval_decision_ack_not_configured(self):
        """Test ack sending when not configured."""
        notifier = ModelValidationNotifier(bot_token=None, chat_id=None)
        result = notifier.send_approval_decision_ack("req-001", "approved", "Test")
        assert result is False

    @patch("autopack.notifications.model_validation_notifier.requests.post")
    def test_send_approval_decision_ack_exception(self, mock_post, notifier):
        """Test exception handling in ack send."""
        mock_post.side_effect = Exception("Network error")
        result = notifier.send_approval_decision_ack("req-001", "approved", "Test")
        assert result is False

    def test_format_model_report(self, notifier, sample_model):
        """Test model report formatting."""
        message = notifier._format_model_report(sample_model, "req-001", 24)

        assert "Test Model" in message
        assert "Test Provider" in message
        assert "reasoning" in message
        assert "4,096" in message  # Numbers are formatted with commas
        assert "req-001" in message
        assert "24h" in message
        # Verify it's properly formatted HTML with tags
        assert "<" in message and ">" in message

    def test_create_approval_keyboard(self, notifier):
        """Test approval keyboard creation."""
        keyboard = notifier._create_approval_keyboard("req-001", "Test Model")

        assert "inline_keyboard" in keyboard
        buttons = keyboard["inline_keyboard"][0]
        assert len(buttons) == 2
        assert "✅ Approve" in buttons[0]["text"]
        assert "❌ Reject" in buttons[1]["text"]
        assert "model_approve:req-001" in buttons[0]["callback_data"]
        assert "model_reject:req-001" in buttons[1]["callback_data"]

    def test_format_model_report_with_no_benchmarks(self, notifier):
        """Test formatting model without benchmarks."""
        model = ModelMetadata(
            name="Simple Model",
            provider="Test",
            model_type=ModelType.GENERAL,
            release_date="2024-01",
            context_window=2048,
        )

        message = notifier._format_model_report(model, "req-001", 24)

        assert "Simple Model" in message
        assert "2,048" in message  # Numbers are formatted with commas
        # Should still format successfully even without benchmarks
        assert len(message) > 0

    @patch("autopack.notifications.model_validation_notifier.requests.post")
    def test_send_with_custom_timeout(self, mock_post, notifier, sample_model):
        """Test sending with custom approval timeout."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 1}}
        mock_post.return_value = mock_response

        result = notifier.send_model_validation_report(sample_model, "req-001", approval_timeout_hours=48)

        assert result["success"]
        call_args = mock_post.call_args
        message_text = call_args.kwargs["json"]["text"]
        assert "48h" in message_text

    def test_callback_url_from_env(self, monkeypatch):
        """Test callback URL initialization from environment."""
        monkeypatch.setenv("TELEGRAM_WEBHOOK_URL", "https://example.com/webhook")
        notifier = ModelValidationNotifier(bot_token="token", chat_id="123")
        assert notifier.callback_url == "https://example.com/webhook"

    def test_callback_url_default(self):
        """Test default callback URL."""
        notifier = ModelValidationNotifier(bot_token="token", chat_id="123")
        assert "localhost:8001" in notifier.callback_url
