"""Artifact redaction and scrubbing.

Implements PII/credential redaction for artifacts:
- Pattern-based redaction for text/JSON
- Browser artifact redaction (HAR logs, cookies)
- Configurable patterns per artifact type
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class RedactionCategory(str, Enum):
    """Categories of data to redact."""

    CREDENTIAL = "credential"  # API keys, tokens, passwords
    PII = "pii"  # Personal information
    FINANCIAL = "financial"  # Financial data
    SESSION = "session"  # Session tokens, cookies
    NETWORK = "network"  # IP addresses, URLs with auth


@dataclass
class RedactionPattern:
    """Pattern for redacting sensitive data."""

    name: str
    category: RedactionCategory
    pattern: str  # Regex pattern
    replacement: str = "[REDACTED]"
    case_insensitive: bool = True
    applies_to: list[str] = field(default_factory=list)  # File extensions

    def compile(self) -> re.Pattern:
        """Compile the regex pattern."""
        flags = re.IGNORECASE if self.case_insensitive else 0
        return re.compile(self.pattern, flags)


# Default redaction patterns
DEFAULT_REDACTION_PATTERNS = [
    # Credentials
    RedactionPattern(
        name="api_key",
        category=RedactionCategory.CREDENTIAL,
        pattern=r'(["\']?(?:api[_-]?key|apikey)["\']?\s*[:=]\s*)["\']?([a-zA-Z0-9_-]{20,})["\']?',
        replacement=r"\1[REDACTED_API_KEY]",
    ),
    RedactionPattern(
        name="bearer_token",
        category=RedactionCategory.CREDENTIAL,
        pattern=r"(Bearer\s+)([a-zA-Z0-9._-]+)",
        replacement=r"\1[REDACTED_TOKEN]",
    ),
    RedactionPattern(
        name="password",
        category=RedactionCategory.CREDENTIAL,
        pattern=r'(["\']?password["\']?\s*[:=]\s*)["\']?([^"\'\s,}]+)["\']?',
        replacement=r"\1[REDACTED_PASSWORD]",
    ),
    RedactionPattern(
        name="secret",
        category=RedactionCategory.CREDENTIAL,
        pattern=r'(["\']?(?:secret|client_secret|api_secret)["\']?\s*[:=]\s*)["\']?([a-zA-Z0-9_-]{16,})["\']?',
        replacement=r"\1[REDACTED_SECRET]",
    ),
    RedactionPattern(
        name="auth_header",
        category=RedactionCategory.CREDENTIAL,
        pattern=r"(Authorization:\s*)(.+)",
        replacement=r"\1[REDACTED_AUTH]",
    ),
    RedactionPattern(
        name="oauth_token",
        category=RedactionCategory.CREDENTIAL,
        pattern=r'(access_token|refresh_token)["\']?\s*[:=]\s*["\']?([a-zA-Z0-9._-]+)["\']?',
        replacement=r"\1=[REDACTED_TOKEN]",
    ),
    # Session data
    RedactionPattern(
        name="cookie_value",
        category=RedactionCategory.SESSION,
        pattern=r"(Cookie:\s*)(.+)",
        replacement=r"\1[REDACTED_COOKIES]",
    ),
    RedactionPattern(
        name="set_cookie",
        category=RedactionCategory.SESSION,
        pattern=r"(Set-Cookie:\s*)(.+)",
        replacement=r"\1[REDACTED_COOKIE]",
    ),
    RedactionPattern(
        name="session_id",
        category=RedactionCategory.SESSION,
        pattern=r'(session[_-]?id["\']?\s*[:=]\s*)["\']?([a-zA-Z0-9_-]+)["\']?',
        replacement=r"\1[REDACTED_SESSION]",
    ),
    # PII patterns
    RedactionPattern(
        name="email",
        category=RedactionCategory.PII,
        pattern=r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        replacement="[REDACTED_EMAIL]",
    ),
    RedactionPattern(
        name="phone",
        category=RedactionCategory.PII,
        pattern=r"(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}",
        replacement="[REDACTED_PHONE]",
    ),
    RedactionPattern(
        name="ssn",
        category=RedactionCategory.PII,
        pattern=r"\b\d{3}-\d{2}-\d{4}\b",
        replacement="[REDACTED_SSN]",
    ),
    # Financial
    RedactionPattern(
        name="credit_card",
        category=RedactionCategory.FINANCIAL,
        pattern=r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b",
        replacement="[REDACTED_CARD]",
    ),
    RedactionPattern(
        name="bank_account",
        category=RedactionCategory.FINANCIAL,
        pattern=r'(account[_-]?(?:number|no)["\']?\s*[:=]\s*)["\']?([0-9]{8,17})["\']?',
        replacement=r"\1[REDACTED_ACCOUNT]",
    ),
    # Network
    RedactionPattern(
        name="ip_address",
        category=RedactionCategory.NETWORK,
        pattern=r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b",
        replacement="[REDACTED_IP]",
    ),
    RedactionPattern(
        name="url_with_auth",
        category=RedactionCategory.NETWORK,
        pattern=r"(https?://)([^:]+):([^@]+)@",
        replacement=r"\1[REDACTED_USER]:[REDACTED_PASS]@",
    ),
]


class ArtifactRedactor:
    """Service for redacting sensitive data from artifacts.

    Usage:
        redactor = ArtifactRedactor()

        # Redact text content
        clean_text = redactor.redact_text(sensitive_text)

        # Redact HAR log
        clean_har = redactor.redact_har(har_data)

        # Redact file in place
        redactor.redact_file(Path("logs/api_response.json"))
    """

    def __init__(
        self,
        patterns: Optional[list[RedactionPattern]] = None,
        categories: Optional[list[RedactionCategory]] = None,
    ):
        """Initialize the redactor.

        Args:
            patterns: Custom patterns (defaults to DEFAULT_REDACTION_PATTERNS)
            categories: Categories to enable (defaults to all)
        """
        self._patterns = patterns or DEFAULT_REDACTION_PATTERNS
        self._enabled_categories = set(categories) if categories else set(RedactionCategory)
        self._compiled_patterns: list[tuple[RedactionPattern, re.Pattern]] = []
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex patterns."""
        self._compiled_patterns = []
        for pattern in self._patterns:
            if pattern.category in self._enabled_categories:
                try:
                    compiled = pattern.compile()
                    self._compiled_patterns.append((pattern, compiled))
                except re.error as e:
                    logger.warning(f"Failed to compile pattern {pattern.name}: {e}")

    def add_pattern(self, pattern: RedactionPattern) -> None:
        """Add a custom redaction pattern."""
        self._patterns.append(pattern)
        if pattern.category in self._enabled_categories:
            try:
                compiled = pattern.compile()
                self._compiled_patterns.append((pattern, compiled))
            except re.error as e:
                logger.warning(f"Failed to compile pattern {pattern.name}: {e}")

    def redact_text(self, text: str) -> tuple[str, int]:
        """Redact sensitive data from text.

        Args:
            text: Text to redact

        Returns:
            Tuple of (redacted_text, redaction_count)
        """
        result = text
        count = 0

        for pattern, compiled in self._compiled_patterns:
            matches = compiled.findall(result)
            if matches:
                count += len(matches)
                result = compiled.sub(pattern.replacement, result)

        return result, count

    def redact_dict(self, data: dict, depth: int = 0, max_depth: int = 10) -> dict:
        """Recursively redact sensitive data from a dictionary.

        Args:
            data: Dictionary to redact
            depth: Current recursion depth
            max_depth: Maximum recursion depth

        Returns:
            Redacted dictionary
        """
        if depth > max_depth:
            return data

        result = {}
        for key, value in data.items():
            # Check if key itself is sensitive
            key_lower = key.lower()
            if any(
                s in key_lower
                for s in [
                    "password",
                    "secret",
                    "token",
                    "key",
                    "auth",
                    "credential",
                    "cookie",
                ]
            ):
                if isinstance(value, str) and len(value) > 0:
                    result[key] = "[REDACTED]"
                    continue

            if isinstance(value, str):
                result[key], _ = self.redact_text(value)
            elif isinstance(value, dict):
                result[key] = self.redact_dict(value, depth + 1, max_depth)
            elif isinstance(value, list):
                result[key] = [
                    (
                        self.redact_dict(item, depth + 1, max_depth)
                        if isinstance(item, dict)
                        else (self.redact_text(item)[0] if isinstance(item, str) else item)
                    )
                    for item in value
                ]
            else:
                result[key] = value

        return result

    def redact_har(self, har_data: dict) -> dict:
        """Redact sensitive data from HAR (HTTP Archive) log.

        HAR logs are particularly sensitive as they contain:
        - Request/response headers (including auth tokens)
        - Cookies
        - POST body data
        - URL query parameters

        Args:
            har_data: HAR log data

        Returns:
            Redacted HAR data
        """
        result = har_data.copy()

        if "log" in result and "entries" in result["log"]:
            result["log"]["entries"] = [
                self._redact_har_entry(entry) for entry in result["log"]["entries"]
            ]

        return result

    def _redact_har_entry(self, entry: dict) -> dict:
        """Redact a single HAR entry."""
        result = entry.copy()

        # Redact request
        if "request" in result:
            request = result["request"].copy()

            # Redact URL
            if "url" in request:
                request["url"], _ = self.redact_text(request["url"])

            # Redact headers
            if "headers" in request:
                request["headers"] = self._redact_headers(request["headers"])

            # Redact cookies
            if "cookies" in request:
                request["cookies"] = [
                    {"name": c.get("name", ""), "value": "[REDACTED]"}
                    for c in request.get("cookies", [])
                ]

            # Redact query string
            if "queryString" in request:
                request["queryString"] = self._redact_query_params(request["queryString"])

            # Redact post data
            if "postData" in request:
                post_data = request["postData"].copy()
                if "text" in post_data:
                    post_data["text"], _ = self.redact_text(post_data["text"])
                if "params" in post_data:
                    post_data["params"] = self._redact_query_params(post_data["params"])
                request["postData"] = post_data

            result["request"] = request

        # Redact response
        if "response" in result:
            response = result["response"].copy()

            # Redact headers
            if "headers" in response:
                response["headers"] = self._redact_headers(response["headers"])

            # Redact cookies
            if "cookies" in response:
                response["cookies"] = [
                    {"name": c.get("name", ""), "value": "[REDACTED]"}
                    for c in response.get("cookies", [])
                ]

            # Redact content
            if "content" in response and "text" in response["content"]:
                content = response["content"].copy()
                content["text"], _ = self.redact_text(content["text"])
                response["content"] = content

            result["response"] = response

        return result

    def _redact_headers(self, headers: list[dict]) -> list[dict]:
        """Redact sensitive headers."""
        sensitive_headers = {
            "authorization",
            "cookie",
            "set-cookie",
            "x-api-key",
            "x-auth-token",
            "x-access-token",
            "proxy-authorization",
        }

        result = []
        for header in headers:
            name = header.get("name", "").lower()
            if name in sensitive_headers:
                result.append({"name": header["name"], "value": "[REDACTED]"})
            else:
                value = header.get("value", "")
                redacted, _ = self.redact_text(value)
                result.append({"name": header["name"], "value": redacted})

        return result

    def _redact_query_params(self, params: list[dict]) -> list[dict]:
        """Redact sensitive query parameters."""
        sensitive_params = {
            "token",
            "key",
            "api_key",
            "apikey",
            "secret",
            "password",
            "auth",
            "access_token",
            "refresh_token",
        }

        result = []
        for param in params:
            name = param.get("name", "").lower()
            if name in sensitive_params:
                result.append({"name": param["name"], "value": "[REDACTED]"})
            else:
                value = param.get("value", "")
                redacted, _ = self.redact_text(value)
                result.append({"name": param["name"], "value": redacted})

        return result

    def redact_file(
        self,
        path: Path,
        output_path: Optional[Path] = None,
    ) -> tuple[Path, int]:
        """Redact sensitive data from a file.

        Args:
            path: Path to file to redact
            output_path: Output path (defaults to overwriting original)

        Returns:
            Tuple of (output_path, redaction_count)
        """
        output_path = output_path or path
        count = 0

        suffix = path.suffix.lower()

        if suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            redacted = self.redact_dict(data)
            output_path.write_text(json.dumps(redacted, indent=2), encoding="utf-8")
            count = 1  # Approximate

        elif suffix == ".har":
            data = json.loads(path.read_text(encoding="utf-8"))
            redacted = self.redact_har(data)
            output_path.write_text(json.dumps(redacted, indent=2), encoding="utf-8")
            count = 1

        else:
            # Text file
            content = path.read_text(encoding="utf-8", errors="replace")
            redacted, count = self.redact_text(content)
            output_path.write_text(redacted, encoding="utf-8")

        logger.info(f"Redacted {path} -> {output_path} ({count} items)")

        return output_path, count

    def get_pattern_stats(self) -> dict:
        """Get statistics about loaded patterns."""
        by_category = {}
        for pattern in self._patterns:
            cat = pattern.category.value
            if cat not in by_category:
                by_category[cat] = 0
            by_category[cat] += 1

        return {
            "total_patterns": len(self._patterns),
            "active_patterns": len(self._compiled_patterns),
            "by_category": by_category,
            "enabled_categories": [c.value for c in self._enabled_categories],
        }
