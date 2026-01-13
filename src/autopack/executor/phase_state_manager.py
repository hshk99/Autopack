"""Unified phase state persistence for executor.

Extracted from autonomous_executor.py as part of PR-EXE-9.
Provides clean interface for phase state lifecycle management.

This module centralizes all database state operations that were scattered
throughout execute_phase(), making the state lifecycle easier to understand
and test in isolation.

State tracked:
- retry_attempt: Monotonic retry counter (for hints and escalation)
- revision_epoch: Replan counter (increments on Doctor replan)
- escalation_level: Model escalation level (0=base, 1=escalated, etc.)
- last_failure_reason: Failure status from most recent attempt
- last_attempt_timestamp: Timestamp of last attempt
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class PhaseState:
    """Phase execution state from database."""

    retry_attempt: int
    revision_epoch: int
    escalation_level: int
    last_failure_reason: Optional[str] = None
    last_attempt_timestamp: Optional[datetime] = None


@dataclass
class StateUpdateRequest:
    """Request to update phase state."""

    increment_retry: bool = False
    increment_epoch: bool = False
    increment_escalation: bool = False
    set_retry: Optional[int] = None
    set_epoch: Optional[int] = None
    set_escalation: Optional[int] = None
    failure_reason: Optional[str] = None
    timestamp: Optional[datetime] = None


class PhaseStateManager:
    """Manages phase state persistence lifecycle.

    Centralizes all database state operations for phase execution,
    providing a clean interface that separates persistence from
    orchestration logic.

    This is a mechanical refactoring - all database calls preserve
    exact semantics from the original scattered implementation.
    """

    def __init__(self, run_id: str, workspace: Path, project_id: Optional[str] = None):
        """Initialize phase state manager.

        Args:
            run_id: Unique run identifier
            workspace: Workspace root path
            project_id: Optional project identifier
        """
        self.run_id = run_id
        self.workspace = workspace
        self.project_id = project_id

    def load_or_create_default(self, phase_id: str) -> PhaseState:
        """Load phase state from DB or create defaults.

        Args:
            phase_id: Phase identifier

        Returns:
            PhaseState with retry/epoch/escalation counters
        """
        phase_db = self._get_phase_from_db(phase_id)
        if not phase_db:
            logger.debug(f"[{phase_id}] No DB state found, using defaults")
            return PhaseState(
                retry_attempt=0,
                revision_epoch=0,
                escalation_level=0,
            )

        return PhaseState(
            retry_attempt=getattr(phase_db, "retry_attempt", 0),
            revision_epoch=getattr(phase_db, "revision_epoch", 0),
            escalation_level=getattr(phase_db, "escalation_level", 0),
            last_failure_reason=getattr(phase_db, "last_failure_reason", None),
            last_attempt_timestamp=getattr(phase_db, "last_attempt_timestamp", None),
        )

    def update(self, phase_id: str, request: StateUpdateRequest) -> bool:
        """Update phase state based on request.

        Args:
            phase_id: Phase identifier
            request: State update request

        Returns:
            True if update successful, False otherwise
        """
        # Load current state to calculate new values
        current_state = self.load_or_create_default(phase_id)

        updates = {}

        # Handle increments
        if request.increment_retry:
            updates["retry_attempt"] = current_state.retry_attempt + 1
        if request.increment_epoch:
            updates["revision_epoch"] = current_state.revision_epoch + 1
        if request.increment_escalation:
            updates["escalation_level"] = current_state.escalation_level + 1

        # Handle explicit sets
        if request.set_retry is not None:
            updates["retry_attempt"] = request.set_retry
        if request.set_epoch is not None:
            updates["revision_epoch"] = request.set_epoch
        if request.set_escalation is not None:
            updates["escalation_level"] = request.set_escalation

        # Handle failure reason and timestamp
        if request.failure_reason is not None:
            updates["last_failure_reason"] = request.failure_reason
        if request.timestamp is not None:
            updates["timestamp"] = request.timestamp

        # Only call DB if we have updates
        if not updates:
            logger.debug(f"[{phase_id}] No state updates to apply")
            return True

        return self._update_phase_attempts_in_db(phase_id, **updates)

    def mark_complete(self, phase_id: str) -> bool:
        """Mark phase as successfully completed.

        Args:
            phase_id: Phase identifier

        Returns:
            True if update successful, False otherwise
        """
        return self._mark_phase_complete_in_db(phase_id)

    def mark_failed(self, phase_id: str, reason: str) -> bool:
        """Mark phase as permanently failed.

        Args:
            phase_id: Phase identifier
            reason: Failure reason (e.g., "MAX_ATTEMPTS_EXHAUSTED")

        Returns:
            True if update successful, False otherwise
        """
        return self._mark_phase_failed_in_db(phase_id, reason)

    # Internal methods that wrap database calls
    # These preserve exact implementation from autonomous_executor.py

    def _get_phase_from_db(self, phase_id: str) -> Optional[Any]:
        """Fetch phase from database with attempt tracking state.

        Args:
            phase_id: Phase identifier (e.g., "fileorg-p2-test-fixes")

        Returns:
            Phase model instance with current attempt state, or None if not found
        """
        try:
            from autopack.database import SessionLocal
            from autopack.models import Phase

            db = SessionLocal()
            try:
                phase = (
                    db.query(Phase)
                    .filter(Phase.phase_id == phase_id, Phase.run_id == self.run_id)
                    .first()
                )
            finally:
                try:
                    db.close()
                except Exception:
                    pass

            if phase:
                logger.debug(
                    f"[{phase_id}] Loaded from DB: retry_attempt={phase.retry_attempt}, "
                    f"revision_epoch={phase.revision_epoch}, escalation_level={phase.escalation_level}, "
                    f"state={phase.state}"
                )
            else:
                logger.warning(f"[{phase_id}] Not found in database")

            return phase

        except Exception as e:
            logger.error(f"[{phase_id}] Failed to fetch from database: {e}")
            return None

    def _update_phase_attempts_in_db(
        self,
        phase_id: str,
        attempts_used: int = None,
        last_failure_reason: Optional[str] = None,
        timestamp: Optional[Any] = None,
        retry_attempt: Optional[int] = None,
        revision_epoch: Optional[int] = None,
        escalation_level: Optional[int] = None,
    ) -> bool:
        """Update phase attempt tracking in database.

        Args:
            phase_id: Phase identifier
            attempts_used: DEPRECATED - use retry_attempt instead
            last_failure_reason: Failure status from most recent attempt
            timestamp: Timestamp of last attempt (defaults to now)
            retry_attempt: Monotonic retry counter
            revision_epoch: Replan counter
            escalation_level: Model escalation level

        Returns:
            True if update successful, False otherwise
        """
        try:
            from autopack.database import SessionLocal
            from autopack.models import Phase

            db = SessionLocal()
            try:
                phase = (
                    db.query(Phase)
                    .filter(Phase.phase_id == phase_id, Phase.run_id == self.run_id)
                    .first()
                )

                if not phase:
                    logger.error(f"[{phase_id}] Cannot update attempts: phase not found in database")
                    return False

                # Update attempt tracking (backwards compatibility)
                if attempts_used is not None and hasattr(phase, "attempts_used"):
                    phase.attempts_used = attempts_used

                # Update decoupled counters
                if retry_attempt is not None:
                    phase.retry_attempt = retry_attempt
                if revision_epoch is not None:
                    phase.revision_epoch = revision_epoch
                if escalation_level is not None:
                    phase.escalation_level = escalation_level

                if last_failure_reason:
                    phase.last_failure_reason = last_failure_reason
                if hasattr(phase, "last_attempt_timestamp"):
                    phase.last_attempt_timestamp = timestamp or datetime.now(timezone.utc)

                # Log while the instance is still bound to a live Session
                if (
                    retry_attempt is not None
                    or revision_epoch is not None
                    or escalation_level is not None
                ):
                    logger.info(
                        f"[{phase_id}] Updated counters in DB: "
                        f"retry={phase.retry_attempt}, epoch={phase.revision_epoch}, "
                        f"escalation={phase.escalation_level} "
                        f"(reason: {last_failure_reason or 'N/A'})"
                    )
                else:
                    logger.info(
                        f"[{phase_id}] Updated attempts in DB: retry={retry_attempt}, "
                        f"epoch={revision_epoch}, escalation={escalation_level} "
                        f"(reason: {last_failure_reason or 'N/A'})"
                    )

                db.commit()
            finally:
                try:
                    db.close()
                except Exception:
                    pass

            return True

        except Exception as e:
            logger.error(f"[{phase_id}] Failed to update attempts in database: {e}")
            return False

    def _mark_phase_complete_in_db(self, phase_id: str) -> bool:
        """Mark phase as COMPLETE in database.

        Args:
            phase_id: Phase identifier

        Returns:
            True if update successful, False otherwise
        """
        try:
            from autopack.database import SessionLocal
            from autopack.models import Phase, PhaseState as PhaseStateEnum

            db = SessionLocal()
            try:
                phase = (
                    db.query(Phase)
                    .filter(Phase.phase_id == phase_id, Phase.run_id == self.run_id)
                    .first()
                )

                if not phase:
                    logger.error(f"[{phase_id}] Cannot mark complete: phase not found in database")
                    return False

                # Update to COMPLETE state
                phase.state = PhaseStateEnum.COMPLETE
                phase.completed_at = datetime.now(timezone.utc)

                db.commit()

                # Note: Phase proof writing handled by caller (autonomous_executor)
                # to avoid circular dependencies with _intention_wiring

            finally:
                try:
                    db.close()
                except Exception:
                    pass

            logger.info(f"[{phase_id}] Marked COMPLETE in database")
            return True

        except Exception as e:
            logger.error(f"[{phase_id}] Failed to mark complete in database: {e}")
            return False

    def _mark_phase_failed_in_db(self, phase_id: str, reason: str) -> bool:
        """Mark phase as FAILED in database.

        Args:
            phase_id: Phase identifier
            reason: Failure reason (e.g., "MAX_ATTEMPTS_EXHAUSTED", "BUILDER_FAILED")

        Returns:
            True if update successful, False otherwise
        """
        try:
            from autopack.database import SessionLocal
            from autopack.models import Phase, PhaseState as PhaseStateEnum

            db = SessionLocal()
            try:
                phase = (
                    db.query(Phase)
                    .filter(Phase.phase_id == phase_id, Phase.run_id == self.run_id)
                    .first()
                )

                if not phase:
                    logger.error(f"[{phase_id}] Cannot mark failed: phase not found in database")
                    return False

                # Update to FAILED state
                phase.state = PhaseStateEnum.FAILED
                phase.last_failure_reason = reason
                phase.completed_at = datetime.now(timezone.utc)

                db.commit()

                # Note: Phase proof writing and telemetry handled by caller
                # (autonomous_executor) to avoid circular dependencies

            finally:
                try:
                    db.close()
                except Exception:
                    pass

            logger.info(f"[{phase_id}] Marked FAILED in database (reason: {reason})")

            # Note: Token efficiency telemetry and Telegram notifications
            # are handled by the caller (autonomous_executor)

            return True

        except Exception as e:
            logger.error(f"[{phase_id}] Failed to mark failed in database: {e}")
            return False
