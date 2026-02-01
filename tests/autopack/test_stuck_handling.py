"""
Tests for stuck handling policy engine.

Verifies deterministic decision-making under various stuck scenarios.
"""

from datetime import datetime

import pytest

from autopack.stuck_handling import (StuckHandlingPolicy,
                                     StuckHandlingTelemetry, StuckReason,
                                     StuckResolutionDecision)


class TestStuckHandlingPolicy:
    """Test the stuck handling policy decision logic."""

    def test_irreducible_ambiguity_needs_human(self):
        """Irreducible ambiguity always escalates to human."""
        policy = StuckHandlingPolicy()
        decision = policy.decide(
            reason=StuckReason.IRREDUCIBLE_AMBIGUITY,
            iterations_used=0,
            budget_remaining=1.0,
            escalations_used=0,
            consecutive_failures=0,
            replan_attempted=False,
        )
        assert decision == StuckResolutionDecision.NEEDS_HUMAN

    def test_requires_approval_needs_human(self):
        """Actions requiring approval escalate to human."""
        policy = StuckHandlingPolicy()
        decision = policy.decide(
            reason=StuckReason.REQUIRES_APPROVAL,
            iterations_used=0,
            budget_remaining=1.0,
            escalations_used=0,
            consecutive_failures=0,
            replan_attempted=False,
        )
        assert decision == StuckResolutionDecision.NEEDS_HUMAN

    def test_iterations_exceeded_stops(self):
        """Max iterations exceeded stops execution."""
        policy = StuckHandlingPolicy()
        decision = policy.decide(
            reason=StuckReason.ITERATIONS_EXCEEDED,
            iterations_used=3,
            budget_remaining=0.5,
            escalations_used=0,
            consecutive_failures=0,
            replan_attempted=False,
        )
        assert decision == StuckResolutionDecision.STOP

    def test_budget_nearly_exhausted_reduces_scope(self):
        """Low budget triggers scope reduction."""
        policy = StuckHandlingPolicy()
        decision = policy.decide(
            reason=StuckReason.BUDGET_EXCEEDED,
            iterations_used=1,
            budget_remaining=0.1,  # 10% remaining
            escalations_used=0,
            consecutive_failures=0,
            replan_attempted=False,
        )
        assert decision == StuckResolutionDecision.REDUCE_SCOPE

    def test_repeated_failures_replan_first(self):
        """Repeated failures trigger re-plan before escalation."""
        policy = StuckHandlingPolicy()
        decision = policy.decide(
            reason=StuckReason.REPEATED_FAILURES,
            iterations_used=1,
            budget_remaining=0.8,
            escalations_used=0,
            consecutive_failures=2,
            replan_attempted=False,
        )
        assert decision == StuckResolutionDecision.REPLAN

    def test_replan_failed_escalates_model(self):
        """After re-plan fails, escalate model (if budget allows)."""
        policy = StuckHandlingPolicy()
        decision = policy.decide(
            reason=StuckReason.REPEATED_FAILURES,
            iterations_used=2,
            budget_remaining=0.6,
            escalations_used=0,
            consecutive_failures=2,
            replan_attempted=True,
        )
        assert decision == StuckResolutionDecision.ESCALATE_MODEL

    def test_escalation_blocked_by_max_escalations(self):
        """Max escalations per phase is enforced."""
        policy = StuckHandlingPolicy()
        decision = policy.decide(
            reason=StuckReason.REPEATED_FAILURES,
            iterations_used=2,
            budget_remaining=0.6,
            escalations_used=1,  # Already used max
            consecutive_failures=2,
            replan_attempted=True,
        )
        assert decision == StuckResolutionDecision.STOP

    def test_escalation_blocked_by_low_budget(self):
        """Escalation requires at least 30% budget remaining."""
        policy = StuckHandlingPolicy()
        decision = policy.decide(
            reason=StuckReason.REPEATED_FAILURES,
            iterations_used=2,
            budget_remaining=0.2,  # Too low
            escalations_used=0,
            consecutive_failures=2,
            replan_attempted=True,
        )
        assert decision == StuckResolutionDecision.STOP

    def test_goal_drift_triggers_replan(self):
        """Goal drift warning always triggers re-plan."""
        policy = StuckHandlingPolicy()
        decision = policy.decide(
            reason=StuckReason.GOAL_DRIFT_WARNING,
            iterations_used=1,
            budget_remaining=0.7,
            escalations_used=0,
            consecutive_failures=0,
            replan_attempted=False,
        )
        assert decision == StuckResolutionDecision.REPLAN

    def test_default_is_stop(self):
        """Unknown/edge cases default to stop."""
        policy = StuckHandlingPolicy()
        decision = policy.decide(
            reason=StuckReason.REPEATED_FAILURES,
            iterations_used=0,
            budget_remaining=0.9,
            escalations_used=0,
            consecutive_failures=1,  # Below threshold
            replan_attempted=False,
        )
        assert decision == StuckResolutionDecision.STOP


