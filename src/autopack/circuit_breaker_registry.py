"""Circuit Breaker Registry for managing multiple circuit breakers.

Provides centralized management and monitoring of circuit breakers
across the application.
"""

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from .circuit_breaker import (CircuitBreaker, CircuitBreakerConfig,
                              CircuitBreakerMetrics, CircuitState)

if TYPE_CHECKING:
    from .circuit_breaker_persistence import CircuitBreakerPersistence

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreakerStatus:
    """Status information for a circuit breaker."""

    name: str
    state: CircuitState
    metrics: CircuitBreakerMetrics
    is_available: bool
    config: CircuitBreakerConfig


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers.

    Provides a centralized way to create, access, and monitor
    circuit breakers across the application.

    Example:
        registry = CircuitBreakerRegistry()

        # Register a circuit breaker
        registry.register(
            "api_service",
            CircuitBreakerConfig(failure_threshold=5)
        )

        # Get and use circuit breaker
        breaker = registry.get("api_service")
        result = breaker.call(lambda: api_call())

        # Monitor all circuit breakers
        statuses = registry.get_all_statuses()
    """

    _instance: Optional["CircuitBreakerRegistry"] = None
    _lock = threading.Lock()

    def __new__(cls, persistence: Optional["CircuitBreakerPersistence"] = None):
        """Implement singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, persistence: Optional["CircuitBreakerPersistence"] = None):
        """Initialize registry.

        Args:
            persistence: Optional persistence layer for state recovery across restarts
        """
        if not hasattr(self, "_initialized"):
            self._breakers: Dict[str, CircuitBreaker] = {}
            self._configs: Dict[str, CircuitBreakerConfig] = {}
            self._registry_lock = threading.RLock()
            self._persistence = persistence
            self._initialized = True
            logger.info("Circuit breaker registry initialized")
        elif persistence is not None:
            # Allow updating persistence on existing singleton
            self._persistence = persistence

    def register(
        self, name: str, config: Optional[CircuitBreakerConfig] = None, force: bool = False
    ) -> CircuitBreaker:
        """Register a new circuit breaker.

        Args:
            name: Unique identifier for the circuit breaker
            config: Configuration for the circuit breaker
            force: If True, replace existing circuit breaker with same name

        Returns:
            The registered circuit breaker

        Raises:
            ValueError: If circuit breaker with name already exists and force=False
        """
        with self._registry_lock:
            if name in self._breakers and not force:
                raise ValueError(
                    f"Circuit breaker '{name}' already registered. Use force=True to replace."
                )

            breaker = CircuitBreaker(name=name, config=config, persistence=self._persistence)

            # Try to restore state from persistence
            if self._persistence is not None:
                saved_state = self._persistence.load_state(name)
                if saved_state is not None:
                    breaker._restore_state(saved_state)
                    logger.info(f"Restored circuit breaker '{name}' from persistence")

            self._breakers[name] = breaker
            self._configs[name] = config or CircuitBreakerConfig()

            logger.info(f"Registered circuit breaker: {name}")
            return breaker

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get a circuit breaker by name.

        Args:
            name: Circuit breaker identifier

        Returns:
            Circuit breaker if found, None otherwise
        """
        with self._registry_lock:
            return self._breakers.get(name)

    def get_breaker(
        self, name: str, config: Optional[CircuitBreakerConfig] = None
    ) -> CircuitBreaker:
        """Get existing circuit breaker or create new one with state restoration.

        This is the preferred method for obtaining circuit breakers as it
        automatically restores state from persistence if available.

        Args:
            name: Circuit breaker identifier
            config: Configuration for new circuit breaker (if created)

        Returns:
            Existing or newly created circuit breaker with restored state
        """
        with self._registry_lock:
            breaker = self._breakers.get(name)
            if breaker is None:
                breaker = self.register(name, config)
            return breaker

    def get_or_create(
        self, name: str, config: Optional[CircuitBreakerConfig] = None
    ) -> CircuitBreaker:
        """Get existing circuit breaker or create new one.

        Args:
            name: Circuit breaker identifier
            config: Configuration for new circuit breaker (if created)

        Returns:
            Existing or newly created circuit breaker

        Note:
            This method is an alias for get_breaker() for backwards compatibility.
        """
        return self.get_breaker(name, config)

    def unregister(self, name: str) -> bool:
        """Unregister a circuit breaker.

        Args:
            name: Circuit breaker identifier

        Returns:
            True if circuit breaker was removed, False if not found
        """
        with self._registry_lock:
            if name in self._breakers:
                del self._breakers[name]
                del self._configs[name]
                logger.info(f"Unregistered circuit breaker: {name}")
                return True
            return False

    def reset(self, name: str) -> bool:
        """Reset a circuit breaker to CLOSED state.

        Args:
            name: Circuit breaker identifier

        Returns:
            True if circuit breaker was reset, False if not found
        """
        with self._registry_lock:
            breaker = self._breakers.get(name)
            if breaker:
                breaker.reset()
                logger.info(f"Reset circuit breaker: {name}")
                return True
            return False

    def reset_all(self):
        """Reset all circuit breakers to CLOSED state."""
        with self._registry_lock:
            for breaker in self._breakers.values():
                breaker.reset()
            logger.info("Reset all circuit breakers")

    def get_status(self, name: str) -> Optional[CircuitBreakerStatus]:
        """Get status of a circuit breaker.

        Args:
            name: Circuit breaker identifier

        Returns:
            Status information if found, None otherwise
        """
        with self._registry_lock:
            breaker = self._breakers.get(name)
            if breaker is None:
                return None

            return CircuitBreakerStatus(
                name=name,
                state=breaker.get_state(),
                metrics=breaker.get_metrics(),
                is_available=breaker.is_available(),
                config=self._configs[name],
            )

    def get_all_statuses(self) -> List[CircuitBreakerStatus]:
        """Get status of all circuit breakers.

        Returns:
            List of status information for all registered circuit breakers
        """
        with self._registry_lock:
            statuses = []
            for name in self._breakers.keys():
                status = self.get_status(name)
                if status:
                    statuses.append(status)
            return statuses

    def get_all_names(self) -> List[str]:
        """Get names of all registered circuit breakers.

        Returns:
            List of circuit breaker names
        """
        with self._registry_lock:
            return list(self._breakers.keys())

    def count(self) -> int:
        """Get count of registered circuit breakers.

        Returns:
            Number of registered circuit breakers
        """
        with self._registry_lock:
            return len(self._breakers)

    def clear(self):
        """Remove all circuit breakers from registry."""
        with self._registry_lock:
            self._breakers.clear()
            self._configs.clear()
            logger.info("Cleared all circuit breakers from registry")

    def persist_all(self, path: Optional[Path] = None) -> bool:
        """Persist all circuit breaker states to disk.

        Args:
            path: Path to persistence file. Defaults to ~/.autopack/circuit_breaker_state.json

        Returns:
            True if persistence succeeded, False otherwise
        """
        persistence_path = path or Path.home() / ".autopack" / "circuit_breaker_state.json"

        with self._registry_lock:
            try:
                states = {name: cb.to_dict() for name, cb in self._breakers.items()}

                persistence_path.parent.mkdir(parents=True, exist_ok=True)
                with open(persistence_path, "w", encoding="utf-8") as f:
                    json.dump(states, f, indent=2)

                logger.info(f"Persisted {len(states)} circuit breakers to {persistence_path}")
                return True
            except Exception as e:
                logger.error(f"Failed to persist circuit breakers: {e}")
                return False

    def restore_all(self, path: Optional[Path] = None) -> int:
        """Restore circuit breaker states from disk.

        Args:
            path: Path to persistence file. Defaults to ~/.autopack/circuit_breaker_state.json

        Returns:
            Number of circuit breakers restored
        """
        persistence_path = path or Path.home() / ".autopack" / "circuit_breaker_state.json"

        if not persistence_path.exists():
            logger.debug(f"No persistence file found at {persistence_path}")
            return 0

        with self._registry_lock:
            try:
                with open(persistence_path, "r", encoding="utf-8") as f:
                    states = json.load(f)

                restored_count = 0
                for name, state_data in states.items():
                    try:
                        cb = CircuitBreaker.from_dict(state_data)
                        self._breakers[name] = cb
                        self._configs[name] = cb.config
                        restored_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to restore circuit breaker '{name}': {e}")

                logger.info(f"Restored {restored_count} circuit breakers from {persistence_path}")
                return restored_count
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in persistence file: {e}")
                return 0
            except Exception as e:
                logger.error(f"Failed to restore circuit breakers: {e}")
                return 0


# Global registry instance
_global_registry: Optional[CircuitBreakerRegistry] = None
_global_registry_lock = threading.Lock()


def get_global_registry() -> CircuitBreakerRegistry:
    """Get the global circuit breaker registry instance.

    Thread-safe singleton access.

    Returns:
        Global registry singleton
    """
    global _global_registry
    if _global_registry is None:
        with _global_registry_lock:
            # Double-check locking pattern
            if _global_registry is None:
                _global_registry = CircuitBreakerRegistry()
    return _global_registry
