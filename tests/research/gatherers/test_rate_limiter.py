import pytest
import time
from src.autopack.research.gatherers.rate_limiter import RateLimiter

def test_rate_limiter_allows_requests():
    limiter = RateLimiter(max_requests=2, time_window=1)

    start_time = time.time()
    limiter.wait()
    limiter.wait()
    end_time = time.time()

    assert end_time - start_time < 1  # Should not wait

def test_rate_limiter_blocks_requests():
    limiter = RateLimiter(max_requests=2, time_window=1)

    limiter.wait()
    limiter.wait()
    start_time = time.time()
    limiter.wait()  # This should block
    end_time = time.time()

    assert end_time - start_time >= 0.5  # Should wait at least 0.5 seconds

def test_rate_limiter_replenishes_tokens():
    limiter = RateLimiter(max_requests=2, time_window=1)

    limiter.wait()
    time.sleep(1)  # Wait for tokens to replenish
    start_time = time.time()
    limiter.wait()  # Should not block
    end_time = time.time()

    assert end_time - start_time < 0.1  # Should not wait
