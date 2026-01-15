"""Tests for circuit breaker state persistence (IMP-030)."""

import json
import pytest

from autopack.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState
from autopack.circuit_breaker_registry import CircuitBreakerRegistry


class TestCircuitBreakerSerialization:
    """Test CircuitBreaker to_dict/from_dict methods."""

    def test_to_dict_captures_state(self):
        """to_dict should capture all relevant state."""
        config = CircuitBreakerConfig(failure_threshold=3, timeout=45.0)
        cb = CircuitBreaker(name="test_breaker", config=config)

        # Simulate some activity
        cb.metrics.total_calls = 10
        cb.metrics.successful_calls = 8
        cb.metrics.failed_calls = 2
        cb.failure_count = 2

        data = cb.to_dict()

        assert data["name"] == "test_breaker"
        assert data["state"] == "closed"
        assert data["failure_count"] == 2
        assert data["config"]["failure_threshold"] == 3
        assert data["config"]["timeout"] == 45.0
        assert data["metrics"]["total_calls"] == 10
        assert data["metrics"]["successful_calls"] == 8

    def test_from_dict_restores_state(self):
        """from_dict should restore circuit breaker state."""
        data = {
            "name": "restored_breaker",
            "state": "open",
            "failure_count": 5,
            "success_count": 0,
            "last_failure_time": 1234567890.0,
            "last_state_change": 1234567890.0,
            "config": {
                "failure_threshold": 10,
                "success_threshold": 3,
                "timeout": 120.0,
                "half_open_timeout": 60.0,
            },
            "metrics": {
                "total_calls": 100,
                "successful_calls": 90,
                "failed_calls": 10,
                "rejected_calls": 5,
                "state_transitions": {"closed_to_open": 2},
            },
        }

        cb = CircuitBreaker.from_dict(data)

        assert cb.name == "restored_breaker"
        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 5
        assert cb.config.failure_threshold == 10
        assert cb.config.timeout == 120.0
        assert cb.metrics.total_calls == 100
        assert cb.metrics.rejected_calls == 5
        assert cb.metrics.state_transitions["closed_to_open"] == 2

    def test_roundtrip_preserves_state(self):
        """to_dict followed by from_dict should preserve state."""
        config = CircuitBreakerConfig(failure_threshold=5, timeout=30.0)
        original = CircuitBreaker(name="roundtrip_test", config=config)

        # Modify state
        original.metrics.total_calls = 50
        original.metrics.failed_calls = 3
        original.failure_count = 3

        # Roundtrip
        data = original.to_dict()
        restored = CircuitBreaker.from_dict(data)

        assert restored.name == original.name
        assert restored.state == original.state
        assert restored.failure_count == original.failure_count
        assert restored.config.failure_threshold == original.config.failure_threshold
        assert restored.metrics.total_calls == original.metrics.total_calls


class TestRegistryPersistence:
    """Test CircuitBreakerRegistry persist_all/restore_all methods."""

    @pytest.fixture
    def temp_persistence_path(self, tmp_path):
        """Create a temporary persistence file path."""
        return tmp_path / "circuit_breaker_state.json"

    @pytest.fixture
    def fresh_registry(self):
        """Create a fresh registry instance (bypass singleton)."""
        registry = object.__new__(CircuitBreakerRegistry)
        registry._breakers = {}
        registry._configs = {}
        registry._registry_lock = __import__("threading").RLock()
        registry._initialized = True
        return registry

    def test_persist_all_creates_file(self, fresh_registry, temp_persistence_path):
        """persist_all should create the persistence file."""
        fresh_registry.register("breaker1", CircuitBreakerConfig(failure_threshold=5))
        fresh_registry.register("breaker2", CircuitBreakerConfig(failure_threshold=10))

        result = fresh_registry.persist_all(temp_persistence_path)

        assert result is True
        assert temp_persistence_path.exists()

        with open(temp_persistence_path) as f:
            data = json.load(f)

        assert "breaker1" in data
        assert "breaker2" in data
        assert data["breaker1"]["config"]["failure_threshold"] == 5

    def test_restore_all_loads_state(self, fresh_registry, temp_persistence_path):
        """restore_all should load circuit breakers from file."""
        # Create persistence file manually
        states = {
            "api_service": {
                "name": "api_service",
                "state": "open",
                "failure_count": 5,
                "success_count": 0,
                "last_failure_time": None,
                "last_state_change": 1234567890.0,
                "config": {
                    "failure_threshold": 5,
                    "success_threshold": 2,
                    "timeout": 60.0,
                    "half_open_timeout": 30.0,
                },
                "metrics": {
                    "total_calls": 20,
                    "successful_calls": 15,
                    "failed_calls": 5,
                    "rejected_calls": 0,
                    "state_transitions": {},
                },
            }
        }
        temp_persistence_path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_persistence_path, "w") as f:
            json.dump(states, f)

        count = fresh_registry.restore_all(temp_persistence_path)

        assert count == 1
        breaker = fresh_registry.get("api_service")
        assert breaker is not None
        assert breaker.state == CircuitState.OPEN
        assert breaker.config.failure_threshold == 5

    def test_restore_all_returns_zero_for_missing_file(self, fresh_registry, tmp_path):
        """restore_all should return 0 if file doesn't exist."""
        nonexistent = tmp_path / "nonexistent.json"
        count = fresh_registry.restore_all(nonexistent)
        assert count == 0

    def test_restore_all_handles_invalid_json(self, fresh_registry, temp_persistence_path):
        """restore_all should handle invalid JSON gracefully."""
        temp_persistence_path.parent.mkdir(parents=True, exist_ok=True)
        temp_persistence_path.write_text("not valid json {{{")

        count = fresh_registry.restore_all(temp_persistence_path)
        assert count == 0

    def test_persist_restore_roundtrip(self, fresh_registry, temp_persistence_path):
        """Full roundtrip: persist, clear, restore."""
        # Register and modify breakers
        fresh_registry.register("service_a", CircuitBreakerConfig(failure_threshold=3))
        fresh_registry.register("service_b", CircuitBreakerConfig(failure_threshold=7))

        breaker_a = fresh_registry.get("service_a")
        breaker_a.metrics.total_calls = 100
        breaker_a.failure_count = 2

        # Persist
        fresh_registry.persist_all(temp_persistence_path)

        # Clear
        fresh_registry.clear()
        assert fresh_registry.count() == 0

        # Restore
        count = fresh_registry.restore_all(temp_persistence_path)

        assert count == 2
        assert fresh_registry.count() == 2

        restored_a = fresh_registry.get("service_a")
        assert restored_a is not None
        assert restored_a.config.failure_threshold == 3
        assert restored_a.metrics.total_calls == 100
