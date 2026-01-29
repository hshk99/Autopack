"""Stale Phase Detection and Reset Handler.

Extracted from autonomous_executor.py as part of IMP-MAINT-001.
Handles detection and automatic reset of stale EXECUTING phases.

Phase 1.6-1.7: Identifies phases stuck in EXECUTING state for >10 minutes
and automatically resets them to QUEUED for retry. This prevents the system
from getting permanently stuck on failed infrastructure issues.

IMP-REL-001: Uses thread-safe locking with double-check pattern to prevent
race conditions when multiple executors attempt concurrent reset.
"""

import logging
import threading
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from autopack.debug_journal import log_error, log_fix

if TYPE_CHECKING:
    from autopack.supervisor import SupervisorApiClient

logger = logging.getLogger(__name__)


class StalePhaseHandler:
    """Handles detection and reset of stale EXECUTING phases.

    This class is responsible for:
    - Detecting phases stuck in EXECUTING state beyond threshold
    - Thread-safe reset with double-check pattern
    - Observability tracking for reset counts
    - Audit logging for all reset operations

    IMP-REL-001: Thread-safe operations prevent race conditions.
    """

    def __init__(
        self,
        run_id: str,
        api_client: "SupervisorApiClient",
        update_status_fn: Callable[[str, str], None],
        get_run_status_fn: Callable[[], Dict[str, Any]],
        stale_threshold_minutes: int = 10,
    ):
        """Initialize stale phase handler.

        Args:
            run_id: Unique run identifier
            api_client: Supervisor API client for phase updates
            update_status_fn: Callback to update phase status
            get_run_status_fn: Callback to fetch current run status
            stale_threshold_minutes: Minutes before phase considered stale
        """
        self.run_id = run_id
        self.api_client = api_client
        self._update_phase_status = update_status_fn
        self._get_run_status = get_run_status_fn
        self.stale_threshold = timedelta(minutes=stale_threshold_minutes)

        # IMP-REL-001: Thread-safe lock for stale phase reset operations
        self._phase_reset_lock = threading.Lock()
        # Track phase reset counts for observability
        self._phase_reset_counts: Dict[str, int] = {}

    def detect_and_reset_stale_phases(self, run_data: Dict[str, Any]) -> int:
        """Detect and auto-reset stale EXECUTING phases.

        Identifies phases stuck in EXECUTING state for longer than
        stale_threshold and automatically resets them to QUEUED for retry.

        Args:
            run_data: Run data from API with tiers and phases

        Returns:
            Number of phases reset
        """
        tiers = run_data.get("tiers", [])
        now = datetime.now()
        reset_count = 0

        for tier in tiers:
            phases = tier.get("phases", [])

            for phase in phases:
                if phase.get("state") != "EXECUTING":
                    continue

                phase_id = phase.get("phase_id")

                # Check if phase has a last_updated timestamp
                last_updated_str = phase.get("updated_at") or phase.get("last_updated")

                if not last_updated_str:
                    # IMP-REL-001: Use locked reset for phases without timestamp
                    if self._reset_with_lock(
                        phase_id=phase_id,
                        reason="no timestamp",
                        time_stale_seconds=None,
                    ):
                        reset_count += 1
                    continue

                try:
                    # Parse timestamp (assuming ISO format)
                    last_updated = datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))

                    # Make timezone-naive for comparison (assuming UTC)
                    if last_updated.tzinfo:
                        last_updated = last_updated.replace(tzinfo=None)

                    time_stale = now - last_updated

                    if time_stale > self.stale_threshold:
                        # IMP-REL-001: Use locked reset with double-check pattern
                        if self._reset_with_lock(
                            phase_id=phase_id,
                            reason="stale",
                            time_stale_seconds=time_stale.total_seconds(),
                            last_updated_str=last_updated_str,
                        ):
                            reset_count += 1

                except Exception as e:
                    logger.warning(
                        f"[{phase_id}] Failed to parse timestamp '{last_updated_str}': {e}"
                    )

        return reset_count

    def _reset_with_lock(
        self,
        phase_id: str,
        reason: str,
        time_stale_seconds: Optional[float] = None,
        last_updated_str: Optional[str] = None,
    ) -> bool:
        """Reset a stale phase with proper locking and double-check pattern.

        Uses thread-safe locking to prevent race conditions when multiple
        executors attempt to reset the same stale phase concurrently.

        Args:
            phase_id: The phase ID to reset
            reason: Reason for reset (e.g., "stale", "no timestamp")
            time_stale_seconds: How long the phase has been stale (for logging)
            last_updated_str: Original timestamp string (for logging)

        Returns:
            True if phase was reset, False if already reset by another executor
        """
        with self._phase_reset_lock:
            # Double-check: Re-fetch run data to verify phase is still stale
            # Another executor may have already reset it while we waited for lock
            try:
                current_run_data = self._get_run_status()
            except Exception as e:
                logger.warning(
                    f"[{phase_id}] IMP-REL-001: Failed to re-fetch run status for "
                    f"double-check: {e}. Proceeding with reset."
                )
                current_run_data = None

            # If we successfully fetched current state, verify phase is still EXECUTING
            if current_run_data:
                phase_still_executing = False
                for tier in current_run_data.get("tiers", []):
                    for phase in tier.get("phases", []):
                        if phase.get("phase_id") == phase_id:
                            if phase.get("state") == "EXECUTING":
                                phase_still_executing = True
                            break

                if not phase_still_executing:
                    logger.info(
                        f"[{phase_id}] IMP-REL-001: Phase no longer EXECUTING "
                        f"(already reset by another executor). Skipping reset."
                    )
                    return False

            # Log stale phase detection
            if reason == "no timestamp":
                logger.warning(
                    f"[{phase_id}] EXECUTING phase has no timestamp - assuming stale and resetting"
                )
            else:
                logger.warning(f"[{phase_id}] STALE PHASE DETECTED")
                logger.warning("  State: EXECUTING")
                if last_updated_str:
                    logger.warning(f"  Last Updated: {last_updated_str}")
                if time_stale_seconds is not None:
                    logger.warning(f"  Time Stale: {time_stale_seconds:.0f} seconds")
                logger.warning("  Auto-resetting to QUEUED...")

            # Phase 1.7: Auto-reset EXECUTING → QUEUED
            try:
                self._update_phase_status(phase_id, "QUEUED")

                # IMP-REL-001: Track reset count for observability
                reset_count = self._phase_reset_counts.get(phase_id, 0) + 1
                self._phase_reset_counts[phase_id] = reset_count

                logger.info(
                    f"[{phase_id}] Successfully reset to QUEUED (reset_count={reset_count})"
                )

                # Log to DEBUG_JOURNAL.md for tracking
                stale_desc = (
                    f"after {time_stale_seconds:.0f}s of inactivity"
                    if time_stale_seconds is not None
                    else "due to missing timestamp"
                )
                log_fix(
                    error_signature=f"Stale Phase Auto-Reset: {phase_id}",
                    fix_description=(
                        f"Automatically reset phase from EXECUTING to QUEUED {stale_desc} "
                        f"(reset_count={reset_count})"
                    ),
                    files_changed=["autonomous_executor.py"],
                    test_run_id=self.run_id,
                    result="success",
                )

                return True

            except Exception as e:
                logger.error(f"[{phase_id}] Failed to reset stale phase: {e}")

                # Log stale phase reset failure
                log_error(
                    error_signature="Stale phase reset failure",
                    symptom=f"Phase {phase_id}: {type(e).__name__}: {str(e)}",
                    run_id=self.run_id,
                    phase_id=phase_id,
                    suspected_cause="Failed to call API to reset stuck phase",
                    priority="HIGH",
                )
                return False

    def get_reset_count(self, phase_id: str) -> int:
        """Get the number of times a phase has been reset.

        Args:
            phase_id: Phase identifier

        Returns:
            Number of resets for this phase
        """
        return self._phase_reset_counts.get(phase_id, 0)

    def get_all_reset_counts(self) -> Dict[str, int]:
        """Get all phase reset counts.

        Returns:
            Dictionary mapping phase_id to reset count
        """
        return dict(self._phase_reset_counts)
