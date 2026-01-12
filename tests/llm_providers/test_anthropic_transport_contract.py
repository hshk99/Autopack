"""Contract tests for Anthropic transport wrapper

These tests verify the transport layer's contract with the Anthropic SDK,
ensuring stable behavior across API changes and proper error handling.

Part of PR-LLM-1 (Item 1.1: god file refactoring).
"""

import os
import pytest
from unittest.mock import Mock, patch
from dataclasses import dataclass

# Import transport module
from autopack.llm.providers.anthropic_transport import (
    AnthropicTransport,
    AnthropicTransportError,
    AnthropicTransportTimeout,
    AnthropicTransportNetworkError,
    AnthropicTransportApiError,
    TransportResponse,
)


# ============================================================================
# Mock Response Objects
# ============================================================================


@dataclass
class MockUsage:
    """Mock Anthropic Usage object"""

    input_tokens: int
    output_tokens: int


@dataclass
class MockContentBlock:
    """Mock Anthropic ContentBlock object"""

    text: str
    type: str = "text"


class MockMessage:
    """Mock Anthropic Message object"""

    def __init__(
        self,
        content_text: str,
        input_tokens: int,
        output_tokens: int,
        stop_reason: str = "end_turn",
        model: str = "claude-sonnet-4-5",
    ):
        self.content = [MockContentBlock(text=content_text)]
        self.usage = MockUsage(input_tokens=input_tokens, output_tokens=output_tokens)
        self.stop_reason = stop_reason
        self.model = model


class MockStream:
    """Mock Anthropic stream context manager"""

    def __init__(self, content_chunks: list, final_message: MockMessage):
        self.content_chunks = content_chunks
        self.final_message = final_message
        self.text_stream = iter(content_chunks)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def get_final_message(self):
        return self.final_message


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_anthropic_client():
    """Create a mock Anthropic client"""
    with patch("autopack.llm.providers.anthropic_transport.Anthropic") as mock_anthropic:
        mock_client = Mock()
        mock_anthropic.return_value = mock_client
        yield mock_client


@pytest.fixture
def transport(mock_anthropic_client):
    """Create transport instance with mocked client"""
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        return AnthropicTransport()


# ============================================================================
# Test: Initialization
# ============================================================================


def test_init_with_api_key():
    """Test initialization with explicit API key"""
    with patch("autopack.llm.providers.anthropic_transport.Anthropic") as mock_anthropic:
        _transport = AnthropicTransport(api_key="explicit-key")
        mock_anthropic.assert_called_once_with(
            api_key="explicit-key", timeout=AnthropicTransport.DEFAULT_TIMEOUT
        )


def test_init_with_env_api_key():
    """Test initialization with API key from environment"""
    with patch("autopack.llm.providers.anthropic_transport.Anthropic") as mock_anthropic:
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}):
            _transport = AnthropicTransport()
            mock_anthropic.assert_called_once_with(
                api_key="env-key", timeout=AnthropicTransport.DEFAULT_TIMEOUT
            )


def test_init_missing_api_key_raises_error():
    """Test that missing API key raises clear error"""
    with patch("autopack.llm.providers.anthropic_transport.Anthropic"):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(AnthropicTransportError) as exc_info:
                AnthropicTransport()
            assert "ANTHROPIC_API_KEY" in str(exc_info.value)


def test_init_custom_timeout():
    """Test initialization with custom timeout"""
    with patch("autopack.llm.providers.anthropic_transport.Anthropic") as mock_anthropic:
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            _transport = AnthropicTransport(timeout=120.0)
            mock_anthropic.assert_called_once_with(api_key="test-key", timeout=120.0)


# ============================================================================
# Test: Successful Non-Streaming Request
# ============================================================================


def test_successful_non_streaming_request(transport, mock_anthropic_client):
    """Test successful non-streaming request returns correct response"""
    # Setup mock response
    mock_response = MockMessage(
        content_text="Hello, world!",
        input_tokens=100,
        output_tokens=50,
        stop_reason="end_turn",
        model="claude-sonnet-4-5",
    )
    mock_anthropic_client.messages.create.return_value = mock_response

    # Execute request
    response = transport.send_request(
        messages=[{"role": "user", "content": "Test message"}],
        model="claude-sonnet-4-5",
        max_tokens=1000,
        system="Test system prompt",
        temperature=0.7,
        stream=False,
    )

    # Verify response structure
    assert isinstance(response, TransportResponse)
    assert response.content == "Hello, world!"
    assert response.usage.input_tokens == 100
    assert response.usage.output_tokens == 50
    assert response.usage.total_tokens == 150
    assert response.stop_reason == "end_turn"
    assert response.model == "claude-sonnet-4-5"

    # Verify API call parameters
    mock_anthropic_client.messages.create.assert_called_once_with(
        model="claude-sonnet-4-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": "Test message"}],
        temperature=0.7,
        system="Test system prompt",
    )


