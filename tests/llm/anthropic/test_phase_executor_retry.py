"""Tests for AnthropicPhaseExecutor retry path using transport wrapper.

IMP-003: Verify retry path uses AnthropicTransport for circuit breaker protection.
"""

from unittest.mock import Mock

import pytest

from autopack.llm.anthropic.phase_executor import AnthropicPhaseExecutor
from autopack.llm.providers.anthropic_transport import (
    AnthropicTransport, AnthropicTransportApiError, TransportResponse,
    TransportUsage)
from autopack.llm_client import BuilderResult


@pytest.fixture
def mock_transport():
    """Create a mock AnthropicTransport."""
    transport = Mock(spec=AnthropicTransport)
    return transport


@pytest.fixture
def mock_client():
    """Create a mock AnthropicBuilderClient with necessary helper methods."""
    client = Mock()

    # Mock the underlying Anthropic client (should NOT be called in retry path)
    client.client = Mock()
    client.client.messages = Mock()
    client.client.messages.stream = Mock()

    # Mock helper methods that phase_executor delegates to
    client._build_system_prompt = Mock(return_value="System prompt")
    client._build_user_prompt = Mock(return_value="User prompt")
    client._parse_full_file_output = Mock(
        return_value=BuilderResult(
            success=True,
            patch_content="diff content",
            builder_messages=[],
            tokens_used=1000,
            model_used="claude-sonnet-4-5",
        )
    )
    client._parse_ndjson_output = Mock(
        return_value=BuilderResult(
            success=True,
            patch_content="diff content",
            builder_messages=[],
            tokens_used=1000,
            model_used="claude-sonnet-4-5",
        )
    )
    client._parse_structured_edit_output = Mock(
        return_value=BuilderResult(
            success=True,
            patch_content="diff content",
            builder_messages=[],
            tokens_used=1000,
            model_used="claude-sonnet-4-5",
        )
    )

    return client


@pytest.fixture
def phase_executor(mock_transport, mock_client):
    """Create a PhaseExecutor instance with mocks."""
    return AnthropicPhaseExecutor(mock_transport, mock_client)


def create_transport_response(content="Test output", stop_reason="end_turn"):
    """Helper to create a TransportResponse."""
    return TransportResponse(
        content=content,
        usage=TransportUsage(input_tokens=500, output_tokens=500),
        stop_reason=stop_reason,
        model="claude-sonnet-4-5",
    )


