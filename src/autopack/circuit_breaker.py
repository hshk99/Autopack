"""Circuit Breaker Pattern Implementation.

Provides fault tolerance and resilience for external service calls.
Implements the circuit breaker pattern with configurable thresholds,
timeouts, and state transitions.
"""

import time
import threading
from enum import Enum
from typing import Callable, Any, Optional, Dict
from dataclasses import dataclass, field
from datetime import datetime
import logging

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

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        """Initialize circuit breaker.

        Args:
            name: Identifier for this circuit breaker
            config: Configuration settings
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

        logger.info(
            f"Circuit breaker '{name}' initialized: "
            f"failure_threshold={self.config.failure_threshold}, "
            f"timeout={self.config.timeout}s"
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

    def reset(self):
        """Manually reset circuit breaker to CLOSED state."""
        with self._lock:
            logger.info(f"Manually resetting circuit breaker '{self.name}'")
            self._transition_to(CircuitState.CLOSED)

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
