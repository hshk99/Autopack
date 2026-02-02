"""Tests for ErrorHandler module with retry budget enforcement (IMP-RELIABILITY-003)."""

from unittest.mock import Mock, patch

import pytest
import requests

from autopack.research.gatherers.error_handler import ErrorHandler


class TestErrorHandler:
    """Test cases for ErrorHandler."""

    def test_initialization(self):
        """Test error handler initialization."""
        handler = ErrorHandler(max_retries=5, backoff_factor=3.0)
        assert handler.max_retries == 5
        assert handler.backoff_factor == 3.0

    def test_default_max_retries_is_3(self):
        """Test that default max_retries is 3 per IMP-RELIABILITY-003."""
        handler = ErrorHandler()
        assert handler.max_retries == 3

    def test_default_max_backoff_is_60s(self):
        """Test that default max_backoff is 60s per IMP-RELIABILITY-003."""
        handler = ErrorHandler()
        assert handler.max_backoff_seconds == 60.0

    def test_execute_with_retry_success(self):
        """Test successful execution without retries."""
        handler = ErrorHandler()

        def successful_func():
            return "success"

        result = handler.execute_with_retry(successful_func)
        assert result == "success"

    def test_execute_with_retry_eventual_success(self):
        """Test execution that succeeds after retries."""
        handler = ErrorHandler(max_retries=3)

        call_count = [0]

        def flaky_func():
            call_count[0] += 1
            if call_count[0] < 3:
                raise requests.exceptions.ConnectionError("Connection failed")
            return "success"

        with patch("time.sleep"):  # Mock sleep to speed up test
            result = handler.execute_with_retry(flaky_func)

        assert result == "success"
        assert call_count[0] == 3

    def test_execute_with_retry_all_failures(self):
        """Test execution that fails all retries."""
        handler = ErrorHandler(max_retries=2)

        def failing_func():
            raise requests.exceptions.ConnectionError("Connection failed")

        with patch("time.sleep"):  # Mock sleep to speed up test
            with pytest.raises(requests.exceptions.ConnectionError):
                handler.execute_with_retry(failing_func)

    def test_execute_with_retry_with_args(self):
        """Test execution with function arguments."""
        handler = ErrorHandler()

        def func_with_args(a, b, c=None):
            return f"{a}-{b}-{c}"

        result = handler.execute_with_retry(func_with_args, "x", "y", c="z")
        assert result == "x-y-z"

    def test_is_retryable_error_connection_error(self):
        """Test that connection errors are retryable."""
        handler = ErrorHandler()
        error = requests.exceptions.ConnectionError("Connection failed")
        assert handler.is_retryable_error(error) is True

    def test_is_retryable_error_timeout(self):
        """Test that timeout errors are retryable."""
        handler = ErrorHandler()
        error = requests.exceptions.Timeout("Request timed out")
        assert handler.is_retryable_error(error) is True

    def test_is_retryable_error_500(self):
        """Test that 500 errors are retryable."""
        handler = ErrorHandler()
        response = Mock()
        response.status_code = 500
        error = requests.exceptions.HTTPError(response=response)
        assert handler.is_retryable_error(error) is True

    def test_is_retryable_error_429(self):
        """Test that 429 (rate limit) errors are retryable."""
        handler = ErrorHandler()
        response = Mock()
        response.status_code = 429
        error = requests.exceptions.HTTPError(response=response)
        assert handler.is_retryable_error(error) is True

    def test_is_retryable_error_404(self):
        """Test that 404 errors are not retryable."""
        handler = ErrorHandler()
        response = Mock()
        response.status_code = 404
        error = requests.exceptions.HTTPError(response=response)
        assert handler.is_retryable_error(error) is False

    def test_is_retryable_error_non_request_exception(self):
        """Test that non-request exceptions are not retryable."""
        handler = ErrorHandler()
        error = ValueError("Invalid value")
        assert handler.is_retryable_error(error) is False

    def test_handle_error_http_error(self):
        """Test handling HTTP errors."""
        handler = ErrorHandler()
        response = Mock()
        response.status_code = 404
        error = requests.exceptions.HTTPError(response=response)

        # Should not raise, just log
        handler.handle_error(error, "test context")

    def test_handle_error_connection_error(self):
        """Test handling connection errors."""
        handler = ErrorHandler()
        error = requests.exceptions.ConnectionError("Connection failed")

        # Should not raise, just log
        handler.handle_error(error, "test context")

    def test_handle_error_timeout(self):
        """Test handling timeout errors."""
        handler = ErrorHandler()
        error = requests.exceptions.Timeout("Request timed out")

        # Should not raise, just log
        handler.handle_error(error, "test context")

    def test_handle_error_generic(self):
        """Test handling generic errors."""
        handler = ErrorHandler()
        error = ValueError("Invalid value")

        # Should not raise, just log
        handler.handle_error(error, "test context")

    def test_backoff_timing(self):
        """Test that backoff timing increases exponentially."""
        handler = ErrorHandler(max_retries=3, backoff_factor=2.0)

        call_count = [0]
        sleep_times = []

        def failing_func():
            call_count[0] += 1
            raise requests.exceptions.ConnectionError("Connection failed")

        def mock_sleep(seconds):
            sleep_times.append(seconds)

        with patch("time.sleep", side_effect=mock_sleep):
            with pytest.raises(requests.exceptions.ConnectionError):
                handler.execute_with_retry(failing_func)

        # Should have slept 3 times (for retries 1, 2, 3)
        assert len(sleep_times) == 3
        # Check exponential backoff: 2^0=1, 2^1=2, 2^2=4
        assert sleep_times[0] == 1.0
        assert sleep_times[1] == 2.0
        assert sleep_times[2] == 4.0


