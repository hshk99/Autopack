"""Tests for budget enforcement in research pipeline.

Tests the BudgetEnforcer class and budget tracking functionality.
"""

import pytest

pytestmark = pytest.mark.research
from datetime import datetime

from autopack.research.analysis import (
    BudgetEnforcer,
    BudgetMetrics,
    BudgetStatus,
    PhaseBudget,
    PhaseType,
)


class TestBudgetMetrics:
    """Test BudgetMetrics dataclass and calculations."""

    def test_metrics_initialization(self):
        """Test BudgetMetrics initialization with defaults."""
        metrics = BudgetMetrics(total_budget=1000.0)
        assert metrics.total_budget == 1000.0
        assert metrics.total_spent == 0.0
        assert metrics.budget_buffer_percent == 20.0
        assert len(metrics.phases_executed) == 0

    def test_available_budget_calculation(self):
        """Test available budget calculation with buffer."""
        metrics = BudgetMetrics(total_budget=1000.0, budget_buffer_percent=20.0)
        # Buffer = 1000 * 0.20 = 200
        # Available = 1000 - 200 = 800
        assert metrics.available_budget == 800.0

    def test_available_budget_after_spending(self):
        """Test available budget after spending."""
        metrics = BudgetMetrics(total_budget=1000.0, budget_buffer_percent=20.0)
        metrics.total_spent = 300.0
        # Buffer = 200, Spent = 300
        # Available = 1000 - 200 - 300 = 500
        assert metrics.available_budget == 500.0

    def test_utilization_percent_calculation(self):
        """Test utilization percentage calculation."""
        metrics = BudgetMetrics(total_budget=1000.0, budget_buffer_percent=20.0)
        metrics.total_spent = 400.0
        # Usable budget = 1000 * (100 - 20) / 100 = 800
        # Utilization = (400 / 800) * 100 = 50%
        assert metrics.utilization_percent == 50.0

    def test_status_healthy(self):
        """Test status is HEALTHY when utilization < 80%."""
        metrics = BudgetMetrics(total_budget=1000.0)
        metrics.total_spent = 300.0  # 37.5% utilization
        assert metrics.status == BudgetStatus.HEALTHY

    def test_status_warn(self):
        """Test status is WARN when utilization 80-95%."""
        metrics = BudgetMetrics(total_budget=1000.0)
        metrics.total_spent = 680.0  # ~85% utilization
        assert metrics.status == BudgetStatus.WARN

    def test_status_critical(self):
        """Test status is CRITICAL when utilization >= 95%."""
        metrics = BudgetMetrics(total_budget=1000.0)
        metrics.total_spent = 750.0  # ~93.75% utilization
        # This should be WARN, let me recalculate
        # Usable = 1000 * 0.8 = 800
        # Utilization = 750 / 800 = 93.75% - still WARN
        # Let's use 760 = 95%
        metrics.total_spent = 760.0
        assert metrics.status == BudgetStatus.CRITICAL

    def test_status_exhausted(self):
        """Test status is EXHAUSTED when spent >= total."""
        metrics = BudgetMetrics(total_budget=1000.0)
        metrics.total_spent = 1000.0
        assert metrics.status == BudgetStatus.EXHAUSTED

    def test_metrics_to_dict(self):
        """Test conversion of metrics to dictionary."""
        metrics = BudgetMetrics(total_budget=1000.0)
        metrics.total_spent = 300.0
        result = metrics.to_dict()
        assert result["total_budget"] == 1000.0
        assert result["total_spent"] == 300.0
        assert result["available_budget"] == 500.0
        assert result["status"] == "healthy"
        assert "utilization_percent" in result
        assert "phases_executed" in result


