"""Tests for IMP-AUT-001: Research Cycle Integration.

This module tests the research cycle integration with autopilot,
including budget enforcement, outcome handling, and metrics.
"""

from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from autopack.autonomy.research_cycle_integration import (
    ResearchCycleDecision, ResearchCycleIntegration, ResearchCycleMetrics,
    ResearchCycleOutcome, create_research_cycle_integration)
from autopack.research.analysis.budget_enforcement import BudgetEnforcer
from autopack.research.analysis.followup_trigger import (FollowupTrigger,
                                                         ResearchPlan,
                                                         TriggerAnalysisResult,
                                                         TriggerPriority,
                                                         TriggerType)


class TestResearchCycleIntegrationInit:
    """Tests for ResearchCycleIntegration initialization."""

    def test_default_initialization(self):
        """Test default initialization creates valid instance."""
        integration = ResearchCycleIntegration()

        assert integration._min_budget_threshold == 0.2
        assert integration._critical_gap_threshold == 3
        assert integration._budget_enforcer is not None
        assert integration._metrics is not None

    def test_custom_initialization(self):
        """Test custom initialization parameters."""
        budget_enforcer = BudgetEnforcer(total_budget=1000.0)

        integration = ResearchCycleIntegration(
            budget_enforcer=budget_enforcer,
            min_budget_threshold=0.3,
            critical_gap_threshold=5,
        )

        assert integration._min_budget_threshold == 0.3
        assert integration._critical_gap_threshold == 5

    def test_factory_function(self):
        """Test factory function creates valid instance."""
        integration = create_research_cycle_integration(
            min_budget_threshold=0.15,
        )

        assert integration is not None
        assert integration._min_budget_threshold == 0.15


class TestBudgetIntegration:
    """Tests for IMP-RES-002 budget integration."""

    @pytest.fixture
    def integration(self):
        """Create integration with fresh budget."""
        budget_enforcer = BudgetEnforcer(total_budget=1000.0)
        return ResearchCycleIntegration(
            budget_enforcer=budget_enforcer,
            min_budget_threshold=0.2,
        )

    def test_can_proceed_with_fresh_budget(self, integration):
        """Test can_proceed returns True with fresh budget."""
        assert integration.can_proceed_with_research() is True

    def test_can_proceed_with_exhausted_budget(self, integration):
        """Test can_proceed returns False with exhausted budget."""
        # Exhaust the budget
        integration._budget_enforcer.metrics.total_spent = 1000.0

        assert integration.can_proceed_with_research() is False

    def test_can_proceed_below_threshold(self, integration):
        """Test can_proceed returns False when below threshold."""
        # Use 85% of budget (above 80% threshold)
        integration._budget_enforcer.metrics.total_spent = 850.0

        # With 20% buffer, 80% is the usable budget = 800
        # 850 spent > 800 usable = blocked
        assert integration.can_proceed_with_research() is False

    def test_get_budget_remaining(self, integration):
        """Test budget remaining calculation."""
        remaining = integration.get_budget_remaining()
        assert remaining == 1.0  # Fresh budget

        # Spend some budget
        integration._budget_enforcer.metrics.total_spent = 400.0
        remaining = integration.get_budget_remaining()
        assert 0.0 < remaining < 1.0

    def test_record_research_cost(self, integration):
        """Test recording research cost updates budget."""
        initial_spent = integration._budget_enforcer.metrics.total_spent

        integration.record_research_cost("test_phase", 100.0)

        assert integration._budget_enforcer.metrics.total_spent == initial_spent + 100.0


