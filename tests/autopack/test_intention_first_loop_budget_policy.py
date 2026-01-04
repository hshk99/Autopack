"""
Tests for budget-driven stuck handling policy enforcement.

Verifies:
- Low budget triggers REDUCE_SCOPE (not escalation)
- Replan-before-escalate under adequate budget
- Max 1 escalation per phase enforced at loop layer
"""


from autopack.autonomous.intention_first_loop import (
    IntentionFirstLoop,
    PhaseLoopState,
)
from autopack.stuck_handling import StuckReason, StuckResolutionDecision


class TestBudgetDrivenPolicy:
    """Test that budget remaining drives policy decisions correctly."""

    def test_low_budget_triggers_reduce_scope(self):
        """Low budget (<15%) triggers REDUCE_SCOPE instead of escalation."""
        loop = IntentionFirstLoop()
        phase_state = PhaseLoopState(
            iterations_used=2,
            consecutive_failures=2,
            replan_attempted=True,  # Already tried replan
            escalations_used=0,  # Escalation would normally be next
        )

        decision = loop.decide_when_stuck(
            reason=StuckReason.REPEATED_FAILURES,
            phase_state=phase_state,
            budget_remaining=0.1,  # Only 10% budget left
        )

        # With low budget, should reduce scope instead of escalating
        assert decision == StuckResolutionDecision.REDUCE_SCOPE

    def test_adequate_budget_allows_escalation(self):
        """Adequate budget (>30%) allows escalation after replan."""
        loop = IntentionFirstLoop()
        phase_state = PhaseLoopState(
            iterations_used=2,
            consecutive_failures=2,
            replan_attempted=True,  # Already tried replan
            escalations_used=0,
        )

        decision = loop.decide_when_stuck(
            reason=StuckReason.REPEATED_FAILURES,
            phase_state=phase_state,
            budget_remaining=0.6,  # 60% budget remaining
        )

        # With adequate budget, should escalate after replan
        assert decision == StuckResolutionDecision.ESCALATE_MODEL

    def test_replan_before_escalate_with_adequate_budget(self):
        """Policy enforces REPLAN before ESCALATE when budget allows."""
        loop = IntentionFirstLoop()
        phase_state = PhaseLoopState(
            iterations_used=1,
            consecutive_failures=2,  # Triggers stuck handling
            replan_attempted=False,  # Haven't tried replan yet
            escalations_used=0,
        )

        decision = loop.decide_when_stuck(
            reason=StuckReason.REPEATED_FAILURES,
            phase_state=phase_state,
            budget_remaining=0.8,  # Plenty of budget
        )

        # Should replan first, not escalate directly
        assert decision == StuckResolutionDecision.REPLAN

    def test_max_one_escalation_per_phase_enforced(self):
        """Max 1 escalation per phase enforced even with adequate budget."""
        loop = IntentionFirstLoop()
        phase_state = PhaseLoopState(
            iterations_used=3,
            consecutive_failures=2,
            replan_attempted=True,
            escalations_used=1,  # Already escalated once
        )

        decision = loop.decide_when_stuck(
            reason=StuckReason.REPEATED_FAILURES,
            phase_state=phase_state,
            budget_remaining=0.7,  # Adequate budget
        )

        # Should NOT escalate again (max 1 per phase)
        assert decision == StuckResolutionDecision.STOP

    def test_budget_warning_threshold_transition(self):
        """Budget exactly at warning threshold (15%) triggers scope reduction."""
        loop = IntentionFirstLoop()
        phase_state = PhaseLoopState(
            iterations_used=2,
            consecutive_failures=2,
            replan_attempted=True,
            escalations_used=0,
        )

        decision = loop.decide_when_stuck(
            reason=StuckReason.BUDGET_EXCEEDED,
            phase_state=phase_state,
            budget_remaining=0.15,  # Exactly at threshold
        )

        # At or below threshold triggers scope reduction
        assert decision == StuckResolutionDecision.REDUCE_SCOPE

    def test_budget_just_above_threshold_allows_escalation(self):
        """Budget just above threshold allows escalation."""
        loop = IntentionFirstLoop()
        phase_state = PhaseLoopState(
            iterations_used=2,
            consecutive_failures=2,
            replan_attempted=True,
            escalations_used=0,
        )

        decision = loop.decide_when_stuck(
            reason=StuckReason.REPEATED_FAILURES,
            phase_state=phase_state,
            budget_remaining=0.35,  # Just above min_budget_for_escalation (0.3)
        )

        # Above threshold allows escalation
        assert decision == StuckResolutionDecision.ESCALATE_MODEL