def test_non_streaming_request_without_system_prompt(transport, mock_anthropic_client):
    """Test non-streaming request without system prompt"""
    mock_response = MockMessage(
        content_text="Response", input_tokens=50, output_tokens=25
    )
    mock_anthropic_client.messages.create.return_value = mock_response

    _response = transport.send_request(
        messages=[{"role": "user", "content": "Test"}],
        model="claude-sonnet-4-5",
        max_tokens=500,
        temperature=1.0,
        stream=False,
    )

    # Verify system not in kwargs
    call_kwargs = mock_anthropic_client.messages.create.call_args[1]
    assert "system" not in call_kwargs


# ============================================================================
# Test: Successful Streaming Request
# ============================================================================


def test_successful_streaming_request(transport, mock_anthropic_client):
    """Test successful streaming request returns correct response"""
    # Setup mock streaming response
    final_message = MockMessage(
        content_text="Full response",
        input_tokens=120,
        output_tokens=60,
        stop_reason="end_turn",
        model="claude-sonnet-4-5",
    )
    mock_stream = MockStream(
        content_chunks=["Hello", ", ", "world", "!"], final_message=final_message
    )
    mock_anthropic_client.messages.stream.return_value = mock_stream

    # Execute streaming request
    response = transport.send_request(
        messages=[{"role": "user", "content": "Test message"}],
        model="claude-sonnet-4-5",
        max_tokens=2000,
        system="Test system",
        temperature=0.5,
        stream=True,
    )

    # Verify response structure
    assert isinstance(response, TransportResponse)
    assert response.content == "Hello, world!"  # Chunks concatenated
    assert response.usage.input_tokens == 120
    assert response.usage.output_tokens == 60
    assert response.usage.total_tokens == 180
    assert response.stop_reason == "end_turn"
    assert response.model == "claude-sonnet-4-5"

    # Verify streaming API call
    mock_anthropic_client.messages.stream.assert_called_once_with(
        model="claude-sonnet-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": "Test message"}],
        temperature=0.5,
        system="Test system",
    )


# ============================================================================
# Test: Usage Extraction Stability
# ============================================================================


def test_usage_extraction_is_stable(transport, mock_anthropic_client):
    """Test that usage extraction handles various response formats"""
    # Test with normal usage
    mock_response = MockMessage(
        content_text="Test", input_tokens=100, output_tokens=50
    )
    mock_anthropic_client.messages.create.return_value = mock_response

    response = transport.send_request(
        messages=[{"role": "user", "content": "Test"}],
        model="claude-sonnet-4-5",
        max_tokens=1000,
    )

    assert response.usage.input_tokens == 100
    assert response.usage.output_tokens == 50


def test_usage_total_tokens_calculation(transport, mock_anthropic_client):
    """Test that total_tokens property calculates correctly"""
    mock_response = MockMessage(
        content_text="Test", input_tokens=250, output_tokens=750
    )
    mock_anthropic_client.messages.create.return_value = mock_response

    response = transport.send_request(
        messages=[{"role": "user", "content": "Test"}],
        model="claude-sonnet-4-5",
        max_tokens=1000,
    )

    assert response.usage.total_tokens == 1000


# ============================================================================
# Test: Timeout Errors
# ============================================================================


def test_timeout_raises_transport_timeout(transport, mock_anthropic_client):
    """Test that timeout errors raise AnthropicTransportTimeout"""
    mock_anthropic_client.messages.create.side_effect = Exception("Request timed out")

    with pytest.raises(AnthropicTransportTimeout) as exc_info:
        transport.send_request(
            messages=[{"role": "user", "content": "Test"}],
            model="claude-sonnet-4-5",
            max_tokens=1000,
        )

    assert "timed out" in str(exc_info.value).lower()


def test_timeout_keyword_variations(transport, mock_anthropic_client):
    """Test various timeout error message formats"""
    timeout_messages = [
        "Connection timeout",
        "Request has timed out after 60s",
        "timeout exceeded",
    ]

    for msg in timeout_messages:
        mock_anthropic_client.messages.create.side_effect = Exception(msg)

        with pytest.raises(AnthropicTransportTimeout):
            transport.send_request(
                messages=[{"role": "user", "content": "Test"}],
                model="claude-sonnet-4-5",
                max_tokens=1000,
            )


