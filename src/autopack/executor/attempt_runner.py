"""Single attempt execution wrapper for AutonomousExecutor.

Goal:
- Extract the "call attempt with error recovery" pattern into a testable module.
- Keep it intentionally boring - don't restructure semantics.

Design:
- This module wraps the error_recovery.execute_with_retry call around
  _execute_phase_with_recovery.
- The executor remains responsible for all state updates, learning hints, etc.
- attempt_runner only handles the mechanics of running a single attempt.

Non-goal (this module):
- DB state updates
- Success/failure telemetry recording
- Diagnostics invocation
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AttemptRunResult:
    """Immutable result from running a single attempt.

    Attributes:
        success: Whether the attempt succeeded (phase completed).
        status: Status string from the attempt (e.g., "COMPLETE", "FAILED", "TOKEN_ESCALATION").
    """

    success: bool
    status: str


def run_single_attempt_with_recovery(
    *,
    executor: Any,
    phase: dict,
    attempt_index: int,
    allowed_paths: list[str] | None,
    memory_context: str | None = None,
    context_reduction_factor: float | None = None,
    model_downgrade: str | None = None,
) -> AttemptRunResult:
    """Run a single phase attempt with error recovery.

    This function wraps executor._execute_phase_with_recovery in the
    error_recovery.execute_with_retry mechanism for transient error handling.

    Args:
        executor: AutonomousExecutor instance (or compatible duck-typed object).
                  Must have `error_recovery` and `_execute_phase_with_recovery`.
        phase: Phase data dictionary with at least "phase_id".
        attempt_index: Current 0-based attempt number.
        allowed_paths: List of allowed file paths for scope enforcement, or None.
        memory_context: Optional memory context to inject (IMP-ARCH-002).
        context_reduction_factor: Optional factor to reduce context by (IMP-TEL-005).
        model_downgrade: Optional target model to use instead (IMP-TEL-005).

    Returns:
        AttemptRunResult with success flag and status string.
    """
    phase_id = phase.get("phase_id")

    def _inner() -> tuple[bool, str]:
        return executor._execute_phase_with_recovery(
            phase,
            attempt_index=attempt_index,
            allowed_paths=allowed_paths,
            memory_context=memory_context,
            context_reduction_factor=context_reduction_factor,
            model_downgrade=model_downgrade,
        )

    success, status = executor.error_recovery.execute_with_retry(
        func=_inner,
        operation_name=f"Phase execution: {phase_id}",
        max_retries=1,  # Only 1 retry for transient errors within an attempt
    )

    return AttemptRunResult(success=success, status=status)
