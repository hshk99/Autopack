"""
Context Sanitization for Error Reporting

Provides robust redaction of sensitive information before persisting to disk.
Used by error_reporter.py and main.py exception handlers to prevent secret leakage.

BUILD-188: Security baseline - sanitize before writing any error artifacts.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Sensitive key patterns (case-insensitive matching)
# ---------------------------------------------------------------------------

# Headers that commonly contain credentials or session tokens
SENSITIVE_HEADERS: Set[str] = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
    "x-github-token",
    "x-access-token",
    "x-refresh-token",
    "x-session-id",
    "x-csrf-token",
    "proxy-authorization",
    "www-authenticate",
}

# Query/body keys that may contain secrets
SENSITIVE_KEYS: Set[str] = {
    "token",
    "secret",
    "password",
    "passwd",
    "pwd",
    "api_key",
    "apikey",
    "api-key",
    "access_key",
    "secret_key",
    "private_key",
    "jwt",
    "session",
    "session_id",
    "sessionid",
    "auth",
    "credentials",
    "credential",
    "bearer",
    "oauth",
    "refresh_token",
    "access_token",
    "id_token",
    "client_secret",
    "database_url",
    "db_url",
    "connection_string",
    "conn_str",
}

# Patterns to detect sensitive values in strings (e.g., URLs with credentials)
SENSITIVE_PATTERNS: List[re.Pattern] = [
    # Database URLs with credentials: postgresql://user:pass@host/db
    re.compile(r"(postgresql|mysql|mongodb|redis|sqlite)://[^:]+:[^@]+@", re.IGNORECASE),
    # Bearer tokens
    re.compile(r"bearer\s+[a-zA-Z0-9\-_\.]+", re.IGNORECASE),
    # API keys (common formats)
    re.compile(r"(sk|pk|api)[_-]?(live|test|key)?[_-]?[a-zA-Z0-9]{20,}", re.IGNORECASE),
    # JWT tokens (header.payload.signature format)
    re.compile(r"eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+"),
]

# Redaction placeholder
REDACTED = "[REDACTED]"

# Maximum length for values before truncation
MAX_VALUE_LENGTH = 200
MAX_NESTED_DEPTH = 5


def _is_sensitive_key(key: str) -> bool:
    """Check if a key name indicates sensitive content."""
    if not isinstance(key, str):
        return False
    key_lower = key.lower().replace("-", "_")
    return key_lower in SENSITIVE_KEYS or key_lower in SENSITIVE_HEADERS


def _redact_sensitive_patterns(value: str) -> str:
    """Redact known sensitive patterns in a string value."""
    result = value
    for pattern in SENSITIVE_PATTERNS:
        result = pattern.sub(REDACTED, result)
    return result


def _truncate(value: str, max_length: int = MAX_VALUE_LENGTH) -> str:
    """Truncate a string value if it exceeds max length."""
    if len(value) <= max_length:
        return value
    return value[:max_length] + f"... [truncated, {len(value)} chars total]"


def sanitize_value(value: Any, depth: int = 0) -> Any:
    """
    Sanitize a single value, redacting sensitive patterns and truncating.

    Args:
        value: The value to sanitize
        depth: Current nesting depth (to prevent infinite recursion)

    Returns:
        Sanitized value
    """
    if depth > MAX_NESTED_DEPTH:
        return "[NESTED_TOO_DEEP]"

    if value is None:
        return None

    if isinstance(value, str):
        # First redact known patterns, then truncate
        sanitized = _redact_sensitive_patterns(value)
        return _truncate(sanitized)

    if isinstance(value, (int, float, bool)):
        return value

    if isinstance(value, dict):
        return sanitize_dict(value, depth + 1)

    if isinstance(value, (list, tuple)):
        return [sanitize_value(item, depth + 1) for item in value[:50]]  # Limit list size

    # For other types, convert to string and sanitize
    try:
        str_value = repr(value)[: MAX_VALUE_LENGTH * 2]
        return _truncate(_redact_sensitive_patterns(str_value))
    except Exception:
        return "[UNSERIALIZABLE]"


def sanitize_dict(data: Dict[str, Any], depth: int = 0) -> Dict[str, Any]:
    """
    Sanitize a dictionary, redacting sensitive keys and values.

    Args:
        data: Dictionary to sanitize
        depth: Current nesting depth

    Returns:
        Sanitized dictionary
    """
    if depth > MAX_NESTED_DEPTH:
        return {"_error": "[NESTED_TOO_DEEP]"}

    if not isinstance(data, dict):
        return {"_error": f"[NOT_A_DICT: {type(data).__name__}]"}

    result = {}
    for key, value in data.items():
        str_key = str(key) if not isinstance(key, str) else key

        if _is_sensitive_key(str_key):
            result[str_key] = REDACTED
        else:
            result[str_key] = sanitize_value(value, depth)

    return result


def sanitize_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """
    Sanitize HTTP headers, redacting sensitive ones.

    Args:
        headers: Dictionary of header name -> value

    Returns:
        Sanitized headers dictionary
    """
    if not headers:
        return {}

    result = {}
    for key, value in headers.items():
        key_lower = key.lower()
        if key_lower in SENSITIVE_HEADERS or _is_sensitive_key(key):
            result[key] = REDACTED
        else:
            result[key] = _truncate(str(value))

    return result


def sanitize_query_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize URL query parameters, redacting sensitive ones.

    Args:
        params: Dictionary of query param name -> value

    Returns:
        Sanitized params dictionary
    """
    if not params:
        return {}

    result = {}
    for key, value in params.items():
        if _is_sensitive_key(key):
            result[key] = REDACTED
        else:
            # Handle multi-value params
            if isinstance(value, list):
                result[key] = [_truncate(str(v)) for v in value[:10]]
            else:
                result[key] = _truncate(str(value))

    return result


