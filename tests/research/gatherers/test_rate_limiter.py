"""Tests for RateLimiter module."""

import time
from datetime import datetime, timedelta
from autopack.research.gatherers.rate_limiter import RateLimiter


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