class TestResearchCycleExecution:
    """Tests for research cycle execution."""

    @pytest.fixture
    def integration(self):
        """Create integration for testing."""
        budget_enforcer = BudgetEnforcer(total_budget=5000.0)
        return ResearchCycleIntegration(
            budget_enforcer=budget_enforcer,
            min_budget_threshold=0.2,
        )

    @pytest.mark.asyncio
    async def test_execute_skips_when_paused(self, integration):
        """Test execution skips when autopilot is paused."""
        # Create mock autopilot that is paused
        mock_autopilot = MagicMock()
        mock_autopilot.is_task_generation_paused.return_value = True
        mock_autopilot.get_pause_reason.return_value = "Test pause"

        outcome = await integration.execute_research_cycle(
            analysis_results={},
            autopilot=mock_autopilot,
        )

        assert outcome.decision == ResearchCycleDecision.SKIP
        assert "paused" in outcome.reason.lower()
        assert integration._metrics.skipped_health == 1

    @pytest.mark.asyncio
    async def test_execute_skips_when_circuit_breaker_open(self, integration):
        """Test execution skips when circuit breaker is open."""
        # Create mock executor context with open circuit
        mock_executor = MagicMock()
        mock_executor.circuit_breaker.is_available.return_value = False
        mock_executor.circuit_breaker.state.value = "open"

        outcome = await integration.execute_research_cycle(
            analysis_results={},
            executor_ctx=mock_executor,
        )

        assert outcome.decision == ResearchCycleDecision.SKIP
        assert "circuit breaker" in outcome.reason.lower()

    @pytest.mark.asyncio
    async def test_execute_skips_when_budget_exhausted(self, integration):
        """Test execution skips when budget is exhausted."""
        # Exhaust budget
        integration._budget_enforcer.metrics.total_spent = 5000.0

        outcome = await integration.execute_research_cycle(
            analysis_results={},
        )

        assert outcome.decision == ResearchCycleDecision.SKIP
        assert integration._metrics.skipped_budget == 1

    @pytest.mark.asyncio
    async def test_execute_proceeds_when_no_triggers(self, integration):
        """Test execution proceeds when no triggers detected."""
        analysis_results = {
            "findings": [],
            "identified_gaps": [],
        }

        outcome = await integration.execute_research_cycle(
            analysis_results=analysis_results,
        )

        assert outcome.decision == ResearchCycleDecision.PROCEED
        assert outcome.should_continue_execution is True

    @pytest.mark.asyncio
    async def test_execute_with_triggers_and_callback(self, integration):
        """Test execution with triggers and callback."""
        # Register a callback
        callback_invoked = []

        def test_callback(trigger: FollowupTrigger) -> Optional[Dict[str, Any]]:
            callback_invoked.append(trigger.trigger_id)
            return {"findings": ["test finding"]}

        integration.register_trigger_callback(test_callback)

        # Analysis results that will trigger research
        analysis_results = {
            "findings": [
                {
                    "id": "f1",
                    "summary": "Low confidence finding",
                    "confidence": 0.3,
                    "topic": "test",
                }
            ],
            "identified_gaps": [
                {
                    "category": "market_research",
                    "description": "Missing market data",
                    "suggested_queries": ["market analysis"],
                }
            ],
        }

        outcome = await integration.execute_research_cycle(
            analysis_results=analysis_results,
        )

        # Should have detected triggers
        assert outcome.trigger_result is not None
        assert outcome.trigger_result.triggers_detected > 0

    @pytest.mark.asyncio
    async def test_execute_respects_max_cycles(self, integration):
        """Test execution respects max cycles per session."""
        integration._cycles_this_session = integration.MAX_CYCLES_PER_SESSION + 1

        outcome = await integration.execute_research_cycle(
            analysis_results={},
        )

        assert outcome.decision == ResearchCycleDecision.SKIP
        assert "max cycles" in outcome.reason.lower()


