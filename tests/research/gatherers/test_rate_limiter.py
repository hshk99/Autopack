"""Tests for RateLimiter module."""

import time
from datetime import datetime, timedelta

import pytest

from autopack.research.gatherers.rate_limiter import (
    RateLimiter,
    RetryBudget,
    RetryBudgetExhausted,
)


class TestRateLimiter:
    """Test cases for RateLimiter."""

    def test_initialization(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter(max_requests_per_hour=100)
        assert limiter.max_requests_per_hour == 100
        assert len(limiter.request_times) == 0

    def test_acquire_single_request(self):
        """Test acquiring a single request."""
        limiter = RateLimiter(max_requests_per_hour=100)
        limiter.acquire()
        assert len(limiter.request_times) == 1

    def test_acquire_multiple_requests(self):
        """Test acquiring multiple requests."""
        limiter = RateLimiter(max_requests_per_hour=100)
        for _ in range(10):
            limiter.acquire()
        assert len(limiter.request_times) == 10

    def test_get_remaining_requests(self):
        """Test getting remaining request count."""
        limiter = RateLimiter(max_requests_per_hour=100)
        assert limiter.get_remaining_requests() == 100

        limiter.acquire()
        assert limiter.get_remaining_requests() == 99

        for _ in range(9):
            limiter.acquire()
        assert limiter.get_remaining_requests() == 90

    def test_reset(self):
        """Test resetting the rate limiter."""
        limiter = RateLimiter(max_requests_per_hour=100)
        for _ in range(10):
            limiter.acquire()
        assert len(limiter.request_times) == 10

        limiter.reset()
        assert len(limiter.request_times) == 0
        assert limiter.get_remaining_requests() == 100

    def test_rate_limiting_blocks(self):
        """Test that rate limiting blocks when limit is reached."""
        # Use a very small limit for testing
        limiter = RateLimiter(max_requests_per_hour=2)

        # First two requests should be immediate
        start = time.time()
        limiter.acquire()
        limiter.acquire()
        elapsed = time.time() - start
        assert elapsed < 0.1  # Should be nearly instant

        # Third request should block (but we won't wait for it in the test)
        # Just verify the state
        assert limiter.get_remaining_requests() == 0

    def test_old_requests_expire(self):
        """Test that old requests are removed from the window."""
        limiter = RateLimiter(max_requests_per_hour=100)

        # Manually add an old request
        old_time = datetime.now() - timedelta(hours=2)
        limiter.request_times.append(old_time)

        # Acquire a new request, which should clean up the old one
        limiter.acquire()

        # Should only have the new request
        assert len(limiter.request_times) == 1
        assert limiter.get_remaining_requests() == 99

    def test_thread_safety(self):
        """Test that rate limiter is thread-safe."""
        import threading

        limiter = RateLimiter(max_requests_per_hour=100)
        results = []

        def acquire_requests():
            for _ in range(10):
                limiter.acquire()
                results.append(1)

        threads = [threading.Thread(target=acquire_requests) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Should have exactly 50 requests (5 threads * 10 requests)
        assert len(results) == 50
        assert len(limiter.request_times) == 50


class TestRetryBudget:
    """Test cases for RetryBudget."""

    def test_default_max_retries_is_3(self):
        """Test that default max_retries is 3 per IMP-RELIABILITY-003."""
        budget = RetryBudget()
        assert budget.max_retries == 3

    def test_default_max_backoff_is_60s(self):
        """Test that default max_backoff is 60s per IMP-RELIABILITY-003."""
        budget = RetryBudget()
        assert budget.max_backoff_seconds == 60.0

    def test_initialization(self):
        """Test retry budget initialization."""
        budget = RetryBudget(max_retries=5)
        assert budget.max_retries == 5
        assert budget.get_remaining_retries() == 5
        assert not budget.is_budget_exhausted()

    def test_record_retry_decreases_budget(self):
        """Test that recording retries decreases remaining budget."""
        budget = RetryBudget(max_retries=3)
        assert budget.get_remaining_retries() == 3

        budget.record_retry()
        assert budget.get_remaining_retries() == 2

        budget.record_retry()
        assert budget.get_remaining_retries() == 1

        budget.record_retry()
        assert budget.get_remaining_retries() == 0
        assert budget.is_budget_exhausted()

    def test_budget_exhausted_raises_exception(self):
        """Test that exceeding budget raises RetryBudgetExhausted."""
        budget = RetryBudget(max_retries=2)

        budget.record_retry()
        budget.record_retry()

        with pytest.raises(RetryBudgetExhausted) as exc_info:
            budget.record_retry()

        assert exc_info.value.total_retries == 2
        assert exc_info.value.budget_limit == 2

    def test_exponential_backoff(self):
        """Test exponential backoff calculation."""
        budget = RetryBudget(
            base_backoff_seconds=1.0,
            max_backoff_seconds=60.0,
            backoff_multiplier=2.0,
        )

        assert budget.get_backoff_time(1) == 1.0
        assert budget.get_backoff_time(2) == 2.0
        assert budget.get_backoff_time(3) == 4.0
        assert budget.get_backoff_time(4) == 8.0

    def test_backoff_capped_at_max(self):
        """Test that backoff is capped at max_backoff_seconds."""
        budget = RetryBudget(
            base_backoff_seconds=1.0,
            max_backoff_seconds=10.0,
            backoff_multiplier=2.0,
        )

        # 2^7 = 128, but should be capped at 10
        assert budget.get_backoff_time(8) == 10.0

    def test_reset_clears_retry_attempts(self):
        """Test that reset clears all retry attempts."""
        budget = RetryBudget(max_retries=3)

        budget.record_retry()
        budget.record_retry()
        assert budget.get_remaining_retries() == 1

        budget.reset()
        assert budget.get_remaining_retries() == 3
        assert not budget.is_budget_exhausted()

    def test_get_retry_stats(self):
        """Test getting retry statistics."""
        budget = RetryBudget(max_retries=5)
        budget.record_retry()
        budget.record_retry()

        stats = budget.get_retry_stats()
        assert stats["total_retries_used"] == 2
        assert stats["max_retries"] == 5
        assert stats["remaining_retries"] == 3
        assert not stats["is_exhausted"]

    def test_expired_retries_cleaned_up(self):
        """Test that retries outside budget window are cleaned up."""
        budget = RetryBudget(max_retries=2, budget_window_seconds=1.0)

        budget.record_retry()
        budget.record_retry()
        assert budget.is_budget_exhausted()

        # Wait for window to expire
        time.sleep(1.1)

        # Budget should be restored
        assert budget.get_remaining_retries() == 2
        assert not budget.is_budget_exhausted()


class TestRateLimiterRetryBudget:
    """Test cases for RateLimiter retry budget integration."""

    def test_rate_limiter_has_retry_budget(self):
        """Test that RateLimiter has retry budget."""
        limiter = RateLimiter(max_retries=5)
        assert limiter.retry_budget.max_retries == 5
        assert not limiter.is_retry_budget_exhausted()

    def test_record_rate_limit_error_uses_budget(self):
        """Test that recording rate limit errors uses retry budget."""
        limiter = RateLimiter(max_retries=3)

        backoff1 = limiter.record_rate_limit_error()
        assert backoff1 == 1.0  # First failure

        backoff2 = limiter.record_rate_limit_error()
        assert backoff2 == 2.0  # Second failure, exponential backoff

        backoff3 = limiter.record_rate_limit_error()
        assert backoff3 == 4.0  # Third failure

        # Budget should now be exhausted
        assert limiter.is_retry_budget_exhausted()

        # Next error should raise exception
        with pytest.raises(RetryBudgetExhausted):
            limiter.record_rate_limit_error()

    def test_record_success_resets_consecutive_failures(self):
        """Test that success resets consecutive failure count."""
        limiter = RateLimiter(max_retries=10)

        limiter.record_rate_limit_error()
        limiter.record_rate_limit_error()
        assert limiter._consecutive_failures == 2

        limiter.record_success()
        assert limiter._consecutive_failures == 0

        # Next error should start fresh
        backoff = limiter.record_rate_limit_error()
        assert backoff == 1.0  # Back to base backoff

    def test_get_stats_includes_retry_budget(self):
        """Test that stats include retry budget information."""
        limiter = RateLimiter(max_requests_per_hour=100, max_retries=5)
        limiter.acquire()
        limiter.record_rate_limit_error()

        stats = limiter.get_stats()
        assert stats["requests_made"] == 1
        assert stats["consecutive_failures"] == 1
        assert "retry_budget" in stats
        assert stats["retry_budget"]["total_retries_used"] == 1
        assert stats["retry_budget"]["remaining_retries"] == 4

    def test_reset_clears_retry_budget(self):
        """Test that reset clears retry budget."""
        limiter = RateLimiter(max_retries=3)

        limiter.record_rate_limit_error()
        limiter.record_rate_limit_error()
        limiter.acquire()

        assert limiter.retry_budget.get_remaining_retries() == 1
        assert len(limiter.request_times) == 1

        limiter.reset()

        assert limiter.retry_budget.get_remaining_retries() == 3
        assert len(limiter.request_times) == 0
        assert limiter._consecutive_failures == 0

    def test_thread_safety_with_retry_budget(self):
        """Test thread safety of retry budget."""
        import threading

        limiter = RateLimiter(max_retries=100)
        errors = []

        def record_errors():
            for _ in range(10):
                try:
                    limiter.record_rate_limit_error()
                except RetryBudgetExhausted:
                    errors.append(1)

        threads = [threading.Thread(target=record_errors) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Should have used exactly 50 retries (5 threads * 10 retries)
        # plus some may have raised exceptions
        total_used = limiter.retry_budget.get_retry_stats()["total_retries_used"]
        total_used_plus_errors = total_used + len(errors)
        assert total_used_plus_errors == 50
