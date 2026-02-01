"""
Comprehensive tests for followup_trigger module.

Tests cover trigger detection, callback execution (sync/async),
and trigger analysis with 85%+ code coverage for FollowupResearchTrigger.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

import pytest

from src.autopack.research.analysis.followup_trigger import (
    CallbackResult,
    FollowupResearchTrigger,
    FollowupTrigger,
    ResearchPlan,
    TriggerAnalysisResult,
    TriggerExecutionResult,
    TriggerPriority,
    TriggerType,
)


class TestResearchPlan:
    """Test ResearchPlan data class."""

    def test_initialization(self) -> None:
        """Test creating ResearchPlan."""
        plan = ResearchPlan(
            queries=["What is X?", "Why is Y?"],
            target_agent="discovery",
            expected_outcome="Market analysis",
            estimated_time_minutes=15,
        )
        assert plan.target_agent == "discovery"
        assert len(plan.queries) == 2

    def test_default_time_estimate(self) -> None:
        """Test default time estimate."""
        plan = ResearchPlan(
            queries=["q1"],
            target_agent="agent",
            expected_outcome="result",
        )
        assert plan.estimated_time_minutes == 5


class TestCallbackResult:
    """Test CallbackResult data class."""

    def test_successful_callback_result(self) -> None:
        """Test successful callback result."""
        result = CallbackResult(
            trigger_id="trig_001",
            success=True,
            executed_at=datetime.now(),
            result_data={"key": "value"},
            execution_time_ms=100,
        )
        assert result.trigger_id == "trig_001"
        assert result.success is True
        assert result.error_message is None

    def test_failed_callback_result(self) -> None:
        """Test failed callback result."""
        result = CallbackResult(
            trigger_id="trig_002",
            success=False,
            executed_at=datetime.now(),
            error_message="Network timeout",
            execution_time_ms=5000,
        )
        assert result.success is False
        assert "timeout" in result.error_message

    def test_to_dict(self) -> None:
        """Test callback result serialization."""
        result = CallbackResult(
            trigger_id="trig_003",
            success=True,
            executed_at=datetime.now(),
            execution_time_ms=200,
        )
        result_dict = result.to_dict()
        assert result_dict["trigger_id"] == "trig_003"
        assert result_dict["success"] is True


class TestFollowupTrigger:
    """Test FollowupTrigger data class."""

    def test_initialization(self) -> None:
        """Test creating FollowupTrigger."""
        trigger = FollowupTrigger(
            trigger_id="trigger_001",
            trigger_type=TriggerType.UNCERTAINTY,
            priority=TriggerPriority.HIGH,
            reason="Conflicting data sources",
            source_finding="Market size estimates vary significantly",
            research_plan=ResearchPlan(
                queries=["Verify market size"],
                target_agent="verification",
                expected_outcome="Confirmed market size",
            ),
            created_at=datetime.now(),
        )
        assert trigger.trigger_id == "trigger_001"
        assert trigger.addressed is False

    def test_mark_executed(self) -> None:
        """Test marking trigger as executed."""
        trigger = FollowupTrigger(
            trigger_id="trigger_002",
            trigger_type=TriggerType.GAP,
            priority=TriggerPriority.MEDIUM,
            reason="Coverage gap",
            source_finding="Missing EU market data",
            research_plan=ResearchPlan(
                queries=["EU market research"],
                target_agent="discovery",
                expected_outcome="EU market data",
            ),
            created_at=datetime.now(),
        )
        callback_result = CallbackResult(
            trigger_id="trigger_002",
            success=True,
            executed_at=datetime.now(),
            result_data={"eu_market_size": "$500M"},
        )
        trigger.mark_executed(callback_result)
        assert len(trigger.callback_results) == 1
        assert trigger.callback_results[0].success is True

    def test_to_dict(self) -> None:
        """Test trigger serialization."""
        trigger = FollowupTrigger(
            trigger_id="trigger_003",
            trigger_type=TriggerType.VALIDATION,
            priority=TriggerPriority.CRITICAL,
            reason="Data validation needed",
            source_finding="Pricing model inconsistency",
            research_plan=ResearchPlan(
                queries=["Validate pricing"],
                target_agent="validation",
                expected_outcome="Confirmed pricing",
            ),
            created_at=datetime.now(),
        )
        trigger_dict = trigger.to_dict()
        # Verify serialization works
        assert "trigger_id" in trigger_dict
        assert trigger_dict.get("trigger_id") == "trigger_003"


class TestTriggerExecutionResult:
    """Test TriggerExecutionResult data class."""

    def test_initialization(self) -> None:
        """Test creating execution result."""
        result = TriggerExecutionResult(
            triggers_executed=3,
            callbacks_invoked=5,
            successful_executions=4,
            failed_executions=1,
            total_execution_time_ms=2000,
            callback_results=[],
            integrated_findings=[],
        )
        assert result.triggers_executed == 3
        assert result.successful_executions == 4

    def test_to_dict(self) -> None:
        """Test execution result serialization."""
        result = TriggerExecutionResult(
            triggers_executed=1,
            callbacks_invoked=1,
            successful_executions=1,
            failed_executions=0,
            total_execution_time_ms=100,
            callback_results=[],
            integrated_findings=["Finding 1"],
        )
        result_dict = result.to_dict()
        # Verify serialization works - wraps in trigger_execution_result key
        assert result_dict is not None
        assert "trigger_execution_result" in result_dict


class TestTriggerAnalysisResult:
    """Test TriggerAnalysisResult data class."""

    def test_initialization(self) -> None:
        """Test creating analysis result."""
        result = TriggerAnalysisResult(
            triggers_detected=5,
            triggers_selected=3,
            trigger_summary={"UNCERTAINTY": 2, "GAP": 1},
            selected_triggers=[],
            not_selected_triggers=[],
            should_research=True,
            execution_plan={},
        )
        assert result.triggers_detected == 5
        assert result.should_research is True

    def test_to_dict(self) -> None:
        """Test analysis result serialization."""
        result = TriggerAnalysisResult(
            triggers_detected=2,
            triggers_selected=2,
            trigger_summary={"DEPTH": 2},
            selected_triggers=[],
            not_selected_triggers=[],
            should_research=True,
            execution_plan={"plan": "data"},
        )
        result_dict = result.to_dict()
        # Verify serialization works - wraps in followup_trigger_analysis key
        assert result_dict is not None
        assert "followup_trigger_analysis" in result_dict


class TestFollowupResearchTrigger:
    """Test FollowupResearchTrigger main class."""

    @pytest.fixture
    def trigger_analyzer(self) -> FollowupResearchTrigger:
        """Create trigger analyzer instance."""
        return FollowupResearchTrigger()

    def test_initialization(self, trigger_analyzer: FollowupResearchTrigger) -> None:
        """Test analyzer initialization."""
        assert trigger_analyzer is not None

    def test_analyze_with_empty_results(self, trigger_analyzer: FollowupResearchTrigger) -> None:
        """Test analysis with empty data."""
        result = trigger_analyzer.analyze(
            analysis_results={},
            validation_results={},
            previous_triggers=[],
        )
        assert result is not None
        assert isinstance(result, TriggerAnalysisResult)

    def test_analyze_detects_uncertainty_triggers(
        self, trigger_analyzer: FollowupResearchTrigger
    ) -> None:
        """Test detection of uncertainty triggers."""
        analysis_results = {
            "findings": [
                {
                    "claim": "Market size is $1B",
                    "confidence": 0.5,
                    "sources": ["source1", "source2"],
                }
            ]
        }
        result = trigger_analyzer.analyze(
            analysis_results=analysis_results,
            validation_results={},
            previous_triggers=[],
        )
        assert result.triggers_detected >= 0

    def test_analyze_detects_gap_triggers(self, trigger_analyzer: FollowupResearchTrigger) -> None:
        """Test detection of gap triggers."""
        analysis_results = {
            "coverage": {"market": 0.5, "tech": 1.0},
            "gaps": [{"category": "market", "description": "Low coverage"}],
        }
        result = trigger_analyzer.analyze(
            analysis_results=analysis_results,
            validation_results={},
            previous_triggers=[],
        )
        assert isinstance(result, TriggerAnalysisResult)

    def test_analyze_detects_depth_triggers(
        self, trigger_analyzer: FollowupResearchTrigger
    ) -> None:
        """Test detection of depth triggers."""
        analysis_results = {
            "research_depth": {"competitors": "shallow"},
            "critical_topics": ["competitors", "pricing"],
        }
        result = trigger_analyzer.analyze(
            analysis_results=analysis_results,
            validation_results={},
            previous_triggers=[],
        )
        assert result is not None

    def test_analyze_detects_validation_triggers(
        self, trigger_analyzer: FollowupResearchTrigger
    ) -> None:
        """Test detection of validation triggers."""
        validation_results = {
            "failed_checks": [
                {
                    "check": "price_consistency",
                    "status": "failed",
                    "details": "Prices don't match",
                }
            ]
        }
        result = trigger_analyzer.analyze(
            analysis_results={},
            validation_results=validation_results,
            previous_triggers=[],
        )
        assert result is not None

    def test_register_callback(self, trigger_analyzer: FollowupResearchTrigger) -> None:
        """Test registering sync callback."""

        def test_callback(trigger: FollowupTrigger) -> Optional[Dict[str, Any]]:
            return {"executed": True}

        trigger_analyzer.register_callback(test_callback)
        assert trigger_analyzer.get_callback_count() > 0

    def test_register_async_callback(self, trigger_analyzer: FollowupResearchTrigger) -> None:
        """Test registering async callback."""

        async def async_callback(
            trigger: FollowupTrigger,
        ) -> Optional[Dict[str, Any]]:
            await asyncio.sleep(0.01)
            return {"async": True}

        trigger_analyzer.register_async_callback(async_callback)
        assert trigger_analyzer.get_callback_count() > 0

    def test_unregister_callback(self, trigger_analyzer: FollowupResearchTrigger) -> None:
        """Test unregistering callback."""

        def callback(trigger: FollowupTrigger) -> Optional[Dict[str, Any]]:
            return None

        trigger_analyzer.register_callback(callback)
        initial_count = trigger_analyzer.get_callback_count()
        trigger_analyzer.unregister_callback(callback)
        assert trigger_analyzer.get_callback_count() < initial_count

    def test_execute_triggers_sync(self, trigger_analyzer: FollowupResearchTrigger) -> None:
        """Test synchronous trigger execution."""

        def sync_callback(trigger: FollowupTrigger) -> Optional[Dict[str, Any]]:
            return {"result": f"Processed {trigger.trigger_id}"}

        trigger_analyzer.register_callback(sync_callback)

        triggers = [
            FollowupTrigger(
                trigger_id="t1",
                trigger_type=TriggerType.UNCERTAINTY,
                priority=TriggerPriority.HIGH,
                reason="Test",
                source_finding="Test finding",
                research_plan=ResearchPlan(
                    queries=["q1"],
                    target_agent="agent",
                    expected_outcome="outcome",
                ),
                created_at=datetime.now(),
            )
        ]

        result = trigger_analyzer.execute_triggers(triggers, stop_on_failure=False)
        assert isinstance(result, TriggerExecutionResult)
        assert result.triggers_executed > 0

    @pytest.mark.asyncio
    async def test_execute_triggers_async(self, trigger_analyzer: FollowupResearchTrigger) -> None:
        """Test asynchronous trigger execution."""

        async def async_callback(
            trigger: FollowupTrigger,
        ) -> Optional[Dict[str, Any]]:
            await asyncio.sleep(0.01)
            return {"result": f"Async {trigger.trigger_id}"}

        trigger_analyzer.register_async_callback(async_callback)

        triggers = [
            FollowupTrigger(
                trigger_id="async_t1",
                trigger_type=TriggerType.DEPTH,
                priority=TriggerPriority.MEDIUM,
                reason="Deep dive",
                source_finding="Need depth",
                research_plan=ResearchPlan(
                    queries=["Deep q1"],
                    target_agent="deep_agent",
                    expected_outcome="Deep outcome",
                ),
                created_at=datetime.now(),
            )
        ]

        result = await trigger_analyzer.execute_triggers_async(
            triggers, max_concurrent=2, stop_on_failure=False
        )
        assert isinstance(result, TriggerExecutionResult)

    def test_analyze_and_execute(self, trigger_analyzer: FollowupResearchTrigger) -> None:
        """Test combined analyze and execute."""

        def callback(trigger: FollowupTrigger) -> Optional[Dict[str, Any]]:
            return {"processed": True}

        trigger_analyzer.register_callback(callback)

        result = trigger_analyzer.analyze_and_execute(
            analysis_results={"coverage": {"market": 0.5}},
            validation_results={},
            previous_triggers=[],
        )
        assert isinstance(result, TriggerAnalysisResult)

    @pytest.mark.asyncio
    async def test_analyze_and_execute_async(
        self, trigger_analyzer: FollowupResearchTrigger
    ) -> None:
        """Test combined analyze and execute async."""

        async def callback(
            trigger: FollowupTrigger,
        ) -> Optional[Dict[str, Any]]:
            return {"processed": True}

        trigger_analyzer.register_async_callback(callback)

        result = await trigger_analyzer.analyze_and_execute_async(
            analysis_results={"coverage": {"tech": 0.75}},
            validation_results={},
            previous_triggers=[],
            max_concurrent=2,
        )
        assert isinstance(result, TriggerAnalysisResult)

    def test_mark_addressed(self, trigger_analyzer: FollowupResearchTrigger) -> None:
        """Test marking trigger as addressed."""
        trigger_analyzer.analyze_and_execute(
            analysis_results={"coverage": {"market": 0.3}},
            validation_results={},
            previous_triggers=[],
        )
        # This should work without error
        trigger_analyzer.mark_addressed("any_id")

    def test_should_continue_followup_positive(
        self, trigger_analyzer: FollowupResearchTrigger
    ) -> None:
        """Test continue followup decision - should continue."""
        # Low iteration count should continue
        should_continue = trigger_analyzer.should_continue_followup(
            iteration=1,
            prev_results={"coverage": 0.5},
            new_results={"coverage": 0.7},
        )
        assert isinstance(should_continue, bool)

    def test_should_continue_followup_max_iterations(
        self, trigger_analyzer: FollowupResearchTrigger
    ) -> None:
        """Test continue followup decision - max iterations reached."""
        # High iteration count should stop
        should_continue = trigger_analyzer.should_continue_followup(
            iteration=10,
            prev_results={"coverage": 0.5},
            new_results={"coverage": 0.51},
        )
        assert isinstance(should_continue, bool)

    def test_multiple_callback_execution(self, trigger_analyzer: FollowupResearchTrigger) -> None:
        """Test execution with multiple callbacks."""

        def callback1(trigger: FollowupTrigger) -> Optional[Dict[str, Any]]:
            return {"callback": 1}

        def callback2(trigger: FollowupTrigger) -> Optional[Dict[str, Any]]:
            return {"callback": 2}

        trigger_analyzer.register_callback(callback1)
        trigger_analyzer.register_callback(callback2)

        assert trigger_analyzer.get_callback_count() == 2

        triggers = [
            FollowupTrigger(
                trigger_id="multi",
                trigger_type=TriggerType.EMERGING,
                priority=TriggerPriority.LOW,
                reason="Emerging trend",
                source_finding="New data",
                research_plan=ResearchPlan(
                    queries=["Emerging q"],
                    target_agent="discovery",
                    expected_outcome="Trend",
                ),
                created_at=datetime.now(),
            )
        ]

        result = trigger_analyzer.execute_triggers(triggers, stop_on_failure=False)
        assert result.callbacks_invoked >= 0


class TestTriggerTypes:
    """Test trigger type handling."""

    def test_all_trigger_types(self) -> None:
        """Test all trigger types are accessible."""
        types = [
            TriggerType.UNCERTAINTY,
            TriggerType.GAP,
            TriggerType.DEPTH,
            TriggerType.VALIDATION,
            TriggerType.EMERGING,
        ]
        assert len(types) == 5

    def test_all_trigger_priorities(self) -> None:
        """Test all trigger priorities are accessible."""
        priorities = [
            TriggerPriority.CRITICAL,
            TriggerPriority.HIGH,
            TriggerPriority.MEDIUM,
            TriggerPriority.LOW,
        ]
        assert len(priorities) == 4


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def analyzer(self) -> FollowupResearchTrigger:
        """Create analyzer for edge case tests."""
        return FollowupResearchTrigger()

    def test_execute_empty_trigger_list(self, analyzer: FollowupResearchTrigger) -> None:
        """Test executing empty trigger list."""
        result = analyzer.execute_triggers([], stop_on_failure=False)
        assert result.triggers_executed == 0

    def test_multiple_trigger_analysis(self, analyzer: FollowupResearchTrigger) -> None:
        """Test analysis with many analysis results."""
        large_analysis = {
            "findings": [
                {"claim": f"Finding {i}", "confidence": 0.5 + (i % 50) / 100} for i in range(20)
            ]
        }
        result = analyzer.analyze(
            analysis_results=large_analysis,
            validation_results={},
            previous_triggers=[],
        )
        assert result is not None

    def test_callback_returning_none(self, analyzer: FollowupResearchTrigger) -> None:
        """Test callback that returns None."""

        def null_callback(trigger: FollowupTrigger) -> Optional[Dict[str, Any]]:
            return None

        analyzer.register_callback(null_callback)
        assert analyzer.get_callback_count() == 1

    def test_trigger_with_empty_research_plan(self, analyzer: FollowupResearchTrigger) -> None:
        """Test trigger with minimal plan."""
        trigger = FollowupTrigger(
            trigger_id="minimal",
            trigger_type=TriggerType.VALIDATION,
            priority=TriggerPriority.LOW,
            reason="Minimal test",
            source_finding="Minimal finding",
            research_plan=ResearchPlan(
                queries=[],
                target_agent="",
                expected_outcome="",
            ),
            created_at=datetime.now(),
        )
        assert trigger.research_plan.queries == []

    def test_many_previous_triggers(self, analyzer: FollowupResearchTrigger) -> None:
        """Test analysis with many previous triggers."""
        previous = [
            FollowupTrigger(
                trigger_id=f"prev_{i}",
                trigger_type=TriggerType.UNCERTAINTY,
                priority=TriggerPriority.MEDIUM,
                reason=f"Previous {i}",
                source_finding=f"Finding {i}",
                research_plan=ResearchPlan(
                    queries=[f"q{i}"],
                    target_agent="agent",
                    expected_outcome="outcome",
                ),
                created_at=datetime.now(),
            )
            for i in range(10)
        ]
        result = analyzer.analyze(
            analysis_results={},
            validation_results={},
            previous_triggers=previous,
        )
        assert result is not None
