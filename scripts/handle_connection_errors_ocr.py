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

from decision_logging.decision_logger import get_decision_logger
from logging_config import setup_logging
from telemetry.event_logger import get_logger

# Module-level logger for persistent logging to rotating files
ocr_logger = setup_logging("ocr_handler")

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
        self.decision_logger = get_decision_logger()

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
                    # Log retry decision (IMP-LOG-001)
                    self.decision_logger.create_and_log_decision(
                        decision_type="retry",
                        context={
                            "operation": operation_name,
                            "attempt": attempt + 1,
                            "max_retries": self.max_retries,
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                            "slot": self.slot,
                            **context,
                        },
                        options_considered=["retry_with_backoff", "fail_immediately", "escalate"],
                        chosen_option="retry_with_backoff",
                        reasoning=f"Attempt {attempt + 1} of {self.max_retries} failed with {type(e).__name__}, retrying after {delay:.1f}s exponential backoff",
                    )
                    ocr_logger.warning(
                        "Connection error on %s (attempt %d/%d): %s. " "Retrying in %.1fs...",
                        operation_name,
                        attempt + 1,
                        self.max_retries,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    # Log escalation decision (IMP-LOG-001)
                    self.decision_logger.create_and_log_decision(
                        decision_type="escalation",
                        context={
                            "operation": operation_name,
                            "total_attempts": self.max_retries,
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                            "slot": self.slot,
                            **context,
                        },
                        options_considered=[
                            "retry_again",
                            "escalate_to_failure",
                            "partial_recovery",
                        ],
                        chosen_option="escalate_to_failure",
                        reasoning=f"Max retries ({self.max_retries}) exceeded for {operation_name}, escalating as permanent failure",
                    )
                    ocr_logger.error(
                        "Connection error on %s (attempt %d/%d): %s. " "Max retries exceeded.",
                        operation_name,
                        attempt + 1,
                        self.max_retries,
                        e,
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


def generate_escalation_report(
    slot_id: int,
    level: int,
    error_message: str,
    phase_id: str | None = None,
    imp_id: str | None = None,
    error_history: list[dict] | None = None,
    ocr_screenshot_path: str | None = None,
) -> dict:
    """Generate context-enriched escalation report.

    Args:
        slot_id: The slot experiencing the issue
        level: Escalation level (1-4)
        error_message: Primary error description
        phase_id: Current phase ID being executed
        imp_id: Improvement ID being implemented
        error_history: List of recent errors for this slot
        ocr_screenshot_path: Path to OCR capture if available

    Returns:
        Enriched escalation report with full context
    """
    from datetime import datetime

    report = {
        "timestamp": datetime.now().isoformat(),
        "slot_id": slot_id,
        "level": level,
        "message": error_message,
        "context": {
            "phase_id": phase_id,
            "imp_id": imp_id,
            "error_count": len(error_history) if error_history else 0,
            "recent_errors": (error_history or [])[-5:],  # Last 5 errors
            "ocr_screenshot": ocr_screenshot_path,
        },
        "analysis": {
            "pattern_match": None,  # To be filled by analysis engine
            "suggested_root_cause": None,
            "recommended_action": None,
        },
    }

    # Try to get analysis insights if available
    try:
        from telemetry.unified_event_log import UnifiedEventLog

        event_log = UnifiedEventLog("telemetry_events.json")
        events = event_log.query({"slot_id": slot_id})

        # Find matching patterns from recent events
        if events:
            error_types: dict[str, int] = {}
            for event in events[-20:]:  # Look at last 20 events
                event_type = getattr(event, "event_type", None)
                if event_type:
                    error_types[event_type] = error_types.get(event_type, 0) + 1

            # Identify most common error pattern
            if error_types:
                most_common = max(error_types.items(), key=lambda x: x[1])
                if most_common[1] >= 3:  # Pattern threshold
                    report["analysis"]["pattern_match"] = most_common[0]
                    report["analysis"]["suggested_root_cause"] = (
                        f"Recurring {most_common[0]} events detected "
                        f"({most_common[1]} occurrences)"
                    )
                    report["analysis"][
                        "recommended_action"
                    ] = f"Investigate {most_common[0]} pattern for slot_{slot_id}"
    except ImportError:
        pass  # Telemetry module not available
    except Exception:
        pass  # Analysis failed, continue without insights

    return report


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
    ocr_logger.info("Result: %s", result)
