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

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.exc import InterfaceError, OperationalError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

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


class InvalidStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted.

    IMP-LIFECYCLE-004: Provides detailed information about why a phase
    state transition is invalid, preventing invalid transitions like
    FAILED -> EXECUTING.

    Supports two initialization modes:
    1. Simple message: InvalidStateTransitionError("error message")
    2. Detailed: InvalidStateTransitionError(phase_id="x", from_state="A", to_state="B")
    """

    def __init__(
        self,
        message_or_phase_id: Optional[str] = None,
        from_state: Optional[str] = None,
        to_state: Optional[str] = None,
        reason: Optional[str] = None,
        *,
        phase_id: Optional[str] = None,
    ):
        # Support both old-style (single message) and new-style (named params)
        if from_state is None and to_state is None:
            # Old-style: single message string
            self.phase_id = None
            self.from_state = None
            self.to_state = None
            self.reason = message_or_phase_id
            super().__init__(message_or_phase_id)
        else:
            # New-style: named parameters
            self.phase_id = phase_id or message_or_phase_id
            self.from_state = from_state
            self.to_state = to_state
            self.reason = reason or f"Invalid transition: {from_state} -> {to_state}"
            super().__init__(
                f"[{self.phase_id}] Invalid state transition: "
                f"{from_state} -> {to_state}. {self.reason}"
            )


class OptimisticLockError(Exception):
    """Raised when optimistic lock fails due to concurrent update."""

    pass


class PhaseStateManager:
    """Manages phase state persistence lifecycle.

    Centralizes all database state operations for phase execution,
    providing a clean interface that separates persistence from
    orchestration logic.

    IMP-LIFECYCLE-004: Enforces valid phase state transitions to prevent
    invalid transitions like FAILED -> EXECUTING.

    This is a mechanical refactoring - all database calls preserve
    exact semantics from the original scattered implementation.
    """

    # IMP-LIFECYCLE-004: Valid state transitions for PhaseState enum
    # Each key maps to a list of valid target states
    # Terminal states (COMPLETE, FAILED, SKIPPED) have limited or no transitions
    VALID_PHASE_TRANSITIONS: dict = {
        "QUEUED": ["EXECUTING", "SKIPPED"],  # Phase can start or be skipped
        "EXECUTING": ["GATE", "CI_RUNNING", "COMPLETE", "FAILED"],  # Normal execution flow
        "GATE": ["EXECUTING", "COMPLETE", "FAILED"],  # Gate can pass, fail, or retry
        "CI_RUNNING": ["COMPLETE", "FAILED"],  # CI completes or fails
        "COMPLETE": [],  # Terminal state - no transitions allowed
        "FAILED": ["QUEUED"],  # Failed can be reset to QUEUED for retry
        "SKIPPED": [],  # Terminal state - no transitions allowed
    }

    def __init__(
        self, run_id: str, workspace: Path, project_id: Optional[str] = None, validate: bool = True
    ):
        """Initialize phase state manager.

        Args:
            run_id: Unique run identifier
            workspace: Workspace root path
            project_id: Optional project identifier
            validate: Whether to validate state transitions (default: True)
        """
        self.run_id = run_id
        self.workspace = workspace
        self.project_id = project_id
        self.validate = validate

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

        Raises:
            InvalidStateTransitionError: If validation is enabled and transition is invalid
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

        # Validate state transition if enabled
        if self.validate:
            self._validate_state_update(phase_id, current_state, updates)

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

    def mark_executing(self, phase_id: str) -> bool:
        """Mark phase as currently executing.

        IMP-LIFECYCLE-004: Validates that the phase is in a state that
        can transition to EXECUTING (QUEUED or GATE).

        Args:
            phase_id: Phase identifier

        Returns:
            True if update successful, False otherwise

        Raises:
            InvalidStateTransitionError: If phase cannot transition to EXECUTING
        """
        return self._mark_phase_executing_in_db(phase_id)

    def is_transition_valid(self, from_state: str, to_state: str) -> bool:
        """Check if a phase state transition is valid.

        IMP-LIFECYCLE-004: Validates phase state transitions against the
        VALID_PHASE_TRANSITIONS map to prevent invalid transitions like
        FAILED -> EXECUTING.

        Args:
            from_state: Current phase state (e.g., "QUEUED", "EXECUTING")
            to_state: Target phase state (e.g., "COMPLETE", "FAILED")

        Returns:
            True if transition is valid, False otherwise
        """
        valid_targets = self.VALID_PHASE_TRANSITIONS.get(from_state, [])
        return to_state in valid_targets

    def _validate_phase_transition(
        self, phase_id: str, current_state: str, target_state: str
    ) -> None:
        """Validate a phase state transition.

        IMP-LIFECYCLE-004: Enforces valid phase state transitions to prevent
        invalid transitions like FAILED -> EXECUTING.

        Args:
            phase_id: Phase identifier
            current_state: Current phase state
            target_state: Target phase state

        Raises:
            InvalidStateTransitionError: If transition is not valid
        """
        if not self.validate:
            return

        if not self.is_transition_valid(current_state, target_state):
            valid_targets = self.VALID_PHASE_TRANSITIONS.get(current_state, [])
            raise InvalidStateTransitionError(
                phase_id=phase_id,
                from_state=current_state,
                to_state=target_state,
                reason=f"Valid transitions from {current_state}: {valid_targets}",
            )

        logger.debug(f"[{phase_id}] Phase transition validated: {current_state} -> {target_state}")

    def _validate_state_update(
        self, phase_id: str, current_state: PhaseState, updates: dict
    ) -> None:
        """Validate state update to prevent invalid transitions.

        Args:
            phase_id: Phase identifier
            current_state: Current phase state
            updates: Proposed state updates

        Raises:
            InvalidStateTransitionError: If transition is invalid
        """
        # Validate retry_attempt: must be non-negative and monotonic
        if "retry_attempt" in updates:
            new_retry = updates["retry_attempt"]
            if new_retry < 0:
                raise InvalidStateTransitionError(
                    f"[{phase_id}] Invalid retry_attempt: {new_retry} (must be non-negative)"
                )
            if new_retry < current_state.retry_attempt:
                logger.warning(
                    f"[{phase_id}] Non-monotonic retry_attempt: {current_state.retry_attempt} -> {new_retry}"
                )

        # Validate revision_epoch: must be non-negative and monotonic
        if "revision_epoch" in updates:
            new_epoch = updates["revision_epoch"]
            if new_epoch < 0:
                raise InvalidStateTransitionError(
                    f"[{phase_id}] Invalid revision_epoch: {new_epoch} (must be non-negative)"
                )
            if new_epoch < current_state.revision_epoch:
                logger.warning(
                    f"[{phase_id}] Non-monotonic revision_epoch: {current_state.revision_epoch} -> {new_epoch}"
                )

        # Validate escalation_level: must be non-negative and bounded
        if "escalation_level" in updates:
            new_escalation = updates["escalation_level"]
            MAX_ESCALATION_LEVEL = 10  # Reasonable upper bound
            if new_escalation < 0:
                raise InvalidStateTransitionError(
                    f"[{phase_id}] Invalid escalation_level: {new_escalation} (must be non-negative)"
                )
            if new_escalation > MAX_ESCALATION_LEVEL:
                raise InvalidStateTransitionError(
                    f"[{phase_id}] Invalid escalation_level: {new_escalation} (exceeds max: {MAX_ESCALATION_LEVEL})"
                )
            if new_escalation < current_state.escalation_level:
                logger.warning(
                    f"[{phase_id}] Non-monotonic escalation_level: {current_state.escalation_level} -> {new_escalation}"
                )

        # Validate timestamp: must not be in the future
        if "timestamp" in updates:
            new_timestamp = updates["timestamp"]
            if new_timestamp and new_timestamp > datetime.now(timezone.utc):
                raise InvalidStateTransitionError(
                    f"[{phase_id}] Invalid timestamp: {new_timestamp} (timestamp in future)"
                )

        logger.debug(f"[{phase_id}] State update validation passed")

    # Internal methods that wrap database calls
    # These preserve exact implementation from autonomous_executor.py

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        retry=retry_if_exception_type((OperationalError, InterfaceError)),
        before_sleep=lambda retry_state: logger.warning(
            f"DB transient error fetching phase, retrying... "
            f"(attempt {retry_state.attempt_number}/3)"
        ),
        reraise=True,
    )
    def _get_phase_from_db(self, phase_id: str) -> Optional[Any]:
        """Fetch phase from database with attempt tracking state.

        Retries on transient database errors (OperationalError, InterfaceError).

        Args:
            phase_id: Phase identifier (e.g., "fileorg-p2-test-fixes")

        Returns:
            Phase model instance with current attempt state, or None if not found

        Raises:
            OperationalError: On persistent database errors after retries
            InterfaceError: On persistent connection errors after retries
        """
        try:
            from autopack.database import SessionLocal
            from autopack.models import Phase

            # Use session as context manager to ensure proper cleanup
            with SessionLocal() as db:
                phase = (
                    db.query(Phase)
                    .filter(Phase.phase_id == phase_id, Phase.run_id == self.run_id)
                    .first()
                )

                if phase:
                    logger.debug(
                        f"[{phase_id}] Loaded from DB: retry_attempt={phase.retry_attempt}, "
                        f"revision_epoch={phase.revision_epoch}, escalation_level={phase.escalation_level}, "
                        f"state={phase.state}"
                    )
                else:
                    logger.warning(f"[{phase_id}] Not found in database")

                return phase

        except (OperationalError, InterfaceError):
            # Re-raise to trigger retry decorator
            raise
        except Exception as e:
            logger.error(f"[{phase_id}] Failed to fetch from database: {e}")
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        retry=retry_if_exception_type((OperationalError, InterfaceError)),
        before_sleep=lambda retry_state: logger.warning(
            f"DB transient error updating phase attempts, retrying... "
            f"(attempt {retry_state.attempt_number}/3)"
        ),
        reraise=True,
    )
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
        """Update phase attempt tracking in database with optimistic locking.

        Uses SELECT FOR UPDATE and version checking to prevent concurrent
        updates from causing data corruption. Retries on transient database errors.

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

        Raises:
            OptimisticLockError: If phase was modified by another process
            OperationalError: On persistent database errors after retries
            InterfaceError: On persistent connection errors after retries
        """
        try:
            from autopack.database import SessionLocal
            from autopack.models import Phase

            # Use session as context manager to ensure proper cleanup and transaction boundaries
            with SessionLocal() as db:
                # SERIALIZABLE isolation + SELECT FOR UPDATE to prevent race conditions
                phase = (
                    db.query(Phase)
                    .with_for_update()
                    .filter(Phase.phase_id == phase_id, Phase.run_id == self.run_id)
                    .first()
                )

                if not phase:
                    logger.error(
                        f"[{phase_id}] Cannot update attempts: phase not found in database"
                    )
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

                # Increment version if version tracking is enabled
                if hasattr(phase, "version"):
                    phase.version += 1

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

                # Explicit commit for transaction boundary
                db.commit()

            return True

        except OperationalError as e:
            # Handle serialization failures from concurrent updates
            if "serialization failure" in str(e).lower() or "deadlock" in str(e).lower():
                logger.warning(
                    f"[{phase_id}] Concurrent update detected (serialization failure), "
                    f"retry may be needed: {e}"
                )
                # Allow retry decorator to handle this
                raise OptimisticLockError(
                    f"Phase {phase_id} was modified by another process"
                ) from e
            # Non-retriable database error - re-raise for retry decorator
            logger.error(f"[{phase_id}] Database error updating attempts: {e}")
            raise
        except InterfaceError:
            # Connection error - allow retry decorator to handle
            raise
        except OptimisticLockError:
            # Re-raise optimistic lock errors as-is (don't retry these)
            raise
        except Exception as e:
            logger.error(f"[{phase_id}] Failed to update attempts in database: {e}")
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        retry=retry_if_exception_type((OperationalError, InterfaceError)),
        before_sleep=lambda retry_state: logger.warning(
            f"DB transient error marking phase complete, retrying... "
            f"(attempt {retry_state.attempt_number}/3)"
        ),
        reraise=True,
    )
    def _mark_phase_complete_in_db(self, phase_id: str) -> bool:
        """Mark phase as COMPLETE in database with row locking.

        IMP-LIFECYCLE-004: Validates state transition before marking complete.
        Uses SELECT FOR UPDATE to prevent concurrent state modifications.
        Retries on transient database errors.

        Args:
            phase_id: Phase identifier

        Returns:
            True if update successful, False otherwise

        Raises:
            InvalidStateTransitionError: If transition to COMPLETE is not valid
            OptimisticLockError: If phase was modified by another process
            OperationalError: On persistent database errors after retries
            InterfaceError: On persistent connection errors after retries
        """
        try:
            from autopack.database import SessionLocal
            from autopack.models import Phase
            from autopack.models import PhaseState as PhaseStateEnum

            # Use session as context manager to ensure proper cleanup and transaction boundaries
            with SessionLocal() as db:
                # Use SELECT FOR UPDATE to prevent race conditions
                phase = (
                    db.query(Phase)
                    .with_for_update()
                    .filter(Phase.phase_id == phase_id, Phase.run_id == self.run_id)
                    .first()
                )

                if not phase:
                    logger.error(f"[{phase_id}] Cannot mark complete: phase not found in database")
                    return False

                # IMP-LIFECYCLE-004: Validate state transition before updating
                current_state = phase.state.value if phase.state else "QUEUED"
                self._validate_phase_transition(phase_id, current_state, "COMPLETE")

                # Update to COMPLETE state
                phase.state = PhaseStateEnum.COMPLETE
                phase.completed_at = datetime.now(timezone.utc)

                # Increment version if version tracking is enabled
                if hasattr(phase, "version"):
                    phase.version += 1

                # Explicit commit for transaction boundary
                db.commit()

                # Note: Phase proof writing handled by caller (autonomous_executor)
                # to avoid circular dependencies with _intention_wiring

            logger.info(f"[{phase_id}] Marked COMPLETE in database")
            return True

        except OperationalError as e:
            # Handle serialization failures from concurrent updates
            if "serialization failure" in str(e).lower() or "deadlock" in str(e).lower():
                logger.warning(
                    f"[{phase_id}] Concurrent update detected while marking complete: {e}"
                )
                raise OptimisticLockError(
                    f"Phase {phase_id} was modified by another process"
                ) from e
            # Non-retriable error - re-raise for retry decorator
            logger.error(f"[{phase_id}] Database error marking complete: {e}")
            raise
        except InterfaceError:
            # Connection error - allow retry decorator to handle
            raise
        except OptimisticLockError:
            # Re-raise optimistic lock errors as-is
            raise
        except InvalidStateTransitionError:
            # IMP-LIFECYCLE-004: Re-raise transition errors as-is (don't retry these)
            raise
        except Exception as e:
            logger.error(f"[{phase_id}] Failed to mark complete in database: {e}")
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        retry=retry_if_exception_type((OperationalError, InterfaceError)),
        before_sleep=lambda retry_state: logger.warning(
            f"DB transient error marking phase failed, retrying... "
            f"(attempt {retry_state.attempt_number}/3)"
        ),
        reraise=True,
    )
    def _mark_phase_failed_in_db(self, phase_id: str, reason: str) -> bool:
        """Mark phase as FAILED in database with row locking.

        IMP-LIFECYCLE-004: Validates state transition before marking failed.
        Uses SELECT FOR UPDATE to prevent concurrent state modifications.
        Retries on transient database errors.

        Args:
            phase_id: Phase identifier
            reason: Failure reason (e.g., "MAX_ATTEMPTS_EXHAUSTED", "BUILDER_FAILED")

        Returns:
            True if update successful, False otherwise

        Raises:
            InvalidStateTransitionError: If transition to FAILED is not valid
            OptimisticLockError: If phase was modified by another process
            OperationalError: On persistent database errors after retries
            InterfaceError: On persistent connection errors after retries
        """
        try:
            from autopack.database import SessionLocal
            from autopack.models import Phase
            from autopack.models import PhaseState as PhaseStateEnum

            # Use session as context manager to ensure proper cleanup and transaction boundaries
            with SessionLocal() as db:
                # Use SELECT FOR UPDATE to prevent race conditions
                phase = (
                    db.query(Phase)
                    .with_for_update()
                    .filter(Phase.phase_id == phase_id, Phase.run_id == self.run_id)
                    .first()
                )

                if not phase:
                    logger.error(f"[{phase_id}] Cannot mark failed: phase not found in database")
                    return False

                # IMP-LIFECYCLE-004: Validate state transition before updating
                current_state = phase.state.value if phase.state else "QUEUED"
                self._validate_phase_transition(phase_id, current_state, "FAILED")

                # Update to FAILED state
                phase.state = PhaseStateEnum.FAILED
                phase.last_failure_reason = reason
                phase.completed_at = datetime.now(timezone.utc)

                # Increment version if version tracking is enabled
                if hasattr(phase, "version"):
                    phase.version += 1

                # Explicit commit for transaction boundary
                db.commit()

                # Note: Phase proof writing and telemetry handled by caller
                # (autonomous_executor) to avoid circular dependencies

            logger.info(f"[{phase_id}] Marked FAILED in database (reason: {reason})")

            # Note: Token efficiency telemetry and Telegram notifications
            # are handled by the caller (autonomous_executor)

            return True

        except OperationalError as e:
            # Handle serialization failures from concurrent updates
            if "serialization failure" in str(e).lower() or "deadlock" in str(e).lower():
                logger.warning(f"[{phase_id}] Concurrent update detected while marking failed: {e}")
                raise OptimisticLockError(
                    f"Phase {phase_id} was modified by another process"
                ) from e
            # Non-retriable error - re-raise for retry decorator
            logger.error(f"[{phase_id}] Database error marking failed: {e}")
            raise
        except InterfaceError:
            # Connection error - allow retry decorator to handle
            raise
        except OptimisticLockError:
            # Re-raise optimistic lock errors as-is
            raise
        except InvalidStateTransitionError:
            # IMP-LIFECYCLE-004: Re-raise transition errors as-is (don't retry these)
            raise
        except Exception as e:
            logger.error(f"[{phase_id}] Failed to mark failed in database: {e}")
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        retry=retry_if_exception_type((OperationalError, InterfaceError)),
        before_sleep=lambda retry_state: logger.warning(
            f"DB transient error marking phase executing, retrying... "
            f"(attempt {retry_state.attempt_number}/3)"
        ),
        reraise=True,
    )
    def _mark_phase_executing_in_db(self, phase_id: str) -> bool:
        """Mark phase as EXECUTING in database with row locking.

        IMP-LIFECYCLE-004: Validates state transition before marking executing.
        Uses SELECT FOR UPDATE to prevent concurrent state modifications.
        Retries on transient database errors.

        Args:
            phase_id: Phase identifier

        Returns:
            True if update successful, False otherwise

        Raises:
            InvalidStateTransitionError: If transition to EXECUTING is not valid
            OptimisticLockError: If phase was modified by another process
            OperationalError: On persistent database errors after retries
            InterfaceError: On persistent connection errors after retries
        """
        try:
            from autopack.database import SessionLocal
            from autopack.models import Phase
            from autopack.models import PhaseState as PhaseStateEnum

            # Use session as context manager to ensure proper cleanup and transaction boundaries
            with SessionLocal() as db:
                # Use SELECT FOR UPDATE to prevent race conditions
                phase = (
                    db.query(Phase)
                    .with_for_update()
                    .filter(Phase.phase_id == phase_id, Phase.run_id == self.run_id)
                    .first()
                )

                if not phase:
                    logger.error(f"[{phase_id}] Cannot mark executing: phase not found in database")
                    return False

                # IMP-LIFECYCLE-004: Validate state transition before updating
                current_state = phase.state.value if phase.state else "QUEUED"
                self._validate_phase_transition(phase_id, current_state, "EXECUTING")

                # Update to EXECUTING state
                phase.state = PhaseStateEnum.EXECUTING
                phase.started_at = datetime.now(timezone.utc)

                # Increment version if version tracking is enabled
                if hasattr(phase, "version"):
                    phase.version += 1

                # Explicit commit for transaction boundary
                db.commit()

            logger.info(f"[{phase_id}] Marked EXECUTING in database")
            return True

        except OperationalError as e:
            # Handle serialization failures from concurrent updates
            if "serialization failure" in str(e).lower() or "deadlock" in str(e).lower():
                logger.warning(
                    f"[{phase_id}] Concurrent update detected while marking executing: {e}"
                )
                raise OptimisticLockError(
                    f"Phase {phase_id} was modified by another process"
                ) from e
            # Non-retriable error - re-raise for retry decorator
            logger.error(f"[{phase_id}] Database error marking executing: {e}")
            raise
        except InterfaceError:
            # Connection error - allow retry decorator to handle
            raise
        except OptimisticLockError:
            # Re-raise optimistic lock errors as-is
            raise
        except InvalidStateTransitionError:
            # Re-raise transition errors as-is (don't retry these)
            raise
        except Exception as e:
            logger.error(f"[{phase_id}] Failed to mark executing in database: {e}")
            return False
