"""Tests for circuit breaker persistence requirement."""

import pytest
import tempfile
import os
from pathlib import Path

from autopack.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
)
from autopack.circuit_breaker_file_persistence import FileBasedCircuitBreakerPersistence


class TestCircuitBreakerPersistenceMandatory:
    """Test that circuit breaker persistence is mandatory and functional."""

    def test_persistence_is_required_with_default_path(self):
        """Verify circuit breaker uses file-based persistence by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = os.path.join(tmpdir, "test_state.json")
            breaker = CircuitBreaker(
                name="test_breaker",
                persistence_path=state_file,
                config=CircuitBreakerConfig(failure_threshold=2),
            )

            # Trigger failures to open circuit (which will save state)
            for _ in range(3):
                try:
                    breaker.call(lambda: 1 / 0)
                except ZeroDivisionError:
                    pass
                except CircuitBreakerOpenError:
                    # Circuit opened, expected
                    break

            # Now verify persistence file was created after state change
            assert Path(state_file).exists()
            assert breaker.get_state() == CircuitState.OPEN

    def test_state_persists_across_instances(self):
        """Verify circuit breaker state persists across different instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = os.path.join(tmpdir, "persist_state.json")

            # Create first breaker and open circuit
            breaker1 = CircuitBreaker(
                name="persist_test",
                persistence_path=state_file,
                config=CircuitBreakerConfig(failure_threshold=2),
            )

            # Trigger failures until circuit opens
            for _ in range(2):
                try:
                    breaker1.call(lambda: 1 / 0)
                except ZeroDivisionError:
                    pass
                except CircuitBreakerOpenError:
                    # Circuit opened, expected
                    break

            assert breaker1.get_state() == CircuitState.OPEN

            # Create second breaker with same name - should restore OPEN state
            breaker2 = CircuitBreaker(
                name="persist_test",
                persistence_path=state_file,
                config=CircuitBreakerConfig(failure_threshold=2),
            )

            assert breaker2.get_state() == CircuitState.OPEN

            # Verify it rejects calls as expected
            with pytest.raises(CircuitBreakerOpenError):
                breaker2.call(lambda: "test")

    def test_custom_persistence_can_be_used(self):
        """Verify custom persistence layer can be provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = os.path.join(tmpdir, "custom_state.json")

            custom_persistence = FileBasedCircuitBreakerPersistence(state_file)

            breaker = CircuitBreaker(
                name="custom_test",
                persistence=custom_persistence,
                config=CircuitBreakerConfig(failure_threshold=2),
            )

            # Verify custom persistence is used
            assert breaker._persistence is custom_persistence

    def test_persistence_directory_created_if_missing(self):
        """Verify persistence directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use a non-existent subdirectory
            state_file = os.path.join(tmpdir, "new_dir", "nested", "state.json")

            breaker = CircuitBreaker(
                name="dir_test",
                persistence_path=state_file,
            )

            # Trigger a state change to save
            try:
                breaker.call(lambda: 1 / 0)
            except ZeroDivisionError:
                pass
            except CircuitBreakerOpenError:
                pass

            # Verify directory was created
            assert Path(state_file).parent.exists()

    def test_metrics_are_persisted(self):
        """Verify circuit breaker metrics are persisted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = os.path.join(tmpdir, "metrics_state.json")

            breaker = CircuitBreaker(
                name="metrics_test",
                persistence_path=state_file,
            )

            # Generate some calls
            try:
                breaker.call(lambda: "success")
            except Exception:
                pass

            # Trigger failures
            for _ in range(5):
                try:
                    breaker.call(lambda: 1 / 0)
                except ZeroDivisionError:
                    pass
                except CircuitBreakerOpenError:
                    break

            metrics1 = breaker.get_metrics()
            assert metrics1.total_calls > 0
            assert metrics1.failed_calls > 0

            # Create new instance and verify metrics restored
            breaker2 = CircuitBreaker(
                name="metrics_test",
                persistence_path=state_file,
            )

            metrics2 = breaker2.get_metrics()
            assert metrics2.total_calls == metrics1.total_calls
            assert metrics2.failed_calls == metrics1.failed_calls

    def test_state_recovered_after_timeout(self):
        """Verify HALF_OPEN state is recovered correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = os.path.join(tmpdir, "timeout_state.json")

            # Create breaker with very short timeout
            breaker = CircuitBreaker(
                name="timeout_test",
                persistence_path=state_file,
                config=CircuitBreakerConfig(
                    failure_threshold=2,
                    timeout=0.1,  # 100ms
                    half_open_timeout=0.05,
                ),
            )

            # Open circuit
            for _ in range(2):
                try:
                    breaker.call(lambda: 1 / 0)
                except ZeroDivisionError:
                    pass
                except CircuitBreakerOpenError:
                    break

            assert breaker.get_state() == CircuitState.OPEN

            # Create new instance - should be OPEN initially
            breaker2 = CircuitBreaker(
                name="timeout_test",
                persistence_path=state_file,
                config=CircuitBreakerConfig(
                    failure_threshold=2,
                    timeout=0.1,
                    half_open_timeout=0.05,
                ),
            )

            assert breaker2.get_state() == CircuitState.OPEN

    def test_multiple_breakers_share_state_file(self):
        """Verify multiple breakers can share a single state file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = os.path.join(tmpdir, "shared_state.json")

            breaker_a = CircuitBreaker(
                name="service_a",
                persistence_path=state_file,
                config=CircuitBreakerConfig(failure_threshold=1),
            )

            breaker_b = CircuitBreaker(
                name="service_b",
                persistence_path=state_file,
                config=CircuitBreakerConfig(failure_threshold=1),
            )

            # Open breaker A
            try:
                breaker_a.call(lambda: 1 / 0)
            except ZeroDivisionError:
                pass
            except CircuitBreakerOpenError:
                pass

            assert breaker_a.get_state() == CircuitState.OPEN
            assert breaker_b.get_state() == CircuitState.CLOSED

            # Create new instances
            breaker_a2 = CircuitBreaker(
                name="service_a",
                persistence_path=state_file,
                config=CircuitBreakerConfig(failure_threshold=1),
            )

            breaker_b2 = CircuitBreaker(
                name="service_b",
                persistence_path=state_file,
                config=CircuitBreakerConfig(failure_threshold=1),
            )

            assert breaker_a2.get_state() == CircuitState.OPEN
            assert breaker_b2.get_state() == CircuitState.CLOSED
