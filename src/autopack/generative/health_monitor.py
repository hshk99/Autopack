"""Health monitoring for generative AI providers."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional


logger = logging.getLogger(__name__)


@dataclass
class ProviderHealth:
    """Health status of a provider."""

    provider_name: str
    is_healthy: bool = True
    last_check: Optional[datetime] = None
    consecutive_failures: int = 0
    last_error: Optional[str] = None
    recovery_attempts: int = 0
    metadata: Dict[str, str] = field(default_factory=dict)


class HealthMonitor:
    """Monitor and track health of generative AI providers."""

    # Configuration constants
    FAILURE_THRESHOLD = 3  # Mark unhealthy after this many consecutive failures
    RECOVERY_WAIT_BASE = 5  # Initial wait in seconds for recovery
    RECOVERY_WAIT_MAX = 300  # Max wait in seconds for recovery
    HEALTH_CHECK_TIMEOUT = 10  # Timeout for individual health checks

    def __init__(self):
        """Initialize health monitor."""
        self.provider_health: Dict[str, ProviderHealth] = {}

    def initialize_provider(self, provider_name: str) -> None:
        """Initialize health tracking for a provider."""
        if provider_name not in self.provider_health:
            self.provider_health[provider_name] = ProviderHealth(provider_name=provider_name)

    def mark_success(self, provider_name: str) -> None:
        """Mark a provider operation as successful."""
        self.initialize_provider(provider_name)
        health = self.provider_health[provider_name]
        health.is_healthy = True
        health.consecutive_failures = 0
        health.last_check = datetime.now()
        health.last_error = None
        logger.debug(f"Provider {provider_name} marked healthy")

    def mark_failure(self, provider_name: str, error: str) -> None:
        """Mark a provider operation as failed."""
        self.initialize_provider(provider_name)
        health = self.provider_health[provider_name]
        health.last_check = datetime.now()
        health.last_error = error
        health.consecutive_failures += 1

        if health.consecutive_failures >= self.FAILURE_THRESHOLD:
            health.is_healthy = False
            logger.warning(
                f"Provider {provider_name} marked unhealthy after "
                f"{health.consecutive_failures} consecutive failures: {error}"
            )
        else:
            logger.debug(
                f"Provider {provider_name} failure #{health.consecutive_failures}: {error}"
            )

    def is_healthy(self, provider_name: str) -> bool:
        """Check if a provider is currently healthy."""
        self.initialize_provider(provider_name)
        return self.provider_health[provider_name].is_healthy

    def get_health_status(self, provider_name: str) -> ProviderHealth:
        """Get detailed health status for a provider."""
        self.initialize_provider(provider_name)
        return self.provider_health[provider_name]

    def get_recovery_wait_time(self, provider_name: str) -> float:
        """Get recommended wait time before attempting recovery."""
        health = self.get_health_status(provider_name)

        # Exponential backoff: 5s, 10s, 20s, 40s, ... up to 5 minutes
        wait_time = min(
            self.RECOVERY_WAIT_BASE * (2**health.recovery_attempts),
            self.RECOVERY_WAIT_MAX,
        )
        return wait_time

    async def wait_for_recovery(self, provider_name: str) -> None:
        """Wait for a provider to be ready for recovery attempt."""
        wait_time = self.get_recovery_wait_time(provider_name)
        logger.info(f"Waiting {wait_time}s before attempting {provider_name} recovery")
        await asyncio.sleep(wait_time)

    def reset_provider(self, provider_name: str) -> None:
        """Reset health status for a provider (e.g., after successful recovery)."""
        self.initialize_provider(provider_name)
        health = self.provider_health[provider_name]
        health.is_healthy = True
        health.consecutive_failures = 0
        health.recovery_attempts = 0
        health.last_error = None
        health.last_check = datetime.now()
        logger.info(f"Provider {provider_name} health reset")

    def increment_recovery_attempts(self, provider_name: str) -> None:
        """Increment recovery attempt counter."""
        health = self.get_health_status(provider_name)
        health.recovery_attempts += 1

    async def check_provider_health(self, provider_name: str, health_check_fn) -> bool:
        """Execute a health check for a provider.

        Args:
            provider_name: Name of the provider to check
            health_check_fn: Async function that returns True if healthy

        Returns:
            True if provider is healthy, False otherwise
        """
        try:
            result = await asyncio.wait_for(health_check_fn(), timeout=self.HEALTH_CHECK_TIMEOUT)
            if result:
                self.mark_success(provider_name)
                return True
            else:
                self.mark_failure(provider_name, "Health check returned False")
                return False
        except asyncio.TimeoutError:
            self.mark_failure(provider_name, "Health check timeout")
            return False
        except Exception as e:
            self.mark_failure(provider_name, str(e))
            return False

    def get_all_health_status(self) -> Dict[str, ProviderHealth]:
        """Get health status for all providers."""
        return dict(self.provider_health)

    def get_healthy_providers(self) -> list[str]:
        """Get list of healthy providers."""
        return [name for name, health in self.provider_health.items() if health.is_healthy]

    def get_unhealthy_providers(self) -> list[str]:
        """Get list of unhealthy providers."""
        return [name for name, health in self.provider_health.items() if not health.is_healthy]