class TestPhaseBudget:
    """Test PhaseBudget tracking."""

    def test_phase_budget_initialization(self):
        """Test PhaseBudget initialization."""
        phase = PhaseBudget(phase=PhaseType.MARKET_RESEARCH, estimated_cost=100.0)
        assert phase.phase == PhaseType.MARKET_RESEARCH
        assert phase.estimated_cost == 100.0
        assert phase.actual_cost == 0.0
        assert not phase.is_complete

    def test_phase_budget_completion(self):
        """Test marking phase as complete."""
        phase = PhaseBudget(phase=PhaseType.MARKET_RESEARCH, estimated_cost=100.0)
        phase.completed_at = datetime.now()
        assert phase.is_complete

    def test_cost_delta_calculation(self):
        """Test cost delta calculation."""
        phase = PhaseBudget(
            phase=PhaseType.MARKET_RESEARCH,
            estimated_cost=100.0,
            actual_cost=120.0,
        )
        assert phase.cost_delta == 20.0

    def test_under_budget(self):
        """Test when actual cost is less than estimated."""
        phase = PhaseBudget(
            phase=PhaseType.MARKET_RESEARCH,
            estimated_cost=100.0,
            actual_cost=80.0,
        )
        assert phase.cost_delta == -20.0


class TestBudgetEnforcer:
    """Test BudgetEnforcer functionality."""

    def test_enforcer_initialization(self):
        """Test BudgetEnforcer initialization."""
        enforcer = BudgetEnforcer(total_budget=5000.0)
        assert enforcer.metrics.total_budget == 5000.0
        assert enforcer.metrics.total_spent == 0.0

    def test_custom_phase_costs(self):
        """Test initialization with custom phase costs."""
        custom_costs = {PhaseType.MARKET_RESEARCH: 200.0}
        enforcer = BudgetEnforcer(total_budget=5000.0, phase_costs=custom_costs)
        assert enforcer.phase_costs[PhaseType.MARKET_RESEARCH] == 200.0

    def test_set_budget(self):
        """Test updating budget."""
        enforcer = BudgetEnforcer(total_budget=5000.0)
        enforcer.set_budget(10000.0)
        assert enforcer.metrics.total_budget == 10000.0

    def test_can_proceed_with_budget(self):
        """Test can proceed when budget available."""
        enforcer = BudgetEnforcer(total_budget=5000.0)
        assert enforcer.can_proceed()

    def test_cannot_proceed_no_budget(self):
        """Test cannot proceed when no budget set."""
        enforcer = BudgetEnforcer(total_budget=0.0)
        assert not enforcer.can_proceed()

    def test_cannot_proceed_budget_exhausted(self):
        """Test cannot proceed when budget exhausted."""
        enforcer = BudgetEnforcer(total_budget=1000.0)
        enforcer.metrics.total_spent = 1000.0
        assert not enforcer.can_proceed()

    def test_can_proceed_with_phase_name(self):
        """Test budget check for specific phase."""
        enforcer = BudgetEnforcer(total_budget=5000.0)
        assert enforcer.can_proceed("market_research")

    def test_cannot_proceed_insufficient_for_phase(self):
        """Test cannot proceed when phase would exceed budget."""
        # Setup: budget = 500, market research costs 100, but we've spent 450
        enforcer = BudgetEnforcer(
            total_budget=500.0,
            phase_costs={PhaseType.MARKET_RESEARCH: 100.0},
        )
        enforcer.metrics.total_spent = 450.0
        assert not enforcer.can_proceed("market_research")

    def test_start_phase(self):
        """Test starting a phase tracking."""
        enforcer = BudgetEnforcer(total_budget=5000.0)
        enforcer.start_phase("market_research")
        assert "market_research" in enforcer._phase_history
        phase = enforcer._phase_history["market_research"]
        assert phase.started_at is not None
        assert phase.estimated_cost == 100.0

    def test_complete_phase(self):
        """Test completing a phase."""
        enforcer = BudgetEnforcer(total_budget=5000.0)
        enforcer.start_phase("market_research")
        enforcer.complete_phase("market_research")
        phase = enforcer._phase_history["market_research"]
        assert phase.is_complete
        assert enforcer.metrics.total_spent == 100.0

    def test_complete_phase_with_actual_cost(self):
        """Test completing phase with actual cost different from estimate."""
        enforcer = BudgetEnforcer(total_budget=5000.0)
        enforcer.start_phase("market_research")
        enforcer.complete_phase("market_research", actual_cost=150.0)
        assert enforcer.metrics.total_spent == 150.0

    def test_record_cost(self):
        """Test recording additional cost."""
        enforcer = BudgetEnforcer(total_budget=5000.0)
        enforcer.record_cost("market_research", 50.0)
        assert enforcer.metrics.total_spent == 50.0

    def test_multiple_phases(self):
        """Test tracking multiple phases."""
        enforcer = BudgetEnforcer(total_budget=5000.0)

        # Execute market research
        enforcer.start_phase("market_research")
        enforcer.complete_phase("market_research")
        assert enforcer.metrics.total_spent == 100.0

        # Execute competitive analysis
        enforcer.start_phase("competitive_analysis")
        enforcer.complete_phase("competitive_analysis")
        assert enforcer.metrics.total_spent == 250.0  # 100 + 150

        # Check phases tracked
        assert len(enforcer.metrics.phases_executed) == 2

    def test_get_metrics(self):
        """Test getting metrics object."""
        enforcer = BudgetEnforcer(total_budget=5000.0)
        enforcer.record_cost("test", 100.0)
        metrics = enforcer.get_metrics()
        assert metrics.total_spent == 100.0
        assert metrics.total_budget == 5000.0

    def test_get_status_summary(self):
        """Test getting human-readable status summary."""
        enforcer = BudgetEnforcer(total_budget=5000.0)
        enforcer.record_cost("test", 1000.0)
        summary = enforcer.get_status_summary()
        assert "status" in summary
        assert "total_budget" in summary
        assert "total_spent" in summary
        assert "available_budget" in summary
        assert "utilization" in summary
        assert "can_proceed" in summary

    def test_phase_type_detection(self):
        """Test automatic phase type detection."""
        enforcer = BudgetEnforcer(total_budget=5000.0)
        phase_type = enforcer._get_phase_type("market_research_phase")
        assert phase_type == PhaseType.MARKET_RESEARCH

    def test_phase_type_detection_case_insensitive(self):
        """Test phase type detection is case insensitive."""
        enforcer = BudgetEnforcer(total_budget=5000.0)
        phase_type = enforcer._get_phase_type("MARKET_RESEARCH")
        assert phase_type == PhaseType.MARKET_RESEARCH

    def test_unknown_phase_type(self):
        """Test unknown phase type defaults to CUSTOM."""
        enforcer = BudgetEnforcer(total_budget=5000.0)
        phase_type = enforcer._get_phase_type("unknown_phase_xyz")
        assert phase_type == PhaseType.CUSTOM


