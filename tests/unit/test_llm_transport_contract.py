"""Contract tests for llm/transport.py module.

These tests verify the transport layer's public API without requiring
actual API calls to Anthropic.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestStreamResponse:
    """Tests for StreamResponse dataclass."""

    def test_stream_response_total_tokens(self):
        """StreamResponse.total_tokens returns sum of input and output."""
        from autopack.llm.transport import StreamResponse

        response = StreamResponse(
            content="Hello",
            input_tokens=100,
            output_tokens=50,
            stop_reason="end_turn",
            model="claude-sonnet-4-5",
        )
        assert response.total_tokens == 150

    def test_stream_response_was_truncated_true(self):
        """StreamResponse.was_truncated returns True for max_tokens stop."""
        from autopack.llm.transport import StreamResponse

        response = StreamResponse(
            content="Hello...",
            input_tokens=100,
            output_tokens=4096,
            stop_reason="max_tokens",
            model="claude-sonnet-4-5",
        )
        assert response.was_truncated is True

    def test_stream_response_was_truncated_false(self):
        """StreamResponse.was_truncated returns False for end_turn stop."""
        from autopack.llm.transport import StreamResponse

        response = StreamResponse(
            content="Hello!",
            input_tokens=100,
            output_tokens=50,
            stop_reason="end_turn",
            model="claude-sonnet-4-5",
        )
        assert response.was_truncated is False

    def test_stream_response_was_truncated_none(self):
        """StreamResponse.was_truncated returns False for None stop_reason."""
        from autopack.llm.transport import StreamResponse

        response = StreamResponse(
            content="Hello!",
            input_tokens=100,
            output_tokens=50,
            stop_reason=None,
            model="claude-sonnet-4-5",
        )
        assert response.was_truncated is False


class TestAnthropicTransport:
    """Tests for AnthropicTransport class."""

    def test_import_error_when_anthropic_missing(self):
        """AnthropicTransport raises ImportError when anthropic not installed."""
        with patch.dict("sys.modules", {"anthropic": None}):
            # Need to reload the module to pick up the patched import
            import autopack.llm.transport as transport_module

            # Save original Anthropic reference
            original_anthropic = transport_module.Anthropic

            try:
                # Simulate missing anthropic
                transport_module.Anthropic = None

                with pytest.raises(ImportError, match="anthropic package not installed"):
                    transport_module.AnthropicTransport()
            finally:
                # Restore original
                transport_module.Anthropic = original_anthropic

    def test_lazy_client_initialization(self):
        """Client is lazily initialized on first access."""
        from autopack.llm.transport import AnthropicTransport

        with patch("autopack.llm.transport.Anthropic") as mock_anthropic:
            mock_anthropic.return_value = MagicMock()

            transport = AnthropicTransport(api_key="test-key")

            # Client not created yet
            mock_anthropic.assert_not_called()

            # Access client property
            _ = transport.client

            # Now client is created
            mock_anthropic.assert_called_once_with(api_key="test-key")

    def test_api_key_from_env(self):
        """Transport uses ANTHROPIC_API_KEY env var when key not provided."""
        from autopack.llm.transport import AnthropicTransport

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-test-key"}):
            with patch("autopack.llm.transport.Anthropic") as mock_anthropic:
                mock_anthropic.return_value = MagicMock()

                transport = AnthropicTransport()
                _ = transport.client

                mock_anthropic.assert_called_once_with(api_key="env-test-key")

    def test_stream_message_caps_max_tokens(self):
        """stream_message caps max_tokens at 64000."""
        from autopack.llm.transport import AnthropicTransport

        with patch("autopack.llm.transport.Anthropic") as mock_anthropic:
            # Create mock stream context manager
            mock_stream = MagicMock()
            mock_stream.__enter__ = MagicMock(return_value=mock_stream)
            mock_stream.__exit__ = MagicMock(return_value=False)
            mock_stream.text_stream = iter(["Hello"])

            mock_final_msg = MagicMock()
            mock_final_msg.usage.input_tokens = 100
            mock_final_msg.usage.output_tokens = 50
            mock_final_msg.stop_reason = "end_turn"
            mock_stream.get_final_message.return_value = mock_final_msg

            mock_client = MagicMock()
            mock_client.messages.stream.return_value = mock_stream
            mock_anthropic.return_value = mock_client

            transport = AnthropicTransport(api_key="test-key")
            transport.stream_message(
                model="claude-sonnet-4-5",
                system="System prompt",
                user_content="User message",
                max_tokens=100000,  # Exceeds limit
            )

            # Verify max_tokens was capped
            call_kwargs = mock_client.messages.stream.call_args[1]
            assert call_kwargs["max_tokens"] == 64000

    def test_stream_message_returns_response(self):
        """stream_message returns StreamResponse with correct data."""
        from autopack.llm.transport import AnthropicTransport, StreamResponse

        with patch("autopack.llm.transport.Anthropic") as mock_anthropic:
            mock_stream = MagicMock()
            mock_stream.__enter__ = MagicMock(return_value=mock_stream)
            mock_stream.__exit__ = MagicMock(return_value=False)
            mock_stream.text_stream = iter(["Hello", " ", "World"])

            mock_final_msg = MagicMock()
            mock_final_msg.usage.input_tokens = 100
            mock_final_msg.usage.output_tokens = 10
            mock_final_msg.stop_reason = "end_turn"
            mock_stream.get_final_message.return_value = mock_final_msg

            mock_client = MagicMock()
            mock_client.messages.stream.return_value = mock_stream
            mock_anthropic.return_value = mock_client

            transport = AnthropicTransport(api_key="test-key")
            response = transport.stream_message(
                model="claude-sonnet-4-5",
                system="System",
                user_content="User",
            )

            assert isinstance(response, StreamResponse)
            assert response.content == "Hello World"
            assert response.input_tokens == 100
            assert response.output_tokens == 10
            assert response.stop_reason == "end_turn"
            assert response.model == "claude-sonnet-4-5"


class TestUtilizationCalculations:
    """Tests for static utilization calculation methods."""

    def test_calculate_utilization_normal(self):
        """calculate_utilization returns correct percentage."""
        from autopack.llm.transport import AnthropicTransport

        result = AnthropicTransport.calculate_utilization(
            output_tokens=800,
            max_tokens=1000,
        )
        assert result == 80.0

    def test_calculate_utilization_full(self):
        """calculate_utilization returns 100% when at max."""
        from autopack.llm.transport import AnthropicTransport

        result = AnthropicTransport.calculate_utilization(
            output_tokens=1000,
            max_tokens=1000,
        )
        assert result == 100.0

    def test_calculate_utilization_zero_max(self):
        """calculate_utilization returns 0 when max_tokens is 0."""
        from autopack.llm.transport import AnthropicTransport

        result = AnthropicTransport.calculate_utilization(
            output_tokens=100,
            max_tokens=0,
        )
        assert result == 0.0

    def test_is_high_utilization_true(self):
        """is_high_utilization returns True when above threshold."""
        from autopack.llm.transport import AnthropicTransport

        assert (
            AnthropicTransport.is_high_utilization(
                output_tokens=960,
                max_tokens=1000,
                threshold=95.0,
            )
            is True
        )

    def test_is_high_utilization_false(self):
        """is_high_utilization returns False when below threshold."""
        from autopack.llm.transport import AnthropicTransport

        assert (
            AnthropicTransport.is_high_utilization(
                output_tokens=900,
                max_tokens=1000,
                threshold=95.0,
            )
            is False
        )

    def test_is_high_utilization_exact_threshold(self):
        """is_high_utilization returns True at exact threshold."""
        from autopack.llm.transport import AnthropicTransport

        assert (
            AnthropicTransport.is_high_utilization(
                output_tokens=950,
                max_tokens=1000,
                threshold=95.0,
            )
            is True
        )

    def test_is_high_utilization_default_threshold(self):
        """is_high_utilization uses 95% as default threshold."""
        from autopack.llm.transport import AnthropicTransport

        # 94% should be below default threshold
        assert (
            AnthropicTransport.is_high_utilization(
                output_tokens=940,
                max_tokens=1000,
            )
            is False
        )

        # 95% should be at default threshold
        assert (
            AnthropicTransport.is_high_utilization(
                output_tokens=950,
                max_tokens=1000,
            )
            is True
        )