class TestRetryBudgetEnforcement:
    """Test cases for retry budget enforcement (IMP-RELIABILITY-003)."""

    def test_max_3_retries_per_agent(self):
        """Test that max 3 retries per agent is enforced by default."""
        handler = ErrorHandler()
        call_count = [0]

        def failing_func():
            call_count[0] += 1
            raise requests.exceptions.ConnectionError("Connection failed")

        with patch("time.sleep"):
            with pytest.raises(requests.exceptions.ConnectionError):
                handler.execute_with_retry(failing_func)

        # Should have called exactly 3 times (default max_retries)
        assert call_count[0] == 3

    def test_backoff_ceiling_60s(self):
        """Test that exponential backoff is capped at 60 seconds."""
        handler = ErrorHandler(
            max_retries=10,
            backoff_factor=3.0,
            base_backoff_seconds=1.0,
            max_backoff_seconds=60.0,
        )

        sleep_times = []

        def failing_func():
            raise requests.exceptions.ConnectionError("Connection failed")

        def mock_sleep(seconds):
            sleep_times.append(seconds)

        with patch("time.sleep", side_effect=mock_sleep):
            with pytest.raises(requests.exceptions.ConnectionError):
                handler.execute_with_retry(failing_func)

        # All sleep times should be <= 60 seconds
        for sleep_time in sleep_times:
            assert sleep_time <= 60.0

        # Later retries should be capped at 60s
        # With base=1.0 and factor=3.0: 1, 3, 9, 27, 60 (capped), 60, 60, 60, 60, 60
        assert sleep_times[-1] == 60.0

    def test_fallback_to_cached_results(self):
        """Test fallback to cached results when retries exhausted."""
        handler = ErrorHandler(max_retries=2, cache_fallback_enabled=True)

        call_count = [0]
        cache_key = "test_cache_key"

        # Pre-populate cache with a fallback value
        handler.set_cached_result(cache_key, "cached_result")

        def failing_func():
            call_count[0] += 1
            raise requests.exceptions.ConnectionError("Connection failed")

        with patch("time.sleep"):
            result = handler.execute_with_retry(failing_func, cache_key=cache_key)

        # Should return cached result after exhausting retries
        assert result == "cached_result"
        assert call_count[0] == 2

    def test_fallback_caches_successful_result(self):
        """Test that successful results are cached for future fallback."""
        handler = ErrorHandler(max_retries=3, cache_fallback_enabled=True)
        cache_key = "test_cache_key"

        def successful_func():
            return "fresh_result"

        # First call should cache the result
        result = handler.execute_with_retry(successful_func, cache_key=cache_key)
        assert result == "fresh_result"

        # Verify result is cached
        cached = handler.get_cached_result(cache_key)
        assert cached == "fresh_result"

    def test_no_fallback_when_disabled(self):
        """Test that fallback is not used when disabled."""
        handler = ErrorHandler(max_retries=2, cache_fallback_enabled=False)
        cache_key = "test_cache_key"

        # Pre-populate cache
        handler._cache[cache_key] = "cached_result"

        def failing_func():
            raise requests.exceptions.ConnectionError("Connection failed")

        with patch("time.sleep"):
            # Should still raise even with cache available (fallback disabled)
            with pytest.raises(requests.exceptions.ConnectionError):
                handler.execute_with_retry(failing_func, cache_key=cache_key)

    def test_logging_of_exhausted_retries(self, caplog):
        """Test that exhausted retries are logged per IMP-RELIABILITY-003."""
        import logging

        handler = ErrorHandler(max_retries=2)

        def failing_func():
            raise requests.exceptions.ConnectionError("Connection failed")

        with caplog.at_level(logging.ERROR):
            with patch("time.sleep"):
                with pytest.raises(requests.exceptions.ConnectionError):
                    handler.execute_with_retry(failing_func)

        # Check that exhaustion was logged
        assert any("RETRY_BUDGET_EXHAUSTED" in record.message for record in caplog.records)
        assert any("Total retries: 2/2" in record.message for record in caplog.records)

    def test_non_retryable_errors_not_retried(self):
        """Test that non-retryable errors are not retried."""
        handler = ErrorHandler(max_retries=5)
        call_count = [0]

        def failing_func():
            call_count[0] += 1
            raise ValueError("Non-retryable error")

        with pytest.raises(ValueError):
            handler.execute_with_retry(failing_func)

        # Should only be called once (no retries for non-retryable errors)
        assert call_count[0] == 1