def sanitize_stack_frames(
    frames: List[Dict[str, Any]], redact_locals: bool = True
) -> List[Dict[str, Any]]:
    """
    Sanitize stack frame information, optionally redacting local variables.

    Args:
        frames: List of stack frame dictionaries
        redact_locals: If True, redact local_vars entirely; if False, sanitize them

    Returns:
        Sanitized frames list
    """
    if not frames:
        return []

    result = []
    for frame in frames:
        sanitized_frame = {
            "filename": frame.get("filename", ""),
            "function": frame.get("function", ""),
            "line_number": frame.get("line_number", 0),
        }

        if redact_locals:
            # By default, don't persist local vars at all (they often contain secrets)
            sanitized_frame["local_vars"] = "[REDACTED_BY_POLICY]"
        else:
            # If explicitly allowed, sanitize them
            local_vars = frame.get("local_vars", {})
            if isinstance(local_vars, dict):
                sanitized_frame["local_vars"] = sanitize_dict(local_vars)
            else:
                sanitized_frame["local_vars"] = "[INVALID_LOCALS]"

        result.append(sanitized_frame)

    return result


def sanitize_context(
    context_data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    query_params: Optional[Dict[str, Any]] = None,
    stack_frames: Optional[List[Dict[str, Any]]] = None,
    redact_stack_locals: bool = True,
) -> Dict[str, Any]:
    """
    Comprehensive context sanitization for error reporting.

    This is the main entry point for sanitizing all context data before
    persisting to disk. It applies appropriate redaction to each data type.

    Args:
        context_data: General context dictionary (request body, state, etc.)
        headers: HTTP headers
        query_params: URL query parameters
        stack_frames: Stack trace frame information
        redact_stack_locals: Whether to redact local variables in stack frames

    Returns:
        Dictionary with all sanitized components
    """
    result = {}

    if context_data is not None:
        result["context_data"] = sanitize_dict(context_data)

    if headers is not None:
        result["headers"] = sanitize_headers(headers)

    if query_params is not None:
        result["query_params"] = sanitize_query_params(query_params)

    if stack_frames is not None:
        result["stack_frames"] = sanitize_stack_frames(
            stack_frames, redact_locals=redact_stack_locals
        )

    return result


def sanitize_url(url: str) -> str:
    """
    Sanitize a URL, redacting credentials if present.

    Handles URLs like: postgresql://user:password@host/db

    Args:
        url: URL string to sanitize

    Returns:
        Sanitized URL with credentials redacted
    """
    if not url:
        return ""

    # Pattern to match credentials in URLs
    url_cred_pattern = re.compile(r"(://[^:]+:)([^@]+)(@)")

    return url_cred_pattern.sub(r"\1[REDACTED]\3", url)
