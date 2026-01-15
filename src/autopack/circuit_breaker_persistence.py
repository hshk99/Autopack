"""Redis-based Circuit Breaker Persistence.

Provides persistence layer for circuit breaker state using Redis,
enabling state recovery across process restarts to prevent retry storms.
"""

import json
import logging
from typing import Optional

import redis

logger = logging.getLogger(__name__)

# Default TTL for circuit breaker state (24 hours)
DEFAULT_STATE_TTL = 86400


class CircuitBreakerPersistence:
    """Redis-based persistence for circuit breaker state.

    Saves and restores circuit breaker state to Redis, allowing
    circuit breakers to maintain their state across process restarts.
    This prevents retry storms to failing external services after
    application restarts.

    Example:
        persistence = CircuitBreakerPersistence("redis://localhost:6379/1")

        # Save state
        persistence.save_state("api_service", {"state": "open", "failure_count": 5})

        # Load state
        state = persistence.load_state("api_service")

        # Clear state
        persistence.clear_state("api_service")
    """

    KEY_PREFIX = "circuit_breaker:"

    def __init__(self, redis_url: str = "redis://localhost:6379/1", ttl: int = DEFAULT_STATE_TTL):
        """Initialize persistence with Redis connection.

        Args:
            redis_url: Redis connection URL
            ttl: Time-to-live for state entries in seconds (default 24 hours)
        """
        self.redis_url = redis_url
        self.ttl = ttl
        self._client: Optional[redis.Redis] = None
        logger.info(f"Circuit breaker persistence initialized with Redis URL: {redis_url}")

    @property
    def client(self) -> redis.Redis:
        """Get or create Redis client (lazy initialization)."""
        if self._client is None:
            self._client = redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    def _get_key(self, service_name: str) -> str:
        """Get Redis key for a service.

        Args:
            service_name: Name of the circuit breaker/service

        Returns:
            Full Redis key with prefix
        """
        return f"{self.KEY_PREFIX}{service_name}"

    def save_state(self, service_name: str, state: dict) -> bool:
        """Save circuit breaker state to Redis.

        Args:
            service_name: Name of the circuit breaker/service
            state: State dictionary to persist

        Returns:
            True if save succeeded, False otherwise
        """
        try:
            key = self._get_key(service_name)
            serialized = json.dumps(state)
            self.client.setex(key, self.ttl, serialized)
            logger.debug(f"Saved circuit breaker state for '{service_name}'")
            return True
        except redis.RedisError as e:
            logger.error(f"Failed to save circuit breaker state for '{service_name}': {e}")
            return False
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize state for '{service_name}': {e}")
            return False

    def load_state(self, service_name: str) -> Optional[dict]:
        """Load circuit breaker state from Redis.

        Args:
            service_name: Name of the circuit breaker/service

        Returns:
            State dictionary if found, None otherwise
        """
        try:
            key = self._get_key(service_name)
            data = self.client.get(key)
            if data is None:
                logger.debug(f"No persisted state found for '{service_name}'")
                return None
            state = json.loads(data)
            logger.debug(f"Loaded circuit breaker state for '{service_name}'")
            return state
        except redis.RedisError as e:
            logger.error(f"Failed to load circuit breaker state for '{service_name}': {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to deserialize state for '{service_name}': {e}")
            return None

    def clear_state(self, service_name: str) -> bool:
        """Clear circuit breaker state from Redis.

        Args:
            service_name: Name of the circuit breaker/service

        Returns:
            True if clear succeeded, False otherwise
        """
        try:
            key = self._get_key(service_name)
            self.client.delete(key)
            logger.debug(f"Cleared circuit breaker state for '{service_name}'")
            return True
        except redis.RedisError as e:
            logger.error(f"Failed to clear circuit breaker state for '{service_name}': {e}")
            return False

    def close(self):
        """Close the Redis connection."""
        if self._client is not None:
            self._client.close()
            self._client = None
            logger.debug("Redis connection closed")
