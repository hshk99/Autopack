"""Tests for IMP-SEC-002: Rate limiter memory bounds with LRU cleanup."""

import time
from autopack.auth.rate_limiter import RateLimiter


class TestRateLimiterMemoryCap:
    """Tests for rate limiter memory cap enforcement."""

    def test_rate_limiter_enforces_memory_cap(self):
        """Verify rate limiter caps memory usage."""
        limiter = RateLimiter(max_tracked_ips=100)

        # Add 100 IPs (at cap)
        for i in range(100):
            limiter.check_rate_limit(f"192.168.1.{i}")

        assert len(limiter.requests) == 100

        # Add 101st IP - should trigger LRU cleanup
        limiter.check_rate_limit("192.168.2.1")

        # Should have removed ~20% (20 IPs) and added 1 new = 81 total
        assert len(limiter.requests) <= 81
        assert "192.168.2.1" in limiter.requests  # New IP should exist

    def test_lru_cleanup_removes_oldest_ips(self):
        """Verify LRU cleanup removes least recently accessed IPs."""
        limiter = RateLimiter(max_tracked_ips=10, max_requests=100)

        # Add 10 IPs with staggered access times
        for i in range(10):
            limiter.check_rate_limit(f"192.168.1.{i}")
            time.sleep(0.01)  # Ensure different access times

        # Access first 5 IPs again (make them "recent")
        for i in range(5):
            limiter.check_rate_limit(f"192.168.1.{i}")

        # Add 11th IP - should trigger cleanup of oldest (IPs 5-9)
        limiter.check_rate_limit("192.168.2.1")

        # Recently accessed IPs (0-4) should remain
        for i in range(5):
            assert f"192.168.1.{i}" in limiter.requests

        # Oldest unaccessed IPs should be removed
        assert len(limiter.requests) < 10  # Some old IPs removed

    def test_memory_cap_prevents_unbounded_growth(self):
        """Verify rate limiter never exceeds max_tracked_ips."""
        limiter = RateLimiter(max_tracked_ips=50, max_requests=100)

        # Simulate 1000 unique IPs hitting API
        for i in range(1000):
            limiter.check_rate_limit(f"10.0.{i // 256}.{i % 256}")

        # Should never exceed cap (with cleanup buffer)
        assert len(limiter.requests) <= 50

    def test_get_tracked_ip_count(self):
        """Verify get_tracked_ip_count returns accurate count."""
        limiter = RateLimiter(max_tracked_ips=100)

        assert limiter.get_tracked_ip_count() == 0

        limiter.check_rate_limit("1.1.1.1")
        assert limiter.get_tracked_ip_count() == 1

        limiter.check_rate_limit("2.2.2.2")
        assert limiter.get_tracked_ip_count() == 2

    def test_last_access_tracking(self):
        """Verify last access time is updated on each check."""
        limiter = RateLimiter(max_tracked_ips=100)

        limiter.check_rate_limit("1.1.1.1")
        first_access = limiter.last_access["1.1.1.1"]

        time.sleep(0.01)
        limiter.check_rate_limit("1.1.1.1")
        second_access = limiter.last_access["1.1.1.1"]

        assert second_access > first_access
