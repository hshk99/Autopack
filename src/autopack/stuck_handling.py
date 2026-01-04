"""
Stuck handling policy engine for intention-first autonomy.

Implements deterministic decision-making when execution hits budgets/iteration limits:
- re-plan (route back to intention)
- reduce_scope (explicitly justify against intention)
- escalate_model (budget-aware, max 1 per phase)
- needs_human (last resort for irreducible ambiguity)
- stop (actionable summary)

All decisions are deterministic, audit-friendly, and bounded.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StuckReason(str, Enum):
    """Why execution is stuck."""

    ITERATIONS_EXCEEDED = "iterations_exceeded"
    BUDGET_EXCEEDED = "budget_exceeded"
    REPEATED_FAILURES = "repeated_failures"
    GOAL_DRIFT_WARNING = "goal_drift_warning"
    IRREDUCIBLE_AMBIGUITY = "irreducible_ambiguity"
    REQUIRES_APPROVAL = "requires_approval"


class StuckResolutionDecision(str, Enum):
    """What to do when stuck."""

    REPLAN = "replan"  # Re-route to intention, revise approach
    REDUCE_SCOPE = "reduce_scope"  # Drop non-critical deliverables
    ESCALATE_MODEL = "escalate_model"  # Use stronger model (budget permitting)
    NEEDS_HUMAN = "needs_human"  # Escalate to human (last resort)
    STOP = "stop"  # Halt with actionable summary


class StuckHandlingPolicy(BaseModel):
    """
    Policy object for deterministic stuck handling.

    Enforces the "lowest-cost safe action" hierarchy:
    1. Re-plan before escalation
    2. Escalate model only after re-plan fails (max 1/phase)
    3. Reduce scope when budgets are near or task is too large
    4. needs-human only for irreducible ambiguity or safety approval
    """

    model_config = ConfigDict(extra="forbid")

    # Thresholds
    max_iterations_per_phase: int = 3
    max_escalations_per_phase: int = 1
    budget_warning_threshold: float = 0.8  # 80% of budget
    consecutive_failures_trigger: int = 2

    def decide(
        self,
        reason: StuckReason,
        iterations_used: int,
        budget_remaining: float,
        escalations_used: int,
        consecutive_failures: int,
        replan_attempted: bool,
    ) -> StuckResolutionDecision:
        """
        Deterministic decision logic.

        Args:
            reason: Why we're stuck
            iterations_used: How many iterations used so far
            budget_remaining: Fraction of budget remaining (0.0 to 1.0)
            escalations_used: How many model escalations used in this phase
            consecutive_failures: How many consecutive similar failures
            replan_attempted: Whether we've already tried re-planning

        Returns:
            The next action to take
        """
        # needs-human is last resort for safety/ambiguity
        if reason in (StuckReason.IRREDUCIBLE_AMBIGUITY, StuckReason.REQUIRES_APPROVAL):
            return StuckResolutionDecision.NEEDS_HUMAN

        # Stop if we've exhausted iterations and options
        if iterations_used >= self.max_iterations_per_phase:
            return StuckResolutionDecision.STOP

        # Reduce scope if budget is nearly exhausted
        if budget_remaining < (1.0 - self.budget_warning_threshold):
            return StuckResolutionDecision.REDUCE_SCOPE

        # Re-plan before escalation (if not already attempted)
        if consecutive_failures >= self.consecutive_failures_trigger and not replan_attempted:
            return StuckResolutionDecision.REPLAN

        # Escalate model only after re-plan fails and within budget
        if (
            replan_attempted
            and consecutive_failures >= self.consecutive_failures_trigger
            and escalations_used < self.max_escalations_per_phase
            and budget_remaining > 0.3  # Need at least 30% budget for escalation
        ):
            return StuckResolutionDecision.ESCALATE_MODEL

        # Goal drift or repeated failures: re-plan
        if reason == StuckReason.GOAL_DRIFT_WARNING:
            return StuckResolutionDecision.REPLAN

        # Default: stop with summary
        return StuckResolutionDecision.STOP


class StuckHandlingTelemetry(BaseModel):
    """
    Bounded telemetry for stuck handling events.

    Designed to be small and audit-friendly (no content dumps).
    """

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    phase_id: str
    stuck_reason: StuckReason
    decision: StuckResolutionDecision
    iterations_used: int
    budget_remaining: float  # 0.0 to 1.0
    escalations_used: int
    consecutive_failures: int
    replan_attempted: bool
    summary: str = Field(
        ..., max_length=500, description="Single-line actionable summary"
    )
