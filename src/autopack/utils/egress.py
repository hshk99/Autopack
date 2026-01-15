"""Outbound egress validation and SSRF guardrails.

This module provides utilities for validating outbound HTTP calls to prevent SSRF
and enforce an allowlist of external hosts.

Phase 5: Outbound egress allowlist / SSRF guardrails
- Validates destination hosts before outbound calls
- Logs all outbound requests for auditability
- Raises ValidationError for disallowed hosts
"""

from __future__ import annotations

import fnmatch
import ipaddress
import logging
from typing import Optional
from urllib.parse import urlparse

from autopack.config import settings
from autopack.exceptions import ValidationError

logger = logging.getLogger(__name__)


def _is_host_allowed(host: str, allowed_entries: list[str]) -> bool:
    """Check if a host matches any entries in the allowlist.

    Supports:
    - Exact matches: "api.anthropic.com"
    - Wildcard patterns: "*.anthropic.com" (uses fnmatch)
    - CIDR ranges: "192.168.0.0/16" (requires numeric IP hosts)

    Args:
        host: The hostname to check (FQDN or IP address)
        allowed_entries: List of allowed hostnames, wildcards, or CIDR ranges

    Returns:
        True if host matches any entry, False otherwise
    """
    for entry in allowed_entries:
        # Try exact match first (most common case)
        if host == entry:
            return True

        # Try wildcard pattern (e.g., "*.domain.com")
        if fnmatch.fnmatch(host, entry):
            return True

        # Try CIDR notation (e.g., "192.168.0.0/16")
        try:
            # Only attempt CIDR parsing if entry contains "/" and host is an IP
            if "/" in entry:
                try:
                    host_ip = ipaddress.ip_address(host)
                    network = ipaddress.ip_network(entry, strict=False)
                    if host_ip in network:
                        return True
                except (ValueError, ipaddress.NetmaskValueError):
                    # host is not a valid IP or entry is not a valid CIDR
                    pass
        except Exception:
            # Skip malformed CIDR entries
            pass

    return False


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

        # Check if host is in allowlist (supports exact, wildcard, and CIDR matching)
        if not _is_host_allowed(host, settings.allowed_external_hosts):
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
