"""Tests for ErrorHandler module."""

import pytest
import requests
from unittest.mock import Mock, patch
from autopack.research.gatherers.error_handler import ErrorHandler


class TestErrorHandler:
    """Test cases for ErrorHandler."""

    def test_initialization(self):
        """Test error handler initialization."""
        handler = ErrorHandler(max_retries=5, backoff_factor=3.0)
        assert handler.max_retries == 5
        assert handler.backoff_factor == 3.0

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