class TestRetryPathUsesTransport:
    """IMP-003: Test that retry path uses transport wrapper instead of direct SDK."""

    def test_retry_uses_transport_send_request_not_direct_sdk(
        self, phase_executor, mock_transport, mock_client
    ):
        """Test that retry path calls transport.send_request, not client.client.messages.stream."""
        # First call raises prompt too long error, second succeeds
        mock_transport.send_request = Mock(
            side_effect=[
                AnthropicTransportApiError("prompt is too long", status_code=400),
                create_transport_response(content="Retry output"),
            ]
        )

        phase_spec = {
            "phase_id": "test_phase",
            "run_id": "test_run",
            "complexity": "medium",
        }

        phase_executor.execute_phase(
            phase_spec=phase_spec,
            file_context={"existing_files": {}},
            model="claude-sonnet-4-5",
            max_tokens=4096,
        )

        # Verify transport.send_request was called twice (initial + retry)
        assert mock_transport.send_request.call_count == 2

        # Verify direct SDK was NOT called
        assert not mock_client.client.messages.stream.called

    def test_retry_path_passes_stream_true_to_transport(
        self, phase_executor, mock_transport, mock_client
    ):
        """Test that retry path uses streaming mode via transport."""
        # First call raises prompt too long error
        mock_transport.send_request = Mock(
            side_effect=[
                AnthropicTransportApiError("prompt is too long", status_code=400),
                create_transport_response(content="Retry output"),
            ]
        )

        phase_spec = {
            "phase_id": "test_phase",
            "run_id": "test_run",
            "complexity": "medium",
        }

        phase_executor.execute_phase(
            phase_spec=phase_spec,
            file_context={"existing_files": {}},
            model="claude-sonnet-4-5",
            max_tokens=4096,
        )

        # Check the second call (retry) used stream=True
        retry_call = mock_transport.send_request.call_args_list[1]
        assert retry_call.kwargs.get("stream") is True

    def test_retry_path_circuit_breaker_protection(
        self, phase_executor, mock_transport, mock_client
    ):
        """Test that retry path benefits from circuit breaker via transport."""

        # First call triggers retry, second call hits open circuit breaker
        mock_transport.send_request = Mock(
            side_effect=[
                AnthropicTransportApiError("prompt is too long", status_code=400),
                AnthropicTransportApiError(
                    "Service temporarily unavailable (circuit breaker open)"
                ),
            ]
        )

        phase_spec = {
            "phase_id": "test_phase",
            "run_id": "test_run",
            "complexity": "medium",
        }

        result = phase_executor.execute_phase(
            phase_spec=phase_spec,
            file_context={"existing_files": {}},
            model="claude-sonnet-4-5",
            max_tokens=4096,
        )

        # Should return error result (the exact error is from first call or retry)
        assert isinstance(result, BuilderResult)
        assert result.success is False
        assert result.error is not None

    def test_retry_preserves_model_and_temperature(
        self, phase_executor, mock_transport, mock_client
    ):
        """Test that retry path preserves model and uses correct temperature."""
        mock_transport.send_request = Mock(
            side_effect=[
                AnthropicTransportApiError("prompt is too long", status_code=400),
                create_transport_response(content="Retry output"),
            ]
        )

        phase_spec = {
            "phase_id": "test_phase",
            "run_id": "test_run",
            "complexity": "medium",
        }

        phase_executor.execute_phase(
            phase_spec=phase_spec,
            file_context={"existing_files": {}},
            model="claude-sonnet-4-5",
            max_tokens=4096,
        )

        # Check the retry call parameters
        retry_call = mock_transport.send_request.call_args_list[1]
        assert retry_call.kwargs.get("model") == "claude-sonnet-4-5"
        assert retry_call.kwargs.get("temperature") == 0.2

    def test_retry_uses_minimal_context_budget(self, phase_executor, mock_transport, mock_client):
        """Test that retry path rebuilds prompt with minimal context budget."""
        mock_transport.send_request = Mock(
            side_effect=[
                AnthropicTransportApiError("prompt is too long", status_code=400),
                create_transport_response(content="Retry output"),
            ]
        )

        phase_spec = {
            "phase_id": "test_phase",
            "run_id": "test_run",
            "complexity": "medium",
        }

        phase_executor.execute_phase(
            phase_spec=phase_spec,
            file_context={"existing_files": {}},
            model="claude-sonnet-4-5",
            max_tokens=4096,
        )

        # Verify _build_user_prompt was called twice (initial + retry with minimal budget)
        assert mock_client._build_user_prompt.call_count == 2

        # The second call should have context_budget_tokens set
        retry_prompt_call = mock_client._build_user_prompt.call_args_list[1]
        assert "context_budget_tokens" in retry_prompt_call.kwargs

    def test_retry_response_content_extracted_correctly(
        self, phase_executor, mock_transport, mock_client
    ):
        """Test that retry response content is correctly extracted from TransportResponse."""
        expected_content = "Retry generated content here"
        mock_transport.send_request = Mock(
            side_effect=[
                AnthropicTransportApiError("prompt is too long", status_code=400),
                create_transport_response(content=expected_content, stop_reason="end_turn"),
            ]
        )

        phase_spec = {
            "phase_id": "test_phase",
            "run_id": "test_run",
            "complexity": "medium",
        }

        phase_executor.execute_phase(
            phase_spec=phase_spec,
            file_context={"existing_files": {}},
            model="claude-sonnet-4-5",
            max_tokens=4096,
        )

        # Verify parser received the correct content
        parser_call = mock_client._parse_full_file_output.call_args
        assert parser_call.args[0] == expected_content

    def test_retry_stop_reason_extracted_correctly(
        self, phase_executor, mock_transport, mock_client
    ):
        """Test that retry stop_reason is correctly extracted from TransportResponse."""
        mock_transport.send_request = Mock(
            side_effect=[
                AnthropicTransportApiError("prompt is too long", status_code=400),
                create_transport_response(content="output", stop_reason="max_tokens"),
            ]
        )

        phase_spec = {
            "phase_id": "test_phase",
            "run_id": "test_run",
            "complexity": "medium",
        }

        phase_executor.execute_phase(
            phase_spec=phase_spec,
            file_context={"existing_files": {}},
            model="claude-sonnet-4-5",
            max_tokens=4096,
        )

        # Verify parser received correct stop_reason and was_truncated
        parser_call = mock_client._parse_full_file_output.call_args
        assert parser_call.kwargs.get("stop_reason") == "max_tokens"
        assert parser_call.kwargs.get("was_truncated") is True


class TestRetryPathErrorHandling:
    """Test error handling in retry path with transport wrapper."""

    def test_retry_typed_error_propagation(self, phase_executor, mock_transport, mock_client):
        """Test that typed transport errors are properly handled in retry path."""
        from autopack.llm.providers.anthropic_transport import \
            AnthropicTransportTimeout

        mock_transport.send_request = Mock(
            side_effect=[
                AnthropicTransportApiError("prompt is too long", status_code=400),
                AnthropicTransportTimeout("Request timed out during retry"),
            ]
        )

        phase_spec = {
            "phase_id": "test_phase",
            "run_id": "test_run",
            "complexity": "medium",
        }

        result = phase_executor.execute_phase(
            phase_spec=phase_spec,
            file_context={"existing_files": {}},
            model="claude-sonnet-4-5",
            max_tokens=4096,
        )

        # Should return error result (may come from first call or retry)
        assert isinstance(result, BuilderResult)
        assert result.success is False
        assert result.error is not None
