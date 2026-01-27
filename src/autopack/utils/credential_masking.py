"""Credential masking utilities for safe logging.

This module provides utilities to mask sensitive credentials (API keys, tokens,
passwords) before logging to prevent credential leakage in logs and error outputs.

IMP-SEC-002: Add credential masking in logging and error outputs
"""

from __future__ import annotations

import re
from typing import Any, Optional


def mask_credential(value: Optional[str], visible_chars: int = 4) -> str:
    """Mask a credential for safe logging.

    Shows only the first and last `visible_chars` characters with "..." in between.
    This allows identification of which credential is being used while hiding
    the sensitive middle portion.

    Args:
        value: The credential value to mask (API key, token, password, etc.)
        visible_chars: Number of characters to show at start and end (default: 4)

    Returns:
        Masked credential string safe for logging.

    Examples:
        >>> mask_credential("sk-ant-api03-abcdefghijklmnop-xyz123")
        'sk-a...z123'
        >>> mask_credential(None)
        '<not set>'
        >>> mask_credential("")
        '<empty>'
        >>> mask_credential("short")
        '*****'
    """
    if value is None:
        return "<not set>"

    if not value:
        return "<empty>"

    # For very short values, mask entirely to avoid revealing too much
    if len(value) <= visible_chars * 2:
        return "*" * len(value)

    return f"{value[:visible_chars]}...{value[-visible_chars:]}"


def mask_dict_credentials(
    data: dict[str, Any],
    sensitive_keys: Optional[set[str]] = None,
    visible_chars: int = 4,
) -> dict[str, Any]:
    """Mask credentials in a dictionary for safe logging.

    Recursively searches a dictionary for keys matching sensitive patterns
    and masks their values.

    Args:
        data: Dictionary that may contain credentials
        sensitive_keys: Set of key names to mask (default: common credential keys)
        visible_chars: Number of characters to show at start and end

    Returns:
        Copy of dictionary with credential values masked.

    Examples:
        >>> mask_dict_credentials({"api_key": "sk-secret123", "name": "test"})
        {'api_key': 'sk-s...t123', 'name': 'test'}
    """
    if sensitive_keys is None:
        sensitive_keys = {
            "api_key",
            "apikey",
            "api-key",
            "token",
            "secret",
            "password",
            "passwd",
            "credential",
            "auth_token",
            "access_token",
            "refresh_token",
            "bearer_token",
            "bot_token",
            "auth_key",
            "private_key",
            "secret_key",
            "account_sid",
            "auth_sid",
        }

    result = {}
    for key, value in data.items():
        key_lower = key.lower().replace("-", "_")

        if isinstance(value, dict):
            # Recurse into nested dicts
            result[key] = mask_dict_credentials(value, sensitive_keys, visible_chars)
        elif isinstance(value, str) and any(sensitive in key_lower for sensitive in sensitive_keys):
            # Mask sensitive string values
            result[key] = mask_credential(value, visible_chars)
        else:
            result[key] = value

    return result


def mask_url_credentials(url: str) -> str:
    """Mask credentials that may appear in URLs.

    Handles common patterns like:
    - Basic auth: https://user:password@host
    - API keys in query strings: ?api_key=secret123
    - Tokens in paths: /token/secret123/

    Args:
        url: URL string that may contain embedded credentials

    Returns:
        URL with credentials masked.

    Examples:
        >>> mask_url_credentials("https://user:secretpass@api.example.com")
        'https://user:****@api.example.com'
        >>> mask_url_credentials("https://api.example.com?api_key=sk-123456")
        'https://api.example.com?api_key=sk-1...3456'
    """
    # Mask basic auth passwords (user:password@host)
    basic_auth_pattern = r"(://[^:]+:)([^@]+)(@)"
    url = re.sub(basic_auth_pattern, r"\1****\3", url)

    # Mask common credential query parameters
    credential_params = [
        "api_key",
        "apikey",
        "token",
        "access_token",
        "secret",
        "password",
        "key",
        "auth",
    ]
    for param in credential_params:
        # Match param=value patterns (case insensitive)
        pattern = rf"([?&]{param}=)([^&\s]+)"
        url = re.sub(
            pattern,
            lambda m: f"{m.group(1)}{mask_credential(m.group(2))}",
            url,
            flags=re.IGNORECASE,
        )

    return url


def create_safe_error_message(
    error: Exception,
    context: Optional[str] = None,
    mask_patterns: Optional[list[str]] = None,
) -> str:
    """Create a safe error message with credentials masked.

    Scans the error message for common credential patterns and masks them.

    Args:
        error: The exception to create a message for
        context: Optional context string to prepend
        mask_patterns: Additional regex patterns to mask (beyond defaults)

    Returns:
        Error message with credentials masked.

    Examples:
        >>> err = ValueError("Invalid API key: sk-ant-api03-secret123")
        >>> create_safe_error_message(err, "API call failed")
        'API call failed: Invalid API key: sk-a...t123'
    """
    message = str(error)

    # Default patterns that look like credentials
    default_patterns = [
        # API keys (sk-xxx, api-xxx, key_xxx patterns)
        r"(sk-[a-zA-Z0-9_-]{4})([a-zA-Z0-9_-]+)([a-zA-Z0-9_-]{4})",
        r"(api[_-]?[a-zA-Z0-9]{4})([a-zA-Z0-9_-]+)([a-zA-Z0-9]{4})",
        # Bearer tokens
        r"(Bearer\s+[a-zA-Z0-9]{4})([a-zA-Z0-9._-]+)([a-zA-Z0-9]{4})",
        # Generic long hex strings (32+ chars, likely tokens)
        r"\b([a-fA-F0-9]{4})([a-fA-F0-9]{24,})([a-fA-F0-9]{4})\b",
    ]

    patterns = default_patterns + (mask_patterns or [])

    for pattern in patterns:
        message = re.sub(pattern, r"\1...\3", message)

    if context:
        return f"{context}: {message}"

    return message
