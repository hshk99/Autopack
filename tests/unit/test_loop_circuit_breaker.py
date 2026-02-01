"""Unit tests for circuit breaker functionality in autonomous loop.

IMP-LOOP-006: Tests for iteration counter and circuit breaker protection
to prevent runaway execution and resource exhaustion.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from autopack.executor.autonomous_loop import (CircuitBreaker,
                                               CircuitBreakerOpenError,
                                               CircuitBreakerState)


class TestCircuitBreakerState:
    """Tests for CircuitBreakerState enum."""

    def test_state_values(self):
        """Test that state enum has expected values."""
        assert CircuitBreakerState.CLOSED.value == "closed"
        assert CircuitBreakerState.OPEN.value == "open"
        assert CircuitBreakerState.HALF_OPEN.value == "half_open"


class TestCircuitBreakerOpenError:
    """Tests for CircuitBreakerOpenError exception."""

    def test_exception_attributes(self):
        """Test that exception carries failure and reset info."""
        exc = CircuitBreakerOpenError(
            "Circuit is open",
            consecutive_failures=5,
            reset_time=120.0,
        )
        assert exc.consecutive_failures == 5
        assert exc.reset_time == 120.0
        assert "Circuit is open" in str(exc)


class TestCircuitBreakerInitialization:
    """Tests for CircuitBreaker initialization."""

    def test_default_initialization(self):
        """Test circuit breaker initializes with defaults."""
        cb = CircuitBreaker()
        assert cb.failure_threshold == 5
        assert cb.reset_timeout_seconds == 300
        assert cb.half_open_max_calls == 1
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.consecutive_failures == 0
        assert cb.total_trips == 0

    def test_custom_initialization(self):
        """Test circuit breaker initializes with custom values."""
        cb = CircuitBreaker(
            failure_threshold=3,
            reset_timeout_seconds=60,
            half_open_max_calls=2,
        )
        assert cb.failure_threshold == 3
        assert cb.reset_timeout_seconds == 60
        assert cb.half_open_max_calls == 2

    def test_initial_state_is_closed(self):
        """Test that initial state is CLOSED."""
        cb = CircuitBreaker()
        assert cb.is_closed
        assert not cb.is_open
        assert not cb.is_half_open


class TestCircuitBreakerClosedState:
    """Tests for circuit breaker in CLOSED state."""

    def test_success_in_closed_state_resets_failures(self):
        """Test that success resets consecutive failures in closed state."""
        cb = CircuitBreaker(failure_threshold=5)
        # Simulate some failures
        cb.record_failure()
        cb.record_failure()
        assert cb.consecutive_failures == 2
        # Record success
        cb.record_success()
        assert cb.consecutive_failures == 0
        assert cb.is_closed

    def test_failures_below_threshold_stay_closed(self):
        """Test that failures below threshold keep circuit closed."""
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        assert cb.consecutive_failures == 4
        assert cb.is_closed

    def test_check_state_passes_when_closed(self):
        """Test that check_state passes when circuit is closed."""
        cb = CircuitBreaker()
        # Should not raise
        cb.check_state()


class TestCircuitBreakerTripping:
    """Tests for circuit breaker tripping to OPEN state."""

    def test_failures_at_threshold_trips_circuit(self):
        """Test that reaching failure threshold trips circuit."""
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_closed
        cb.record_failure()  # Third failure trips circuit
        assert cb.is_open
        assert cb.total_trips == 1

    def test_failures_above_threshold_stay_open(self):
        """Test that additional failures in open state don't re-trip."""
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(5):
            cb.record_failure()
        assert cb.is_open
        assert cb.total_trips == 1  # Only tripped once
        assert cb.consecutive_failures == 5

    def test_check_state_raises_when_open(self):
        """Test that check_state raises CircuitBreakerOpenError when open."""
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open

        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            cb.check_state()
        assert exc_info.value.consecutive_failures == 2


class TestCircuitBreakerTimeout:
    """Tests for circuit breaker timeout and HALF_OPEN transition."""

    def test_timeout_transitions_to_half_open(self):
        """Test that timeout transitions from OPEN to HALF_OPEN."""
        cb = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=1)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open

        # Wait for timeout
        time.sleep(1.1)

        # Accessing state property triggers transition
        assert cb.state == CircuitBreakerState.HALF_OPEN
        assert cb.is_half_open

    def test_no_transition_before_timeout(self):
        """Test that circuit stays OPEN before timeout elapses."""
        cb = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=10)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open

        # State should still be OPEN
        assert cb.state == CircuitBreakerState.OPEN


