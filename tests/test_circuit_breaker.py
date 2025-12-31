"""Tests for circuit breaker implementation."""
import pytest
import time
from unittest.mock import Mock, patch

from autopack.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    CircuitBreakerOpenError,
    CircuitBreakerMetrics
)


class TestCircuitBreakerConfig:
    """Tests for CircuitBreakerConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.success_threshold == 2
        assert config.timeout == 60.0
        assert config.half_open_timeout == 30.0
        assert config.expected_exception == Exception

    def test_custom_config(self):
        """Test custom configuration values."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=1,
            timeout=30.0,
            half_open_timeout=15.0
        )
        assert config.failure_threshold == 3
        assert config.success_threshold == 1
        assert config.timeout == 30.0
        assert config.half_open_timeout == 15.0


class TestCircuitBreakerMetrics:
    """Tests for CircuitBreakerMetrics."""

    def test_initial_metrics(self):
        """Test initial metrics values."""
        metrics = CircuitBreakerMetrics()
        assert metrics.total_calls == 0
        assert metrics.successful_calls == 0
        assert metrics.failed_calls == 0
        assert metrics.rejected_calls == 0
        assert metrics.last_failure_time is None
        assert metrics.last_success_time is None

    def test_record_success(self):
        """Test recording successful calls."""
        metrics = CircuitBreakerMetrics()
        metrics.record_success()
        assert metrics.total_calls == 1
        assert metrics.successful_calls == 1
        assert metrics.last_success_time is not None

    def test_record_failure(self):
        """Test recording failed calls."""
        metrics = CircuitBreakerMetrics()
        metrics.record_failure()
        assert metrics.total_calls == 1
        assert metrics.failed_calls == 1
        assert metrics.last_failure_time is not None

    def test_record_rejection(self):
        """Test recording rejected calls."""
        metrics = CircuitBreakerMetrics()
        metrics.record_rejection()
        assert metrics.total_calls == 1
        assert metrics.rejected_calls == 1

    def test_record_state_transition(self):
        """Test recording state transitions."""
        metrics = CircuitBreakerMetrics()
        metrics.record_state_transition(CircuitState.CLOSED, CircuitState.OPEN)
        assert metrics.state_transitions["closed_to_open"] == 1


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    def test_initialization(self):
        """Test circuit breaker initialization."""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker(name="test", config=config)
        
        assert breaker.name == "test"
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
        assert breaker.success_count == 0

    def test_successful_call_in_closed_state(self):
        """Test successful call when circuit is closed."""
        breaker = CircuitBreaker(name="test")
        mock_func = Mock(return_value="success")
        
        result = breaker.call(mock_func)
        
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED
        assert breaker.metrics.successful_calls == 1
        mock_func.assert_called_once()

    def test_failed_call_in_closed_state(self):
        """Test failed call when circuit is closed."""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker(name="test", config=config)
        mock_func = Mock(side_effect=Exception("error"))
        
        with pytest.raises(Exception, match="error"):
            breaker.call(mock_func)
        
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 1
        assert breaker.metrics.failed_calls == 1

    def test_transition_to_open_on_threshold(self):
        """Test transition to OPEN state when failure threshold is reached."""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker(name="test", config=config)
        mock_func = Mock(side_effect=Exception("error"))
        
        # Fail 3 times to reach threshold
        for _ in range(3):
            with pytest.raises(Exception):
                breaker.call(mock_func)
        
        assert breaker.state == CircuitState.OPEN
        assert breaker.metrics.failed_calls == 3

    def test_reject_calls_when_open(self):
        """Test that calls are rejected when circuit is open."""
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker = CircuitBreaker(name="test", config=config)
        mock_func = Mock(side_effect=Exception("error"))
        
        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                breaker.call(mock_func)
        
        # Next call should be rejected
        with pytest.raises(CircuitBreakerOpenError):
            breaker.call(mock_func)
        
        assert breaker.metrics.rejected_calls == 1

    def test_transition_to_half_open_after_timeout(self):
        """Test transition to HALF_OPEN state after timeout."""
        config = CircuitBreakerConfig(failure_threshold=2, timeout=0.1)
        breaker = CircuitBreaker(name="test", config=config)
        mock_func = Mock(side_effect=Exception("error"))
        
        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                breaker.call(mock_func)
        
        assert breaker.state == CircuitState.OPEN
        
        # Wait for timeout
        time.sleep(0.15)
        
        # Next call should trigger state update to HALF_OPEN
        mock_func.side_effect = None
        mock_func.return_value = "success"
        result = breaker.call(mock_func)
        
        assert result == "success"
        assert breaker.state == CircuitState.HALF_OPEN

    def test_recovery_in_half_open_state(self):
        """Test recovery to CLOSED state from HALF_OPEN."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=2,
            timeout=0.1
        )
        breaker = CircuitBreaker(name="test", config=config)
        mock_func = Mock(side_effect=Exception("error"))
        
        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                breaker.call(mock_func)
        
        # Wait for timeout
        time.sleep(0.15)
        
        # Succeed twice in HALF_OPEN to recover
        mock_func.side_effect = None
        mock_func.return_value = "success"
        
        breaker.call(mock_func)
        assert breaker.state == CircuitState.HALF_OPEN
        
        breaker.call(mock_func)
        assert breaker.state == CircuitState.CLOSED

    def test_failure_in_half_open_reopens_circuit(self):
        """Test that failure in HALF_OPEN immediately reopens circuit."""
        config = CircuitBreakerConfig(failure_threshold=2, timeout=0.1)
        breaker = CircuitBreaker(name="test", config=config)
        mock_func = Mock(side_effect=Exception("error"))
        
        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                breaker.call(mock_func)
        
        # Wait for timeout to enter HALF_OPEN
        time.sleep(0.15)
        
        # Fail in HALF_OPEN
        with pytest.raises(Exception):
            breaker.call(mock_func)
        
        assert breaker.state == CircuitState.OPEN

    def test_manual_reset(self):
        """Test manual reset of circuit breaker."""
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker = CircuitBreaker(name="test", config=config)
        mock_func = Mock(side_effect=Exception("error"))
        
        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                breaker.call(mock_func)
        
        assert breaker.state == CircuitState.OPEN
        
        # Manual reset
        breaker.reset()
        
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_is_available(self):
        """Test is_available method."""
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker = CircuitBreaker(name="test", config=config)
        
        assert breaker.is_available() is True
        
        # Open the circuit
        mock_func = Mock(side_effect=Exception("error"))
        for _ in range(2):
            with pytest.raises(Exception):
                breaker.call(mock_func)
        
        assert breaker.is_available() is False

    def test_get_state(self):
        """Test get_state method."""
        breaker = CircuitBreaker(name="test")
        assert breaker.get_state() == CircuitState.CLOSED

    def test_get_metrics(self):
        """Test get_metrics method."""
        breaker = CircuitBreaker(name="test")
        mock_func = Mock(return_value="success")
        
        breaker.call(mock_func)
        
        metrics = breaker.get_metrics()
        assert metrics.total_calls == 1
        assert metrics.successful_calls == 1

    def test_thread_safety(self):
        """Test thread safety of circuit breaker."""
        import threading
        
        breaker = CircuitBreaker(name="test")
        results = []
        errors = []
        
        def worker():
            try:
                result = breaker.call(lambda: "success")
                results.append(result)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(results) == 10
        assert len(errors) == 0
        assert breaker.metrics.successful_calls == 10