# ============================================================================
# Test: Connection/Network Errors
# ============================================================================


def test_connection_error_raises_network_error(transport, mock_anthropic_client):
    """Test that connection errors raise AnthropicTransportNetworkError"""
    mock_anthropic_client.messages.create.side_effect = Exception(
        "Connection refused by server"
    )

    with pytest.raises(AnthropicTransportNetworkError) as exc_info:
        transport.send_request(
            messages=[{"role": "user", "content": "Test"}],
            model="claude-sonnet-4-5",
            max_tokens=1000,
        )

    assert "network error" in str(exc_info.value).lower()


def test_network_error_keyword_variations(transport, mock_anthropic_client):
    """Test various network error message formats"""
    network_messages = [
        "Network unreachable",
        "Connection error",
        "Connection refused",
        "Network failure",
    ]

    for msg in network_messages:
        mock_anthropic_client.messages.create.side_effect = Exception(msg)

        with pytest.raises(AnthropicTransportNetworkError):
            transport.send_request(
                messages=[{"role": "user", "content": "Test"}],
                model="claude-sonnet-4-5",
                max_tokens=1000,
            )


# ============================================================================
# Test: API Errors with Status Codes
# ============================================================================


def test_api_error_400_raises_with_status_code(transport, mock_anthropic_client):
    """Test that 400 errors raise AnthropicTransportApiError with status code"""
    mock_error = Exception("Bad request (status_code: 400)")
    mock_anthropic_client.messages.create.side_effect = mock_error

    with pytest.raises(AnthropicTransportApiError) as exc_info:
        transport.send_request(
            messages=[{"role": "user", "content": "Test"}],
            model="claude-sonnet-4-5",
            max_tokens=1000,
        )

    assert exc_info.value.status_code == 400


def test_api_error_429_rate_limit(transport, mock_anthropic_client):
    """Test that 429 rate limit errors raise AnthropicTransportApiError"""
    mock_error = Exception("Rate limit exceeded (status_code: 429)")
    mock_anthropic_client.messages.create.side_effect = mock_error

    with pytest.raises(AnthropicTransportApiError) as exc_info:
        transport.send_request(
            messages=[{"role": "user", "content": "Test"}],
            model="claude-sonnet-4-5",
            max_tokens=1000,
        )

    assert exc_info.value.status_code == 429


def test_api_error_500_server_error(transport, mock_anthropic_client):
    """Test that 500 server errors raise AnthropicTransportApiError"""
    mock_error = Exception("Internal server error (status_code: 500)")
    mock_anthropic_client.messages.create.side_effect = mock_error

    with pytest.raises(AnthropicTransportApiError) as exc_info:
        transport.send_request(
            messages=[{"role": "user", "content": "Test"}],
            model="claude-sonnet-4-5",
            max_tokens=1000,
        )

    assert exc_info.value.status_code == 500


def test_api_error_with_status_code_attribute(transport, mock_anthropic_client):
    """Test error with status_code attribute (like anthropic SDK exceptions)"""

    class MockApiError(Exception):
        def __init__(self, message, status_code):
            super().__init__(message)
            self.status_code = status_code

    mock_error = MockApiError("API error", status_code=503)
    mock_anthropic_client.messages.create.side_effect = mock_error

    with pytest.raises(AnthropicTransportApiError) as exc_info:
        transport.send_request(
            messages=[{"role": "user", "content": "Test"}],
            model="claude-sonnet-4-5",
            max_tokens=1000,
        )

    assert exc_info.value.status_code == 503


# ============================================================================
# Test: Stream Mode Chunk Handling
# ============================================================================


def test_stream_mode_yields_chunks_correctly(transport, mock_anthropic_client):
    """Test that streaming mode correctly collects and concatenates chunks"""
    # Setup stream with multiple chunks
    final_message = MockMessage(
        content_text="Full response", input_tokens=100, output_tokens=50
    )
    mock_stream = MockStream(
        content_chunks=["Chunk 1", " Chunk 2", " Chunk 3"], final_message=final_message
    )
    mock_anthropic_client.messages.stream.return_value = mock_stream

    response = transport.send_request(
        messages=[{"role": "user", "content": "Test"}],
        model="claude-sonnet-4-5",
        max_tokens=1000,
        stream=True,
    )

    # Verify chunks were concatenated
    assert response.content == "Chunk 1 Chunk 2 Chunk 3"