class TestErrorHandlerCaching:
    """Test cases for error handler caching functionality."""

    def test_set_and_get_cached_result(self):
        """Test setting and getting cached results."""
        handler = ErrorHandler()

        handler.set_cached_result("key1", {"data": "value"})
        result = handler.get_cached_result("key1")
        assert result == {"data": "value"}

    def test_get_nonexistent_cache_returns_none(self):
        """Test that getting nonexistent cache key returns None."""
        handler = ErrorHandler()
        result = handler.get_cached_result("nonexistent")
        assert result is None

    def test_clear_cache(self):
        """Test clearing the cache."""
        handler = ErrorHandler()

        handler.set_cached_result("key1", "value1")
        handler.set_cached_result("key2", "value2")
        assert handler.get_cached_result("key1") is not None

        handler.clear_cache()
        assert handler.get_cached_result("key1") is None
        assert handler.get_cached_result("key2") is None

    def test_get_retry_stats(self):
        """Test getting retry statistics."""
        handler = ErrorHandler(
            max_retries=5,
            base_backoff_seconds=2.0,
            max_backoff_seconds=30.0,
            backoff_factor=3.0,
        )
        handler.set_cached_result("key1", "value1")

        stats = handler.get_retry_stats()
        assert stats["max_retries"] == 5
        assert stats["base_backoff_seconds"] == 2.0
        assert stats["max_backoff_seconds"] == 30.0
        assert stats["backoff_factor"] == 3.0
        assert stats["cache_fallback_enabled"] is True
        assert stats["cached_items"] == 1


class TestErrorHandlerBackwardCompatibility:
    """Test cases ensuring backward compatibility with existing code."""

    def test_handle_error_with_callable(self):
        """Test handle_error works with callable (new mode)."""
        handler = ErrorHandler()

        def successful_func():
            return "result"

        result = handler.handle_error(successful_func)
        assert result == "result"

    def test_handle_error_with_exception(self):
        """Test handle_error works with exception (legacy mode)."""
        handler = ErrorHandler()
        error = requests.exceptions.ConnectionError("Connection failed")

        # Should not raise, just log
        result = handler.handle_error(error, "test context")
        assert result is None

    def test_handle_error_returns_none_on_failure(self):
        """Test that handle_error returns None when function fails all retries."""
        handler = ErrorHandler(max_retries=2)

        def failing_func():
            raise requests.exceptions.ConnectionError("Connection failed")

        with patch("time.sleep"):
            result = handler.handle_error(failing_func)

        assert result is None

    def test_default_error_handler_instance(self):
        """Test that default error_handler instance exists."""
        from autopack.research.gatherers.error_handler import error_handler

        assert error_handler is not None
        assert isinstance(error_handler, ErrorHandler)
        assert error_handler.max_retries == 3  # Default per IMP-RELIABILITY-003
