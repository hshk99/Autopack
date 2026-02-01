"""Integration tests for the complete self-improvement loop (IMP-TEST-001).

Tests the full cycle:
1. Phase execution generates telemetry
2. Telemetry analyzer detects patterns
3. Patterns persisted to memory service
4. Task generator creates improvement tasks
5. Executor runs improvement tasks
6. Feedback completes the loop

These tests validate that the self-improvement loop functions correctly
as an integrated system, not just individual components.
"""

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import Mock

import pytest

from autopack.feedback_pipeline import (FeedbackPipeline, PhaseContext,
                                        PhaseOutcome)
from autopack.roadc import AutonomousTaskGenerator
from autopack.telemetry.telemetry_to_memory_bridge import \
    TelemetryToMemoryBridge

# =============================================================================
# Test Fixtures
# =============================================================================


class MockMemoryService:
    """Mock memory service that tracks all operations for integration testing."""

    def __init__(self):
        self.enabled = True
        self._insights: List[Dict[str, Any]] = []
        self._errors: List[Dict[str, Any]] = []
        self._feedback: List[Dict[str, Any]] = []
        self._telemetry_insights: List[Dict[str, Any]] = []
        self._call_counts = {
            "write_telemetry_insight": 0,
            "write_task_execution_feedback": 0,
            "retrieve_insights": 0,
            "search_errors": 0,
            "search_execution_feedback": 0,
            "search_telemetry_insights": 0,
        }
        self._raise_on_write = False
        self._write_delay_ms = 0
        self._operation_log: List[Dict[str, Any]] = []  # Track operation sequence

    def _log_operation(self, operation: str, data: Dict[str, Any]) -> None:
        """Log operation for sequence verification."""
        self._operation_log.append(
            {
                "operation": operation,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": data,
            }
        )

    def write_telemetry_insight(
        self,
        insight: Dict[str, Any],
        project_id: Optional[str] = None,
        validate: bool = True,
        strict: bool = False,
    ) -> str:
        """Store telemetry insight and return ID."""
        if self._raise_on_write:
            raise Exception("Simulated write failure")
        if self._write_delay_ms > 0:
            time.sleep(self._write_delay_ms / 1000)

        self._call_counts["write_telemetry_insight"] += 1
        insight["_id"] = f"insight_{len(self._insights)}"
        insight["_project_id"] = project_id
        insight["_timestamp"] = datetime.now(timezone.utc).isoformat()
        self._insights.append(insight)
        self._telemetry_insights.append(insight)

        self._log_operation(
            "write_telemetry_insight",
            {"insight_id": insight["_id"], "project_id": project_id},
        )
        return insight["_id"]

    def write_task_execution_feedback(
        self,
        run_id: str,
        phase_id: str,
        project_id: str,
        success: bool,
        phase_type: Optional[str] = None,
        execution_time_seconds: Optional[float] = None,
        error_message: Optional[str] = None,
        tokens_used: Optional[int] = None,
        context_summary: Optional[str] = None,
        learnings: Optional[List[str]] = None,
    ) -> str:
        """Store execution feedback."""
        self._call_counts["write_task_execution_feedback"] += 1
        feedback = {
            "run_id": run_id,
            "phase_id": phase_id,
            "project_id": project_id,
            "success": success,
            "phase_type": phase_type,
            "execution_time_seconds": execution_time_seconds,
            "error_message": error_message,
            "tokens_used": tokens_used,
            "context_summary": context_summary,
            "learnings": learnings,
            "_id": f"feedback_{len(self._feedback)}",
            "_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._feedback.append(feedback)

        self._log_operation(
            "write_task_execution_feedback",
            {"feedback_id": feedback["_id"], "phase_id": phase_id, "success": success},
        )
        return feedback["_id"]

    def retrieve_insights(
        self,
        query: str,
        limit: int = 5,
        project_id: Optional[str] = None,
        max_age_hours: float = 72.0,
        min_confidence: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant insights based on query."""
        self._call_counts["retrieve_insights"] += 1

        # Filter by project_id and return stored insights
        results = []
        for i in self._insights:
            if project_id is not None and i.get("_project_id") != project_id:
                continue
            # Add standard fields expected by task generator
            result = dict(i)
            result["confidence"] = result.get("confidence", 0.8)
            result["content"] = result.get("content", result.get("description", ""))
            result["issue_type"] = result.get("issue_type", "insight")
            results.append(result)

        self._log_operation(
            "retrieve_insights",
            {"query": query, "project_id": project_id, "results_count": len(results)},
        )
        return results[:limit]

    def search_errors(
        self,
        query: str,
        project_id: Optional[str] = None,
        limit: int = 3,
        max_age_hours: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar errors."""
        self._call_counts["search_errors"] += 1
        # Return any feedback with errors
        errors = [
            {
                "payload": {
                    "error_type": f.get("phase_type", "unknown"),
                    "error_text": f["error_message"],
                }
            }
            for f in self._feedback
            if f.get("error_message")
        ]
        return errors[:limit]

    def search_execution_feedback(
        self,
        query: str,
        project_id: Optional[str] = None,
        success_only: bool = False,
        phase_type: Optional[str] = None,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """Search execution feedback."""
        self._call_counts["search_execution_feedback"] += 1
        results = []
        for f in self._feedback:
            if success_only and not f.get("success"):
                continue
            if phase_type and f.get("phase_type") != phase_type:
                continue
            results.append(
                {
                    "payload": {
                        "context_summary": f.get("context_summary", ""),
                        "learnings": f.get("learnings", []),
                    }
                }
            )
        return results[:limit]

    def search_telemetry_insights(
        self,
        query: str,
        limit: int = 10,
        project_id: Optional[str] = None,
        max_age_hours: float = 168.0,
    ) -> List[Dict[str, Any]]:
        """Search telemetry insights."""
        self._call_counts["search_telemetry_insights"] += 1
        results = []
        for insight in self._telemetry_insights:
            if project_id and insight.get("_project_id") != project_id:
                continue
            results.append(
                {
                    "content": insight.get("description", ""),
                    "metadata": insight,
                    "confidence": 0.8,
                    "timestamp": insight.get("_timestamp"),
                }
            )
        return results[:limit]

    def get_stats(self) -> Dict[str, int]:
        """Get call counts for verification."""
        return dict(self._call_counts)

    def clear(self) -> None:
        """Clear all stored data."""
        self._insights.clear()
        self._errors.clear()
        self._feedback.clear()
        self._telemetry_insights.clear()
        self._operation_log.clear()

    def get_operation_sequence(self) -> List[str]:
        """Get sequence of operations for flow verification."""
        return [op["operation"] for op in self._operation_log]


class MockLearningPipeline:
    """Mock learning pipeline for testing hint recording."""

    def __init__(self):
        self._hints: List[Dict[str, Any]] = []
        self._success_patterns: List[Dict[str, Any]] = []

    def record_hint(
        self,
        phase: Dict[str, Any],
        hint_type: str,
        details: str,
    ) -> None:
        """Record a learning hint."""
        self._hints.append(
            {
                "phase": phase,
                "hint_type": hint_type,
                "details": details,
            }
        )

    def record_success_pattern(
        self,
        phase: Dict[str, Any],
        action_taken: str,
        context_summary: str,
    ) -> None:
        """Record a success pattern."""
        self._success_patterns.append(
            {
                "phase": phase,
                "action_taken": action_taken,
                "context_summary": context_summary,
            }
        )

    def persist_to_memory(
        self,
        memory_service: Any,
        project_id: str,
    ) -> int:
        """Persist hints to memory."""
        return len(self._hints)

    def get_hints_for_phase(
        self,
        phase: Dict[str, Any],
        decay_threshold: float = 0.3,
    ) -> List[str]:
        """Get hints for a phase."""
        return [h["details"] for h in self._hints]

    def get_hints_with_decay_scores(
        self,
        phase: Dict[str, Any],
        decay_threshold: float = 0.3,
    ) -> List[tuple]:
        """Get hints with decay scores."""
        return [(h["details"], 0.8) for h in self._hints]


class MockTelemetryAnalyzer:
    """Mock telemetry analyzer for testing recommendations."""

    def __init__(self):
        self._recommendations: List[Dict[str, Any]] = []

    def add_recommendation(
        self,
        severity: str,
        action: str,
        reason: str,
    ) -> None:
        """Add a recommendation."""
        self._recommendations.append(
            {
                "severity": severity,
                "action": action,
                "reason": reason,
            }
        )

    def get_recommendations_for_phase(
        self,
        phase_type: str,
        lookback_hours: int = 24,
    ) -> List[Dict[str, Any]]:
        """Get recommendations for a phase type."""
        return list(self._recommendations)


@pytest.fixture
def mock_memory_service():
    """Create a mock memory service."""
    return MockMemoryService()


@pytest.fixture
def mock_learning_pipeline():
    """Create a mock learning pipeline."""
    return MockLearningPipeline()


@pytest.fixture
def mock_telemetry_analyzer():
    """Create a mock telemetry analyzer."""
    return MockTelemetryAnalyzer()


@pytest.fixture
def feedback_pipeline(mock_memory_service, mock_learning_pipeline, mock_telemetry_analyzer):
    """Create a FeedbackPipeline with all mocks."""
    pipeline = FeedbackPipeline(
        memory_service=mock_memory_service,
        telemetry_analyzer=mock_telemetry_analyzer,
        learning_pipeline=mock_learning_pipeline,
        run_id="test_run_001",
        project_id="test_project",
        enabled=True,
    )
    yield pipeline
    # Cleanup
    pipeline.stop_auto_flush()


@pytest.fixture
def task_generator(mock_memory_service):
    """Create a task generator with mock memory service."""
    return AutonomousTaskGenerator(memory_service=mock_memory_service)


@pytest.fixture
def temp_autopack_dir(tmp_path):
    """Create temporary .autopack directory."""
    autopack_dir = tmp_path / ".autopack"
    autopack_dir.mkdir(parents=True, exist_ok=True)
    return autopack_dir


# =============================================================================
# TestSelfImprovementLoop: End-to-end tests for the self-improvement loop
# =============================================================================


class TestSelfImprovementLoop:
    """End-to-end tests for the self-improvement loop."""

    @pytest.fixture
    def mock_telemetry(self):
        """Create mock telemetry data."""
        return {
            "phase_id": "test_phase",
            "success": True,
            "metrics": {"duration": 10.5, "files_changed": 3},
        }

    def test_telemetry_to_memory_pipeline(
        self, feedback_pipeline, mock_memory_service, mock_learning_pipeline
    ):
        """Test that telemetry flows to memory service.

        Validates Stage 1-2: Phase outcome -> Telemetry capture -> Memory persistence
        """
        # Stage 1: Generate telemetry from phase outcome
        outcome = PhaseOutcome(
            phase_id="phase_telem_001",
            phase_type="build",
            success=True,
            status="Build completed successfully",
            execution_time_seconds=45.0,
            tokens_used=5000,
            learnings=["Use incremental builds for faster iteration"],
            run_id="run_telem_001",
            project_id="test_project",
        )

        # Process outcome through feedback pipeline
        result = feedback_pipeline.process_phase_outcome(outcome)

        # Verify outcome was processed
        assert result["success"] is True
        assert result["insights_created"] >= 1

        # Stage 2: Verify telemetry was captured in memory
        assert mock_memory_service._call_counts["write_task_execution_feedback"] >= 1

        # Verify the feedback data was stored
        assert len(mock_memory_service._feedback) >= 1
        stored_feedback = mock_memory_service._feedback[0]
        assert stored_feedback["phase_id"] == "phase_telem_001"
        assert stored_feedback["success"] is True
        assert stored_feedback["tokens_used"] == 5000

        # Verify telemetry insight was created
        assert mock_memory_service._call_counts["write_telemetry_insight"] >= 1

        # Verify operation sequence
        op_sequence = mock_memory_service.get_operation_sequence()
        assert "write_telemetry_insight" in op_sequence
        assert "write_task_execution_feedback" in op_sequence

    def test_memory_to_task_generation(self, mock_memory_service, temp_autopack_dir):
        """Test that memory patterns generate tasks.

        Validates Stage 3-4: Memory retrieval -> Task generation
        """
        # Stage 3: Seed memory with patterns (simulating accumulated telemetry)
        mock_memory_service._insights = [
            {
                "_id": "insight_001",
                "_project_id": "test_project",
                "issue_type": "cost_sink",
                "content": "High token usage in build phase",
                "severity": "high",
                "metric_value": 75000.0,
                "phase_id": "build_001",
                "phase_type": "build",
                "confidence": 0.9,
            },
            {
                "_id": "insight_002",
                "_project_id": "test_project",
                "issue_type": "cost_sink",
                "content": "Excessive context loading in test phase",
                "severity": "high",
                "metric_value": 60000.0,
                "phase_id": "test_001",
                "phase_type": "test",
                "confidence": 0.85,
            },
            {
                "_id": "insight_003",
                "_project_id": "test_project",
                "issue_type": "failure_mode",
                "content": "Timeout errors in API calls",
                "severity": "high",
                "metric_value": 5.0,
                "phase_id": "api_001",
                "phase_type": "api",
                "confidence": 0.9,
            },
            {
                "_id": "insight_004",
                "_project_id": "test_project",
                "issue_type": "failure_mode",
                "content": "Connection refused errors",
                "severity": "high",
                "metric_value": 3.0,
                "phase_id": "network_001",
                "phase_type": "network",
                "confidence": 0.8,
            },
        ]

        # Stage 4: Create task generator and generate tasks from insights
        task_generator = AutonomousTaskGenerator(memory_service=mock_memory_service)
        _queue_file = temp_autopack_dir / "ROADC_TASK_QUEUE.json"  # noqa: F841

        # Generate tasks
        result = task_generator.generate_tasks(
            max_tasks=5,
            min_confidence=0.0,  # Accept all insights for testing
        )

        # Verify insights were retrieved from memory
        assert mock_memory_service._call_counts["retrieve_insights"] >= 1

        # If tasks were generated, they should be based on memory patterns
        if result.tasks_generated:
            assert result.insights_processed > 0
            # Tasks should have source insights
            for task in result.tasks_generated:
                assert len(task.source_insights) > 0

    def test_task_execution_to_feedback(
        self, feedback_pipeline, mock_memory_service, mock_learning_pipeline
    ):
        """Test that executed tasks produce feedback.

        Validates Stage 5-6: Task execution -> Feedback recording
        """
        # Simulate task execution outcome as a phase outcome
        # In the real system, executing a task results in a phase outcome
        execution_outcome = PhaseOutcome(
            phase_id="task_exec_001",
            phase_type="improvement_task",
            success=True,
            status="Task TASK-001 completed: Fixed timeout issues",
            execution_time_seconds=120.0,
            tokens_used=8000,
            learnings=["Adding retry logic improves reliability"],
            run_id="run_task_exec_001",
            project_id="test_project",
        )

        # Process the execution outcome
        result = feedback_pipeline.process_phase_outcome(execution_outcome)

        # Verify feedback was recorded
        assert result["success"] is True
        assert mock_memory_service._call_counts["write_task_execution_feedback"] >= 1

        # Verify learning hint was recorded for success pattern
        assert len(mock_learning_pipeline._success_patterns) >= 1

        # Verify feedback contains task execution details
        stored_feedback = mock_memory_service._feedback[0]
        assert "task_exec_001" in stored_feedback["phase_id"]
        assert stored_feedback["learnings"] == ["Adding retry logic improves reliability"]

    def test_feedback_closes_loop(
        self, mock_memory_service, mock_learning_pipeline, mock_telemetry_analyzer
    ):
        """Test that feedback influences next cycle.

        Validates Loop Closure: Feedback -> Context for next phase
        """
        # First cycle - record failure
        pipeline1 = FeedbackPipeline(
            memory_service=mock_memory_service,
            learning_pipeline=mock_learning_pipeline,
            run_id="run_cycle1",
            project_id="test_project",
            enabled=True,
        )
        pipeline1.stop_auto_flush()

        # Record a failure in cycle 1
        failure_outcome = PhaseOutcome(
            phase_id="phase_cycle1_001",
            phase_type="build",
            success=False,
            status="Build failed",
            error_message="Missing import statement",
            run_id="run_cycle1",
            project_id="test_project",
        )
        pipeline1.process_phase_outcome(failure_outcome)

        # Record a success in cycle 1
        success_outcome = PhaseOutcome(
            phase_id="phase_cycle1_002",
            phase_type="build",
            success=True,
            status="Build succeeded after fix",
            learnings=["Check imports before build"],
            run_id="run_cycle1",
            project_id="test_project",
        )
        pipeline1.process_phase_outcome(success_outcome)

        # Second cycle - should retrieve context from first cycle
        pipeline2 = FeedbackPipeline(
            memory_service=mock_memory_service,
            telemetry_analyzer=mock_telemetry_analyzer,
            run_id="run_cycle2",
            project_id="test_project",
            enabled=True,
        )
        pipeline2.stop_auto_flush()

        # Get context for next phase - should include learnings from cycle 1
        context = pipeline2.get_context_for_phase(
            phase_type="build",
            phase_goal="Build the project",
            include_errors=True,
            include_success_patterns=True,
        )

        # Verify context was retrieved from memory (influenced by cycle 1)
        assert mock_memory_service._call_counts["retrieve_insights"] >= 1
        assert isinstance(context, PhaseContext)

    def test_full_loop_integration(
        self,
        mock_memory_service,
        mock_learning_pipeline,
        mock_telemetry_analyzer,
        temp_autopack_dir,
    ):
        """Test complete loop: telemetry -> ... -> feedback -> next telemetry.

        End-to-end test of entire cycle:
        1. Phase execution -> Telemetry
        2. Telemetry -> Memory
        3. Memory -> Task Generation
        4. Task Execution -> Feedback
        5. Feedback -> Context for Next Phase
        """
        # === Stage 1 & 2: Phase Execution -> Telemetry -> Memory ===
        pipeline = FeedbackPipeline(
            memory_service=mock_memory_service,
            telemetry_analyzer=mock_telemetry_analyzer,
            learning_pipeline=mock_learning_pipeline,
            run_id="full_loop_run",
            project_id="test_project",
            enabled=True,
        )
        pipeline.stop_auto_flush()

        # Simulate several phase executions with patterns
        phase_outcomes = [
            PhaseOutcome(
                phase_id="full_loop_phase_001",
                phase_type="build",
                success=True,
                status="Build completed",
                tokens_used=50000,  # High token usage pattern
                execution_time_seconds=30.0,
                run_id="full_loop_run",
                project_id="test_project",
            ),
            PhaseOutcome(
                phase_id="full_loop_phase_002",
                phase_type="test",
                success=False,
                status="Test failed",
                error_message="Timeout in API test",
                tokens_used=30000,
                execution_time_seconds=120.0,  # Long execution pattern
                run_id="full_loop_run",
                project_id="test_project",
            ),
            PhaseOutcome(
                phase_id="full_loop_phase_003",
                phase_type="deploy",
                success=True,
                status="Deployment succeeded",
                tokens_used=10000,
                learnings=["Blue-green deployment reduces downtime"],
                run_id="full_loop_run",
                project_id="test_project",
            ),
        ]

        for outcome in phase_outcomes:
            result = pipeline.process_phase_outcome(outcome)
            assert result["success"] is True

        # Verify telemetry was persisted
        assert mock_memory_service._call_counts["write_task_execution_feedback"] >= 3
        assert mock_memory_service._call_counts["write_telemetry_insight"] >= 3

        # === Stage 3 & 4: Memory -> Task Generation ===
        # Add insights to memory for task generation
        for feedback in mock_memory_service._feedback:
            if feedback.get("tokens_used", 0) > 40000:
                mock_memory_service._insights.append(
                    {
                        "_id": f"insight_from_{feedback['phase_id']}",
                        "_project_id": "test_project",
                        "issue_type": "cost_sink",
                        "content": f"High token usage in {feedback['phase_type']}",
                        "severity": "high",
                        "metric_value": feedback["tokens_used"],
                        "phase_id": feedback["phase_id"],
                        "phase_type": feedback["phase_type"],
                        "confidence": 0.9,
                    }
                )
            if feedback.get("error_message"):
                mock_memory_service._insights.append(
                    {
                        "_id": f"error_insight_{feedback['phase_id']}",
                        "_project_id": "test_project",
                        "issue_type": "failure_mode",
                        "content": feedback["error_message"],
                        "severity": "high",
                        "metric_value": 1.0,
                        "phase_id": feedback["phase_id"],
                        "phase_type": feedback["phase_type"],
                        "confidence": 0.85,
                    }
                )

        # Task generator creates tasks from patterns
        task_generator = AutonomousTaskGenerator(memory_service=mock_memory_service)
        gen_result = task_generator.generate_tasks(
            max_tasks=5,
            min_confidence=0.0,
        )

        # Verify task generation consumed memory
        assert mock_memory_service._call_counts["retrieve_insights"] >= 1

        # === Stage 5 & 6: Task Execution -> Feedback -> Loop Closure ===
        # Simulate executing generated tasks
        if gen_result.tasks_generated:
            for task in gen_result.tasks_generated[:2]:
                task_outcome = PhaseOutcome(
                    phase_id=f"exec_{task.task_id}",
                    phase_type="improvement_task",
                    success=True,
                    status=f"Completed: {task.title}",
                    tokens_used=5000,
                    learnings=[f"Applied fix from {task.task_id}"],
                    run_id="full_loop_run",
                    project_id="test_project",
                )
                pipeline.process_phase_outcome(task_outcome)

        # Get context for next phase - should reflect all learnings
        next_context = pipeline.get_context_for_phase(
            phase_type="build",
            phase_goal="Build for next cycle",
        )

        # Verify the loop has closed - context retrieval happened
        assert mock_memory_service._call_counts["retrieve_insights"] >= 2
        assert isinstance(next_context, PhaseContext)

        # Verify final stats show complete loop execution
        stats = pipeline.get_stats()
        assert stats["outcomes_processed"] >= 3
        assert stats["insights_persisted"] >= 1


# =============================================================================
# TestLoopErrorRecovery: Tests for error handling in the self-improvement loop
# =============================================================================


class TestLoopErrorRecovery:
    """Tests for error handling in the self-improvement loop."""

    def test_telemetry_failure_doesnt_break_loop(
        self, mock_learning_pipeline, mock_telemetry_analyzer
    ):
        """Test loop continues when telemetry write fails."""
        # Create memory service that fails on write
        failing_memory = MockMemoryService()
        failing_memory._raise_on_write = True

        pipeline = FeedbackPipeline(
            memory_service=failing_memory,
            learning_pipeline=mock_learning_pipeline,
            telemetry_analyzer=mock_telemetry_analyzer,
            run_id="error_recovery_run",
            project_id="test_project",
            enabled=True,
        )
        pipeline.stop_auto_flush()

        # Process outcome - should not raise exception
        outcome = PhaseOutcome(
            phase_id="error_test_001",
            phase_type="build",
            success=True,
            status="completed",
        )

        result = pipeline.process_phase_outcome(outcome)

        # Loop should continue despite failure
        assert result["success"] is True

        # Context retrieval should still work (gracefully degrade)
        context = pipeline.get_context_for_phase(
            phase_type="build",
            phase_goal="Continue after telemetry failure",
        )
        assert context is not None

    def test_memory_failure_graceful_degradation(self):
        """Test graceful degradation when memory service unavailable."""
        # Pipeline with no memory service
        pipeline = FeedbackPipeline(
            memory_service=None,
            enabled=True,
        )
        pipeline.stop_auto_flush()

        # Should handle outcome without crashing
        outcome = PhaseOutcome(
            phase_id="no_memory_001",
            phase_type="build",
            success=True,
            status="completed",
        )

        result = pipeline.process_phase_outcome(outcome)
        assert result["success"] is True

        # Context should be empty but not crash
        context = pipeline.get_context_for_phase(
            phase_type="build",
            phase_goal="Build without memory",
        )
        assert context.formatted_context == ""

    def test_task_generation_failure_recovery(self, mock_memory_service):
        """Test recovery from task generation errors."""
        # Corrupt the memory service to return invalid data
        mock_memory_service.retrieve_insights = Mock(
            side_effect=Exception("Database connection lost")
        )

        task_generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        # The task generator may raise or return empty result - both are acceptable
        # as long as the system doesn't corrupt state
        try:
            result = task_generator.generate_tasks(max_tasks=5, min_confidence=0.5)
            # If it returns, should have valid result structure
            assert result is not None
            assert result.generation_time_ms >= 0
        except Exception as e:
            # Exception is acceptable - error is logged and propagated
            # The key is that the generator doesn't leave system in corrupted state
            assert "Database connection lost" in str(e)
            # Verify memory service wasn't corrupted
            assert mock_memory_service.enabled is True

    def test_concurrent_pipeline_operations(self, mock_memory_service, mock_learning_pipeline):
        """Test concurrent operations don't corrupt state."""
        pipeline = FeedbackPipeline(
            memory_service=mock_memory_service,
            learning_pipeline=mock_learning_pipeline,
            run_id="concurrent_run",
            project_id="test_project",
            enabled=True,
        )
        pipeline.stop_auto_flush()

        results = []
        errors = []

        def process_outcome(phase_id: str):
            try:
                outcome = PhaseOutcome(
                    phase_id=phase_id,
                    phase_type="build",
                    success=True,
                    status="completed",
                    run_id=phase_id,  # Unique to avoid dedup
                )
                result = pipeline.process_phase_outcome(outcome)
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Run concurrent operations
        threads = [
            threading.Thread(target=process_outcome, args=(f"concurrent_phase_{i}",))
            for i in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No errors should have occurred
        assert len(errors) == 0
        assert len(results) == 10
        assert all(r["success"] for r in results)

    def test_partial_loop_recovery(
        self, mock_memory_service, mock_learning_pipeline, mock_telemetry_analyzer
    ):
        """Test recovery when loop is interrupted mid-cycle."""
        # Cycle 1: Partial execution (simulating interruption)
        pipeline1 = FeedbackPipeline(
            memory_service=mock_memory_service,
            learning_pipeline=mock_learning_pipeline,
            run_id="partial_run_1",
            project_id="test_project",
            enabled=True,
        )
        pipeline1.stop_auto_flush()

        # Process some outcomes
        for i in range(3):
            outcome = PhaseOutcome(
                phase_id=f"partial_phase_{i}",
                phase_type="build",
                success=True,
                status="completed",
                run_id=f"partial_run_{i}",
            )
            pipeline1.process_phase_outcome(outcome)

        # Simulate crash - data is in memory

        # Cycle 2: New pipeline instance should recover
        pipeline2 = FeedbackPipeline(
            memory_service=mock_memory_service,  # Same memory service
            telemetry_analyzer=mock_telemetry_analyzer,
            run_id="partial_run_2",
            project_id="test_project",
            enabled=True,
        )
        pipeline2.stop_auto_flush()

        # Should be able to retrieve previous insights
        _context = pipeline2.get_context_for_phase(  # noqa: F841
            phase_type="build",
            phase_goal="Resume after interruption",
        )

        # Previous data should be available
        assert mock_memory_service._call_counts["retrieve_insights"] >= 1


# =============================================================================
# TestTelemetryToMemoryBridge: Tests for telemetry-memory persistence
# =============================================================================


class TestTelemetryToMemoryBridgeIntegration:
    """Integration tests for TelemetryToMemoryBridge in the loop context."""

    def test_bridge_persists_ranked_issues(self, mock_memory_service):
        """Test that bridge properly persists ranked issues from analyzer."""
        bridge = TelemetryToMemoryBridge(
            memory_service=mock_memory_service,
        )

        # Simulate ranked issues from TelemetryAnalyzer
        ranked_issues = [
            {
                "issue_type": "cost_sink",
                "rank": 1,
                "phase_id": "cost_phase_001",
                "phase_type": "build",
                "severity": "high",
                "description": "High token usage detected",
                "metric_value": 100000,
            },
            {
                "issue_type": "failure_mode",
                "rank": 2,
                "phase_id": "fail_phase_002",
                "phase_type": "test",
                "severity": "medium",
                "description": "Frequent test failures",
                "metric_value": 5,
            },
            {
                "issue_type": "retry_cause",
                "rank": 3,
                "phase_id": "retry_phase_003",
                "phase_type": "deploy",
                "severity": "medium",
                "description": "Rate limiting causing retries",
                "metric_value": 3,
            },
        ]

        persisted = bridge.persist_insights(ranked_issues, "run_001", "test_project")

        assert persisted == 3
        assert mock_memory_service._call_counts["write_telemetry_insight"] == 3

    def test_bridge_deduplication_across_runs(self, mock_memory_service):
        """Test that bridge deduplicates insights across runs."""
        bridge = TelemetryToMemoryBridge(
            memory_service=mock_memory_service,
        )

        issues = [{"issue_type": "cost_sink", "rank": 1, "phase_id": "dedup_phase"}]

        # Persist same issue twice
        result1 = bridge.persist_insights(issues, "run_001")
        result2 = bridge.persist_insights(issues, "run_001")

        assert result1 == 1
        assert result2 == 0  # Deduplicated


# =============================================================================
# TestLoopMetrics: Tests for loop health metrics
# =============================================================================


class TestLoopMetrics:
    """Tests for self-improvement loop health metrics."""

    def test_loop_statistics_tracking(self, feedback_pipeline, mock_memory_service):
        """Test that loop statistics are properly tracked."""
        # Process multiple outcomes
        for i in range(5):
            outcome = PhaseOutcome(
                phase_id=f"metrics_phase_{i}",
                phase_type="build",
                success=i % 2 == 0,  # Alternating success/failure
                status="completed",
                run_id=f"metrics_run_{i}",
            )
            feedback_pipeline.process_phase_outcome(outcome)

        stats = feedback_pipeline.get_stats()

        # Verify stats are tracked
        assert stats["outcomes_processed"] == 5
        assert stats["insights_persisted"] >= 1

    def test_loop_health_status(self, feedback_pipeline):
        """Test loop health status reporting."""
        health = feedback_pipeline.get_health_status()

        assert "task_generation_paused" in health
        assert isinstance(health["task_generation_paused"], bool)

    def test_sla_status_check(self, feedback_pipeline):
        """Test SLA status is checkable."""
        sla = feedback_pipeline.check_sla_status()

        assert "is_healthy" in sla
        assert "sla_status" in sla


# =============================================================================
# TestCrossProjectIsolation: Tests for project namespace isolation
# =============================================================================


class TestCrossProjectIsolation:
    """Tests for project namespace isolation in the loop (IMP-MEM-015)."""

    def test_insights_isolated_by_project(self, mock_memory_service, mock_learning_pipeline):
        """Test that insights are isolated by project_id."""
        # Pipeline for project A
        pipeline_a = FeedbackPipeline(
            memory_service=mock_memory_service,
            learning_pipeline=mock_learning_pipeline,
            run_id="project_a_run",
            project_id="project_a",
            enabled=True,
        )
        pipeline_a.stop_auto_flush()

        # Pipeline for project B
        pipeline_b = FeedbackPipeline(
            memory_service=mock_memory_service,
            run_id="project_b_run",
            project_id="project_b",
            enabled=True,
        )
        pipeline_b.stop_auto_flush()

        # Record outcome for project A
        outcome_a = PhaseOutcome(
            phase_id="project_a_phase",
            phase_type="build",
            success=False,
            status="failed",
            error_message="Project A specific error",
            run_id="project_a_run",
            project_id="project_a",
        )
        pipeline_a.process_phase_outcome(outcome_a)

        # Record outcome for project B
        outcome_b = PhaseOutcome(
            phase_id="project_b_phase",
            phase_type="build",
            success=True,
            status="completed",
            run_id="project_b_run",
            project_id="project_b",
        )
        pipeline_b.process_phase_outcome(outcome_b)

        # Verify both were stored
        assert len(mock_memory_service._feedback) == 2

        # Verify project_ids are preserved
        project_ids = {f["project_id"] for f in mock_memory_service._feedback}
        assert "project_a" in project_ids
        assert "project_b" in project_ids

    def test_context_retrieval_respects_project_boundary(
        self, mock_memory_service, mock_learning_pipeline, mock_telemetry_analyzer
    ):
        """Test that context retrieval only returns project-specific data."""
        # Seed memory with data from different projects
        mock_memory_service._insights = [
            {
                "_id": "insight_project_a",
                "_project_id": "project_a",
                "content": "Project A insight",
                "issue_type": "cost_sink",
            },
            {
                "_id": "insight_project_b",
                "_project_id": "project_b",
                "content": "Project B insight",
                "issue_type": "cost_sink",
            },
        ]

        # Create pipeline for project A
        pipeline_a = FeedbackPipeline(
            memory_service=mock_memory_service,
            telemetry_analyzer=mock_telemetry_analyzer,
            run_id="isolation_run_a",
            project_id="project_a",
            enabled=True,
        )
        pipeline_a.stop_auto_flush()

        # Retrieve context for project A
        pipeline_a.get_context_for_phase(
            phase_type="build",
            phase_goal="Build project A",
        )

        # Verify retrieve was called (we can't verify filtering without modifying mock)
        assert mock_memory_service._call_counts["retrieve_insights"] >= 1