class TestDecisionDetermination:
    """Tests for decision determination logic."""

    @pytest.fixture
    def integration(self):
        """Create integration for testing."""
        return ResearchCycleIntegration()

    def test_block_decision_with_critical_gaps(self, integration):
        """Test BLOCK decision when critical gaps exceed threshold."""
        # Create triggers with critical priority
        triggers = [
            FollowupTrigger(
                trigger_id=f"trig-{i}",
                trigger_type=TriggerType.GAP,
                priority=TriggerPriority.CRITICAL,
                reason="Critical gap",
                source_finding="test",
                research_plan=ResearchPlan(
                    queries=["test"],
                    target_agent="test",
                    expected_outcome="test",
                ),
            )
            for i in range(4)  # Exceed threshold of 3
        ]

        trigger_result = TriggerAnalysisResult(
            triggers_detected=4,
            triggers_selected=4,
            trigger_summary={},
            selected_triggers=triggers,
            not_selected_triggers=[],
            should_research=True,
            execution_plan={},
        )

        from autopack.research.analysis.followup_trigger import \
            TriggerExecutionResult

        execution_result = TriggerExecutionResult(
            triggers_executed=4,
            callbacks_invoked=4,
            successful_executions=2,
            failed_executions=2,
            total_execution_time_ms=100,
        )

        outcome = integration._determine_decision(
            trigger_result=trigger_result,
            execution_result=execution_result,
            analysis_results={},
        )

        assert outcome.decision == ResearchCycleDecision.BLOCK
        assert outcome.should_continue_execution is False

    def test_adjust_plan_with_many_findings(self, integration):
        """Test ADJUST_PLAN decision with many findings."""
        triggers = [
            FollowupTrigger(
                trigger_id="trig-1",
                trigger_type=TriggerType.GAP,
                priority=TriggerPriority.MEDIUM,
                reason="Gap",
                source_finding="test",
                research_plan=ResearchPlan(
                    queries=["test"],
                    target_agent="test",
                    expected_outcome="test",
                ),
            )
        ]

        trigger_result = TriggerAnalysisResult(
            triggers_detected=1,
            triggers_selected=1,
            trigger_summary={},
            selected_triggers=triggers,
            not_selected_triggers=[],
            should_research=True,
            execution_plan={},
        )

        from autopack.research.analysis.followup_trigger import \
            TriggerExecutionResult

        execution_result = TriggerExecutionResult(
            triggers_executed=1,
            callbacks_invoked=3,
            successful_executions=3,
            failed_executions=0,
            total_execution_time_ms=100,
            integrated_findings=[
                {"finding": "1"},
                {"finding": "2"},
                {"finding": "3"},
            ],
        )

        outcome = integration._determine_decision(
            trigger_result=trigger_result,
            execution_result=execution_result,
            analysis_results={},
        )

        assert outcome.decision == ResearchCycleDecision.ADJUST_PLAN
        assert outcome.should_continue_execution is True

    def test_pause_for_research_with_failures(self, integration):
        """Test PAUSE_FOR_RESEARCH when failures exceed successes."""
        triggers = []
        trigger_result = TriggerAnalysisResult(
            triggers_detected=1,
            triggers_selected=1,
            trigger_summary={},
            selected_triggers=triggers,
            not_selected_triggers=[],
            should_research=True,
            execution_plan={},
        )

        from autopack.research.analysis.followup_trigger import \
            TriggerExecutionResult

        execution_result = TriggerExecutionResult(
            triggers_executed=3,
            callbacks_invoked=3,
            successful_executions=1,
            failed_executions=2,  # More failures than successes
            total_execution_time_ms=100,
        )

        outcome = integration._determine_decision(
            trigger_result=trigger_result,
            execution_result=execution_result,
            analysis_results={},
        )

        assert outcome.decision == ResearchCycleDecision.PAUSE_FOR_RESEARCH
        assert outcome.should_continue_execution is False


class TestMetrics:
    """Tests for research cycle metrics."""

    @pytest.fixture
    def integration(self):
        """Create integration for testing."""
        return ResearchCycleIntegration()

    def test_initial_metrics(self, integration):
        """Test initial metrics are zero."""
        metrics = integration.get_metrics()

        assert metrics.total_cycles_triggered == 0
        assert metrics.successful_cycles == 0
        assert metrics.failed_cycles == 0
        assert metrics.skipped_budget == 0
        assert metrics.skipped_health == 0

    @pytest.mark.asyncio
    async def test_metrics_updated_on_skip(self, integration):
        """Test metrics updated when cycle is skipped."""
        # Exhaust budget
        integration._budget_enforcer.metrics.total_spent = 5000.0

        await integration.execute_research_cycle(analysis_results={})

        metrics = integration.get_metrics()
        assert metrics.total_cycles_triggered == 1
        assert metrics.skipped_budget == 1

    @pytest.mark.asyncio
    async def test_metrics_updated_on_success(self, integration):
        """Test metrics updated on successful cycle."""
        # Register a callback that succeeds
        integration.register_trigger_callback(lambda t: {"result": "success"})

        analysis_results = {
            "findings": [{"id": "f1", "summary": "Test", "confidence": 0.3, "topic": "test"}],
        }

        await integration.execute_research_cycle(analysis_results=analysis_results)

        metrics = integration.get_metrics()
        assert metrics.total_cycles_triggered == 1
        assert metrics.last_cycle_at is not None

    def test_metrics_to_dict(self, integration):
        """Test metrics serialization."""
        metrics = integration.get_metrics()
        data = metrics.to_dict()

        assert "research_cycle_metrics" in data
        assert "total_cycles_triggered" in data["research_cycle_metrics"]
        assert "decisions" in data["research_cycle_metrics"]