class TestCircuitBreakerHalfOpenState:
    """Tests for circuit breaker in HALF_OPEN state."""

    def test_success_in_half_open_closes_circuit(self):
        """Test that success in HALF_OPEN closes circuit."""
        cb = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=0, half_open_max_calls=1)
        cb.record_failure()
        cb.record_failure()
        # With reset_timeout_seconds=0, state immediately transitions to HALF_OPEN
        # when the state property is accessed
        assert cb.is_half_open

        # Record success
        cb.record_success()
        assert cb.is_closed
        assert cb.consecutive_failures == 0

    def test_multiple_successes_needed_in_half_open(self):
        """Test that multiple successes can be required in HALF_OPEN."""
        cb = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=0, half_open_max_calls=3)
        cb.record_failure()
        cb.record_failure()
        _ = cb.state  # Trigger transition

        # First two successes keep it half-open
        cb.record_success()
        assert cb.is_half_open
        cb.record_success()
        assert cb.is_half_open

        # Third success closes it
        cb.record_success()
        assert cb.is_closed

    def test_failure_in_half_open_reopens_circuit(self):
        """Test that failure in HALF_OPEN immediately reopens circuit."""
        cb = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=10, half_open_max_calls=1)
        cb.record_failure()
        cb.record_failure()
        assert cb.total_trips == 1

        # Manually force transition to half-open for testing
        cb._state = CircuitBreakerState.HALF_OPEN
        assert cb.is_half_open

        # Failure should reopen
        cb.record_failure()
        assert cb.is_open
        assert cb.total_trips == 2


class TestCircuitBreakerReset:
    """Tests for manual circuit breaker reset."""

    def test_manual_reset_closes_circuit(self):
        """Test that manual reset closes circuit."""
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open

        cb.reset()
        assert cb.is_closed
        assert cb.consecutive_failures == 0

    def test_manual_reset_from_half_open(self):
        """Test that manual reset works from HALF_OPEN state."""
        cb = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=0)
        cb.record_failure()
        cb.record_failure()
        _ = cb.state  # Transition to half-open

        cb.reset()
        assert cb.is_closed


class TestCircuitBreakerStats:
    """Tests for circuit breaker statistics."""

    def test_get_stats_returns_expected_keys(self):
        """Test that get_stats returns all expected keys."""
        cb = CircuitBreaker()
        stats = cb.get_stats()

        expected_keys = {
            "state",
            "consecutive_failures",
            "total_trips",
            "failure_threshold",
            "reset_timeout_seconds",
            "time_in_current_state_seconds",
            "half_open_calls",
        }
        assert set(stats.keys()) == expected_keys

    def test_stats_reflect_current_state(self):
        """Test that stats reflect the current circuit state."""
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        stats = cb.get_stats()

        assert stats["state"] == "closed"
        assert stats["consecutive_failures"] == 1
        assert stats["total_trips"] == 0

    def test_stats_after_trip(self):
        """Test stats after circuit trips."""
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        stats = cb.get_stats()

        assert stats["state"] == "open"
        assert stats["consecutive_failures"] == 2
        assert stats["total_trips"] == 1