class TestBudgetEnforcementGates:
    """Test budget enforcement gates in research phases."""

    def test_expensive_phase_blocked_when_budget_low(self):
        """Test expensive phases are blocked when budget is low."""
        # Set a budget for 2-3 phases
        # Usable budget = 1000 * (100 - 20) / 100 = 800
        enforcer = BudgetEnforcer(total_budget=1000.0)

        # Should be able to do one market research (100)
        assert enforcer.can_proceed("market_research")
        enforcer.start_phase("market_research")
        enforcer.complete_phase("market_research")

        # Should be able to do competitive analysis (150)
        assert enforcer.can_proceed("competitive_analysis")
        enforcer.start_phase("competitive_analysis")
        enforcer.complete_phase("competitive_analysis")

        # Should be able to do technical feasibility (150)
        assert enforcer.can_proceed("technical_feasibility")
        enforcer.start_phase("technical_feasibility")
        enforcer.complete_phase("technical_feasibility")

        # Now should not be able to do follow-up research (200) as it would exceed budget
        # Spent so far: 100 + 150 + 150 = 400
        # Available: 800 - 400 = 400
        # Followup costs 200, so we should be able to proceed
        assert enforcer.can_proceed("followup_research")
        enforcer.start_phase("followup_research")
        enforcer.complete_phase("followup_research")

        # Now spent = 600, available = 200 - should not be able to do another followup (200)
        # Actually available = 800 - 600 = 200, followup needs 200, so barely passes
        assert enforcer.can_proceed("followup_research")
        enforcer.start_phase("followup_research")
        enforcer.complete_phase("followup_research")

        # Now spent = 800, should be exhausted
        assert not enforcer.can_proceed("market_research")

    def test_followup_research_more_expensive(self):
        """Test that follow-up research is more expensive."""
        enforcer = BudgetEnforcer(total_budget=5000.0)
        followup_cost = enforcer.phase_costs.get(PhaseType.FOLLOWUP_RESEARCH, 0)
        normal_cost = enforcer.phase_costs.get(PhaseType.MARKET_RESEARCH, 0)
        assert followup_cost > normal_cost

    def test_buffer_protection(self):
        """Test that buffer percentage is protected."""
        enforcer = BudgetEnforcer(
            total_budget=1000.0,
            buffer_percent=20.0,
        )

        # With 20% buffer (200), we only have 800 usable
        # If we spend 700, we have 100 left
        enforcer.metrics.total_spent = 700.0

        # Should not be able to proceed with market research (100) as it would use all available
        # Actually 100 left, and market research costs 100, so we should barely pass
        assert enforcer.can_proceed("market_research")

        # But not with competitive analysis (150)
        assert not enforcer.can_proceed("competitive_analysis")

    def test_phase_cost_tracking_accuracy(self):
        """Test that phase costs are tracked accurately."""
        enforcer = BudgetEnforcer(total_budget=1000.0)

        # Track several phases
        for phase_name in ["market_research", "competitive_analysis", "technical_feasibility"]:
            enforcer.start_phase(phase_name)
            enforcer.complete_phase(phase_name)

        # Verify total
        expected = 100.0 + 150.0 + 150.0  # Sum of phase costs
        assert enforcer.metrics.total_spent == expected
        assert len(enforcer.metrics.phases_executed) == 3


