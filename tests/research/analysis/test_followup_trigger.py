"""Tests for IMP-HIGH-005: FollowupResearchTrigger callback execution.

This module tests the callback registration and execution mechanism
in the FollowupResearchTrigger class.
"""

import asyncio
from typing import Dict, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from autopack.research.analysis.followup_trigger import (
    CallbackResult, FollowupResearchTrigger, FollowupTrigger, ResearchPlan,
    TriggerExecutionResult, TriggerPriority, TriggerType)


class TestCallbackRegistration:
    """Tests for callback registration and unregistration."""

    @pytest.fixture
    def trigger(self):
        """Create a FollowupResearchTrigger instance."""
        return FollowupResearchTrigger()

    def test_initial_callback_count_is_zero(self, trigger):
        """Test that no callbacks are registered initially."""
        assert trigger.get_callback_count() == 0

    def test_register_sync_callback(self, trigger):
        """Test registering a synchronous callback."""

        def callback(t: FollowupTrigger) -> Optional[Dict]:
            return {"result": "success"}

        trigger.register_callback(callback)
        assert trigger.get_callback_count() == 1

    def test_register_multiple_callbacks(self, trigger):
        """Test registering multiple callbacks."""
        callback1 = MagicMock(return_value=None)
        callback2 = MagicMock(return_value=None)

        trigger.register_callback(callback1)
        trigger.register_callback(callback2)

        assert trigger.get_callback_count() == 2

    def test_register_async_callback(self, trigger):
        """Test registering an async callback."""

        async def async_callback(t: FollowupTrigger) -> Optional[Dict]:
            return {"result": "async_success"}

        trigger.register_async_callback(async_callback)
        assert trigger.get_callback_count() == 1

    def test_register_both_sync_and_async_callbacks(self, trigger):
        """Test registering both sync and async callbacks."""
        sync_callback = MagicMock(return_value=None)

        async def async_callback(t: FollowupTrigger) -> Optional[Dict]:
            return None

        trigger.register_callback(sync_callback)
        trigger.register_async_callback(async_callback)

        assert trigger.get_callback_count() == 2

    def test_unregister_sync_callback(self, trigger):
        """Test unregistering a synchronous callback."""
        callback = MagicMock(return_value=None)
        trigger.register_callback(callback)

        result = trigger.unregister_callback(callback)

        assert result is True
        assert trigger.get_callback_count() == 0

    def test_unregister_nonexistent_callback(self, trigger):
        """Test unregistering a callback that wasn't registered."""
        callback = MagicMock(return_value=None)

        result = trigger.unregister_callback(callback)

        assert result is False

    def test_unregister_async_callback(self, trigger):
        """Test unregistering an async callback."""

        async def async_callback(t: FollowupTrigger) -> Optional[Dict]:
            return None

        trigger.register_async_callback(async_callback)
        result = trigger.unregister_async_callback(async_callback)

        assert result is True
        assert trigger.get_callback_count() == 0

    def test_duplicate_callback_not_added(self, trigger):
        """Test that registering the same callback twice doesn't add duplicates."""
        callback = MagicMock(return_value=None)

        trigger.register_callback(callback)
        trigger.register_callback(callback)

        assert trigger.get_callback_count() == 1