class TestAutonomousLoopCircuitBreakerIntegration:
    """Integration tests for circuit breaker with AutonomousLoop."""

    @patch("autopack.executor.autonomous_loop.settings")
    def test_circuit_breaker_disabled_by_config(self, mock_settings):
        """Test that circuit breaker can be disabled via config."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_settings.circuit_breaker_enabled = False
        mock_settings.context_ceiling_tokens = 50000

        mock_executor = MagicMock()
        loop = AutonomousLoop(mock_executor)

        assert loop._circuit_breaker is None

    @patch("autopack.executor.autonomous_loop.settings")
    def test_circuit_breaker_enabled_by_config(self, mock_settings):
        """Test that circuit breaker is enabled via config."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_settings.circuit_breaker_enabled = True
        mock_settings.circuit_breaker_failure_threshold = 3
        mock_settings.circuit_breaker_reset_timeout_seconds = 120
        mock_settings.circuit_breaker_half_open_max_calls = 2
        mock_settings.context_ceiling_tokens = 50000

        mock_executor = MagicMock()
        loop = AutonomousLoop(mock_executor)

        assert loop._circuit_breaker is not None
        assert loop._circuit_breaker.failure_threshold == 3
        assert loop._circuit_breaker.reset_timeout_seconds == 120
        assert loop._circuit_breaker.half_open_max_calls == 2

    @patch("autopack.executor.autonomous_loop.settings")
    def test_get_loop_stats_includes_circuit_breaker(self, mock_settings):
        """Test that get_loop_stats includes circuit breaker info."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_settings.circuit_breaker_enabled = True
        mock_settings.circuit_breaker_failure_threshold = 5
        mock_settings.circuit_breaker_reset_timeout_seconds = 300
        mock_settings.circuit_breaker_half_open_max_calls = 1
        mock_settings.context_ceiling_tokens = 50000

        mock_executor = MagicMock()
        loop = AutonomousLoop(mock_executor)

        stats = loop.get_loop_stats()
        assert "circuit_breaker" in stats
        assert stats["circuit_breaker"]["state"] == "closed"

    @patch("autopack.executor.autonomous_loop.settings")
    def test_reset_circuit_breaker_method(self, mock_settings):
        """Test that reset_circuit_breaker works."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_settings.circuit_breaker_enabled = True
        mock_settings.circuit_breaker_failure_threshold = 2
        mock_settings.circuit_breaker_reset_timeout_seconds = 300
        mock_settings.circuit_breaker_half_open_max_calls = 1
        mock_settings.context_ceiling_tokens = 50000

        mock_executor = MagicMock()
        loop = AutonomousLoop(mock_executor)

        # Trip the circuit
        loop._circuit_breaker.record_failure()
        loop._circuit_breaker.record_failure()
        assert loop._circuit_breaker.is_open

        # Reset via loop method
        result = loop.reset_circuit_breaker()
        assert result is True
        assert loop._circuit_breaker.is_closed

    @patch("autopack.executor.autonomous_loop.settings")
    def test_reset_circuit_breaker_returns_false_when_disabled(self, mock_settings):
        """Test that reset_circuit_breaker returns False when disabled."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_settings.circuit_breaker_enabled = False
        mock_settings.context_ceiling_tokens = 50000

        mock_executor = MagicMock()
        loop = AutonomousLoop(mock_executor)

        result = loop.reset_circuit_breaker()
        assert result is False


class TestConfigCircuitBreakerSettings:
    """Tests for circuit breaker configuration in config.py."""

    def test_config_has_circuit_breaker_settings(self):
        """Test that Settings has circuit breaker fields."""
        from autopack.config import Settings

        settings = Settings()
        assert hasattr(settings, "circuit_breaker_enabled")
        assert hasattr(settings, "circuit_breaker_failure_threshold")
        assert hasattr(settings, "circuit_breaker_reset_timeout_seconds")
        assert hasattr(settings, "circuit_breaker_half_open_max_calls")

    def test_config_default_values(self):
        """Test that circuit breaker config has sensible defaults."""
        from autopack.config import Settings

        settings = Settings()
        assert settings.circuit_breaker_enabled is True
        assert settings.circuit_breaker_failure_threshold == 5
        assert settings.circuit_breaker_reset_timeout_seconds == 300
        assert settings.circuit_breaker_half_open_max_calls == 1

    def test_config_validation_rejects_invalid_threshold(self):
        """Test that config validation catches invalid threshold."""
        from unittest.mock import MagicMock

        from autopack.config import Settings, validate_config

        mock_config = MagicMock(spec=Settings)
        mock_config.run_token_cap = 5000000
        mock_config.phase_token_cap_default = 500000
        mock_config.context_budget_tokens = 100000
        mock_config.run_max_phases = 25
        mock_config.run_max_duration_minutes = 120
        mock_config.phase_timeout_minutes = 15
        mock_config.health_check_timeout = 2.0
        mock_config.approval_check_interval = 60.0
        mock_config.db_operation_timeout = 30.0
        mock_config.autopack_sot_retrieval_max_chars = 4000
        mock_config.autopack_sot_retrieval_top_k = 3
        mock_config.autopack_sot_chunk_max_chars = 1200
        mock_config.autopilot_gap_scan_frequency = 5
        mock_config.autopilot_max_proposals_per_session = 3
        mock_config.task_generation_max_tasks_per_run = 10
        mock_config.task_generation_min_confidence = 0.7
        mock_config.access_token_expire_minutes = 1440
        mock_config.autopack_env = "development"

        # Set invalid circuit breaker value
        mock_config.circuit_breaker_failure_threshold = 0
        mock_config.circuit_breaker_reset_timeout_seconds = 300
        mock_config.circuit_breaker_half_open_max_calls = 1

        errors = validate_config(mock_config)
        assert any("circuit_breaker_failure_threshold" in e for e in errors)