def test_stream_empty_chunks_handled(transport, mock_anthropic_client):
    """Test that empty chunks in stream are handled correctly"""
    final_message = MockMessage(
        content_text="Response", input_tokens=50, output_tokens=25
    )
    mock_stream = MockStream(
        content_chunks=["Hello", "", " ", "world"], final_message=final_message
    )
    mock_anthropic_client.messages.stream.return_value = mock_stream

    response = transport.send_request(
        messages=[{"role": "user", "content": "Test"}],
        model="claude-sonnet-4-5",
        max_tokens=1000,
        stream=True,
    )

    assert response.content == "Hello world"


# ============================================================================
# Test: Stop Reason Handling
# ============================================================================


def test_max_tokens_stop_reason(transport, mock_anthropic_client):
    """Test that max_tokens stop reason is captured correctly"""
    mock_response = MockMessage(
        content_text="Truncated response",
        input_tokens=100,
        output_tokens=1000,
        stop_reason="max_tokens",
    )
    mock_anthropic_client.messages.create.return_value = mock_response

    response = transport.send_request(
        messages=[{"role": "user", "content": "Test"}],
        model="claude-sonnet-4-5",
        max_tokens=1000,
    )

    assert response.stop_reason == "max_tokens"


def test_end_turn_stop_reason(transport, mock_anthropic_client):
    """Test that end_turn stop reason is captured correctly"""
    mock_response = MockMessage(
        content_text="Complete response",
        input_tokens=100,
        output_tokens=500,
        stop_reason="end_turn",
    )
    mock_anthropic_client.messages.create.return_value = mock_response

    response = transport.send_request(
        messages=[{"role": "user", "content": "Test"}],
        model="claude-sonnet-4-5",
        max_tokens=1000,
    )

    assert response.stop_reason == "end_turn"


# ============================================================================
# Test: Edge Cases
# ============================================================================


def test_empty_content_handled(transport, mock_anthropic_client):
    """Test that empty content from API is handled gracefully"""

    class EmptyContentMessage:
        def __init__(self):
            self.content = []
            self.usage = MockUsage(input_tokens=10, output_tokens=0)
            self.stop_reason = "end_turn"
            self.model = "claude-sonnet-4-5"

    mock_anthropic_client.messages.create.return_value = EmptyContentMessage()

    response = transport.send_request(
        messages=[{"role": "user", "content": "Test"}],
        model="claude-sonnet-4-5",
        max_tokens=1000,
    )

    assert response.content == ""
    assert response.usage.output_tokens == 0


def test_multiple_messages_in_conversation(transport, mock_anthropic_client):
    """Test that multi-turn conversations are handled correctly"""
    mock_response = MockMessage(
        content_text="Response", input_tokens=200, output_tokens=100
    )
    mock_anthropic_client.messages.create.return_value = mock_response

    messages = [
        {"role": "user", "content": "First message"},
        {"role": "assistant", "content": "First response"},
        {"role": "user", "content": "Second message"},
    ]

    _response = transport.send_request(
        messages=messages, model="claude-sonnet-4-5", max_tokens=1000
    )

    # Verify messages passed through correctly
    call_kwargs = mock_anthropic_client.messages.create.call_args[1]
    assert call_kwargs["messages"] == messages


# ============================================================================
# Test: Error Messages
# ============================================================================


def test_generic_api_error_without_status_code(transport, mock_anthropic_client):
    """Test generic API errors without status codes"""
    mock_anthropic_client.messages.create.side_effect = Exception(
        "API authentication failed"
    )

    with pytest.raises(AnthropicTransportApiError) as exc_info:
        transport.send_request(
            messages=[{"role": "user", "content": "Test"}],
            model="claude-sonnet-4-5",
            max_tokens=1000,
        )

    # Should still be API error, but status_code may be None
    assert exc_info.value.status_code is None or isinstance(
        exc_info.value.status_code, int
    )


def test_unknown_error_wrapped_as_generic_transport_error(
    transport, mock_anthropic_client
):
    """Test that unknown errors are wrapped as generic AnthropicTransportError"""
    mock_anthropic_client.messages.create.side_effect = ValueError(
        "Unexpected internal error"
    )

    with pytest.raises(AnthropicTransportError):
        transport.send_request(
            messages=[{"role": "user", "content": "Test"}],
            model="claude-sonnet-4-5",
            max_tokens=1000,
        )
