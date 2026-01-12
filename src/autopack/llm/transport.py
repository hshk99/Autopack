"""Anthropic API transport wrapper for Autopack.

Provides:
- Client initialization with graceful degradation
- Streaming message handling
- Token usage tracking
- Stop reason detection

This module extracts the transport layer from anthropic_clients.py.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

# Graceful degradation if anthropic package not installed
try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None  # type: ignore[misc, assignment]


@dataclass
class StreamResponse:
    """Response from a streaming API call.

    Attributes:
        content: Full response text accumulated from stream
        input_tokens: Number of tokens in the prompt
        output_tokens: Number of tokens in the completion
        stop_reason: Why generation stopped ('end_turn', 'max_tokens', etc.)
        model: Model identifier used
    """

    content: str
    input_tokens: int
    output_tokens: int
    stop_reason: Optional[str]
    model: str

    @property
    def total_tokens(self) -> int:
        """Total tokens used (input + output)."""
        return self.input_tokens + self.output_tokens

    @property
    def was_truncated(self) -> bool:
        """Whether output was truncated due to max_tokens."""
        return self.stop_reason == "max_tokens"


class AnthropicTransport:
    """Transport wrapper for Anthropic Claude API.

    Handles:
    - Client initialization and configuration
    - Streaming message execution
    - Token usage extraction
    - Error handling and graceful degradation

    Example:
        transport = AnthropicTransport()
        response = transport.stream_message(
            model="claude-sonnet-4-5",
            system="You are a helpful assistant.",
            user_content="Hello, Claude!",
            max_tokens=1024,
        )
        print(response.content)
        print(f"Used {response.total_tokens} tokens")
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Anthropic transport.

        Args:
            api_key: Anthropic API key. Defaults to ANTHROPIC_API_KEY env var.

        Raises:
            ImportError: If anthropic package is not installed.
        """
        if Anthropic is None:
            raise ImportError(
                "anthropic package not installed. " "Install with: pip install anthropic"
            )

        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._client: Optional[Anthropic] = None

    @property
    def client(self) -> Anthropic:
        """Lazy-initialized Anthropic client."""
        if self._client is None:
            self._client = Anthropic(api_key=self._api_key)
        return self._client

    def stream_message(
        self,
        model: str,
        system: str,
        user_content: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> StreamResponse:
        """Execute a streaming message request.

        Args:
            model: Claude model identifier (e.g., 'claude-sonnet-4-5')
            system: System prompt content
            user_content: User message content
            max_tokens: Maximum tokens for completion
            temperature: Sampling temperature (0-1)

        Returns:
            StreamResponse with accumulated content and usage metadata
        """
        # Cap max_tokens to Claude's limit
        effective_max_tokens = min(max_tokens, 64000)

        with self.client.messages.stream(
            model=model,
            max_tokens=effective_max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}],
            temperature=temperature,
        ) as stream:
            # Accumulate streaming response
            content = ""
            for text in stream.text_stream:
                content += text

            # Get final message for metadata
            response = stream.get_final_message()

        return StreamResponse(
            content=content,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=getattr(response, "stop_reason", None),
            model=model,
        )

    def stream_message_with_callback(
        self,
        model: str,
        system: str,
        user_content: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        on_text: Optional[Any] = None,
    ) -> StreamResponse:
        """Execute a streaming request with real-time text callback.

        Args:
            model: Claude model identifier
            system: System prompt content
            user_content: User message content
            max_tokens: Maximum tokens for completion
            temperature: Sampling temperature
            on_text: Callback function(text: str) called for each chunk

        Returns:
            StreamResponse with accumulated content and usage metadata
        """
        effective_max_tokens = min(max_tokens, 64000)

        with self.client.messages.stream(
            model=model,
            max_tokens=effective_max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}],
            temperature=temperature,
        ) as stream:
            content = ""
            for text in stream.text_stream:
                content += text
                if on_text is not None:
                    on_text(text)

            response = stream.get_final_message()

        return StreamResponse(
            content=content,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=getattr(response, "stop_reason", None),
            model=model,
        )

    def stream_chunks(
        self,
        model: str,
        system: str,
        user_content: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> Iterator[str]:
        """Yield text chunks as they arrive from the stream.

        Args:
            model: Claude model identifier
            system: System prompt content
            user_content: User message content
            max_tokens: Maximum tokens for completion
            temperature: Sampling temperature

        Yields:
            Text chunks as they arrive from the API
        """
        effective_max_tokens = min(max_tokens, 64000)

        with self.client.messages.stream(
            model=model,
            max_tokens=effective_max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}],
            temperature=temperature,
        ) as stream:
            for text in stream.text_stream:
                yield text

    @staticmethod
    def calculate_utilization(output_tokens: int, max_tokens: int) -> float:
        """Calculate token utilization percentage.

        Args:
            output_tokens: Actual output tokens used
            max_tokens: Maximum tokens allowed

        Returns:
            Utilization percentage (0-100)
        """
        if max_tokens <= 0:
            return 0.0
        return (output_tokens / max_tokens) * 100

    @staticmethod
    def is_high_utilization(output_tokens: int, max_tokens: int, threshold: float = 95.0) -> bool:
        """Check if token utilization exceeds threshold.

        Args:
            output_tokens: Actual output tokens used
            max_tokens: Maximum tokens allowed
            threshold: Utilization percentage threshold (default 95%)

        Returns:
            True if utilization >= threshold
        """
        return AnthropicTransport.calculate_utilization(output_tokens, max_tokens) >= threshold
