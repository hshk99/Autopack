"""Outbound egress validation and SSRF guardrails.

This module provides utilities for validating outbound HTTP calls to prevent SSRF
and enforce an allowlist of external hosts.

Phase 5: Outbound egress allowlist / SSRF guardrails
- Validates destination hosts before outbound calls
- Logs all outbound requests for auditability
- Raises ValidationError for disallowed hosts
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

from autopack.config import settings
from autopack.exceptions import ValidationError

logger = logging.getLogger(__name__)


def validate_outbound_host(url: str, operation: Optional[str] = None) -> None:
    """Validate that the destination host is allowed for outbound calls.

    Args:
        url: The full URL to validate (e.g., "https://api.anthropic.com/v1/messages")
        operation: Optional description of the operation (for logging)

    Raises:
        ValidationError: If the host is not in the allowed list (when allowlist is configured)

    Examples:
        >>> validate_outbound_host("https://api.anthropic.com/v1/messages", "Claude API call")
        >>> validate_outbound_host("http://localhost:8080/health")  # Always allowed
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname

        if not host:
            raise ValidationError(f"Invalid URL (no hostname): {url}")

        # Always allow localhost and loopback addresses (private/internal use)
        if host in ("localhost", "127.0.0.1", "::1") or host.startswith("127."):
            logger.debug(f"Outbound call to localhost: {url} (operation: {operation or 'unknown'})")
            return

        # If no allowlist is configured, permit all hosts (default for private/internal use)
        if not settings.allowed_external_hosts:
            logger.debug(
                f"Outbound call (no allowlist): {host} (operation: {operation or 'unknown'})"
            )
            return

        # Check if host is in allowlist
        if host not in settings.allowed_external_hosts:
            msg = (
                f"Outbound call to {host} blocked by egress allowlist. "
                f"Allowed hosts: {', '.join(settings.allowed_external_hosts)}"
            )
            logger.warning(msg)
            raise ValidationError(msg)

        logger.info(f"Outbound call allowed: {host} (operation: {operation or 'unknown'})")

    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Error validating outbound host {url}: {e}")
        raise ValidationError(f"Failed to validate outbound URL: {e}") from e


def log_outbound_request(url: str, method: str = "GET", operation: Optional[str] = None) -> None:
    """Log an outbound HTTP request for auditability.

    Args:
        url: The full URL being requested
        method: HTTP method (GET, POST, etc.)
        operation: Optional description of the operation

    Examples:
        >>> log_outbound_request("https://api.anthropic.com/v1/messages", "POST", "Claude API call")
    """
    parsed = urlparse(url)
    host = parsed.hostname or "unknown"
    path = parsed.path or "/"

    logger.info(
        f"Outbound HTTP request: {method} {host}{path} (operation: {operation or 'unknown'})"
    )
