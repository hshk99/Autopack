"""Phase state management for AutonomousExecutor.

Extracted from autonomous_executor.py as part of IMP-MAINT-006.
Handles phase status transitions, outcome tracking, and state management.

This module provides:
- Phase status transitions via API
- Status to outcome mapping for escalation tracking
- Force-mark phase status for recovery scenarios
- Run-level health budget tracking

IMP-REL-003: Thread-safe phase state updates with locking:
- Add _state_lock (threading.Lock) to protect health budget counters
- All counter increments and reads are protected by the lock
"""

import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

if TYPE_CHECKING:
    from autopack.supervisor import SupervisorApiClient

logger = logging.getLogger(__name__)


class ExecutorStateManager:
    """Manages phase state transitions for the autonomous executor.

    Centralizes phase status updates and state tracking that enables
    proper run lifecycle management and failure recovery.

    This class handles:
    - Phase status updates via supervisor API
    - Mapping phase statuses to escalation outcomes
    - Force-marking phase status for recovery
    - Run-level health budget tracking

    IMP-REL-003: Thread-safe health budget counter management with locking.
    """

    # Status to outcome mapping for escalation tracking
    STATUS_TO_OUTCOME_MAP = {
        "FAILED": "auditor_reject",
        "PATCH_FAILED": "patch_apply_error",
        "BLOCKED": "auditor_reject",
        "CI_FAILED": "ci_fail",
        # BUILD-049 / DBG-014: deliverables validation failures are tactical path-correction issues
        "DELIVERABLES_VALIDATION_FAILED": "deliverables_validation_failed",
    }

    def __init__(
        self,
        run_id: str,
        api_client: "SupervisorApiClient",
        write_run_summary_callback: Optional[Callable[[], None]] = None,
    ):
        """Initialize state manager.

        Args:
            run_id: Unique run identifier
            api_client: SupervisorApiClient for status updates
            write_run_summary_callback: Optional callback to write run summary on terminal states
        """
        self.run_id = run_id
        self.api_client = api_client
        self._write_run_summary_callback = write_run_summary_callback

        # IMP-REL-003: Thread-safe health budget tracking with lock
        self._state_lock = threading.Lock()

        # Health budget tracking
        self._http_500_count = 0
        self._patch_failure_count = 0
        self._total_failures = 0

    def update_phase_status(self, phase_id: str, status: str) -> bool:
        """Update phase status via API.

        Uses the /runs/{run_id}/phases/{phase_id}/update_status endpoint.

        Args:
            phase_id: Phase ID
            status: New status (QUEUED, EXECUTING, GATE, CI_RUNNING, COMPLETE, FAILED, SKIPPED)

        Returns:
            True if update succeeded, False otherwise
        """
        try:
            # The API only accepts models.PhaseState values; "BLOCKED" is a quality-gate
            # outcome, not a phase state. Represent blocked states as FAILED.
            if status == "BLOCKED":
                status = "FAILED"

            self.api_client.update_phase_status(self.run_id, phase_id, status, timeout=30)
            logger.info(f"Updated phase {phase_id} status to {status}")

            # Best-effort run_summary rewrite when a phase reaches a terminal state
            if status in ("COMPLETE", "FAILED", "SKIPPED"):
                if self._write_run_summary_callback:
                    try:
                        self._write_run_summary_callback()
                    except Exception as e:
                        logger.debug(f"Failed to write run summary: {e}")

            return True

        except Exception as e:
            logger.warning(f"Failed to update phase {phase_id} status: {e}")
            return False

    def status_to_outcome(self, status: str) -> str:
        """Map phase status to outcome for escalation tracking.

        Args:
            status: Phase status string

        Returns:
            Outcome string for escalation tracking
        """
        return self.STATUS_TO_OUTCOME_MAP.get(status, "auditor_reject")

    def force_mark_phase_failed(self, phase_id: str, max_retries: int = 3) -> bool:
        """Force mark a phase as FAILED directly via API.

        This bypasses normal flow when API is returning errors, ensuring
        we can progress past stuck phases.

        Args:
            phase_id: Phase ID to mark as failed
            max_retries: Maximum retry attempts

        Returns:
            True if successfully updated, False otherwise
        """
        for attempt in range(max_retries):
            success = self.update_phase_status(phase_id, "FAILED")
            if success:
                logger.info(
                    f"[Self-Troubleshoot] Force-marked phase {phase_id} as FAILED "
                    f"via API (attempt {attempt + 1})"
                )
                return True
            else:
                logger.warning(f"[Self-Troubleshoot] API update attempt {attempt + 1} failed")
                time.sleep(1)

        logger.error(
            f"[Self-Troubleshoot] All attempts to mark phase {phase_id} as FAILED have failed"
        )
        return False

    def get_health_budget(self) -> Dict[str, int]:
        """Get current health budget as a single source of truth.

        Per GPT_RESPONSE8 Section 2.2: Single health budget source.

        IMP-REL-003: Thread-safe read of health budget counters.

        Returns:
            Dict with health budget counters
        """
        with self._state_lock:
            return {
                "http_500": self._http_500_count,
                "patch_failures": self._patch_failure_count,
                "total_failures": self._total_failures,
            }

    def increment_http_500_count(self) -> int:
        """Increment HTTP 500 error count.

        IMP-REL-003: Thread-safe counter increment with locking.

        Returns:
            New count value
        """
        with self._state_lock:
            self._http_500_count += 1
            return self._http_500_count

    def increment_patch_failure_count(self) -> int:
        """Increment patch failure count.

        IMP-REL-003: Thread-safe counter increment with locking.

        Returns:
            New count value
        """
        with self._state_lock:
            self._patch_failure_count += 1
            return self._patch_failure_count

    def increment_total_failures(self) -> int:
        """Increment total failure count.

        IMP-REL-003: Thread-safe counter increment with locking.

        Returns:
            New count value
        """
        with self._state_lock:
            self._total_failures += 1
            return self._total_failures

    def set_counters(
        self,
        http_500_count: Optional[int] = None,
        patch_failure_count: Optional[int] = None,
        total_failures: Optional[int] = None,
    ) -> None:
        """Set health budget counters.

        IMP-REL-003: Thread-safe counter updates with locking.

        Args:
            http_500_count: Optional new HTTP 500 count
            patch_failure_count: Optional new patch failure count
            total_failures: Optional new total failures count
        """
        with self._state_lock:
            if http_500_count is not None:
                self._http_500_count = http_500_count
            if patch_failure_count is not None:
                self._patch_failure_count = patch_failure_count
            if total_failures is not None:
                self._total_failures = total_failures


