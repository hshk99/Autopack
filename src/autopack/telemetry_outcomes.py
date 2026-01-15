"""
ROAD-A: Phase Outcome Telemetry

Tracks per-phase outcomes with stop reasons and stuck decision rationales.
Implements invariant enforcement: no duplicate events, stable IDs, bounded payloads.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class PhaseOutcome(str, Enum):
    """Phase execution outcomes"""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    STUCK = "STUCK"


class PhaseOutcomeRecorder:
    """Record phase outcomes with stop reasons and rationales."""

    def __init__(self, db_session=None):
        """Initialize outcome recorder.

        Args:
            db_session: SQLAlchemy session for database operations
        """
        self.db_session = db_session
        self.recorded_phase_ids = set()  # Track phase_ids to prevent duplicates

    def record_outcome(
        self,
        phase_id: str,
        outcome: PhaseOutcome,
        stop_reason: Optional[str] = None,
        stuck_decision_rationale: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record a phase outcome with invariant enforcement.

        Args:
            phase_id: Stable phase identifier
            outcome: Phase outcome (SUCCESS, FAILED, TIMEOUT, STUCK)
            stop_reason: Why phase stopped (e.g., max_tokens, retry_limit, user_abort)
            stuck_decision_rationale: Rationale for stuck decision if applicable
            metadata: Additional telemetry metadata

        Returns:
            Event record with validation results

        Raises:
            ValueError: If invariants are violated (duplicate, unstable ID, payload too large)
        """
        # Invariant 1: Stable phase_id
        if not phase_id or len(phase_id) >= 256:
            raise ValueError(
                f"Invalid phase_id: must be non-empty and < 256 chars. Got: {phase_id}"
            )

        # Invariant 2: No duplicate events (same phase_id)
        if phase_id in self.recorded_phase_ids:
            raise ValueError(f"Duplicate event detected: {phase_id} already recorded")

        self.recorded_phase_ids.add(phase_id)

        # Invariant 3: Bounded payload sizes
        if stuck_decision_rationale and len(stuck_decision_rationale) > 10000:
            raise ValueError(f"Rationale too large: {len(stuck_decision_rationale)} > 10000 chars")

        if stop_reason and len(stop_reason) > 256:
            raise ValueError(f"Stop reason too large: {len(stop_reason)} > 256 chars")

        # Create event ID
        event_id = f"{phase_id}:{outcome.value}:{datetime.now(timezone.utc).isoformat()}"

        # Build event record
        event = {
            "event_id": event_id,
            "phase_id": phase_id,
            "outcome": outcome.value,
            "stop_reason": stop_reason,
            "stuck_decision_rationale": stuck_decision_rationale,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }

        logger.info(f"Recorded phase outcome: {phase_id} -> {outcome.value}")
        return event

    def record_failure(
        self,
        phase_id: str,
        stop_reason: str,
        decision_rationale: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record a phase failure with stop reason.

        Args:
            phase_id: Phase identifier
            stop_reason: Why phase failed (e.g., builder_crash, auditor_timeout, budget_exceeded)
            decision_rationale: Detailed rationale for failure decision
            metadata: Additional telemetry

        Returns:
            Event record
        """
        return self.record_outcome(
            phase_id=phase_id,
            outcome=PhaseOutcome.FAILED,
            stop_reason=stop_reason,
            stuck_decision_rationale=decision_rationale,
            metadata=metadata,
        )

    def record_success(
        self,
        phase_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record a successful phase completion.

        Args:
            phase_id: Phase identifier
            metadata: Additional telemetry (e.g., duration, tokens used)

        Returns:
            Event record
        """
        return self.record_outcome(
            phase_id=phase_id,
            outcome=PhaseOutcome.SUCCESS,
            stop_reason="completed",
            metadata=metadata,
        )

    def record_stuck(
        self,
        phase_id: str,
        decision_rationale: str,
        stop_reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record a phase stuck with decision rationale.

        Args:
            phase_id: Phase identifier
            decision_rationale: Rationale for stuck decision
            stop_reason: Optional stop reason (e.g., max_revisions, unrecoverable_state)
            metadata: Additional telemetry

        Returns:
            Event record
        """
        return self.record_outcome(
            phase_id=phase_id,
            outcome=PhaseOutcome.STUCK,
            stop_reason=stop_reason or "stuck_decision",
            stuck_decision_rationale=decision_rationale,
            metadata=metadata,
        )


# Global recorder instance
_recorder = None


def get_recorder(db_session=None) -> PhaseOutcomeRecorder:
    """Get or create global outcome recorder."""
    global _recorder
    if _recorder is None:
        _recorder = PhaseOutcomeRecorder(db_session)
    return _recorder


def record_phase_outcome(
    phase_id: str,
    outcome: PhaseOutcome,
    stop_reason: Optional[str] = None,
    stuck_decision_rationale: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience function to record outcome using global recorder."""
    return get_recorder().record_outcome(
        phase_id=phase_id,
        outcome=outcome,
        stop_reason=stop_reason,
        stuck_decision_rationale=stuck_decision_rationale,
        metadata=metadata,
    )
