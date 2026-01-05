import time
from threading import Lock


class RateLimiter:
    """Rate limiter using token bucket algorithm."""

    def __init__(self, max_requests=10, time_window=60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.tokens = max_requests
        self.lock = Lock()
        self.last_request_time = time.time()

    def wait(self):
        """Waits until a request can be made."""
        with self.lock:
            current_time = time.time()
            elapsed = current_time - self.last_request_time
            self.last_request_time = current_time
            self.tokens += elapsed * (self.max_requests / self.time_window)
            if self.tokens > self.max_requests:
                self.tokens = self.max_requests
            if self.tokens < 1:
                sleep_time = (1 - self.tokens) * (self.time_window / self.max_requests)
                time.sleep(sleep_time)
                self.tokens = 0
            else:
                self.tokens -= 1


rate_limiter = RateLimiter()


def limited_function():
    rate_limiter.wait()
    print("Function executed")


limited_function()
