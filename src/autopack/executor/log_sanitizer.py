"""Log sanitization utility for removing sensitive data from logs.

IMP-SEC-007: Removes environment variables, API keys, credentials, and other
sensitive information from error messages and debug logs to prevent exposure.
"""

import re
from typing import Any


class LogSanitizer:
    """Sanitizes logs to remove sensitive information."""

    # Patterns for common sensitive data
    _ENV_VAR_PATTERN = re.compile(
        r"([A-Z_][A-Z0-9_]*)\s*=\s*(?:['\"]?)([^'\"\s]+)(?:['\"]?)", re.IGNORECASE
    )

    # API key patterns for common providers
    _API_KEY_PATTERNS = {
        "together": re.compile(r"together[_-]?api[_-]?key\s*[:=]\s*([a-zA-Z0-9]+)", re.IGNORECASE),
        "openai": re.compile(r"openai[_-]?api[_-]?key\s*[:=]\s*(sk-[a-zA-Z0-9]+)", re.IGNORECASE),
        "runpod": re.compile(r"runpod[_-]?api[_-]?key\s*[:=]\s*([a-zA-Z0-9]+)", re.IGNORECASE),
        "anthropic": re.compile(
            r"anthropic[_-]?api[_-]?key\s*[:=]\s*([a-zA-Z0-9\-]+)", re.IGNORECASE
        ),
        "google": re.compile(r"google[_-]?api[_-]?key\s*[:=]\s*([a-zA-Z0-9_\-]+)", re.IGNORECASE),
        "github": re.compile(r"github[_-]?token\s*[:=]\s*(ghp_[a-zA-Z0-9]+)", re.IGNORECASE),
    }

    # Patterns for credentials
    _CREDENTIAL_PATTERNS = {
        "password": re.compile(r'password\s*[:=]\s*([^\s,}\]"\']+)', re.IGNORECASE),
        "secret": re.compile(r'secret\s*[:=]\s*([^\s,}\]"\']+)', re.IGNORECASE),
        "token": re.compile(r'token\s*[:=]\s*([^\s,}\]"\']+)', re.IGNORECASE),
        "jwt": re.compile(r'jwt\s*[:=]\s*([^\s,}\]"\']+)', re.IGNORECASE),
    }

    # Patterns for URLs with credentials
    _URL_WITH_CREDS_PATTERN = re.compile(r"(https?://)[a-zA-Z0-9_:\-\.]+@", re.IGNORECASE)

    # Common sensitive environment variables
    _SENSITIVE_ENV_VARS = {
        "DATABASE_URL",
        "DB_PASSWORD",
        "DB_USER",
        "API_KEY",
        "API_SECRET",
        "SECRET_KEY",
        "PRIVATE_KEY",
        "OAUTH_TOKEN",
        "JWT_SECRET",
        "TOGETHER_API_KEY",
        "RUNPOD_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GITHUB_TOKEN",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_ACCESS_KEY_ID",
        "AZURE_CREDENTIALS",
        "GCP_CREDENTIALS",
    }

    # Patterns for common structured secret formats
    _SECRET_FORMATS = {
        "url": re.compile(r"((?:https?|postgresql|mysql|mongodb)://[^\s]+)", re.IGNORECASE),
        "json": re.compile(r"(\{[^{}]*(?:key|secret|password|token)[^{}]*\})", re.IGNORECASE),
        "path": re.compile(r"(/[^\s]*(?:secret|private|credential|key)[^\s]*)", re.IGNORECASE),
    }

    @classmethod
    def sanitize(cls, data: Any) -> str:
        """Sanitize data by removing sensitive information.

        Args:
            data: Data to sanitize (will be converted to string if not already)

        Returns:
            Sanitized string with sensitive data replaced with [REDACTED]
        """
        if data is None:
            return "[None]"

        text = str(data)
        return cls._sanitize_text(text)

    @classmethod
    def sanitize_exception(cls, exception: Exception) -> str:
        """Sanitize an exception message.

        Args:
            exception: Exception to sanitize

        Returns:
            Sanitized exception string
        """
        return cls.sanitize(str(exception))

    @classmethod
    def _sanitize_text(cls, text: str) -> str:
        """Internal method to sanitize a text string.

        Args:
            text: Text to sanitize

        Returns:
            Sanitized text
        """
        if not text:
            return text

        # Remove URLs with credentials
        text = cls._URL_WITH_CREDS_PATTERN.sub(r"\1[REDACTED]@", text)

        # Remove API keys
        for provider, pattern in cls._API_KEY_PATTERNS.items():
            text = pattern.sub(f"{provider.upper()}_API_KEY=[REDACTED]", text)

        # Remove credentials
        for cred_type, pattern in cls._CREDENTIAL_PATTERNS.items():
            text = pattern.sub(f"{cred_type.upper()}=[REDACTED]", text)

        # Remove sensitive environment variables
        for env_var in cls._SENSITIVE_ENV_VARS:
            # Pattern: VAR_NAME = value or VAR_NAME: value
            # Construct pattern string to avoid f-string brace issues
            pattern_str = env_var + r'\s*[:=]\s*[^\s,}\]"\']+'
            pattern = re.compile(pattern_str, re.IGNORECASE)
            text = pattern.sub(f"{env_var}=[REDACTED]", text)

        # Remove common structured formats
        for format_type, pattern in cls._SECRET_FORMATS.items():
            # Only redact if it looks like it might contain secrets
            matches = pattern.finditer(text)
            for match in matches:
                matched_text = match.group(1)
                if any(
                    keyword in matched_text.lower()
                    for keyword in ["password", "secret", "key", "token", "credential", "auth"]
                ):
                    text = text.replace(matched_text, "[REDACTED]")

        return text

    @classmethod
    def sanitize_dict(cls, data: dict) -> dict:
        """Sanitize a dictionary by sanitizing all values.

        Args:
            data: Dictionary to sanitize

        Returns:
            New dictionary with sanitized values
        """
        result = {}
        for key, value in data.items():
            if isinstance(value, dict):
                result[key] = cls.sanitize_dict(value)
            elif isinstance(value, list):
                result[key] = [cls.sanitize(v) if isinstance(v, str) else v for v in value]
            elif isinstance(value, str):
                result[key] = cls.sanitize(value)
            else:
                result[key] = value
        return result