# Convenience functions for backward compatibility with executor methods


def update_phase_status(
    executor: Any,
    phase_id: str,
    status: str,
) -> bool:
    """Update phase status via API.

    Wrapper for backward compatibility with existing executor code.

    Args:
        executor: AutonomousExecutor instance
        phase_id: Phase ID
        status: New status

    Returns:
        True if update succeeded
    """
    try:
        # The API only accepts models.PhaseState values; "BLOCKED" is a quality-gate
        # outcome, not a phase state.
        if status == "BLOCKED":
            status = "FAILED"

        executor.api_client.update_phase_status(executor.run_id, phase_id, status, timeout=30)
        logger.info(f"Updated phase {phase_id} status to {status}")

        # Best-effort run_summary rewrite when a phase reaches a terminal state
        if status in ("COMPLETE", "FAILED", "SKIPPED"):
            if hasattr(executor, "_best_effort_write_run_summary"):
                try:
                    executor._best_effort_write_run_summary()
                except Exception:
                    pass

        return True

    except Exception as e:
        logger.warning(f"Failed to update phase {phase_id} status: {e}")
        return False


def status_to_outcome(status: str) -> str:
    """Map phase status to outcome for escalation tracking.

    Wrapper for backward compatibility with existing executor code.

    Args:
        status: Phase status string

    Returns:
        Outcome string for escalation tracking
    """
    return ExecutorStateManager.STATUS_TO_OUTCOME_MAP.get(status, "auditor_reject")


def force_mark_phase_failed(
    executor: Any,
    phase_id: str,
    max_retries: int = 3,
) -> bool:
    """Force mark a phase as FAILED directly via API.

    Wrapper for backward compatibility with existing executor code.

    Args:
        executor: AutonomousExecutor instance
        phase_id: Phase ID to mark as failed
        max_retries: Maximum retry attempts

    Returns:
        True if successfully updated, False otherwise
    """
    for attempt in range(max_retries):
        success = update_phase_status(executor, phase_id, "FAILED")
        if success:
            logger.info(
                f"[Self-Troubleshoot] Force-marked phase {phase_id} as FAILED "
                f"via API (attempt {attempt + 1})"
            )
            return True
        else:
            logger.warning(f"[Self-Troubleshoot] API update attempt {attempt + 1} failed")
            time.sleep(1)

    logger.error(f"[Self-Troubleshoot] All attempts to mark phase {phase_id} as FAILED have failed")
    return False