class TestEscalationBudgetRequirement:
    """Test that escalation requires minimum budget threshold."""

    def test_escalation_requires_30_percent_budget(self):
        """Escalation requires at least 30% budget remaining."""
        loop = IntentionFirstLoop()
        phase_state = PhaseLoopState(
            iterations_used=2,
            consecutive_failures=2,
            replan_attempted=True,
            escalations_used=0,
        )

        # Just below 30% threshold
        decision = loop.decide_when_stuck(
            reason=StuckReason.REPEATED_FAILURES,
            phase_state=phase_state,
            budget_remaining=0.29,
        )

        # Should stop (not enough budget for escalation)
        assert decision == StuckResolutionDecision.STOP

    def test_escalation_allowed_with_exactly_30_percent(self):
        """Escalation requires > 30% budget (not >= 30%)."""
        loop = IntentionFirstLoop()
        phase_state = PhaseLoopState(
            iterations_used=2,
            consecutive_failures=2,
            replan_attempted=True,
            escalations_used=0,
        )

        decision = loop.decide_when_stuck(
            reason=StuckReason.REPEATED_FAILURES,
            phase_state=phase_state,
            budget_remaining=0.3,  # Exactly at threshold
        )

        # Policy requires > 0.3, not >= 0.3, so this stops
        assert decision == StuckResolutionDecision.STOP


class TestReplanBeforeEscalateSequence:
    """Test the replan→escalate sequence under various budget conditions."""

    def test_full_sequence_replan_then_escalate(self):
        """Full sequence: stuck → replan → stuck again → escalate."""
        loop = IntentionFirstLoop()

        # First stuck: should replan
        phase_state_attempt1 = PhaseLoopState(
            iterations_used=1,
            consecutive_failures=2,
            replan_attempted=False,
            escalations_used=0,
        )

        decision1 = loop.decide_when_stuck(
            reason=StuckReason.REPEATED_FAILURES,
            phase_state=phase_state_attempt1,
            budget_remaining=0.8,
        )

        assert decision1 == StuckResolutionDecision.REPLAN

        # Simulate replan attempted
        phase_state_attempt1.replan_attempted = True

        # Second stuck (after replan failed): should escalate
        phase_state_attempt2 = PhaseLoopState(
            iterations_used=2,
            consecutive_failures=2,
            replan_attempted=True,  # Already tried
            escalations_used=0,
        )

        decision2 = loop.decide_when_stuck(
            reason=StuckReason.REPEATED_FAILURES,
            phase_state=phase_state_attempt2,
            budget_remaining=0.7,
        )

        assert decision2 == StuckResolutionDecision.ESCALATE_MODEL

    def test_replan_skipped_if_budget_too_low(self):
        """If budget is critically low, skip replan and reduce scope."""
        loop = IntentionFirstLoop()
        phase_state = PhaseLoopState(
            iterations_used=1,
            consecutive_failures=2,
            replan_attempted=False,  # Haven't tried replan
            escalations_used=0,
        )

        decision = loop.decide_when_stuck(
            reason=StuckReason.BUDGET_EXCEEDED,
            phase_state=phase_state,
            budget_remaining=0.05,  # Only 5% left
        )

        # Should reduce scope immediately (not replan)
        assert decision == StuckResolutionDecision.REDUCE_SCOPE


class TestGoalDriftWarning:
    """Test that GOAL_DRIFT_WARNING always triggers replan."""

    def test_goal_drift_always_triggers_replan(self):
        """Goal drift with adequate budget triggers replan."""
        loop = IntentionFirstLoop()
        phase_state = PhaseLoopState(
            iterations_used=1,
            consecutive_failures=0,
            replan_attempted=False,
            escalations_used=0,
        )

        decision = loop.decide_when_stuck(
            reason=StuckReason.GOAL_DRIFT_WARNING,
            phase_state=phase_state,
            budget_remaining=0.5,  # Adequate budget
        )

        # Goal drift triggers replan when budget allows
        assert decision == StuckResolutionDecision.REPLAN

    def test_goal_drift_with_replan_already_attempted(self):
        """Goal drift after replan attempted still triggers replan."""
        loop = IntentionFirstLoop()
        phase_state = PhaseLoopState(
            iterations_used=2,
            consecutive_failures=0,
            replan_attempted=True,  # Already tried once
            escalations_used=0,
        )

        decision = loop.decide_when_stuck(
            reason=StuckReason.GOAL_DRIFT_WARNING,
            phase_state=phase_state,
            budget_remaining=0.7,
        )

        # Goal drift always replan (even if already attempted)
        assert decision == StuckResolutionDecision.REPLAN