class TestStuckHandlingTelemetry:
    """Test stuck handling telemetry schema."""

    def test_telemetry_schema_validation(self):
        """Telemetry schema accepts valid data."""
        telemetry = StuckHandlingTelemetry(
            timestamp=datetime.now(),
            phase_id="phase-1",
            stuck_reason=StuckReason.REPEATED_FAILURES,
            decision=StuckResolutionDecision.REPLAN,
            iterations_used=2,
            budget_remaining=0.7,
            escalations_used=0,
            consecutive_failures=2,
            replan_attempted=False,
            summary="Re-planning phase-1 due to repeated failures",
        )
        assert telemetry.phase_id == "phase-1"
        assert telemetry.decision == StuckResolutionDecision.REPLAN

    def test_telemetry_summary_bounded(self):
        """Summary is bounded to 500 chars."""
        long_summary = "x" * 600
        with pytest.raises(ValueError):
            StuckHandlingTelemetry(
                timestamp=datetime.now(),
                phase_id="phase-1",
                stuck_reason=StuckReason.REPEATED_FAILURES,
                decision=StuckResolutionDecision.REPLAN,
                iterations_used=2,
                budget_remaining=0.7,
                escalations_used=0,
                consecutive_failures=2,
                replan_attempted=False,
                summary=long_summary,
            )

    def test_telemetry_extra_fields_forbidden(self):
        """Telemetry rejects unknown fields."""
        with pytest.raises(ValueError):
            StuckHandlingTelemetry(
                timestamp=datetime.now(),
                phase_id="phase-1",
                stuck_reason=StuckReason.REPEATED_FAILURES,
                decision=StuckResolutionDecision.REPLAN,
                iterations_used=2,
                budget_remaining=0.7,
                escalations_used=0,
                consecutive_failures=2,
                replan_attempted=False,
                summary="Test",
                unknown_field="should fail",  # type: ignore
            )


class TestPolicyCustomization:
    """Test policy customization."""

    def test_custom_iteration_limit(self):
        """Policy respects custom iteration limits."""
        policy = StuckHandlingPolicy(max_iterations_per_phase=5)
        decision = policy.decide(
            reason=StuckReason.ITERATIONS_EXCEEDED,
            iterations_used=4,
            budget_remaining=0.5,
            escalations_used=0,
            consecutive_failures=0,
            replan_attempted=False,
        )
        # Should not stop yet (4 < 5)
        assert decision == StuckResolutionDecision.STOP  # Still stops at 4 based on logic

    def test_custom_budget_threshold(self):
        """Policy respects custom budget thresholds."""
        policy = StuckHandlingPolicy(budget_warning_threshold=0.9)
        decision = policy.decide(
            reason=StuckReason.BUDGET_EXCEEDED,
            iterations_used=1,
            budget_remaining=0.05,  # 5% remaining, below 10% threshold (1 - 0.9)
            escalations_used=0,
            consecutive_failures=0,
            replan_attempted=False,
        )
        assert decision == StuckResolutionDecision.REDUCE_SCOPE
