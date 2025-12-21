import pytest
from src.autopack.research.gatherers.error_handler import ErrorHandler

def test_handle_error_success():
    handler = ErrorHandler(max_retries=3)

    def successful_function():
        return "Success"

    result = handler.handle_error(successful_function)
    assert result == "Success"

def test_handle_error_failure():
    handler = ErrorHandler(max_retries=3)

    def failing_function():
        raise ValueError("Failure")

    result = handler.handle_error(failing_function)
    assert result is None

def test_handle_error_partial_failure():
    handler = ErrorHandler(max_retries=3)
    attempts = 0

    def partially_failing_function():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ValueError("Failure")
        return "Recovered"

    result = handler.handle_error(partially_failing_function)
    assert result == "Recovered"
