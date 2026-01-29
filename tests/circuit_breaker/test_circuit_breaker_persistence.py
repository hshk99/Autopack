"""Tests for circuit breaker persistence.

Verifies that circuit breaker state is persisted to Redis and
restored correctly after process restarts.
"""

import fakeredis
import pytest

from src.autopack.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState
from src.autopack.circuit_breaker_persistence import CircuitBreakerPersistence
from src.autopack.circuit_breaker_registry import CircuitBreakerRegistry


class FakeRedisPersistence(CircuitBreakerPersistence):
    """Persistence using fakeredis for testing."""

    def __init__(self):
        super().__init__(redis_url="redis://localhost:6379/1")
        # Replace client with fakeredis
        self._client = fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def fake_persistence():
    """Create a persistence instance with fakeredis."""
    return FakeRedisPersistence()


@pytest.fixture
def registry_with_persistence(fake_persistence):
    """Create a fresh registry with persistence for each test."""
    # Reset singleton state for testing
    CircuitBreakerRegistry._instance = None
    registry = CircuitBreakerRegistry(persistence=fake_persistence)
    yield registry
    # Cleanup
    registry.clear()
    CircuitBreakerRegistry._instance = None


class TestCircuitStatePersistence:
    """Tests for circuit breaker state persistence."""

    def test_circuit_state_persisted_on_status_change(self, fake_persistence):
        """Verify that circuit breaker state is saved when status changes."""
        # Create circuit breaker with persistence
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker = CircuitBreaker(name="test_service", config=config, persistence=fake_persistence)

        # Initially CLOSED, state should not be persisted yet (no transition)
        assert breaker.get_state() == CircuitState.CLOSED
        initial_state = fake_persistence.load_state("test_service")
        assert initial_state is None  # No state saved until transition

        # Trigger failures to open circuit
        for _ in range(2):
            try:
                breaker.call(lambda: exec('raise Exception("fail")'))
            except Exception:
                pass

        # Circuit should now be OPEN
        assert breaker.get_state() == CircuitState.OPEN

        # State should be persisted
        saved_state = fake_persistence.load_state("test_service")
        assert saved_state is not None
        assert saved_state["state"] == "open"
        assert saved_state["name"] == "test_service"

    def test_circuit_state_restored_after_restart(self, fake_persistence):
        """Verify that circuit breaker state is restored correctly after restart."""
        # Create first circuit breaker and trigger it to OPEN
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker1 = CircuitBreaker(name="api_service", config=config, persistence=fake_persistence)

        # Trigger failures to open circuit
        for _ in range(2):
            try:
                breaker1.call(lambda: exec('raise Exception("fail")'))
            except Exception:
                pass

        assert breaker1.get_state() == CircuitState.OPEN

        # Simulate restart by creating a new circuit breaker with same name
        breaker2 = CircuitBreaker(name="api_service", config=config, persistence=fake_persistence)

        # Load state from persistence
        saved_state = fake_persistence.load_state("api_service")
        assert saved_state is not None
        breaker2._restore_state(saved_state)

        # Verify state was restored
        assert breaker2.get_state() == CircuitState.OPEN
        assert breaker2.name == "api_service"

    def test_registry_restores_state_on_get_breaker(
        self, registry_with_persistence, fake_persistence
    ):
        """Verify that registry restores state when getting a circuit breaker."""
        # First, manually save a state to simulate previous run
        saved_state = {
            "name": "payment_service",
            "state": "open",
            "failure_count": 5,
            "success_count": 0,
            "last_failure_time": 1234567890.0,
            "last_state_change": 1234567890.0,
            "config": {
                "failure_threshold": 5,
                "success_threshold": 2,
                "timeout": 60.0,
                "half_open_timeout": 30.0,
            },
            "metrics": {
                "total_calls": 10,
                "successful_calls": 5,
                "failed_calls": 5,
                "rejected_calls": 0,
                "state_transitions": {"closed_to_open": 1},
            },
        }
        fake_persistence.save_state("payment_service", saved_state)

        # Get circuit breaker from registry (should restore state)
        breaker = registry_with_persistence.get_breaker("payment_service")

        # Verify state was restored
        assert breaker.get_state() == CircuitState.OPEN
        assert breaker.name == "payment_service"
        assert breaker.metrics.total_calls == 10
        assert breaker.metrics.failed_calls == 5

    def test_clear_state_removes_persisted_data(self, fake_persistence):
        """Verify that clear_state removes data from Redis."""
        # Save state
        fake_persistence.save_state("temp_service", {"state": "open", "name": "temp_service"})
        assert fake_persistence.load_state("temp_service") is not None

        # Clear state
        result = fake_persistence.clear_state("temp_service")
        assert result is True

        # Verify cleared
        assert fake_persistence.load_state("temp_service") is None

    def test_persistence_handles_missing_state_gracefully(self, fake_persistence):
        """Verify that loading non-existent state returns None."""
        state = fake_persistence.load_state("nonexistent_service")
        assert state is None

    def test_multiple_circuit_breakers_independent(self, fake_persistence):
        """Verify that multiple circuit breakers have independent state."""
        config = CircuitBreakerConfig(failure_threshold=2)

        breaker_a = CircuitBreaker(name="service_a", config=config, persistence=fake_persistence)
        breaker_b = CircuitBreaker(name="service_b", config=config, persistence=fake_persistence)

        # Open breaker_a
        for _ in range(2):
            try:
                breaker_a.call(lambda: exec('raise Exception("fail")'))
            except Exception:
                pass

        assert breaker_a.get_state() == CircuitState.OPEN
        assert breaker_b.get_state() == CircuitState.CLOSED

        # Verify persistence is independent
        state_a = fake_persistence.load_state("service_a")
        state_b = fake_persistence.load_state("service_b")

        assert state_a is not None
        assert state_a["state"] == "open"
        assert state_b is None  # Never transitioned, so not saved