class TestSyncCallbackExecution:
    """Tests for synchronous callback execution."""

    @pytest.fixture
    def trigger(self):
        """Create a FollowupResearchTrigger instance."""
        return FollowupResearchTrigger()

    @pytest.fixture
    def sample_triggers(self):
        """Create sample FollowupTrigger instances."""
        return [
            FollowupTrigger(
                trigger_id="trig-001",
                trigger_type=TriggerType.GAP,
                priority=TriggerPriority.HIGH,
                reason="Missing market data",
                source_finding="gap:market",
                research_plan=ResearchPlan(
                    queries=["market size research"],
                    target_agent="market-research-agent",
                    expected_outcome="Market size data",
                ),
            ),
            FollowupTrigger(
                trigger_id="trig-002",
                trigger_type=TriggerType.UNCERTAINTY,
                priority=TriggerPriority.MEDIUM,
                reason="Low confidence on pricing",
                source_finding="finding:pricing",
                research_plan=ResearchPlan(
                    queries=["competitor pricing analysis"],
                    target_agent="competitive-analysis-agent",
                    expected_outcome="Pricing insights",
                ),
            ),
        ]

    def test_execute_with_no_callbacks_returns_empty_result(self, trigger, sample_triggers):
        """Test execution with no callbacks registered returns empty result."""
        result = trigger.execute_triggers(sample_triggers)

        assert isinstance(result, TriggerExecutionResult)
        assert result.triggers_executed == 0
        assert result.callbacks_invoked == 0
        assert result.successful_executions == 0
        assert result.failed_executions == 0

    def test_execute_invokes_callback_for_each_trigger(self, trigger, sample_triggers):
        """Test that callback is invoked for each trigger."""
        callback = MagicMock(return_value={"data": "test"})
        trigger.register_callback(callback)

        trigger.execute_triggers(sample_triggers)

        assert callback.call_count == 2

    def test_execute_returns_result_data(self, trigger, sample_triggers):
        """Test that execution returns callback result data."""
        callback = MagicMock(return_value={"findings": ["data1", "data2"]})
        trigger.register_callback(callback)

        result = trigger.execute_triggers(sample_triggers)

        assert result.successful_executions == 2
        assert len(result.integrated_findings) == 2
        assert result.integrated_findings[0] == {"findings": ["data1", "data2"]}

    def test_execute_marks_triggers_as_addressed(self, trigger, sample_triggers):
        """Test that successful execution marks triggers as addressed."""
        callback = MagicMock(return_value=None)
        trigger.register_callback(callback)

        trigger.execute_triggers(sample_triggers)

        assert sample_triggers[0].addressed is True
        assert sample_triggers[1].addressed is True

    def test_execute_handles_callback_exceptions(self, trigger, sample_triggers):
        """Test that callback exceptions are handled gracefully."""
        callback = MagicMock(side_effect=ValueError("Test error"))
        trigger.register_callback(callback)

        result = trigger.execute_triggers(sample_triggers)

        assert result.failed_executions == 2
        assert result.successful_executions == 0
        assert len(result.callback_results) == 2
        assert result.callback_results[0].success is False
        assert "Test error" in result.callback_results[0].error_message

    def test_execute_stop_on_failure(self, trigger, sample_triggers):
        """Test that stop_on_failure stops execution after first failure."""
        callback = MagicMock(side_effect=ValueError("Test error"))
        trigger.register_callback(callback)

        result = trigger.execute_triggers(sample_triggers, stop_on_failure=True)

        # Should stop after first failure
        assert result.failed_executions == 1
        assert callback.call_count == 1

    def test_execute_skips_already_addressed_triggers(self, trigger, sample_triggers):
        """Test that already addressed triggers are skipped."""
        callback = MagicMock(return_value=None)
        trigger.register_callback(callback)

        # Mark first trigger as addressed
        trigger.mark_addressed("trig-001")

        result = trigger.execute_triggers(sample_triggers)

        # Should only execute for trig-002
        assert callback.call_count == 1
        assert result.successful_executions == 1

    def test_execute_records_execution_time(self, trigger, sample_triggers):
        """Test that execution time is recorded."""
        import time

        def slow_callback(t: FollowupTrigger) -> Optional[Dict]:
            time.sleep(0.01)  # 10ms delay
            return None

        trigger.register_callback(slow_callback)

        result = trigger.execute_triggers(sample_triggers[:1])

        assert result.total_execution_time_ms >= 10
        assert result.callback_results[0].execution_time_ms >= 10


