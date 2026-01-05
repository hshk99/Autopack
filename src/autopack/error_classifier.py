"""
Error classification system to prevent infinite retry loops on deterministic failures.

Key principle: Never retry a request that fails deterministically with the same inputs.

Per BUILD-130 Phase 0: Circuit Breaker implementation.
"""

from enum import Enum
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class ErrorClass(Enum):
    """Error classification for retry strategy"""

    TRANSIENT_INFRA = "transient_infra"  # Infrastructure errors - retry with backoff
    TRANSIENT_LLM = "transient_llm"  # LLM errors (rate limit, overload) - retry
    DETERMINISTIC_SCHEMA = "deterministic_schema"  # Schema/DB violations - fail-fast
    DETERMINISTIC_LOGIC = "deterministic_logic"  # Logic errors - fail-fast
    DETERMINISTIC_INPUT = "deterministic_input"  # Invalid input - fail-fast


class ErrorClassifier:
    """
    Classify errors to determine retry strategy.

    Prevents infinite retry loops by identifying deterministic failures
    that will never succeed with the same inputs.
    """

    def classify_api_error(
        self, status_code: int, response_body: str, request_data: Optional[dict] = None
    ) -> Tuple[ErrorClass, str]:
        """
        Classify API error to determine retry strategy.

        Args:
            status_code: HTTP status code
            response_body: Response body text
            request_data: Optional request data for context

        Returns:
            (error_class, remediation_suggestion)
        """
        response_lower = response_body.lower() if response_body else ""

        # 500 errors: Check if deterministic schema violation or transient
        if status_code == 500:
            # Enum validation errors are deterministic schema issues
            if self._is_enum_violation(response_body):
                return (
                    ErrorClass.DETERMINISTIC_SCHEMA,
                    "Database contains invalid enum value. Run: python scripts/break_glass_repair.py diagnose",
                )

            # NOT NULL constraint violations are deterministic
            if "not null constraint" in response_lower or "integrity constraint" in response_lower:
                return (
                    ErrorClass.DETERMINISTIC_SCHEMA,
                    "Database schema constraint violation. Check required fields.",
                )

            # Serialization errors often indicate schema issues
            if "serialization" in response_lower or "cannot serialize" in response_lower:
                return (
                    ErrorClass.DETERMINISTIC_SCHEMA,
                    "Object serialization failed. Check database schema matches code models.",
                )

            # Other 500 errors are typically transient infrastructure issues
            return (ErrorClass.TRANSIENT_INFRA, "Server error - retry with exponential backoff")

        # 404 errors are deterministic (resource doesn't exist)
        if status_code == 404:
            return (
                ErrorClass.DETERMINISTIC_INPUT,
                "Resource not found. Check endpoint URL and resource ID.",
            )

        # 400 errors are deterministic input issues
        if status_code == 400:
            return (
                ErrorClass.DETERMINISTIC_INPUT,
                "Bad request - check request parameters and format.",
            )

        # 401/403 are authentication/authorization issues (deterministic)
        if status_code in (401, 403):
            return (
                ErrorClass.DETERMINISTIC_INPUT,
                "Authentication/authorization failed. Check API keys and permissions.",
            )

        # 429 is rate limiting (transient, retry with backoff)
        if status_code == 429:
            return (
                ErrorClass.TRANSIENT_LLM,
                "Rate limit exceeded - retry with exponential backoff (60s+)",
            )

        # 503 is service unavailable (transient)
        if status_code == 503:
            return (
                ErrorClass.TRANSIENT_INFRA,
                "Service temporarily unavailable - retry with backoff",
            )

        # Connection errors are transient
        if status_code == 0 or status_code is None:
            if any(
                marker in response_lower
                for marker in ["connection", "timeout", "timed out", "refused", "reset"]
            ):
                return (
                    ErrorClass.TRANSIENT_INFRA,
                    "Network connectivity issue - retry with backoff",
                )

        # Default: treat as transient for safety
        return (
            ErrorClass.TRANSIENT_INFRA,
            f"Unknown error (HTTP {status_code}) - retry cautiously",
        )

    def classify_builder_error(
        self, error_message: str, builder_messages: Optional[list] = None
    ) -> Tuple[ErrorClass, str]:
        """
        Classify Builder/LLM error to determine retry strategy.

        Args:
            error_message: Error message from builder
            builder_messages: Optional builder messages for context

        Returns:
            (error_class, remediation_suggestion)
        """
        error_lower = error_message.lower() if error_message else ""

        # Empty patch is deterministic if not a known no-op case
        if "empty_patch" in error_lower or "no changes" in error_lower:
            if builder_messages and any("no operations" in m for m in builder_messages):
                # Explicit no-op from structured edit is acceptable
                return (
                    ErrorClass.DETERMINISTIC_LOGIC,
                    "Builder produced no operations (structured edit no-op). This may be acceptable.",
                )
            return (
                ErrorClass.DETERMINISTIC_LOGIC,
                "Builder produced empty output. Check scope, deliverables, and Builder prompt.",
            )

        # JSON parsing errors are deterministic
        if "json" in error_lower and ("parse" in error_lower or "invalid" in error_lower):
            return (
                ErrorClass.DETERMINISTIC_LOGIC,
                "Builder output format error. May need JSON repair or format fix.",
            )

        # Token budget issues are transient (can escalate)
        if "max_tokens" in error_lower or "truncat" in error_lower:
            return (
                ErrorClass.TRANSIENT_LLM,
                "Token budget exceeded - escalate token cap and retry",
            )

        # LLM provider errors (rate limits, overload)
        if any(marker in error_lower for marker in ["rate limit", "overload", "capacity"]):
            return (ErrorClass.TRANSIENT_LLM, "LLM provider capacity issue - retry with backoff")

        # Connection/network errors
        if any(marker in error_lower for marker in ["connection", "timeout", "api failure"]):
            return (ErrorClass.TRANSIENT_INFRA, "LLM API connectivity issue - retry with backoff")

        # Default: treat as deterministic logic error (don't retry blindly)
        return (ErrorClass.DETERMINISTIC_LOGIC, f"Builder error: {error_message[:200]}")

    def _is_enum_violation(self, response_body: str) -> bool:
        """
        Detect if error is due to invalid enum value in database.

        Patterns:
        - "is not among the defined enum values"
        - "LookupError: 'READY' is not among..."
        - "Enum name: runstate" / "phasestate" / "tierstate"
        """
        if not response_body:
            return False

        response_lower = response_body.lower()

        # Check for explicit enum error messages
        if "not among the defined enum values" in response_lower:
            return True

        if "lookuper error" in response_lower and "enum" in response_lower:
            return True

        # Check for specific enum names from models.py
        if any(
            enum_name in response_lower for enum_name in ["runstate", "phasestate", "tierstate"]
        ):
            if any(marker in response_lower for marker in ["invalid", "not defined", "not among"]):
                return True

        return False

    def should_retry(self, error_class: ErrorClass) -> bool:
        """
        Determine if error should be retried.

        Args:
            error_class: Classified error type

        Returns:
            True if retry is appropriate, False for fail-fast
        """
        return error_class in (ErrorClass.TRANSIENT_INFRA, ErrorClass.TRANSIENT_LLM)

    def get_backoff_seconds(self, error_class: ErrorClass, attempt: int) -> int:
        """
        Calculate backoff duration for retry.

        Args:
            error_class: Classified error type
            attempt: Retry attempt number (0-indexed)

        Returns:
            Seconds to wait before retry
        """
        if error_class == ErrorClass.TRANSIENT_LLM:
            # LLM errors: longer backoff for rate limits
            return min(60 * (2**attempt), 300)  # 60s, 120s, 240s, 300s max

        if error_class == ErrorClass.TRANSIENT_INFRA:
            # Infrastructure errors: shorter backoff
            return min(5 * (attempt + 1), 30)  # 5s, 10s, 15s, ..., 30s max

        # Deterministic errors: no backoff (shouldn't retry anyway)
        return 0
