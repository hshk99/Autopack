#!/usr/bin/env python3
"""Handle connection errors with OCR retry logic and centralized logging.

This module provides utilities for handling connection errors that may occur
during OCR (Optical Character Recognition) operations, with integrated
telemetry logging for persistent analysis.
"""

import sys
import time
from typing import Any, Callable, Dict, Optional, TypeVar

# Add src to path for imports
sys.path.insert(0, "src")

from telemetry.event_logger import get_logger

T = TypeVar("T")


class ConnectionErrorHandler:
    """Handle connection errors with retry logic and telemetry logging."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        slot: Optional[int] = None,
    ):
        """Initialize the connection error handler.

        Args:
            max_retries: Maximum number of retry attempts.
            base_delay: Initial delay between retries in seconds.
            max_delay: Maximum delay between retries in seconds.
            slot: Optional slot number for telemetry tracking.
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.slot = slot
        self.logger = get_logger()

    def handle_with_retry(
        self,
        operation: Callable[[], T],
        operation_name: str = "ocr_operation",
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[T]:
        """Execute an operation with retry logic on connection errors.

        Args:
            operation: The callable operation to execute.
            operation_name: Name of the operation for logging.
            context: Additional context for logging.

        Returns:
            The result of the operation, or None if all retries failed.
        """
        context = context or {}
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                result = operation()

                # Log successful recovery if this wasn't the first attempt
                if attempt > 0:
                    self.logger.log_connection_error(
                        error_type="recovery",
                        details={
                            "operation": operation_name,
                            "attempt": attempt + 1,
                            "recovered": True,
                            **context,
                        },
                        slot=self.slot,
                    )

                return result

            except (ConnectionError, TimeoutError, OSError) as e:
                last_error = e
                delay = min(
                    self.base_delay * (2**attempt),
                    self.max_delay,
                )

                # Log the connection error
                self.logger.log_connection_error(
                    error_type=type(e).__name__,
                    details={
                        "operation": operation_name,
                        "attempt": attempt + 1,
                        "max_retries": self.max_retries,
                        "error_message": str(e),
                        "next_delay": delay if attempt < self.max_retries - 1 else None,
                        **context,
                    },
                    slot=self.slot,
                )

                if attempt < self.max_retries - 1:
                    print(
                        f"Connection error on {operation_name} "
                        f"(attempt {attempt + 1}/{self.max_retries}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                else:
                    print(
                        f"Connection error on {operation_name} "
                        f"(attempt {attempt + 1}/{self.max_retries}): {e}. "
                        "Max retries exceeded."
                    )

        # Log final failure
        self.logger.log_connection_error(
            error_type="max_retries_exceeded",
            details={
                "operation": operation_name,
                "total_attempts": self.max_retries,
                "final_error": str(last_error) if last_error else None,
                **context,
            },
            slot=self.slot,
        )

        return None

    def log_error(
        self,
        error_type: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a connection error event.

        Args:
            error_type: Type of error (e.g., 'timeout', 'refused', 'reset').
            message: Error message.
            context: Additional context.
        """
        self.logger.log_connection_error(
            error_type=error_type,
            details={
                "message": message,
                **(context or {}),
            },
            slot=self.slot,
        )


def handle_ocr_connection_error(
    error: Exception,
    operation: str = "ocr_request",
    slot: Optional[int] = None,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """Log an OCR connection error to the centralized telemetry system.

    Args:
        error: The exception that occurred.
        operation: Name of the OCR operation.
        slot: Optional slot number.
        context: Additional context for logging.
    """
    logger = get_logger()
    logger.log_connection_error(
        error_type=type(error).__name__,
        details={
            "operation": operation,
            "error_message": str(error),
            **(context or {}),
        },
        slot=slot,
    )


if __name__ == "__main__":
    # Example usage
    handler = ConnectionErrorHandler(max_retries=3, slot=1)

    def example_operation() -> str:
        # Simulated operation that might fail
        return "success"

    result = handler.handle_with_retry(
        example_operation,
        operation_name="example_ocr",
        context={"source": "test"},
    )
    print(f"Result: {result}")
