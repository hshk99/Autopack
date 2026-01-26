"""Centralized event logging for Autopack automation."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class EventLogger:
    """Append-only event logger with structured JSON output.

    Provides centralized logging for slot operations, PR events, CI failures,
    nudges, and state transitions with persistent JSONL storage.
    """

    def __init__(self, log_dir: Optional[str] = None):
        """Initialize the event logger.

        Args:
            log_dir: Directory for log files. Defaults to AUTOPACK_LOG_DIR
                    environment variable or ./logs.
        """
        self.log_dir = Path(log_dir or os.environ.get("AUTOPACK_LOG_DIR", "./logs"))
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.current_log = self.log_dir / f"events_{datetime.now().strftime('%Y%m%d')}.jsonl"

    def log(
        self,
        event_type: str,
        data: Dict[str, Any],
        slot: Optional[int] = None,
    ) -> None:
        """Log an event to the JSONL file.

        Args:
            event_type: Type of event (e.g., 'pr_merged', 'ci_failure',
                       'slot_filled', 'nudge_sent', 'state_transition').
            data: Event-specific data dictionary.
            slot: Optional slot number associated with the event.
        """
        event = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "slot": slot,
            "data": data,
        }
        with open(self.current_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def log_pr_event(
        self,
        action: str,
        pr_number: int,
        details: Dict[str, Any],
        slot: Optional[int] = None,
    ) -> None:
        """Log a PR-related event.

        Args:
            action: PR action (e.g., 'merged', 'opened', 'ci_failed').
            pr_number: The PR number.
            details: Additional PR details.
            slot: Optional slot number.
        """
        self.log(
            event_type=f"pr_{action}",
            data={"pr_number": pr_number, **details},
            slot=slot,
        )

    def log_slot_operation(
        self,
        operation: str,
        slot: int,
        details: Dict[str, Any],
    ) -> None:
        """Log a slot operation event.

        Args:
            operation: Slot operation (e.g., 'filled', 'cleared', 'assigned').
            slot: Slot number.
            details: Additional operation details.
        """
        self.log(
            event_type=f"slot_{operation}",
            data=details,
            slot=slot,
        )

    def log_ci_failure(
        self,
        run_id: str,
        failure_category: str,
        details: Dict[str, Any],
        slot: Optional[int] = None,
    ) -> None:
        """Log a CI failure event.

        Args:
            run_id: CI run identifier.
            failure_category: Category of failure (e.g., 'flaky_test',
                            'code_failure', 'unrelated_ci').
            details: Additional failure details.
            slot: Optional slot number.
        """
        self.log(
            event_type="ci_failure",
            data={"run_id": run_id, "category": failure_category, **details},
            slot=slot,
        )

    def log_nudge(
        self,
        template_id: str,
        slot: int,
        context: Dict[str, Any],
    ) -> None:
        """Log a nudge event.

        Args:
            template_id: Nudge template identifier.
            slot: Slot number receiving the nudge.
            context: Context for the nudge.
        """
        self.log(
            event_type="nudge_sent",
            data={"template_id": template_id, "context": context},
            slot=slot,
        )

    def log_state_transition(
        self,
        from_state: str,
        to_state: str,
        details: Dict[str, Any],
        slot: Optional[int] = None,
    ) -> None:
        """Log a state transition event.

        Args:
            from_state: Previous state.
            to_state: New state.
            details: Additional transition details.
            slot: Optional slot number.
        """
        self.log(
            event_type="state_transition",
            data={"from_state": from_state, "to_state": to_state, **details},
            slot=slot,
        )

    def log_connection_error(
        self,
        error_type: str,
        details: Dict[str, Any],
        slot: Optional[int] = None,
    ) -> None:
        """Log a connection error event.

        Args:
            error_type: Type of connection error.
            details: Error details including message and context.
            slot: Optional slot number.
        """
        self.log(
            event_type="connection_error",
            data={"error_type": error_type, **details},
            slot=slot,
        )


# Global logger instance for convenience
_default_logger: Optional[EventLogger] = None


def get_logger(log_dir: Optional[str] = None) -> EventLogger:
    """Get or create the default EventLogger instance.

    Args:
        log_dir: Optional directory override for log files.

    Returns:
        The EventLogger instance.
    """
    global _default_logger
    if _default_logger is None or log_dir is not None:
        _default_logger = EventLogger(log_dir)
    return _default_logger
