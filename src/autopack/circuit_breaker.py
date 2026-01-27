"""Circuit Breaker Pattern Implementation.

Provides fault tolerance and resilience for external service calls.
Implements the circuit breaker pattern with configurable thresholds,
timeouts, and state transitions.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

if TYPE_CHECKING:
    from .circuit_breaker_file_persistence import FileBasedCircuitBreakerPersistence
    from .circuit_breaker_persistence import CircuitBreakerPersistence
else:
    from .circuit_breaker_file_persistence import FileBasedCircuitBreakerPersistence

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5
    success_threshold: int = 2
    timeout: float = 60.0  # seconds
    half_open_timeout: float = 30.0  # seconds
    expected_exception: type = Exception


@dataclass
class CircuitBreakerMetrics:
    """Metrics for circuit breaker monitoring."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_transitions: Dict[str, int] = field(default_factory=dict)
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None

    def record_success(self):
        """Record a successful call."""
        self.total_calls += 1
        self.successful_calls += 1
        self.last_success_time = datetime.now()

    def record_failure(self):
        """Record a failed call."""
        self.total_calls += 1
        self.failed_calls += 1
        self.last_failure_time = datetime.now()

    def record_rejection(self):
        """Record a rejected call."""
        self.total_calls += 1
        self.rejected_calls += 1

    def record_state_transition(self, from_state: CircuitState, to_state: CircuitState):
        """Record a state transition."""
        key = f"{from_state.value}_to_{to_state.value}"
        self.state_transitions[key] = self.state_transitions.get(key, 0) + 1


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and rejects calls."""

    pass


class CircuitBreaker:
    """Circuit breaker for fault tolerance.

    Implements the circuit breaker pattern to prevent cascading failures
    and provide graceful degradation when external services fail.

    States:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Too many failures, reject all calls
    - HALF_OPEN: Testing if service recovered, allow limited calls

    Example:
        breaker = CircuitBreaker(
            name="api_service",
            config=CircuitBreakerConfig(failure_threshold=3, timeout=30.0)
        )

        try:
            result = breaker.call(lambda: external_api_call())
        except CircuitBreakerOpenError:
            # Handle circuit open
            result = fallback_value
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        persistence: Optional["CircuitBreakerPersistence"] = None,
        persistence_path: str = ".autopack/circuit_breaker_state.json",
    ):
        """Initialize circuit breaker.

        Args:
            name: Identifier for this circuit breaker
            config: Configuration settings
            persistence: Optional custom persistence layer for state recovery.
                       If None, uses file-based persistence with default path.
            persistence_path: Path for file-based persistence (default: .autopack/circuit_breaker_state.json)
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.last_state_change: float = time.time()
        self.metrics = CircuitBreakerMetrics()
        self._lock = threading.RLock()

        # Persistence is now mandatory - use file-based by default
        if persistence is None:
            self._persistence = FileBasedCircuitBreakerPersistence(persistence_path)
            logger.info(
                f"Circuit breaker '{name}' initialized with file-based persistence: "
                f"{persistence_path}"
            )
        else:
            self._persistence = persistence
            logger.info(f"Circuit breaker '{name}' initialized with custom persistence layer")

        # Try to restore previous state
        self._try_restore_state()

        logger.info(
            f"Circuit breaker '{name}' fully initialized: "
            f"failure_threshold={self.config.failure_threshold}, "
            f"timeout={self.config.timeout}s, "
            f"state={self.state.value}"
        )

    def _try_restore_state(self):
        """Try to restore circuit breaker state from persistence.

        Logs but continues on failure to prevent startup issues.
        """
        try:
            saved_state = self._persistence.load_state(self.name)
            if saved_state is not None:
                self._restore_state(saved_state)
        except Exception as e:
            logger.warning(
                f"Failed to restore circuit breaker '{self.name}' state: {e}. "
                f"Starting with default CLOSED state."
            )

    def call(self, func: Callable[[], Any], *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result of func execution

        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: Any exception raised by func
        """
        with self._lock:
            self._update_state()

            if self.state == CircuitState.OPEN:
                self.metrics.record_rejection()
                logger.warning(f"Circuit breaker '{self.name}' is OPEN, rejecting call")
                raise CircuitBreakerOpenError(f"Circuit breaker '{self.name}' is open")

            # Allow call in CLOSED or HALF_OPEN state
            try:
                result = func(*args, **kwargs)
                self._on_success()
                return result
            except self.config.expected_exception:
                self._on_failure()
                raise

    def _update_state(self):
        """Update circuit breaker state based on current conditions."""
        current_time = time.time()

        if self.state == CircuitState.OPEN:
            # Check if timeout has elapsed to move to HALF_OPEN
            if current_time - self.last_state_change >= self.config.timeout:
                self._transition_to(CircuitState.HALF_OPEN)
                logger.info(
                    f"Circuit breaker '{self.name}' transitioning to HALF_OPEN "
                    f"after {self.config.timeout}s timeout"
                )

        elif self.state == CircuitState.HALF_OPEN:
            # Check if half-open timeout has elapsed
            if current_time - self.last_state_change >= self.config.half_open_timeout:
                # Reset to CLOSED if we've been stable
                if self.failure_count == 0:
                    self._transition_to(CircuitState.CLOSED)
                    logger.info(f"Circuit breaker '{self.name}' recovered, transitioning to CLOSED")

    def _on_success(self):
        """Handle successful call."""
        self.metrics.record_success()

        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            logger.debug(
                f"Circuit breaker '{self.name}' success in HALF_OPEN: "
                f"{self.success_count}/{self.config.success_threshold}"
            )

            if self.success_count >= self.config.success_threshold:
                self._transition_to(CircuitState.CLOSED)
                logger.info(
                    f"Circuit breaker '{self.name}' recovered after "
                    f"{self.success_count} successful calls"
                )
        else:
            # Reset failure count on success in CLOSED state
            self.failure_count = 0

    def _on_failure(self):
        """Handle failed call."""
        self.metrics.record_failure()
        self.failure_count += 1
        self.last_failure_time = time.time()

        logger.warning(
            f"Circuit breaker '{self.name}' failure: "
            f"{self.failure_count}/{self.config.failure_threshold}"
        )

        if self.state == CircuitState.HALF_OPEN:
            # Any failure in HALF_OPEN immediately opens circuit
            self._transition_to(CircuitState.OPEN)
            logger.error(
                f"Circuit breaker '{self.name}' failed in HALF_OPEN, transitioning to OPEN"
            )
        elif self.failure_count >= self.config.failure_threshold:
            # Too many failures in CLOSED state
            self._transition_to(CircuitState.OPEN)
            logger.error(f"Circuit breaker '{self.name}' threshold exceeded, transitioning to OPEN")

    def _transition_to(self, new_state: CircuitState):
        """Transition to a new state."""
        old_state = self.state
        self.state = new_state
        self.last_state_change = time.time()
        self.failure_count = 0
        self.success_count = 0
        self.metrics.record_state_transition(old_state, new_state)

        logger.info(
            f"Circuit breaker '{self.name}' state transition: "
            f"{old_state.value} -> {new_state.value}"
        )

        # Persist state immediately on status change
        if self._persistence is not None:
            self._persistence.save_state(self.name, self.to_dict())

    def reset(self):
        """Manually reset circuit breaker to CLOSED state."""
        with self._lock:
            logger.info(f"Manually resetting circuit breaker '{self.name}'")
            self._transition_to(CircuitState.CLOSED)

    def _restore_state(self, saved_state: dict):
        """Restore circuit breaker state from persisted data.

        Args:
            saved_state: State dictionary from persistence layer
        """
        with self._lock:
            self.state = CircuitState(saved_state.get("state", "closed"))
            self.failure_count = saved_state.get("failure_count", 0)
            self.success_count = saved_state.get("success_count", 0)
            self.last_failure_time = saved_state.get("last_failure_time")
            self.last_state_change = saved_state.get("last_state_change", time.time())

            # Restore metrics if available
            metrics_data = saved_state.get("metrics", {})
            self.metrics.total_calls = metrics_data.get("total_calls", 0)
            self.metrics.successful_calls = metrics_data.get("successful_calls", 0)
            self.metrics.failed_calls = metrics_data.get("failed_calls", 0)
            self.metrics.rejected_calls = metrics_data.get("rejected_calls", 0)
            self.metrics.state_transitions = metrics_data.get("state_transitions", {}).copy()

            logger.info(
                f"Restored circuit breaker '{self.name}' state: {self.state.value}, "
                f"failures={self.failure_count}"
            )

    def get_state(self) -> CircuitState:
        """Get current circuit breaker state."""
        with self._lock:
            return self.state

    def get_metrics(self) -> CircuitBreakerMetrics:
        """Get circuit breaker metrics."""
        with self._lock:
            return self.metrics

    def is_available(self) -> bool:
        """Check if circuit breaker will allow calls."""
        with self._lock:
            self._update_state()
            return self.state != CircuitState.OPEN

    def to_dict(self) -> dict:
        """Serialize circuit breaker state to dictionary.

        Returns:
            Dictionary representation of circuit breaker state for persistence.
        """
        with self._lock:
            return {
                "name": self.name,
                "state": self.state.value,
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "last_failure_time": self.last_failure_time,
                "last_state_change": self.last_state_change,
                "config": {
                    "failure_threshold": self.config.failure_threshold,
                    "success_threshold": self.config.success_threshold,
                    "timeout": self.config.timeout,
                    "half_open_timeout": self.config.half_open_timeout,
                },
                "metrics": {
                    "total_calls": self.metrics.total_calls,
                    "successful_calls": self.metrics.successful_calls,
                    "failed_calls": self.metrics.failed_calls,
                    "rejected_calls": self.metrics.rejected_calls,
                    "state_transitions": self.metrics.state_transitions.copy(),
                },
            }

    @classmethod
    def from_dict(cls, data: dict) -> "CircuitBreaker":
        """Restore circuit breaker from dictionary.

        Args:
            data: Dictionary from to_dict()

        Returns:
            Restored CircuitBreaker instance
        """
        config_data = data.get("config", {})
        config = CircuitBreakerConfig(
            failure_threshold=config_data.get("failure_threshold", 5),
            success_threshold=config_data.get("success_threshold", 2),
            timeout=config_data.get("timeout", 60.0),
            half_open_timeout=config_data.get("half_open_timeout", 30.0),
        )

        cb = cls(name=data["name"], config=config)

        # Restore state
        cb.state = CircuitState(data.get("state", "closed"))
        cb.failure_count = data.get("failure_count", 0)
        cb.success_count = data.get("success_count", 0)
        cb.last_failure_time = data.get("last_failure_time")
        cb.last_state_change = data.get("last_state_change", time.time())

        # Restore metrics
        metrics_data = data.get("metrics", {})
        cb.metrics.total_calls = metrics_data.get("total_calls", 0)
        cb.metrics.successful_calls = metrics_data.get("successful_calls", 0)
        cb.metrics.failed_calls = metrics_data.get("failed_calls", 0)
        cb.metrics.rejected_calls = metrics_data.get("rejected_calls", 0)
        cb.metrics.state_transitions = metrics_data.get("state_transitions", {}).copy()

        logger.debug(f"Restored circuit breaker '{cb.name}' in state {cb.state.value}")
        return cb
