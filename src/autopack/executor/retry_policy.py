"""Pure retry/escalation decision functions for AutonomousExecutor.

Goal:
- Extract deterministic retry/escalation decisioning into testable pure functions.
- Reduce merge conflicts and cognitive load in `autonomous_executor.py`.

Design:
- All functions are pure (no side effects, no DB access).
- The executor remains responsible for acting on these decisions (DB updates, etc.).
- Returns decision dataclasses so logic is explicit and testable.

Non-goal (this module):
- Model selection logic (deferred to ModelRouter).
- DB state persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Status = Literal["COMPLETE", "FAILED", "BLOCKED", "TOKEN_ESCALATION", "PATCH_FAILED"]


@dataclass(frozen=True)
class AttemptContext:
    """Immutable context for retry decision-making.

    Attributes:
        attempt_index: Current 0-based attempt number (from phase_db.retry_attempt).
        max_attempts: Maximum allowed attempts (from MAX_RETRY_ATTEMPTS constant).
        escalation_level: Model escalation level (0=base, higher=stronger models).
    """

    attempt_index: int
    max_attempts: int
    escalation_level: int


@dataclass(frozen=True)
class AttemptDecision:
    """Decision output for what the executor should do next.

    Attributes:
        next_retry_attempt: New retry_attempt value to persist (None = no update).
        should_run_diagnostics: Whether to run diagnostics/Doctor for this failure.
        should_escalate_model: Whether to escalate to a stronger model.
        terminal: Whether to stop the retry loop at executor level.
    """

    next_retry_attempt: Optional[int]
    should_run_diagnostics: bool
    should_escalate_model: bool
    terminal: bool


def should_escalate(status: str) -> bool:
    """Check if status indicates token budget escalation.

    TOKEN_ESCALATION is a special control-flow signal (BUILD-129/P10):
    - Indicates the attempt failed due to truncation/high token utilization.
    - The next attempt should use a larger completion budget.
    - Does NOT require diagnostics/Doctor intervention.

    Args:
        status: The status string from phase execution.

    Returns:
        True if this is a TOKEN_ESCALATION status.
    """
    return status == "TOKEN_ESCALATION"


def should_run_diagnostics(status: str) -> bool:
    """Determine if diagnostics should run for this status.

    BUILD-129/P10: TOKEN_ESCALATION is not a diagnosable "approach flaw".
    It's an intentional control-flow signal to retry with a larger budget.
    Running diagnostics would reset state and prevent the stateful retry
    budget from being applied.

    Success (COMPLETE) also skips diagnostics since there's no failure.

    Args:
        status: The status string from phase execution.

    Returns:
        True if diagnostics/Doctor should be invoked for this failure.
    """
    if status == "TOKEN_ESCALATION":
        return False
    if status == "COMPLETE":
        return False
    # All other failures should trigger diagnostics
    return True


def next_attempt_state(ctx: AttemptContext, status: str) -> AttemptDecision:
    """Compute the next attempt state based on current context and status.

    This is the main decision function that determines:
    - Whether to advance the retry attempt counter
    - Whether to run diagnostics
    - Whether to escalate the model
    - Whether this is a terminal state

    Args:
        ctx: Current attempt context (attempt_index, max_attempts, escalation_level).
        status: The status string from phase execution.

    Returns:
        AttemptDecision with instructions for the executor.
    """
    # Edge case: zero max_attempts means always terminal
    if ctx.max_attempts <= 0:
        return AttemptDecision(
            next_retry_attempt=None,
            should_run_diagnostics=False,
            should_escalate_model=False,
            terminal=True,
        )

    # Already exhausted attempts
    if ctx.attempt_index >= ctx.max_attempts:
        return AttemptDecision(
            next_retry_attempt=None,
            should_run_diagnostics=False,
            should_escalate_model=False,
            terminal=True,
        )

    # Success: terminal but no state update needed
    if status == "COMPLETE":
        return AttemptDecision(
            next_retry_attempt=None,
            should_run_diagnostics=False,
            should_escalate_model=False,
            terminal=True,
        )

    # Compute next attempt index
    next_attempt = ctx.attempt_index + 1

    # TOKEN_ESCALATION: advance retry_attempt, no diagnostics
    # BUILD-129/P10: Don't run diagnostics/Doctor - just retry with larger budget
    if should_escalate(status):
        is_terminal = next_attempt >= ctx.max_attempts
        return AttemptDecision(
            next_retry_attempt=next_attempt,
            should_run_diagnostics=False,
            should_escalate_model=False,  # Token budget escalation, not model escalation
            terminal=is_terminal,
        )

    # Normal failure: advance retry_attempt, run diagnostics
    # Failures: FAILED, BLOCKED, PATCH_FAILED, or unknown statuses
    is_terminal = next_attempt >= ctx.max_attempts
    return AttemptDecision(
        next_retry_attempt=next_attempt,
        should_run_diagnostics=should_run_diagnostics(status),
        should_escalate_model=False,  # Model escalation handled separately by stuck handling
        terminal=is_terminal,
    )


def choose_model_for_attempt(ctx: AttemptContext) -> Optional[str]:
    """Return model id override for this attempt, or None to defer to ModelRouter.

    Currently returns None to defer all model selection to the existing ModelRouter.
    This function exists as a hook point for future escalation policies.

    Per the design doc:
    - `choose_model_for_attempt()` returns **None by default** (defer to existing ModelRouter).
    - Only encode override logic if it already exists as a deterministic mapping.

    Args:
        ctx: Current attempt context.

    Returns:
        Model ID string to override, or None to use ModelRouter default.
    """
    # Defer to ModelRouter for now
    return None
