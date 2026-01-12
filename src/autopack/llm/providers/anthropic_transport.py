"""Anthropic SDK transport layer with typed exceptions

This module provides a clean abstraction over the Anthropic SDK for HTTP transport,
separating concerns between network communication and prompt/parsing logic.

Extracted from anthropic_clients.py as part of PR-LLM-1 (Item 1.1: god file refactoring).
"""

import os
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

try:
    from anthropic import Anthropic
    from anthropic.types import Message, ContentBlock, Usage
except ImportError:
    Anthropic = None
    Message = None
    ContentBlock = None
    Usage = None


logger = logging.getLogger(__name__)


# ============================================================================
# Typed Exceptions
# ============================================================================


class AnthropicTransportError(Exception):
    """Base exception for transport layer errors"""
    pass


class AnthropicTransportTimeout(AnthropicTransportError):
    """Raised when request times out"""
    pass


class AnthropicTransportNetworkError(AnthropicTransportError):
    """Raised when network/connection errors occur"""
    pass


class AnthropicTransportApiError(AnthropicTransportError):
    """Raised when API returns an error (with status code)"""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


# ============================================================================
# Response Data Structure
# ============================================================================


@dataclass
class TransportUsage:
    """Token usage information from API response"""
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class TransportResponse:
    """Normalized response from Anthropic API"""
    content: str
    usage: TransportUsage
    stop_reason: Optional[str]
    model: str


# ============================================================================
# Transport Wrapper
# ============================================================================


class AnthropicTransport:
    """Pure HTTP transport wrapper for Anthropic SDK

    This class handles only network communication with the Anthropic API,
    delegating all prompt building and response parsing to higher layers.

    Provides:
    - Typed exception hierarchy for different error categories
    - Configurable timeout with default 60s
    - Usage extraction (input_tokens, output_tokens)
    - Support for both streaming and non-streaming modes
    - API key from environment (ANTHROPIC_API_KEY)
    """

    DEFAULT_TIMEOUT = 60.0  # seconds

    def __init__(self, api_key: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT):
        """Initialize transport wrapper

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            timeout: Request timeout in seconds (default: 60s)

        Raises:
            AnthropicTransportError: If anthropic package not installed or API key missing
        """
        if Anthropic is None:
            raise AnthropicTransportError(
                "anthropic package not installed. Install with: pip install anthropic"
            )

        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise AnthropicTransportError(
                "ANTHROPIC_API_KEY environment variable not set and no api_key provided"
            )

        self.client = Anthropic(api_key=api_key, timeout=timeout)
        self.timeout = timeout

    def send_request(
        self,
        messages: list,
        model: str,
        max_tokens: int,
        system: Optional[str] = None,
        temperature: float = 1.0,
        stream: bool = False,
    ) -> TransportResponse:
        """Send request to Anthropic API (non-streaming)

        Args:
            messages: List of message dicts [{"role": "user", "content": "..."}]
            model: Model identifier (e.g., "claude-sonnet-4-5")
            max_tokens: Maximum tokens to generate
            system: Optional system prompt
            temperature: Sampling temperature (default: 1.0)
            stream: If True, use streaming mode (default: False)

        Returns:
            TransportResponse with content, usage, and stop_reason

        Raises:
            AnthropicTransportTimeout: On timeout
            AnthropicTransportNetworkError: On connection errors
            AnthropicTransportApiError: On API errors (with status code)
        """
        if stream:
            return self._send_streaming_request(
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                system=system,
                temperature=temperature,
            )
        else:
            return self._send_non_streaming_request(
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                system=system,
                temperature=temperature,
            )

    def _send_non_streaming_request(
        self,
        messages: list,
        model: str,
        max_tokens: int,
        system: Optional[str] = None,
        temperature: float = 1.0,
    ) -> TransportResponse:
        """Send non-streaming request to Anthropic API"""
        try:
            kwargs: Dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
                "temperature": temperature,
            }
            if system is not None:
                kwargs["system"] = system

            response = self.client.messages.create(**kwargs)

            # Extract content from first content block
            content = response.content[0].text if response.content else ""

            # Extract usage
            usage = TransportUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

            # Extract stop reason
            stop_reason = getattr(response, "stop_reason", None)

            return TransportResponse(
                content=content,
                usage=usage,
                stop_reason=stop_reason,
                model=response.model,
            )

        except Exception as e:
            self._handle_exception(e)

    def _send_streaming_request(
        self,
        messages: list,
        model: str,
        max_tokens: int,
        system: Optional[str] = None,
        temperature: float = 1.0,
    ) -> TransportResponse:
        """Send streaming request to Anthropic API"""
        try:
            kwargs: Dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
                "temperature": temperature,
            }
            if system is not None:
                kwargs["system"] = system

            # Use streaming context manager
            with self.client.messages.stream(**kwargs) as stream:
                # Collect streaming text
                content = ""
                for text in stream.text_stream:
                    content += text

                # Get final message for usage metadata
                response = stream.get_final_message()

            # Extract usage
            usage = TransportUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

            # Extract stop reason
            stop_reason = getattr(response, "stop_reason", None)

            return TransportResponse(
                content=content,
                usage=usage,
                stop_reason=stop_reason,
                model=response.model,
            )

        except Exception as e:
            self._handle_exception(e)

    def _handle_exception(self, e: Exception) -> None:
        """Convert exceptions to typed transport errors"""
        error_msg = str(e).lower()

        # Timeout errors
        if "timeout" in error_msg or "timed out" in error_msg:
            raise AnthropicTransportTimeout(f"Request timed out: {e}") from e

        # Network/connection errors
        if any(
            keyword in error_msg
            for keyword in ["connection", "network", "unreachable", "refused"]
        ):
            raise AnthropicTransportNetworkError(f"Network error: {e}") from e

        # API errors with status codes
        # Check if exception has status_code attribute (from anthropic SDK)
        if hasattr(e, "status_code"):
            status_code = getattr(e, "status_code")
            raise AnthropicTransportApiError(
                f"API error: {e}", status_code=status_code
            ) from e

        # Parse status code from error message if present
        import re

        status_match = re.search(r"status[_\s]code[:\s]+(\d+)", error_msg)
        if status_match:
            status_code = int(status_match.group(1))
            raise AnthropicTransportApiError(
                f"API error: {e}", status_code=status_code
            ) from e

        # Check for common HTTP status indicators in message
        if any(code in error_msg for code in ["400", "429", "500", "502", "503"]):
            # Try to extract status code
            for code in [400, 429, 500, 502, 503]:
                if str(code) in error_msg:
                    raise AnthropicTransportApiError(
                        f"API error: {e}", status_code=code
                    ) from e

        # Generic API error
        if "api" in error_msg or "rate limit" in error_msg:
            raise AnthropicTransportApiError(f"API error: {e}") from e

        # Unknown error - wrap as generic transport error
        raise AnthropicTransportError(f"Transport error: {e}") from e
