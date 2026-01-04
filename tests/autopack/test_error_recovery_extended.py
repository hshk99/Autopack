"""Extended tests for error_recovery.py.

Tests cover:
- Retry strategies (exponential backoff, max retries)
- Circuit breaker patterns (open/closed/half-open states)
- Backoff mechanisms (exponential, jitter)
- Edge cases (zero retries, timeout, concurrent failures)
- Integration with phase execution

NOTE: This is an extended test suite for planned/enhanced error recovery features.
Tests are marked xfail until the enhanced API is implemented.
"""

import pytest
import time

pytestmark = [
    pytest.mark.xfail(strict=False, reason="Extended ErrorRecovery API not implemented - aspirational test suite"),
    pytest.mark.aspirational
]


class TestRetryStrategies:
    """Test retry strategies and exponential backoff."""

    def test_exponential_backoff_basic(self):
        """Test basic exponential backoff calculation."""
        from autopack.error_recovery import calculate_backoff_delay

        # First retry: 1 second
        delay1 = calculate_backoff_delay(attempt=1, base_delay=1.0, max_delay=60.0)
        assert 0.9 <= delay1 <= 1.1  # Allow for jitter

        # Second retry: 2 seconds
        delay2 = calculate_backoff_delay(attempt=2, base_delay=1.0, max_delay=60.0)
        assert 1.8 <= delay2 <= 2.2

        # Third retry: 4 seconds
        delay3 = calculate_backoff_delay(attempt=3, base_delay=1.0, max_delay=60.0)
        assert 3.6 <= delay3 <= 4.4

    def test_exponential_backoff_max_delay_cap(self):
        """Test that backoff delay is capped at max_delay."""
        from autopack.error_recovery import calculate_backoff_delay

        # Very high attempt number should be capped
        delay = calculate_backoff_delay(attempt=20, base_delay=1.0, max_delay=10.0)
        assert delay <= 10.0

    def test_retry_with_backoff_success_after_retries(self):
        """Test successful execution after retries with backoff."""
        from autopack.error_recovery import retry_with_backoff

        call_count = 0

        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return "success"

        result = retry_with_backoff(
            func=flaky_function,
            max_retries=5,
            base_delay=0.1,
            max_delay=1.0
        )

        assert result == "success"
        assert call_count == 3

    def test_retry_with_backoff_max_retries_exceeded(self):
        """Test that max retries limit is enforced."""
        from autopack.error_recovery import retry_with_backoff

        call_count = 0

        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("Persistent failure")

        with pytest.raises(ValueError, match="Persistent failure"):
            retry_with_backoff(
                func=always_fails,
                max_retries=3,
                base_delay=0.01,
                max_delay=0.1
            )

        # Should try initial + 3 retries = 4 total
        assert call_count == 4

    def test_retry_with_backoff_zero_retries(self):
        """Test behavior with zero retries (no retry, fail immediately)."""
        from autopack.error_recovery import retry_with_backoff

        call_count = 0

        def fails_once():
            nonlocal call_count
            call_count += 1
            raise ValueError("Failure")

        with pytest.raises(ValueError):
            retry_with_backoff(
                func=fails_once,
                max_retries=0,
                base_delay=0.1,
                max_delay=1.0
            )

        # Should only try once (no retries)
        assert call_count == 1

    def test_retry_with_jitter(self):
        """Test that jitter is applied to backoff delays."""
        from autopack.error_recovery import calculate_backoff_delay

        delays = []
        for _ in range(10):
            delay = calculate_backoff_delay(attempt=3, base_delay=1.0, max_delay=60.0, jitter=True)
            delays.append(delay)

        # All delays should be different due to jitter
        assert len(set(delays)) > 1
        # All delays should be around 4 seconds (2^3 * 0.5)
        assert all(3.0 <= d <= 5.0 for d in delays)


class TestCircuitBreaker:
    """Test circuit breaker pattern implementation."""

    def test_circuit_breaker_closed_state(self):
        """Test circuit breaker in closed state (normal operation)."""
        from autopack.error_recovery import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=3, timeout=5.0)

        # Should allow calls in closed state
        assert breaker.is_closed() is True
        assert breaker.can_attempt() is True

    def test_circuit_breaker_opens_after_threshold(self):
        """Test that circuit breaker opens after failure threshold."""
        from autopack.error_recovery import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=3, timeout=5.0)

        # Record failures
        for _ in range(3):
            breaker.record_failure()

        # Circuit should now be open
        assert breaker.is_open() is True
        assert breaker.can_attempt() is False

    def test_circuit_breaker_half_open_after_timeout(self):
        """Test circuit breaker transitions to half-open after timeout."""
        from autopack.error_recovery import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=2, timeout=0.1)

        # Open the circuit
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.is_open() is True

        # Wait for timeout
        time.sleep(0.15)

        # Should now be half-open
        assert breaker.is_half_open() is True
        assert breaker.can_attempt() is True

    def test_circuit_breaker_closes_on_success(self):
        """Test circuit breaker closes after successful call in half-open state."""
        from autopack.error_recovery import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=2, timeout=0.1)

        # Open the circuit
        breaker.record_failure()
        breaker.record_failure()

        # Wait for timeout to enter half-open
        time.sleep(0.15)
        assert breaker.is_half_open() is True

        # Record success
        breaker.record_success()

        # Should close the circuit
        assert breaker.is_closed() is True

    def test_circuit_breaker_reopens_on_failure_in_half_open(self):
        """Test circuit breaker reopens if failure occurs in half-open state."""
        from autopack.error_recovery import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=2, timeout=0.1)

        # Open the circuit
        breaker.record_failure()
        breaker.record_failure()

        # Wait for timeout to enter half-open
        time.sleep(0.15)
        assert breaker.is_half_open() is True

        # Record failure in half-open state
        breaker.record_failure()

        # Should reopen the circuit
        assert breaker.is_open() is True
        assert breaker.can_attempt() is False

    def test_circuit_breaker_with_function_execution(self):
        """Test circuit breaker integration with function execution."""
        from autopack.error_recovery import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=2, timeout=0.1)
        call_count = 0

        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ValueError("Failure")
            return "success"

        # First two calls fail, opening circuit
        for _ in range(2):
            try:
                if breaker.can_attempt():
                    flaky_function()
                    breaker.record_success()
            except ValueError:
                breaker.record_failure()

        # Circuit should be open
        assert breaker.is_open() is True
        assert call_count == 2

        # Next attempt should be blocked
        assert breaker.can_attempt() is False