class TestBudgetIntegration:
    """Integration tests for budget enforcement."""

    def test_full_research_pipeline_with_budget(self):
        """Test a complete research pipeline with budget tracking."""
        # Set budget for a complete pipeline
        enforcer = BudgetEnforcer(total_budget=1000.0)

        # Run research phases
        phases = [
            "market_research",
            "competitive_analysis",
            "technical_feasibility",
            "cost_effectiveness_analysis",
        ]

        for phase in phases:
            if not enforcer.can_proceed(phase):
                pytest.fail(f"Budget insufficient for {phase}")

            enforcer.start_phase(phase)
            enforcer.complete_phase(phase)

        # Check final state
        assert len(enforcer.metrics.phases_executed) == 4
        assert enforcer.metrics.status != BudgetStatus.EXHAUSTED

    def test_budget_exhaustion_prevents_additional_phases(self):
        """Test that budget exhaustion prevents additional phases."""
        enforcer = BudgetEnforcer(total_budget=400.0)

        # Complete first two phases (100 + 150 = 250)
        enforcer.start_phase("market_research")
        enforcer.complete_phase("market_research")

        enforcer.start_phase("competitive_analysis")
        enforcer.complete_phase("competitive_analysis")

        # Third phase (150) would exceed budget
        assert not enforcer.can_proceed("technical_feasibility")

    def test_cost_overrun_detection(self):
        """Test detection of cost overruns."""
        enforcer = BudgetEnforcer(total_budget=500.0)

        # Start and complete phase with overrun
        enforcer.start_phase("market_research")
        enforcer.complete_phase("market_research", actual_cost=150.0)  # Overrun

        phase = enforcer._phase_history["market_research"]
        assert phase.cost_delta == 50.0  # Overspent by 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