class TestAsyncCallbackExecution:
    """Tests for asynchronous callback execution."""

    @pytest.fixture
    def trigger(self):
        """Create a FollowupResearchTrigger instance."""
        return FollowupResearchTrigger()

    @pytest.fixture
    def sample_triggers(self):
        """Create sample FollowupTrigger instances."""
        return [
            FollowupTrigger(
                trigger_id="async-001",
                trigger_type=TriggerType.DEPTH,
                priority=TriggerPriority.HIGH,
                reason="Needs deep analysis",
                source_finding="coverage:api",
                research_plan=ResearchPlan(
                    queries=["API deep dive"],
                    target_agent="deep-dive-research",
                    expected_outcome="API analysis",
                ),
            ),
        ]

    @pytest.mark.asyncio
    async def test_async_execute_with_async_callback(self, trigger, sample_triggers):
        """Test async execution with async callback."""
        async_callback = AsyncMock(return_value={"async_data": "result"})
        trigger.register_async_callback(async_callback)

        result = await trigger.execute_triggers_async(sample_triggers)

        assert result.successful_executions == 1
        async_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_execute_with_sync_callback(self, trigger, sample_triggers):
        """Test async execution can also run sync callbacks."""
        sync_callback = MagicMock(return_value={"sync_data": "result"})
        trigger.register_callback(sync_callback)

        result = await trigger.execute_triggers_async(sample_triggers)

        assert result.successful_executions == 1
        sync_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_execute_handles_exceptions(self, trigger, sample_triggers):
        """Test that async execution handles exceptions."""
        async_callback = AsyncMock(side_effect=ValueError("Async error"))
        trigger.register_async_callback(async_callback)

        result = await trigger.execute_triggers_async(sample_triggers)

        assert result.failed_executions == 1
        assert result.successful_executions == 0

    @pytest.mark.asyncio
    async def test_async_execute_respects_max_concurrent(self, trigger):
        """Test that max_concurrent is respected."""
        execution_count = 0
        max_concurrent_seen = 0
        lock = asyncio.Lock()

        async def tracking_callback(t: FollowupTrigger) -> Optional[Dict]:
            nonlocal execution_count, max_concurrent_seen
            async with lock:
                execution_count += 1
                if execution_count > max_concurrent_seen:
                    max_concurrent_seen = execution_count
            await asyncio.sleep(0.05)  # Simulate work
            async with lock:
                execution_count -= 1
            return None

        trigger.register_async_callback(tracking_callback)

        # Create 5 triggers
        triggers = [
            FollowupTrigger(
                trigger_id=f"concurrent-{i}",
                trigger_type=TriggerType.GAP,
                priority=TriggerPriority.MEDIUM,
                reason=f"Test trigger {i}",
                source_finding=f"test:{i}",
                research_plan=ResearchPlan(
                    queries=["test"],
                    target_agent="test",
                    expected_outcome="test",
                ),
            )
            for i in range(5)
        ]

        await trigger.execute_triggers_async(triggers, max_concurrent=2)

        # Max concurrent should be limited to 2
        assert max_concurrent_seen <= 2


class TestAnalyzeAndExecute:
    """Tests for combined analyze and execute methods."""

    @pytest.fixture
    def trigger(self):
        """Create a FollowupResearchTrigger instance."""
        return FollowupResearchTrigger()

    @pytest.fixture
    def analysis_results_with_gaps(self):
        """Create analysis results that will trigger research."""
        return {
            "findings": [
                {
                    "id": "finding-1",
                    "summary": "Market data incomplete",
                    "confidence": 0.4,  # Below threshold
                    "topic": "market",
                }
            ],
            "identified_gaps": [
                {
                    "category": "market_research",
                    "description": "Missing competitor analysis",
                    "suggested_queries": ["competitor market share"],
                }
            ],
        }

    def test_analyze_and_execute_with_callbacks(self, trigger, analysis_results_with_gaps):
        """Test analyze_and_execute runs callbacks when triggers detected."""
        callback = MagicMock(return_value={"research_data": "found"})
        trigger.register_callback(callback)

        result = trigger.analyze_and_execute(analysis_results_with_gaps)

        assert result.should_research is True
        assert result.execution_result is not None
        assert result.execution_result.successful_executions > 0

    def test_analyze_and_execute_without_callbacks(self, trigger, analysis_results_with_gaps):
        """Test analyze_and_execute without callbacks still returns result."""
        result = trigger.analyze_and_execute(analysis_results_with_gaps)

        assert result.should_research is True
        assert result.execution_result is None  # No callbacks to execute

    @pytest.mark.asyncio
    async def test_analyze_and_execute_async(self, trigger, analysis_results_with_gaps):
        """Test async analyze and execute."""
        async_callback = AsyncMock(return_value={"async_data": "result"})
        trigger.register_async_callback(async_callback)

        result = await trigger.analyze_and_execute_async(analysis_results_with_gaps)

        assert result.should_research is True
        assert result.execution_result is not None


