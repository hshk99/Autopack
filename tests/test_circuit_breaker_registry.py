"""Tests for circuit breaker registry."""

from unittest.mock import Mock

import pytest

from autopack.circuit_breaker import CircuitBreakerConfig, CircuitState
from autopack.circuit_breaker_registry import (CircuitBreakerRegistry,
                                               get_global_registry)


class TestCircuitBreakerRegistry:
    """Tests for CircuitBreakerRegistry."""

    @pytest.fixture
    def registry(self):
        """Create a fresh registry for each test."""
        reg = CircuitBreakerRegistry()
        reg.clear()  # Ensure clean state
        return reg

    def test_singleton_pattern(self):
        """Test that registry implements singleton pattern."""
        reg1 = CircuitBreakerRegistry()
        reg2 = CircuitBreakerRegistry()
        assert reg1 is reg2

    def test_register_circuit_breaker(self, registry):
        """Test registering a new circuit breaker."""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = registry.register("test", config)

        assert breaker is not None
        assert breaker.name == "test"
        assert registry.count() == 1

    def test_register_duplicate_raises_error(self, registry):
        """Test that registering duplicate name raises error."""
        registry.register("test")

        with pytest.raises(ValueError, match="already registered"):
            registry.register("test")

    def test_register_duplicate_with_force(self, registry):
        """Test that force=True allows replacing existing breaker."""
        breaker1 = registry.register("test")
        breaker2 = registry.register("test", force=True)

        assert breaker1 is not breaker2
        assert registry.count() == 1

    def test_get_circuit_breaker(self, registry):
        """Test getting a circuit breaker by name."""
        original = registry.register("test")
        retrieved = registry.get("test")

        assert retrieved is original

    def test_get_nonexistent_returns_none(self, registry):
        """Test that getting nonexistent breaker returns None."""
        result = registry.get("nonexistent")
        assert result is None

    def test_get_or_create_existing(self, registry):
        """Test get_or_create with existing breaker."""
        original = registry.register("test")
        retrieved = registry.get_or_create("test")

        assert retrieved is original
        assert registry.count() == 1

    def test_get_or_create_new(self, registry):
        """Test get_or_create with new breaker."""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = registry.get_or_create("test", config)

        assert breaker is not None
        assert breaker.name == "test"
        assert registry.count() == 1

    def test_unregister_circuit_breaker(self, registry):
        """Test unregistering a circuit breaker."""
        registry.register("test")
        assert registry.count() == 1

        result = registry.unregister("test")

        assert result is True
        assert registry.count() == 0
        assert registry.get("test") is None

    def test_unregister_nonexistent(self, registry):
        """Test unregistering nonexistent breaker returns False."""
        result = registry.unregister("nonexistent")
        assert result is False

    def test_reset_circuit_breaker(self, registry):
        """Test resetting a circuit breaker."""
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker = registry.register("test", config)

        # Open the circuit
        mock_func = Mock(side_effect=Exception("error"))
        for _ in range(2):
            with pytest.raises(Exception):
                breaker.call(mock_func)

        assert breaker.state == CircuitState.OPEN

        # Reset via registry
        result = registry.reset("test")

        assert result is True
        assert breaker.state == CircuitState.CLOSED

    def test_reset_nonexistent(self, registry):
        """Test resetting nonexistent breaker returns False."""
        result = registry.reset("nonexistent")
        assert result is False

    def test_reset_all(self, registry):
        """Test resetting all circuit breakers."""
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker1 = registry.register("test1", config)
        breaker2 = registry.register("test2", config)

        # Open both circuits
        mock_func = Mock(side_effect=Exception("error"))
        for breaker in [breaker1, breaker2]:
            for _ in range(2):
                with pytest.raises(Exception):
                    breaker.call(mock_func)

        assert breaker1.state == CircuitState.OPEN
        assert breaker2.state == CircuitState.OPEN

        # Reset all
        registry.reset_all()

        assert breaker1.state == CircuitState.CLOSED
        assert breaker2.state == CircuitState.CLOSED

    def test_get_status(self, registry):
        """Test getting status of a circuit breaker."""
        config = CircuitBreakerConfig(failure_threshold=3)
        registry.register("test", config)

        status = registry.get_status("test")

        assert status is not None
        assert status.name == "test"
        assert status.state == CircuitState.CLOSED
        assert status.is_available is True
        assert status.config.failure_threshold == 3

    def test_get_status_nonexistent(self, registry):
        """Test getting status of nonexistent breaker returns None."""
        status = registry.get_status("nonexistent")
        assert status is None

    def test_get_all_statuses(self, registry):
        """Test getting status of all circuit breakers."""
        registry.register("test1")
        registry.register("test2")
        registry.register("test3")

        statuses = registry.get_all_statuses()

        assert len(statuses) == 3
        names = {s.name for s in statuses}
        assert names == {"test1", "test2", "test3"}

    def test_get_all_names(self, registry):
        """Test getting all circuit breaker names."""
        registry.register("test1")
        registry.register("test2")
        registry.register("test3")

        names = registry.get_all_names()

        assert len(names) == 3
        assert set(names) == {"test1", "test2", "test3"}

    def test_count(self, registry):
        """Test counting circuit breakers."""
        assert registry.count() == 0

        registry.register("test1")
        assert registry.count() == 1

        registry.register("test2")
        assert registry.count() == 2

        registry.unregister("test1")
        assert registry.count() == 1

    def test_clear(self, registry):
        """Test clearing all circuit breakers."""
        registry.register("test1")
        registry.register("test2")
        registry.register("test3")

        assert registry.count() == 3

        registry.clear()

        assert registry.count() == 0
        assert registry.get_all_names() == []

    def test_thread_safety(self, registry):
        """Test thread safety of registry operations."""
        import threading

        def worker(name):
            registry.register(name)
            breaker = registry.get(name)
            breaker.call(lambda: "success")

        threads = [threading.Thread(target=worker, args=(f"test{i}",)) for i in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert registry.count() == 10


class TestGlobalRegistry:
    """Tests for global registry function."""

    def test_get_global_registry(self):
        """Test getting global registry instance."""
        reg1 = get_global_registry()
        reg2 = get_global_registry()

        assert reg1 is reg2
        assert isinstance(reg1, CircuitBreakerRegistry)

    def test_global_registry_persistence(self):
        """Test that global registry persists across calls."""
        reg = get_global_registry()
        reg.register("test")

        reg2 = get_global_registry()
        breaker = reg2.get("test")

        assert breaker is not None
        assert breaker.name == "test"
