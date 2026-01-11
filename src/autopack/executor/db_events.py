"""Best-effort DB/telemetry operations for AutonomousExecutor.

Goal:
- Extract DB reads/writes that must never block execution into a testable module.
- All functions use best-effort semantics: must never raise, failures are logged.

Design:
- Import DB models inside functions to avoid import-time coupling.
- All operations wrapped in try/except with pass or logging.
- Functions return success/failure indicators where appropriate.

Non-goal (this module):
- Critical DB operations that should fail loudly.
- Complex transaction handling.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _get_session_local() -> Any:
    """Get SessionLocal factory from autopack.database.

    Isolated for testability - can be monkeypatched in tests.
    """
    from autopack.database import SessionLocal

    return SessionLocal()


def _get_token_budget_escalation_event_model() -> Any:
    """Get TokenBudgetEscalationEvent model from autopack.models.

    Isolated for testability - can be monkeypatched in tests.
    Imported inside function to avoid import-time DB coupling.
    """
    from autopack.models import TokenBudgetEscalationEvent

    return TokenBudgetEscalationEvent


def maybe_apply_retry_max_tokens_from_db(
    *,
    run_id: str,
    phase: dict,
    attempt_index: int,
) -> None:
    """Best-effort: read TokenBudgetEscalationEvent and set phase['_escalated_tokens'] if present.

    BUILD-129 Phase 3 P10: Apply persisted escalate-once budget on the *next* attempt.
    We persist P10 decisions into token_budget_escalation_events with attempt_index=1-based
    attempt that triggered. When retry_attempt increments from 0->1, we should apply the
    retry budget for that next attempt.

    Must never raise - failures are silently ignored to avoid blocking execution.

    Args:
        run_id: The run ID to query for.
        phase: Phase dict to mutate with '_escalated_tokens' if event found.
        attempt_index: Current 0-based attempt number.
    """
    try:
        phase_id = phase.get("phase_id")
        TokenBudgetEscalationEvent = _get_token_budget_escalation_event_model()
        db = _get_session_local()

        try:
            evt = (
                db.query(TokenBudgetEscalationEvent)
                .filter(
                    TokenBudgetEscalationEvent.run_id == run_id,
                    TokenBudgetEscalationEvent.phase_id == phase_id,
                )
                .order_by(TokenBudgetEscalationEvent.timestamp.desc())
                .first()
            )
        finally:
            try:
                db.close()
            except Exception:
                pass

        if evt and (attempt_index == int(evt.attempt_index or 0)) and evt.retry_max_tokens:
            # Attach a transient override used by execute_builder_phase(max_tokens=...)
            phase["_escalated_tokens"] = int(evt.retry_max_tokens)

    except Exception:
        # Best-effort only; do not block execution if DB telemetry isn't available.
        pass


def try_record_token_budget_escalation_event(
    *,
    run_id: str,
    phase_id: str,
    attempt_index: int,
    reason: str,
    was_truncated: bool,
    completion_tokens_used: Optional[int] = None,
    retry_max_tokens: Optional[int] = None,
    output_utilization: Optional[float] = None,
    escalation_factor: Optional[float] = None,
    base_value: Optional[int] = None,
    base_source: Optional[str] = None,
    selected_budget: Optional[int] = None,
    actual_max_tokens: Optional[int] = None,
    tokens_used: Optional[int] = None,
) -> bool:
    """Best-effort telemetry write for token budget escalation events.

    Records an escalation event to the database for P10 telemetry tracking.
    Must never raise - failures are logged and return False.

    Args:
        run_id: The run ID.
        phase_id: The phase ID.
        attempt_index: The attempt index (1-based, the attempt that triggered escalation).
        reason: Reason for escalation ("truncation" or "utilization").
        was_truncated: Whether the response was truncated.
        completion_tokens_used: Number of completion tokens used.
        retry_max_tokens: The new max_tokens budget for retry.
        output_utilization: Output token utilization ratio (0.0-1.0).
        escalation_factor: Factor used to escalate (e.g., 1.25).
        base_value: Original max_tokens value before escalation.
        base_source: Source of the base value (e.g., "default", "config").
        selected_budget: Budget that was selected for this attempt.
        actual_max_tokens: Actual max_tokens used in the request.
        tokens_used: Actual tokens consumed in the response.

    Returns:
        True if write succeeded, False otherwise.
    """
    try:
        TokenBudgetEscalationEvent = _get_token_budget_escalation_event_model()
        session = _get_session_local()

        try:
            evt = TokenBudgetEscalationEvent(
                run_id=run_id,
                phase_id=phase_id,
                attempt_index=attempt_index,
                reason=reason,
                was_truncated=was_truncated,
                completion_tokens_used=completion_tokens_used,
                retry_max_tokens=retry_max_tokens,
                output_utilization=output_utilization,
                escalation_factor=escalation_factor,
                base_value=base_value,
                base_source=base_source,
                selected_budget=selected_budget,
                actual_max_tokens=actual_max_tokens,
                tokens_used=tokens_used,
            )
            session.add(evt)
            session.commit()
            return True
        finally:
            try:
                session.close()
            except Exception:
                pass

    except Exception as e:
        logger.debug(f"[BUILD-129:P10] Failed to write DB escalation telemetry: {e}")
        return False
