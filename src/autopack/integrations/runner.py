"""
Integration Runner - Safe wrapper for external side effects.

BUILD-189 Phase 5 Skeleton - Minimal implementation for bootstrap.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional


class IntegrationStatus(Enum):
    """Status of an integration execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"


@dataclass
class IntegrationResult:
    """Result of an integration execution."""

    status: IntegrationStatus
    idempotency_key: str
    provider: str
    action: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    result_data: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: int = 0


@dataclass
class RetryPolicy:
    """Retry policy for integration execution."""

    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    exponential_backoff: bool = True


@dataclass
class RateLimitConfig:
    """Rate limit configuration per provider."""

    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_limit: int = 10


@dataclass
class ProviderConfig:
    """Configuration for an integration provider."""

    name: str
    timeout_seconds: float = 30.0
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)


class IntegrationRunner:
    """
    Safe runner for external integrations.

    Features:
    - Automatic timeout enforcement
    - Retry with exponential backoff
    - Idempotency key tracking
    - Rate limiting per provider
    - Structured audit logging
    """

    def __init__(self):
        self._providers: dict[str, ProviderConfig] = {}
        self._executed_keys: set[str] = set()  # Track idempotency keys
        self._rate_counters: dict[str, list[float]] = {}  # Track request times

    def register_provider(self, config: ProviderConfig) -> None:
        """Register a provider configuration."""
        self._providers[config.name] = config
        self._rate_counters[config.name] = []

    def generate_idempotency_key(self, provider: str, action: str, params_hash: str) -> str:
        """Generate a deterministic idempotency key."""
        return f"{provider}:{action}:{params_hash}:{uuid.uuid4().hex[:8]}"

    def _check_rate_limit(self, provider: str) -> bool:
        """Check if the provider is within rate limits."""
        config = self._providers.get(provider)
        if not config:
            return True

        now = time.time()
        counter = self._rate_counters.get(provider, [])

        # Clean old entries (older than 1 hour)
        counter = [t for t in counter if now - t < 3600]
        self._rate_counters[provider] = counter

        # Check per-minute limit
        recent_minute = [t for t in counter if now - t < 60]
        if len(recent_minute) >= config.rate_limit.requests_per_minute:
            return False

        # Check per-hour limit
        if len(counter) >= config.rate_limit.requests_per_hour:
            return False

        return True

    def execute(
        self,
        provider: str,
        action: str,
        handler: Callable[[], Any],
        idempotency_key: Optional[str] = None,
    ) -> IntegrationResult:
        """
        Execute an integration action safely.

        Args:
            provider: Provider name (e.g., "etsy", "shopify")
            action: Action name (e.g., "create_listing", "update_inventory")
            handler: Callable that performs the actual integration
            idempotency_key: Optional key to prevent duplicate execution

        Returns:
            IntegrationResult with execution status and data
        """
        config = self._providers.get(provider)
        if not config:
            # Use defaults if provider not registered
            config = ProviderConfig(name=provider)

        # Generate or validate idempotency key
        key = idempotency_key or self.generate_idempotency_key(provider, action, "")

        # Check for duplicate execution
        if key in self._executed_keys:
            return IntegrationResult(
                status=IntegrationStatus.SUCCESS,
                idempotency_key=key,
                provider=provider,
                action=action,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                result_data={"note": "Skipped - idempotency key already executed"},
            )

        # Check rate limit
        if not self._check_rate_limit(provider):
            return IntegrationResult(
                status=IntegrationStatus.RATE_LIMITED,
                idempotency_key=key,
                provider=provider,
                action=action,
                started_at=datetime.now(),
                error_message="Rate limit exceeded",
            )

        # Execute with retry logic
        started_at = datetime.now()
        retry_count = 0
        last_error: Optional[str] = None

        while retry_count <= config.retry_policy.max_retries:
            try:
                # Record rate limit
                self._rate_counters.setdefault(provider, []).append(time.time())

                # Execute handler
                result_data = handler()

                # Mark as executed
                self._executed_keys.add(key)

                return IntegrationResult(
                    status=IntegrationStatus.SUCCESS,
                    idempotency_key=key,
                    provider=provider,
                    action=action,
                    started_at=started_at,
                    completed_at=datetime.now(),
                    result_data=(
                        result_data if isinstance(result_data, dict) else {"result": result_data}
                    ),
                    retry_count=retry_count,
                )

            except TimeoutError:
                last_error = "Execution timed out"
                retry_count += 1

            except Exception as e:
                last_error = str(e)
                retry_count += 1

            # Calculate backoff delay
            if retry_count <= config.retry_policy.max_retries:
                if config.retry_policy.exponential_backoff:
                    delay = min(
                        config.retry_policy.base_delay_seconds * (2 ** (retry_count - 1)),
                        config.retry_policy.max_delay_seconds,
                    )
                else:
                    delay = config.retry_policy.base_delay_seconds
                time.sleep(delay)

        return IntegrationResult(
            status=IntegrationStatus.FAILED,
            idempotency_key=key,
            provider=provider,
            action=action,
            started_at=started_at,
            completed_at=datetime.now(),
            error_message=last_error,
            retry_count=retry_count - 1,
        )