class TestCallbackRegistration:
    """Tests for callback registration."""

    @pytest.fixture
    def integration(self):
        """Create integration for testing."""
        return ResearchCycleIntegration()

    def test_register_trigger_callback(self, integration):
        """Test registering a trigger callback."""
        callback = MagicMock(return_value=None)

        integration.register_trigger_callback(callback)

        assert integration._followup_trigger.get_callback_count() == 1

    def test_register_async_trigger_callback(self, integration):
        """Test registering an async trigger callback."""

        async def async_callback(trigger):
            return {"async": True}

        integration.register_async_trigger_callback(async_callback)

        assert integration._followup_trigger.get_callback_count() == 1

    def test_register_completion_callback(self, integration):
        """Test registering a completion callback."""
        callback = MagicMock()

        integration.register_completion_callback(callback)

        assert len(integration._completion_callbacks) == 1

    @pytest.mark.asyncio
    async def test_completion_callback_invoked(self, integration):
        """Test completion callback is invoked after cycle."""
        callback_invoked = []

        def completion_callback(outcome: ResearchCycleOutcome):
            callback_invoked.append(outcome.decision)

        integration.register_completion_callback(completion_callback)

        # Use analysis results that trigger research
        analysis_results = {
            "findings": [{"id": "f1", "summary": "Test", "confidence": 0.3, "topic": "test"}],
            "identified_gaps": [
                {"category": "market_research", "description": "Gap", "suggested_queries": ["q1"]}
            ],
        }

        # Register a trigger callback so execution completes
        integration.register_trigger_callback(lambda t: {"result": "test"})

        await integration.execute_research_cycle(analysis_results=analysis_results)

        # Completion callback should be invoked regardless of triggers
        assert len(callback_invoked) >= 1


class TestSessionState:
    """Tests for session state management."""

    @pytest.fixture
    def integration(self):
        """Create integration for testing."""
        return ResearchCycleIntegration()

    def test_reset_session(self, integration):
        """Test session reset clears state."""
        integration._cycles_this_session = 5
        integration._last_outcome = MagicMock()

        integration.reset_session()

        assert integration._cycles_this_session == 0
        assert integration._last_outcome is None

    def test_get_last_outcome(self, integration):
        """Test getting last outcome."""
        assert integration.get_last_outcome() is None

        mock_outcome = MagicMock()
        integration._last_outcome = mock_outcome

        assert integration.get_last_outcome() is mock_outcome