class TestFollowupTriggerMarkExecuted:
    """Tests for FollowupTrigger.mark_executed method."""

    def test_mark_executed_adds_result(self):
        """Test that mark_executed adds callback result."""
        trigger = FollowupTrigger(
            trigger_id="test-001",
            trigger_type=TriggerType.GAP,
            priority=TriggerPriority.HIGH,
            reason="Test",
            source_finding="test",
            research_plan=ResearchPlan(
                queries=["test"],
                target_agent="test",
                expected_outcome="test",
            ),
        )

        result = CallbackResult(
            trigger_id="test-001",
            success=True,
            result_data={"data": "test"},
        )

        trigger.mark_executed(result)

        assert len(trigger.callback_results) == 1
        assert trigger.callback_results[0] == result

    def test_mark_executed_updates_addressed_on_success(self):
        """Test that successful execution marks trigger as addressed."""
        trigger = FollowupTrigger(
            trigger_id="test-001",
            trigger_type=TriggerType.GAP,
            priority=TriggerPriority.HIGH,
            reason="Test",
            source_finding="test",
            research_plan=ResearchPlan(
                queries=["test"],
                target_agent="test",
                expected_outcome="test",
            ),
        )

        result = CallbackResult(
            trigger_id="test-001",
            success=True,
        )

        trigger.mark_executed(result)

        assert trigger.addressed is True
        assert trigger.addressed_at is not None

    def test_mark_executed_does_not_update_addressed_on_failure(self):
        """Test that failed execution doesn't mark trigger as addressed."""
        trigger = FollowupTrigger(
            trigger_id="test-001",
            trigger_type=TriggerType.GAP,
            priority=TriggerPriority.HIGH,
            reason="Test",
            source_finding="test",
            research_plan=ResearchPlan(
                queries=["test"],
                target_agent="test",
                expected_outcome="test",
            ),
        )

        result = CallbackResult(
            trigger_id="test-001",
            success=False,
            error_message="Test error",
        )

        trigger.mark_executed(result)

        assert trigger.addressed is False
        assert trigger.addressed_at is None


class TestTriggerExecutionResultSerialization:
    """Tests for TriggerExecutionResult serialization."""

    def test_to_dict(self):
        """Test TriggerExecutionResult.to_dict serialization."""
        result = TriggerExecutionResult(
            triggers_executed=5,
            callbacks_invoked=10,
            successful_executions=8,
            failed_executions=2,
            total_execution_time_ms=1500,
            integrated_findings=[{"data": "test"}],
        )

        data = result.to_dict()

        assert data["trigger_execution_result"]["triggers_executed"] == 5
        assert data["trigger_execution_result"]["callbacks_invoked"] == 10
        assert data["trigger_execution_result"]["successful_executions"] == 8
        assert data["trigger_execution_result"]["failed_executions"] == 2
        assert data["trigger_execution_result"]["total_execution_time_ms"] == 1500
        assert data["trigger_execution_result"]["integrated_findings_count"] == 1