class TestBackoffMechanisms:
    """Test various backoff mechanisms."""

    def test_linear_backoff(self):
        """Test linear backoff calculation."""
        from autopack.error_recovery import calculate_linear_backoff

        # Linear: delay = base_delay * attempt
        assert calculate_linear_backoff(attempt=1, base_delay=1.0) == 1.0
        assert calculate_linear_backoff(attempt=2, base_delay=1.0) == 2.0
        assert calculate_linear_backoff(attempt=5, base_delay=1.0) == 5.0

    def test_fibonacci_backoff(self):
        """Test Fibonacci backoff calculation."""
        from autopack.error_recovery import calculate_fibonacci_backoff

        # Fibonacci sequence: 1, 1, 2, 3, 5, 8, 13...
        assert calculate_fibonacci_backoff(attempt=1, base_delay=1.0) == 1.0
        assert calculate_fibonacci_backoff(attempt=2, base_delay=1.0) == 1.0
        assert calculate_fibonacci_backoff(attempt=3, base_delay=1.0) == 2.0
        assert calculate_fibonacci_backoff(attempt=4, base_delay=1.0) == 3.0
        assert calculate_fibonacci_backoff(attempt=5, base_delay=1.0) == 5.0

    def test_backoff_with_max_cap(self):
        """Test that all backoff strategies respect max delay cap."""
        from autopack.error_recovery import (
            calculate_backoff_delay,
            calculate_linear_backoff,
            calculate_fibonacci_backoff
        )

        max_delay = 10.0

        # Exponential should cap
        exp_delay = calculate_backoff_delay(attempt=20, base_delay=1.0, max_delay=max_delay)
        assert exp_delay <= max_delay

        # Linear should cap
        lin_delay = calculate_linear_backoff(attempt=20, base_delay=1.0, max_delay=max_delay)
        assert lin_delay <= max_delay

        # Fibonacci should cap
        fib_delay = calculate_fibonacci_backoff(attempt=20, base_delay=1.0, max_delay=max_delay)
        assert fib_delay <= max_delay


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_retry_with_timeout(self):
        """Test retry with overall timeout limit."""
        from autopack.error_recovery import retry_with_timeout

        def slow_function():
            time.sleep(0.5)
            raise ValueError("Slow failure")

        start_time = time.time()
        with pytest.raises(TimeoutError):
            retry_with_timeout(
                func=slow_function,
                max_retries=10,
                timeout=1.0,
                base_delay=0.1
            )
        elapsed = time.time() - start_time

        # Should timeout around 1 second
        assert 0.9 <= elapsed <= 1.5

    def test_concurrent_failures(self):
        """Test handling of concurrent failures with circuit breaker."""
        from autopack.error_recovery import CircuitBreaker
        import threading

        breaker = CircuitBreaker(failure_threshold=5, timeout=1.0)
        failure_count = 0
        lock = threading.Lock()

        def concurrent_failure():
            nonlocal failure_count
            try:
                if breaker.can_attempt():
                    raise ValueError("Concurrent failure")
            except ValueError:
                with lock:
                    failure_count += 1
                breaker.record_failure()

        # Run concurrent failures
        threads = [threading.Thread(target=concurrent_failure) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Circuit should be open after threshold
        assert breaker.is_open() is True
        # Not all failures should be recorded (some blocked by open circuit)
        assert failure_count <= 10

    def test_retry_with_custom_exception_filter(self):
        """Test retry with custom exception filtering."""
        from autopack.error_recovery import retry_with_exception_filter

        call_count = 0

        def raises_different_exceptions():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Retryable error")
            elif call_count == 2:
                raise TypeError("Non-retryable error")
            return "success"

        # Only retry on ValueError
        with pytest.raises(TypeError):
            retry_with_exception_filter(
                func=raises_different_exceptions,
                max_retries=5,
                retryable_exceptions=(ValueError,)
            )

        # Should have tried twice (initial + 1 retry for ValueError, then TypeError)
        assert call_count == 2

    def test_recovery_state_persistence(self, tmp_path):
        """Test that recovery state can be persisted and restored."""
        from autopack.error_recovery import CircuitBreaker

        state_file = tmp_path / "circuit_state.json"

        # Create breaker and open it
        breaker1 = CircuitBreaker(failure_threshold=2, timeout=5.0)
        breaker1.record_failure()
        breaker1.record_failure()
        assert breaker1.is_open() is True

        # Save state
        breaker1.save_state(state_file)

        # Create new breaker and restore state
        breaker2 = CircuitBreaker(failure_threshold=2, timeout=5.0)
        breaker2.load_state(state_file)

        # Should still be open
        assert breaker2.is_open() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