class TestAutopilotIntegration:
    """Tests for autopilot integration methods."""

    @pytest.fixture
    def controller(self, tmp_path):
        """Create an AutopilotController instance."""
        from autopack.autonomy.autopilot import AutopilotController

        return AutopilotController(
            workspace_root=tmp_path,
            project_id="test-project",
            run_id="test-run",
            enabled=True,
        )

    def test_initialize_research_cycle_integration(self, controller):
        """Test initializing research cycle integration."""
        integration = controller.initialize_research_cycle_integration(
            min_budget_threshold=0.25,
        )

        assert integration is not None
        assert controller.get_research_cycle_integration() is integration

    def test_get_research_cycle_integration_not_initialized(self, controller):
        """Test getting integration when not initialized."""
        assert controller.get_research_cycle_integration() is None

    def test_should_execute_research_cycle_when_paused(self, controller):
        """Test should_execute returns False when paused."""
        controller._pause_task_generation("Test pause")

        result = controller.should_execute_research_cycle(
            gap_report={"summary": {"total_gaps": 10, "critical_gaps": 5}}
        )

        assert result is False

    def test_should_execute_research_cycle_with_critical_gaps(self, controller):
        """Test should_execute returns True with critical gaps."""
        controller.initialize_research_cycle_integration()

        result = controller.should_execute_research_cycle(
            gap_report={"summary": {"total_gaps": 3, "critical_gaps": 2}}
        )

        assert result is True

    def test_should_execute_research_cycle_with_many_gaps(self, controller):
        """Test should_execute returns True with many total gaps."""
        controller.initialize_research_cycle_integration()

        result = controller.should_execute_research_cycle(
            gap_report={"summary": {"total_gaps": 10, "critical_gaps": 0}}
        )

        assert result is True

    def test_should_execute_research_cycle_with_few_gaps(self, controller):
        """Test should_execute returns False with few gaps."""
        controller.initialize_research_cycle_integration()

        result = controller.should_execute_research_cycle(
            gap_report={"summary": {"total_gaps": 2, "critical_gaps": 0}}
        )

        assert result is False

    def test_get_research_cycle_metrics_not_initialized(self, controller):
        """Test getting metrics when not initialized."""
        assert controller.get_research_cycle_metrics() is None

    def test_get_research_cycle_metrics_initialized(self, controller):
        """Test getting metrics when initialized."""
        controller.initialize_research_cycle_integration()

        metrics = controller.get_research_cycle_metrics()

        assert metrics is not None
        assert isinstance(metrics, ResearchCycleMetrics)

    @pytest.mark.asyncio
    async def test_execute_integrated_research_cycle(self, controller):
        """Test executing integrated research cycle."""
        analysis_results = {
            "findings": [],
            "identified_gaps": [],
        }

        outcome = await controller.execute_integrated_research_cycle(
            analysis_results=analysis_results,
        )

        assert outcome is not None
        assert outcome.decision == ResearchCycleDecision.PROCEED
        assert controller.get_last_research_outcome() is outcome

    @pytest.mark.asyncio
    async def test_handle_research_outcome_block(self, controller):
        """Test handling BLOCK outcome pauses task generation."""
        controller.initialize_research_cycle_integration()

        outcome = ResearchCycleOutcome(
            decision=ResearchCycleDecision.BLOCK,
            budget_remaining=0.5,
            should_continue_execution=False,
            reason="Critical gaps",
        )

        await controller._handle_research_outcome(outcome)

        assert controller.is_task_generation_paused() is True
        assert "BLOCK" in controller.get_pause_reason()


class TestResearchCycleOutcome:
    """Tests for ResearchCycleOutcome dataclass."""

    def test_outcome_to_dict(self):
        """Test outcome serialization."""
        outcome = ResearchCycleOutcome(
            decision=ResearchCycleDecision.PROCEED,
            budget_remaining=0.8,
            should_continue_execution=True,
            reason="All good",
            cycle_time_ms=150,
        )

        data = outcome.to_dict()

        assert "research_cycle_outcome" in data
        assert data["research_cycle_outcome"]["decision"] == "proceed"
        assert data["research_cycle_outcome"]["budget_remaining"] == 0.8
        assert data["research_cycle_outcome"]["cycle_time_ms"] == 150

    def test_outcome_with_findings(self):
        """Test outcome with findings."""
        outcome = ResearchCycleOutcome(
            decision=ResearchCycleDecision.ADJUST_PLAN,
            findings=[{"data": "test"}],
            gaps_addressed=2,
            gaps_remaining=1,
            budget_remaining=0.6,
            should_continue_execution=True,
            plan_adjustments=[{"type": "test"}],
            reason="Adjustments needed",
        )

        data = outcome.to_dict()

        assert data["research_cycle_outcome"]["findings_count"] == 1
        assert data["research_cycle_outcome"]["gaps_addressed"] == 2
        assert data["research_cycle_outcome"]["gaps_remaining"] == 1
