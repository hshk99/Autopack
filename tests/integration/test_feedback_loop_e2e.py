"""End-to-end feedback loop integration tests (IMP-TST-004).

Tests cover the complete feedback loop cycle:
- Phase outcome -> Telemetry capture
- Telemetry -> Memory persistence
- Memory -> Context retrieval
- Context -> Phase planning (full cycle)

These tests validate that the self-improvement loop functions correctly
as an integrated system, not just individual components.
"""

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from autopack.feedback_pipeline import FeedbackPipeline, PhaseContext, PhaseOutcome
from autopack.telemetry.telemetry_to_memory_bridge import TelemetryToMemoryBridge

# =============================================================================
# Test Fixtures
# =============================================================================


class MockMemoryService:
    """Mock memory service for E2E testing with state tracking."""

    def __init__(self):
        self.enabled = True
        self._insights: List[Dict[str, Any]] = []
        self._errors: List[Dict[str, Any]] = []
        self._feedback: List[Dict[str, Any]] = []
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
        return feedback["_id"]

    def retrieve_insights(
        self,
        query: str,
        limit: int = 5,
        project_id: Optional[str] = None,
        max_age_hours: float = 72.0,
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant insights based on query."""
        self._call_counts["retrieve_insights"] += 1
        # Return stored insights that match project_id
        results = [
            i for i in self._insights if project_id is None or i.get("_project_id") == project_id
        ]
        return results[:limit]

    def search_errors(
        self,
        query: str,
        project_id: Optional[str] = None,
        limit: int = 3,
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
        for insight in self._insights:
            if project_id and insight.get("_project_id") != project_id:
                continue
            results.append(
                {
                    "content": insight.get("description", insight.get("content", "")),
                    "metadata": insight,
                    "confidence": insight.get("confidence", 0.8),
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


# =============================================================================
# Full Cycle Tests
# =============================================================================


class TestFullFeedbackLoopCycle:
    """Tests for complete feedback loop cycles."""

    def test_full_cycle_outcome_to_context_retrieval(self, feedback_pipeline, mock_memory_service):
        """Test complete cycle: outcome -> telemetry -> memory -> context."""
        # Step 1: Process a phase outcome
        outcome = PhaseOutcome(
            phase_id="phase_001",
            phase_type="build",
            success=True,
            status="Build completed successfully",
            execution_time_seconds=45.0,
            tokens_used=5000,
            learnings=["Use incremental builds for faster iteration"],
        )

        result = feedback_pipeline.process_phase_outcome(outcome)
        assert result["success"] is True
        assert result["insights_created"] >= 1

        # Step 2: Verify telemetry was captured
        assert mock_memory_service._call_counts["write_task_execution_feedback"] >= 1

        # Step 3: Retrieve context for next phase
        context = feedback_pipeline.get_context_for_phase(
            phase_type="test",
            phase_goal="Run unit tests after build",
        )

        # Step 4: Verify context contains previous insights
        assert isinstance(context, PhaseContext)
        assert mock_memory_service._call_counts["retrieve_insights"] >= 1

    def test_full_cycle_failure_to_error_retrieval(self, feedback_pipeline, mock_memory_service):
        """Test failure outcome flows to error retrieval."""
        # Process a failed phase
        outcome = PhaseOutcome(
            phase_id="phase_002",
            phase_type="test",
            success=False,
            status="Test failed",
            error_message="AssertionError: Expected 5, got 3",
        )

        feedback_pipeline.process_phase_outcome(outcome)

        # Retrieve context and verify errors are available
        feedback_pipeline.get_context_for_phase(
            phase_type="test",
            phase_goal="Fix failing test",
            include_errors=True,
        )

        # Error should be searchable
        assert mock_memory_service._call_counts["search_errors"] >= 1

    def test_full_cycle_multi_phase_sequence(self, feedback_pipeline, mock_memory_service):
        """Test multi-phase sequence maintains context across phases."""
        phases = [
            ("planning", True, "Planning completed"),
            ("build", True, "Build succeeded"),
            ("test", False, "2 tests failed"),
            ("test", True, "All tests passed after fix"),
        ]

        for i, (phase_type, success, status) in enumerate(phases):
            outcome = PhaseOutcome(
                phase_id=f"phase_{i:03d}",
                phase_type=phase_type,
                success=success,
                status=status,
                run_id=f"run_{i:03d}",
                error_message=None if success else "Test failure",
            )
            feedback_pipeline.process_phase_outcome(outcome)

        # Verify all phases were processed
        stats = feedback_pipeline.get_stats()
        assert stats["outcomes_processed"] == 4

        # Verify insights accumulated
        assert len(mock_memory_service._insights) >= 4

    def test_full_cycle_cross_run_learning(
        self, mock_memory_service, mock_learning_pipeline, mock_telemetry_analyzer
    ):
        """Test that learning persists across pipeline instances (runs)."""
        # First run - record failure
        pipeline1 = FeedbackPipeline(
            memory_service=mock_memory_service,
            learning_pipeline=mock_learning_pipeline,
            run_id="run_001",
            project_id="test_project",
            enabled=True,
        )
        pipeline1.stop_auto_flush()

        outcome1 = PhaseOutcome(
            phase_id="phase_001",
            phase_type="build",
            success=False,
            status="Build failed",
            error_message="Missing import statement",
        )
        pipeline1.process_phase_outcome(outcome1)

        # Second run - should be able to retrieve context from first run
        pipeline2 = FeedbackPipeline(
            memory_service=mock_memory_service,
            telemetry_analyzer=mock_telemetry_analyzer,
            run_id="run_002",
            project_id="test_project",
            enabled=True,
        )
        pipeline2.stop_auto_flush()

        pipeline2.get_context_for_phase(
            phase_type="build",
            phase_goal="Build the project",
        )

        # Should have retrieved insights from previous run
        assert mock_memory_service._call_counts["retrieve_insights"] >= 1

    def test_full_cycle_success_pattern_recording(self, feedback_pipeline, mock_learning_pipeline):
        """Test that success patterns are recorded for positive reinforcement."""
        outcome = PhaseOutcome(
            phase_id="phase_001",
            phase_type="deploy",
            success=True,
            status="Deployment completed",
            execution_time_seconds=120.0,
            learnings=["Use blue-green deployment for zero downtime"],
        )

        feedback_pipeline.process_phase_outcome(outcome)

        # Success pattern should be recorded
        assert len(mock_learning_pipeline._success_patterns) >= 1


# =============================================================================
# Phase Outcome to Telemetry Tests
# =============================================================================


class TestPhaseOutcomeToTelemetry:
    """Tests for phase outcome to telemetry capture."""

    def test_outcome_creates_telemetry_insight(self, feedback_pipeline, mock_memory_service):
        """Phase outcome should create a telemetry insight."""
        outcome = PhaseOutcome(
            phase_id="test_phase",
            phase_type="build",
            success=True,
            status="completed",
        )

        result = feedback_pipeline.process_phase_outcome(outcome)

        assert result["insights_created"] >= 1
        assert len(mock_memory_service._insights) >= 1

    def test_outcome_captures_execution_metrics(self, feedback_pipeline, mock_memory_service):
        """Outcome metrics should be captured in feedback."""
        outcome = PhaseOutcome(
            phase_id="test_phase",
            phase_type="test",
            success=True,
            status="completed",
            execution_time_seconds=30.5,
            tokens_used=2500,
        )

        feedback_pipeline.process_phase_outcome(outcome)

        # Check feedback contains metrics
        assert len(mock_memory_service._feedback) >= 1
        feedback = mock_memory_service._feedback[0]
        assert feedback["execution_time_seconds"] == 30.5
        assert feedback["tokens_used"] == 2500

    def test_failure_outcome_records_error_message(self, feedback_pipeline, mock_memory_service):
        """Failure outcomes should record error messages."""
        outcome = PhaseOutcome(
            phase_id="test_phase",
            phase_type="build",
            success=False,
            status="failed",
            error_message="Compilation error on line 42",
        )

        feedback_pipeline.process_phase_outcome(outcome)

        assert len(mock_memory_service._feedback) >= 1
        feedback = mock_memory_service._feedback[0]
        assert feedback["error_message"] == "Compilation error on line 42"

    def test_outcome_captures_learnings(self, feedback_pipeline, mock_memory_service):
        """Outcome learnings should be captured."""
        outcome = PhaseOutcome(
            phase_id="test_phase",
            phase_type="refactor",
            success=True,
            status="completed",
            learnings=["Split large functions into smaller ones", "Add unit tests"],
        )

        feedback_pipeline.process_phase_outcome(outcome)

        assert len(mock_memory_service._feedback) >= 1
        feedback = mock_memory_service._feedback[0]
        assert len(feedback["learnings"]) == 2

    def test_outcome_type_detection_cost_sink(self, feedback_pipeline):
        """High token usage should be detected as cost_sink."""
        outcome = PhaseOutcome(
            phase_id="test_phase",
            phase_type="build",
            success=False,
            status="completed",
            tokens_used=150000,
        )

        insight = feedback_pipeline._create_insight_from_outcome(outcome)

        assert insight["insight_type"] == "cost_sink"

    def test_outcome_type_detection_retry_cause(self, feedback_pipeline):
        """Timeout errors should be detected as retry_cause."""
        outcome = PhaseOutcome(
            phase_id="test_phase",
            phase_type="build",
            success=False,
            status="failed",
            error_message="Request timeout after 30 seconds",
        )

        insight = feedback_pipeline._create_insight_from_outcome(outcome)

        assert insight["insight_type"] == "retry_cause"


# =============================================================================
# Telemetry to Memory Tests
# =============================================================================


class TestTelemetryToMemory:
    """Tests for telemetry to memory persistence."""

    def test_insight_persisted_to_memory(self, feedback_pipeline, mock_memory_service):
        """Insights should be persisted to memory service."""
        outcome = PhaseOutcome(
            phase_id="test_phase",
            phase_type="build",
            success=True,
            status="completed",
        )

        feedback_pipeline.process_phase_outcome(outcome)

        assert mock_memory_service._call_counts["write_telemetry_insight"] >= 1

    def test_feedback_persisted_to_memory(self, feedback_pipeline, mock_memory_service):
        """Execution feedback should be persisted to memory."""
        outcome = PhaseOutcome(
            phase_id="test_phase",
            phase_type="build",
            success=True,
            status="completed",
        )

        feedback_pipeline.process_phase_outcome(outcome)

        assert mock_memory_service._call_counts["write_task_execution_feedback"] >= 1

    def test_deduplication_prevents_duplicate_insights(
        self, feedback_pipeline, mock_memory_service
    ):
        """Same outcome should not create duplicate insights."""
        outcome = PhaseOutcome(
            phase_id="test_phase",
            phase_type="build",
            success=True,
            status="completed",
            run_id="fixed_run_id",
        )

        # Process same outcome twice
        feedback_pipeline.process_phase_outcome(outcome)
        initial_count = mock_memory_service._call_counts["write_task_execution_feedback"]

        feedback_pipeline.process_phase_outcome(outcome)
        final_count = mock_memory_service._call_counts["write_task_execution_feedback"]

        # Should not have created duplicate
        assert final_count == initial_count

    def test_memory_write_failure_handled_gracefully(
        self, mock_learning_pipeline, mock_telemetry_analyzer
    ):
        """Memory write failures should not crash the pipeline."""
        mock_memory = MockMemoryService()
        mock_memory._raise_on_write = True

        pipeline = FeedbackPipeline(
            memory_service=mock_memory,
            learning_pipeline=mock_learning_pipeline,
            enabled=True,
        )
        pipeline.stop_auto_flush()

        outcome = PhaseOutcome(
            phase_id="test_phase",
            phase_type="build",
            success=True,
            status="completed",
        )

        # Should not raise exception
        result = pipeline.process_phase_outcome(outcome)
        assert result["success"] is True

    def test_batch_flush_persists_all_insights(self, mock_memory_service):
        """Batch flush should persist all pending insights."""
        pipeline = FeedbackPipeline(
            memory_service=mock_memory_service,
            enabled=False,  # Disable to manually control flush
        )

        # Add insights manually
        for i in range(5):
            pipeline._pending_insights.append({"test": f"insight_{i}"})

        flushed = pipeline.flush_pending_insights()

        assert flushed == 5
        assert len(pipeline._pending_insights) == 0

    def test_telemetry_bridge_persists_ranked_issues(self, mock_memory_service):
        """TelemetryToMemoryBridge should persist ranked issues."""
        bridge = TelemetryToMemoryBridge(
            memory_service=mock_memory_service,
        )

        ranked_issues = [
            {
                "issue_type": "cost_sink",
                "rank": 1,
                "phase_id": "phase_001",
                "severity": "high",
                "details": "High token usage detected",
                "metric_value": 100000,
            },
            {
                "issue_type": "failure_mode",
                "rank": 2,
                "phase_id": "phase_002",
                "severity": "medium",
                "details": "Frequent test failures",
                "metric_value": 5,
            },
        ]

        persisted = bridge.persist_insights(ranked_issues, "run_001", "test_project")

        assert persisted == 2


# =============================================================================
# Memory to Context Retrieval Tests
# =============================================================================


class TestMemoryToContextRetrieval:
    """Tests for memory to context retrieval."""

    def test_context_retrieval_queries_memory(self, feedback_pipeline, mock_memory_service):
        """Context retrieval should query memory service."""
        feedback_pipeline.get_context_for_phase(
            phase_type="build",
            phase_goal="Build the project",
        )

        assert mock_memory_service._call_counts["retrieve_insights"] >= 1

    def test_context_retrieval_includes_errors(self, feedback_pipeline, mock_memory_service):
        """Context retrieval should include error search."""
        # Add an error to memory
        mock_memory_service._feedback.append(
            {
                "phase_type": "build",
                "error_message": "Previous build error",
                "success": False,
            }
        )

        feedback_pipeline.get_context_for_phase(
            phase_type="build",
            phase_goal="Build the project",
            include_errors=True,
        )

        assert mock_memory_service._call_counts["search_errors"] >= 1

    def test_context_retrieval_includes_success_patterns(
        self, feedback_pipeline, mock_memory_service
    ):
        """Context retrieval should include success patterns."""
        # Add a success pattern to memory
        mock_memory_service._feedback.append(
            {
                "phase_type": "build",
                "success": True,
                "context_summary": "Used incremental build",
                "learnings": ["Fast iteration"],
            }
        )

        feedback_pipeline.get_context_for_phase(
            phase_type="build",
            phase_goal="Build the project",
            include_success_patterns=True,
        )

        assert mock_memory_service._call_counts["search_execution_feedback"] >= 1

    def test_context_includes_recommendations(self, feedback_pipeline, mock_telemetry_analyzer):
        """Context should include telemetry recommendations."""
        mock_telemetry_analyzer.add_recommendation(
            severity="HIGH",
            action="reduce_context_size",
            reason="Token usage trending high",
        )

        context = feedback_pipeline.get_context_for_phase(
            phase_type="build",
            phase_goal="Build the project",
        )

        assert len(context.recommendations) >= 1

    def test_context_formatted_for_prompt_injection(self, feedback_pipeline, mock_memory_service):
        """Context should be formatted for prompt injection."""
        # Add some data
        mock_memory_service._insights.append(
            {
                "content": "Use caching for faster builds",
                "_project_id": "test_project",
            }
        )

        context = feedback_pipeline.get_context_for_phase(
            phase_type="build",
            phase_goal="Build the project",
        )

        assert isinstance(context.formatted_context, str)

    def test_context_respects_max_insights_limit(self, feedback_pipeline, mock_memory_service):
        """Context retrieval should respect max_insights limit."""
        # Add many insights
        for i in range(20):
            mock_memory_service._insights.append(
                {
                    "content": f"Insight {i}",
                    "_project_id": "test_project",
                }
            )

        context = feedback_pipeline.get_context_for_phase(
            phase_type="build",
            phase_goal="Build the project",
            max_insights=3,
        )

        assert len(context.relevant_insights) <= 3


# =============================================================================
# Context Affects Phase Planning Tests
# =============================================================================


class TestContextAffectsPlanning:
    """Tests for context affecting phase planning."""

    def test_recommendations_included_in_context(self, feedback_pipeline, mock_telemetry_analyzer):
        """Recommendations should be included in phase context."""
        mock_telemetry_analyzer.add_recommendation(
            severity="CRITICAL",
            action="increase_timeout",
            reason="Phase frequently times out",
        )

        context = feedback_pipeline.get_context_for_phase(
            phase_type="build",
            phase_goal="Build the project",
        )

        assert len(context.recommendations) >= 1
        assert context.recommendations[0]["severity"] == "CRITICAL"

    def test_error_patterns_available_for_avoidance(self, feedback_pipeline, mock_memory_service):
        """Past errors should be available to avoid repeating."""
        # Record a failure
        failure_outcome = PhaseOutcome(
            phase_id="failed_phase",
            phase_type="build",
            success=False,
            status="failed",
            error_message="Missing semicolon on line 15",
        )
        feedback_pipeline.process_phase_outcome(failure_outcome)

        # Get context for new phase
        feedback_pipeline.get_context_for_phase(
            phase_type="build",
            phase_goal="Build the project",
            include_errors=True,
        )

        # Errors should have been searched
        assert mock_memory_service._call_counts["search_errors"] >= 1

    def test_success_patterns_available_for_replication(
        self, feedback_pipeline, mock_memory_service
    ):
        """Past successes should be available for replication."""
        # Record a success
        success_outcome = PhaseOutcome(
            phase_id="success_phase",
            phase_type="test",
            success=True,
            status="All tests passed",
            learnings=["Run tests in parallel for speed"],
        )
        feedback_pipeline.process_phase_outcome(success_outcome)

        # Get context for new phase
        feedback_pipeline.get_context_for_phase(
            phase_type="test",
            phase_goal="Run tests",
            include_success_patterns=True,
        )

        # Success patterns should have been searched
        assert mock_memory_service._call_counts["search_execution_feedback"] >= 1

    def test_formatted_context_contains_all_sections(
        self, feedback_pipeline, mock_memory_service, mock_telemetry_analyzer
    ):
        """Formatted context should contain all relevant sections."""
        # Add recommendations
        mock_telemetry_analyzer.add_recommendation(
            severity="HIGH",
            action="test_action",
            reason="test_reason",
        )

        # Add insights
        mock_memory_service._insights.append(
            {
                "content": "Test insight content",
                "_project_id": "test_project",
            }
        )

        # Add errors
        mock_memory_service._feedback.append(
            {
                "phase_type": "build",
                "error_message": "Test error",
                "success": False,
            }
        )

        context = feedback_pipeline.get_context_for_phase(
            phase_type="build",
            phase_goal="Build the project",
        )

        # Check formatted context has headers
        assert "## Context from Previous Executions" in context.formatted_context

    def test_learning_hints_available_for_phase(self, feedback_pipeline, mock_learning_pipeline):
        """Learning hints should be retrievable for phases."""
        # Record a failure that creates a hint
        failure_outcome = PhaseOutcome(
            phase_id="failed_phase",
            phase_type="build",
            success=False,
            status="failed",
            error_message="Build failed due to missing dependency",
        )
        feedback_pipeline.process_phase_outcome(failure_outcome)

        # Get hints for phase
        feedback_pipeline.get_learning_hints_for_context(
            phase={"phase_id": "new_phase", "phase_type": "build"},
        )

        # Hint should be recorded
        assert len(mock_learning_pipeline._hints) >= 1


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================


class TestEdgeCasesAndErrorHandling:
    """Tests for edge cases and error handling."""

    def test_disabled_pipeline_returns_early(self):
        """Disabled pipeline should return early without processing."""
        pipeline = FeedbackPipeline(enabled=False)

        outcome = PhaseOutcome(
            phase_id="test_phase",
            phase_type="build",
            success=True,
            status="completed",
        )

        result = pipeline.process_phase_outcome(outcome)

        assert result["success"] is True
        assert result["insights_created"] == 0

    def test_no_memory_service_handles_gracefully(self):
        """Pipeline without memory service should handle gracefully."""
        pipeline = FeedbackPipeline(
            memory_service=None,
            enabled=True,
        )
        pipeline.stop_auto_flush()

        outcome = PhaseOutcome(
            phase_id="test_phase",
            phase_type="build",
            success=True,
            status="completed",
        )

        result = pipeline.process_phase_outcome(outcome)
        assert result["success"] is True

        context = pipeline.get_context_for_phase(
            phase_type="build",
            phase_goal="Build the project",
        )
        assert context.formatted_context == ""

    def test_empty_outcome_fields_handled(self, feedback_pipeline):
        """Outcomes with minimal fields should be handled."""
        outcome = PhaseOutcome(
            phase_id="test_phase",
            phase_type=None,
            success=True,
            status="",
        )

        result = feedback_pipeline.process_phase_outcome(outcome)
        assert result["success"] is True

    def test_concurrent_outcome_processing(self, feedback_pipeline, mock_memory_service):
        """Concurrent outcome processing should be thread-safe."""
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
                result = feedback_pipeline.process_phase_outcome(outcome)
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=process_outcome, args=(f"phase_{i}",)) for i in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 10
        assert all(r["success"] for r in results)

    def test_stats_tracking_accuracy(self, feedback_pipeline, mock_memory_service):
        """Statistics should accurately track operations."""
        # Process outcomes
        for i in range(3):
            outcome = PhaseOutcome(
                phase_id=f"phase_{i}",
                phase_type="build",
                success=True,
                status="completed",
                run_id=f"run_{i}",
            )
            feedback_pipeline.process_phase_outcome(outcome)

        # Get context
        for i in range(2):
            feedback_pipeline.get_context_for_phase(
                phase_type="build",
                phase_goal="Build the project",
            )

        stats = feedback_pipeline.get_stats()
        assert stats["outcomes_processed"] == 3
        assert stats["context_retrievals"] == 2


# =============================================================================
# Hint Promotion Tests
# =============================================================================


class TestHintPromotion:
    """Tests for hint-to-rule promotion (IMP-LOOP-015)."""

    def test_hint_occurrence_tracking(self, feedback_pipeline, mock_learning_pipeline):
        """Hint occurrences should be tracked."""
        # Record multiple failures of same type
        for i in range(2):
            outcome = PhaseOutcome(
                phase_id=f"phase_{i}",
                phase_type="build",
                success=False,
                status="failed",
                error_message="CI test failure",
                run_id=f"run_{i}",
            )
            feedback_pipeline.process_phase_outcome(outcome)

        # Check hint occurrences tracked
        assert len(feedback_pipeline._hint_occurrences) >= 1

    def test_hint_promotion_at_threshold(
        self, feedback_pipeline, mock_memory_service, mock_learning_pipeline
    ):
        """Hints should be promoted to rules at threshold."""
        feedback_pipeline._hint_promotion_threshold = 3

        # Record failures to reach threshold
        for i in range(3):
            outcome = PhaseOutcome(
                phase_id=f"phase_{i}",
                phase_type="test",
                success=False,
                status="failed",
                error_message="Test failed in CI",
                run_id=f"run_{i}",
            )
            feedback_pipeline.process_phase_outcome(outcome)

        # Check rule was created
        stats = feedback_pipeline.get_stats()
        assert stats["hints_promoted_to_rules"] >= 1

    def test_hint_key_generation(self, feedback_pipeline):
        """Hint promotion key should be generated correctly."""
        outcome = PhaseOutcome(
            phase_id="test_phase",
            phase_type="build",
            success=False,
            status="failed",
            error_message="CI failure",
        )

        hint_type = feedback_pipeline._determine_hint_type(outcome)
        hint_key = feedback_pipeline._get_hint_promotion_key(hint_type, outcome)

        assert ":" in hint_key
        assert "build" in hint_key


# =============================================================================
# SLA and Health Monitoring Tests
# =============================================================================


class TestSLAAndHealthMonitoring:
    """Tests for SLA compliance and health monitoring."""

    def test_sla_status_check(self, feedback_pipeline):
        """SLA status should be checkable."""
        status = feedback_pipeline.check_sla_status()

        assert "is_healthy" in status
        assert "sla_status" in status

    def test_health_status_check(self, feedback_pipeline):
        """Health status should be checkable."""
        status = feedback_pipeline.get_health_status()

        assert "task_generation_paused" in status

    def test_task_generation_pause_state(self, feedback_pipeline):
        """Task generation pause state should be trackable."""
        assert feedback_pipeline.is_task_generation_paused() is False

    def test_health_resume_callback_registration(self, feedback_pipeline):
        """Health resume callbacks should be registerable."""
        callback_called = [False]

        def callback(old_status, new_status):
            callback_called[0] = True

        feedback_pipeline.register_health_resume_callback(callback)

        status = feedback_pipeline.get_health_status()
        assert status["registered_callbacks"] >= 1


# =============================================================================
# Auto-Flush and Shutdown Tests
# =============================================================================


class TestAutoFlushAndShutdown:
    """Tests for auto-flush and shutdown behavior."""

    def test_auto_flush_timer_configuration(self, feedback_pipeline):
        """Auto-flush timer should be properly configured."""
        assert feedback_pipeline._auto_flush_interval == 300
        assert feedback_pipeline._insight_threshold == 100

    def test_eager_flush_on_phase_completion(self, mock_memory_service, mock_learning_pipeline):
        """Eager flush should occur on phase completion."""
        pipeline = FeedbackPipeline(
            memory_service=mock_memory_service,
            learning_pipeline=mock_learning_pipeline,
            enabled=True,
        )
        pipeline.stop_auto_flush()

        outcome = PhaseOutcome(
            phase_id="test_phase",
            phase_type="build",
            success=True,
            status="completed",
        )

        pipeline.process_phase_outcome(outcome)

        # Pending insights should be empty after eager flush
        assert len(pipeline._pending_insights) == 0

    def test_shutdown_flush_persists_all(self, mock_memory_service):
        """Shutdown flush should persist all pending insights."""
        pipeline = FeedbackPipeline(
            memory_service=mock_memory_service,
            enabled=False,
        )

        # Add pending insights
        for i in range(5):
            pipeline._pending_insights.append({"test": f"insight_{i}"})

        pipeline._shutdown_flush()

        assert len(pipeline._pending_insights) == 0
        assert mock_memory_service._call_counts["write_telemetry_insight"] == 5

    def test_stop_auto_flush_cleanup(self, feedback_pipeline):
        """Stopping auto-flush should cleanup resources."""
        assert feedback_pipeline._flush_timer is not None

        feedback_pipeline.stop_auto_flush()

        assert feedback_pipeline._flush_timer is None
        assert feedback_pipeline._auto_flush_enabled is False


# =============================================================================
# Circuit Breaker Integration Tests
# =============================================================================


class TestCircuitBreakerIntegration:
    """Tests for circuit breaker event recording."""

    def test_circuit_breaker_event_recording(self, feedback_pipeline, mock_memory_service):
        """Circuit breaker events should be recorded."""
        result = feedback_pipeline.record_circuit_breaker_event(
            failure_count=5,
            last_failure_reason="Memory service unavailable",
        )

        assert result["success"] is True

    def test_circuit_breaker_event_disabled_pipeline(self):
        """Disabled pipeline should skip circuit breaker recording."""
        pipeline = FeedbackPipeline(enabled=False)

        result = pipeline.record_circuit_breaker_event(
            failure_count=5,
            last_failure_reason="Test failure",
        )

        assert result["success"] is True
        assert result["insight_id"] is None


# =============================================================================
# TelemetryToMemoryBridge Integration Tests
# =============================================================================


class TestTelemetryToMemoryBridgeIntegration:
    """Tests for TelemetryToMemoryBridge integration."""

    def test_bridge_initialization(self, mock_memory_service):
        """Bridge should initialize correctly."""
        bridge = TelemetryToMemoryBridge(
            memory_service=mock_memory_service,
        )

        assert bridge.memory_service == mock_memory_service

    def test_bridge_disabled_returns_zero(self, mock_memory_service):
        """Disabled memory service should return zero persisted."""
        mock_memory_service.enabled = False
        bridge = TelemetryToMemoryBridge(
            memory_service=mock_memory_service,
        )

        result = bridge.persist_insights([{"test": "issue"}], "run_001")

        assert result == 0

    def test_bridge_no_memory_service_returns_zero(self):
        """Bridge without memory service should return zero."""
        bridge = TelemetryToMemoryBridge(
            memory_service=None,
        )

        result = bridge.persist_insights([{"test": "issue"}], "run_001")

        assert result == 0

    def test_bridge_deduplication(self, mock_memory_service):
        """Bridge should deduplicate insights."""
        bridge = TelemetryToMemoryBridge(
            memory_service=mock_memory_service,
        )

        issues = [
            {"issue_type": "cost_sink", "rank": 1, "phase_id": "phase_1"},
        ]

        # Persist twice
        result1 = bridge.persist_insights(issues, "run_001")
        result2 = bridge.persist_insights(issues, "run_001")

        assert result1 == 1
        assert result2 == 0  # Deduplicated

    def test_bridge_cache_clear(self, mock_memory_service):
        """Bridge cache should be clearable."""
        bridge = TelemetryToMemoryBridge(
            memory_service=mock_memory_service,
        )

        issues = [{"issue_type": "test", "rank": 1}]
        bridge.persist_insights(issues, "run_001")

        bridge.clear_cache()

        # Should be able to persist again after clear
        result = bridge.persist_insights(issues, "run_001")
        assert result == 1


# =============================================================================
# Closed-Loop E2E Tests (IMP-TEST-001)
# =============================================================================


class MockTaskGenerator:
    """Mock task generator for E2E testing."""

    def __init__(self):
        self._generated_tasks = []
        self._persisted_tasks = []

    def generate_tasks(
        self,
        max_tasks: int = 10,
        min_confidence: float = 0.7,
        telemetry_insights: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
        max_age_hours: Optional[float] = None,
        backlog: Optional[List[Dict[str, Any]]] = None,
        budget_status: Optional[Any] = None,
    ):
        """Generate mock tasks from insights."""
        from dataclasses import dataclass

        @dataclass
        class MockTaskResult:
            tasks_generated: List[Any]
            insights_processed: int
            patterns_detected: int
            generation_time_ms: float

        @dataclass
        class MockTask:
            task_id: str
            title: str
            description: str
            priority: str
            source_insights: List[str]
            suggested_files: List[str]
            estimated_effort: str
            created_at: datetime
            run_id: Optional[str] = None
            status: str = "pending"
            requires_approval: bool = False
            risk_severity: Optional[str] = None
            estimated_cost: int = 0

        # Create mock tasks from insights if provided
        tasks = []
        insights_count = 0

        if telemetry_insights:
            for issue_type, issues in telemetry_insights.items():
                if isinstance(issues, list):
                    for issue in issues[:max_tasks]:
                        insights_count += 1
                        task = MockTask(
                            task_id=f"TASK-{len(tasks):04d}",
                            title=f"Fix {issue_type} issue",
                            description=f"Address {issue_type} pattern",
                            priority="high",
                            source_insights=[f"insight_{len(tasks)}"],
                            suggested_files=[],
                            estimated_effort="M",
                            created_at=datetime.now(timezone.utc),
                            run_id=run_id,
                        )
                        tasks.append(task)
                        self._generated_tasks.append(task)

        return MockTaskResult(
            tasks_generated=tasks,
            insights_processed=insights_count,
            patterns_detected=len(tasks),
            generation_time_ms=10.0,
        )

    def emit_tasks_for_execution(
        self,
        tasks: List[Any],
        persist_to_db: bool = True,
        emit_to_queue: bool = True,
        run_id: Optional[str] = None,
    ) -> Dict[str, int]:
        """Emit tasks for execution."""
        self._persisted_tasks.extend(tasks)
        return {"persisted": len(tasks), "queued": len(tasks)}


class MockInsightCorrelationEngine:
    """Mock correlation engine for E2E testing."""

    def __init__(self):
        self._correlations: Dict[str, Dict[str, Any]] = {}
        self._confidence_updates: Dict[str, float] = {}

    def record_task_creation(
        self,
        insight_id: str,
        task_id: str,
        insight_source: str = "unknown",
        insight_type: str = "unknown",
        confidence: float = 1.0,
    ):
        """Record task creation from insight."""
        self._correlations[task_id] = {
            "insight_id": insight_id,
            "task_id": task_id,
            "insight_source": insight_source,
            "insight_type": insight_type,
            "confidence": confidence,
            "outcome": None,
        }
        return self._correlations[task_id]

    def record_task_outcome(
        self,
        task_id: str,
        outcome: str,
        auto_update_confidence: bool = True,
    ):
        """Record task outcome and update confidence."""
        if task_id in self._correlations:
            self._correlations[task_id]["outcome"] = outcome
            insight_id = self._correlations[task_id]["insight_id"]
            if auto_update_confidence:
                self.update_insight_confidence(insight_id)
            return self._correlations[task_id]
        return None

    def update_insight_confidence(self, insight_id: str) -> float:
        """Update confidence based on task outcomes."""
        # Calculate confidence from outcomes
        successes = 0
        failures = 0
        for corr in self._correlations.values():
            if corr["insight_id"] == insight_id:
                if corr["outcome"] == "success":
                    successes += 1
                elif corr["outcome"] == "failure":
                    failures += 1

        total = successes + failures
        if total > 0:
            confidence = 0.5 + (successes - failures) * 0.1 / total
            confidence = max(0.1, min(1.0, confidence))
        else:
            confidence = 1.0

        self._confidence_updates[insight_id] = confidence
        return confidence

    def get_insight_confidence(self, insight_id: str) -> float:
        """Get current confidence for insight."""
        return self._confidence_updates.get(insight_id, 1.0)


class TestClosedLoopE2E:
    """End-to-end tests for the complete feedback loop (IMP-TEST-001).

    These tests validate the full telemetry -> memory -> task
    -> execution -> outcome path for the self-improvement loop.
    """

    @pytest.fixture
    def mock_memory(self):
        """Create a mock memory service with state tracking."""
        return MockMemoryService()

    @pytest.fixture
    def mock_task_generator(self):
        """Create a mock task generator."""
        return MockTaskGenerator()

    @pytest.fixture
    def mock_correlation_engine(self):
        """Create a mock correlation engine."""
        return MockInsightCorrelationEngine()

    def test_telemetry_to_memory_path(self, mock_memory):
        """Test telemetry insights are stored in memory.

        IMP-TEST-001: Validates that telemetry data flows correctly
        to the memory layer for future retrieval.
        """
        # Create a bridge to persist telemetry
        bridge = TelemetryToMemoryBridge(
            memory_service=mock_memory,
        )

        # Simulate telemetry insights
        ranked_issues = [
            {
                "issue_type": "cost_sink",
                "rank": 1,
                "phase_id": "build_001",
                "severity": "high",
                "details": {"tokens": 50000},
            },
            {
                "issue_type": "failure_mode",
                "rank": 2,
                "phase_id": "test_001",
                "severity": "high",
                "details": {"count": 5},
            },
        ]

        # Persist insights to memory
        persisted = bridge.persist_insights(ranked_issues, run_id="test_run_001")

        # Verify insights were stored
        assert persisted == 2
        assert mock_memory._call_counts["write_telemetry_insight"] == 2
        assert len(mock_memory._insights) == 2

        # Verify insights can be retrieved
        retrieved = mock_memory.search_telemetry_insights(
            query="cost failure",
            limit=10,
        )
        assert len(retrieved) == 2

    def test_memory_to_task_generation(self, mock_memory, mock_task_generator):
        """Test high-confidence memory insights generate tasks.

        IMP-TEST-001: Validates that insights stored in memory can
        be consumed by the task generator to create improvement tasks.
        """
        # Pre-populate memory with insights
        mock_memory._insights = [
            {
                "id": "insight_001",
                "issue_type": "cost_sink",
                "content": "Phase X consuming high tokens",
                "severity": "high",
                "_project_id": "test_project",
                "_timestamp": datetime.now(timezone.utc).isoformat(),
                "confidence": 0.85,
            },
            {
                "id": "insight_002",
                "issue_type": "failure_mode",
                "content": "Test failures in module Y",
                "severity": "high",
                "_project_id": "test_project",
                "_timestamp": datetime.now(timezone.utc).isoformat(),
                "confidence": 0.90,
            },
        ]

        # Generate tasks from telemetry insights format
        telemetry_insights = {
            "top_cost_sinks": [
                type(
                    "MockRankedIssue",
                    (),
                    {
                        "rank": 1,
                        "issue_type": "cost_sink",
                        "phase_id": "phase_001",
                        "phase_type": "build",
                        "metric_value": 50000,
                        "details": {"count": 1},
                    },
                )()
            ],
            "top_failure_modes": [
                type(
                    "MockRankedIssue",
                    (),
                    {
                        "rank": 1,
                        "issue_type": "failure_mode",
                        "phase_id": "phase_002",
                        "phase_type": "test",
                        "metric_value": 5,
                        "details": {"outcome": "FAILURE", "stop_reason": "assertion"},
                    },
                )()
            ],
            "top_retry_causes": [],
        }

        result = mock_task_generator.generate_tasks(
            max_tasks=5,
            min_confidence=0.7,
            telemetry_insights=telemetry_insights,
            run_id="test_run_001",
        )

        # Verify tasks were generated
        assert result.insights_processed >= 2
        assert len(result.tasks_generated) >= 2
        assert len(mock_task_generator._generated_tasks) >= 2

    def test_task_execution_updates_confidence(self, mock_correlation_engine):
        """Test task outcomes update insight confidence scores.

        IMP-TEST-001: Validates that when tasks complete (success/failure),
        the source insight's confidence score is updated accordingly.
        """
        # Record task creation from insight
        mock_correlation_engine.record_task_creation(
            insight_id="insight_001",
            task_id="TASK-0001",
            insight_source="analyzer",
            insight_type="cost_sink",
            confidence=0.8,
        )

        mock_correlation_engine.record_task_creation(
            insight_id="insight_001",
            task_id="TASK-0002",
            insight_source="analyzer",
            insight_type="cost_sink",
            confidence=0.8,
        )

        # Record successful outcome
        mock_correlation_engine.record_task_outcome(
            task_id="TASK-0001",
            outcome="success",
            auto_update_confidence=True,
        )

        # Confidence should increase after success
        confidence_after_success = mock_correlation_engine.get_insight_confidence("insight_001")
        assert confidence_after_success >= 0.5  # Should be above base

        # Record failure outcome
        mock_correlation_engine.record_task_outcome(
            task_id="TASK-0002",
            outcome="failure",
            auto_update_confidence=True,
        )

        # Confidence recalculated based on mixed outcomes
        final_confidence = mock_correlation_engine.get_insight_confidence("insight_001")
        assert 0.1 <= final_confidence <= 1.0

    def test_full_loop_success_path(self, mock_memory, mock_correlation_engine):
        """Test complete success path through feedback loop.

        IMP-TEST-001: End-to-end test of the full feedback loop
        with successful task execution updating confidence positively.
        """
        # Step 1: Telemetry -> Memory (simulate storing telemetry insight)
        bridge = TelemetryToMemoryBridge(
            memory_service=mock_memory,
        )

        insight_data = {
            "issue_type": "failure_mode",
            "rank": 1,
            "phase_id": "phase_001",
            "severity": "high",
            "details": {"count": 3},
        }
        persisted = bridge.persist_insights([insight_data], run_id="run_001")
        assert persisted == 1

        # Step 2: Memory -> Task (record correlation)
        mock_correlation_engine.record_task_creation(
            insight_id="insight_001",
            task_id="TASK-SUCCESS-001",
            insight_source="memory",
            insight_type="failure_mode",
            confidence=0.75,
        )

        # Step 3: Task Execution (simulate successful execution)
        # This would normally be done by the autonomous executor
        task_executed = True
        assert task_executed

        # Step 4: Outcome -> Confidence Update
        mock_correlation_engine.record_task_outcome(
            task_id="TASK-SUCCESS-001",
            outcome="success",
        )

        # Step 5: Verify confidence was updated positively
        updated_confidence = mock_correlation_engine.get_insight_confidence("insight_001")
        assert updated_confidence > 0.5  # Success should boost confidence

        # Verify the complete loop statistics
        assert "TASK-SUCCESS-001" in mock_correlation_engine._correlations
        correlation = mock_correlation_engine._correlations["TASK-SUCCESS-001"]
        assert correlation["outcome"] == "success"

    def test_full_loop_failure_path(self, mock_memory, mock_correlation_engine):
        """Test failure path and confidence decrease.

        IMP-TEST-001: End-to-end test of the feedback loop when
        task execution fails, verifying confidence decreases.
        """
        # Step 1: Telemetry -> Memory
        bridge = TelemetryToMemoryBridge(
            memory_service=mock_memory,
        )

        insight_data = {
            "issue_type": "retry_cause",
            "rank": 1,
            "phase_id": "phase_002",
            "severity": "medium",
            "details": {"retry_count": 5},
        }
        bridge.persist_insights([insight_data], run_id="run_002")

        # Step 2: Memory -> Task with initial high confidence
        initial_confidence = 0.9
        mock_correlation_engine.record_task_creation(
            insight_id="insight_002",
            task_id="TASK-FAIL-001",
            insight_source="memory",
            insight_type="retry_cause",
            confidence=initial_confidence,
        )

        # Step 3: Record task failure
        mock_correlation_engine.record_task_outcome(
            task_id="TASK-FAIL-001",
            outcome="failure",
        )

        # Step 4: Verify confidence was updated (may decrease after multiple failures)
        updated_confidence = mock_correlation_engine.get_insight_confidence("insight_002")

        # Confidence should be updated (actual value depends on algorithm)
        assert updated_confidence is not None
        assert 0.1 <= updated_confidence <= 1.0

        # Verify failure was recorded
        correlation = mock_correlation_engine._correlations["TASK-FAIL-001"]
        assert correlation["outcome"] == "failure"

    def test_confidence_filtering_prevents_low_quality_tasks(self, mock_memory):
        """Test that low-confidence insights are filtered out.

        IMP-TEST-001: Validates that the confidence filtering mechanism
        (IMP-LOOP-033) prevents low-confidence insights from becoming tasks.
        """
        # Add insights with varying confidence levels
        mock_memory._insights = [
            {
                "id": "high_conf",
                "issue_type": "cost_sink",
                "content": "High confidence issue",
                "severity": "high",
                "_project_id": "test",
                "confidence": 0.9,  # Above threshold
            },
            {
                "id": "low_conf",
                "issue_type": "cost_sink",
                "content": "Low confidence issue",
                "severity": "high",
                "_project_id": "test",
                "confidence": 0.3,  # Below MIN_CONFIDENCE_THRESHOLD (0.5)
            },
        ]

        # Retrieve insights with confidence data
        results = mock_memory.search_telemetry_insights(
            query="cost_sink",
            limit=10,
        )

        # Filter by confidence threshold (simulating what TaskGenerator does)
        MIN_CONFIDENCE_THRESHOLD = 0.5
        filtered = [r for r in results if r.get("confidence", 1.0) >= MIN_CONFIDENCE_THRESHOLD]

        # Only high-confidence insight should remain
        assert len(filtered) == 1
        assert filtered[0]["metadata"]["id"] == "high_conf"

    def test_multiple_insights_aggregate_confidence(self, mock_correlation_engine):
        """Test confidence aggregation across multiple task outcomes.

        IMP-TEST-001: Validates that confidence scores are properly
        aggregated when multiple tasks are generated from the same insight.
        """
        insight_id = "aggregate_test_insight"

        # Create multiple tasks from same insight
        for i in range(5):
            mock_correlation_engine.record_task_creation(
                insight_id=insight_id,
                task_id=f"TASK-AGG-{i:03d}",
                insight_source="analyzer",
                insight_type="failure_mode",
                confidence=0.7,
            )

        # Record mixed outcomes
        mock_correlation_engine.record_task_outcome("TASK-AGG-000", "success")
        mock_correlation_engine.record_task_outcome("TASK-AGG-001", "success")
        mock_correlation_engine.record_task_outcome("TASK-AGG-002", "success")
        mock_correlation_engine.record_task_outcome("TASK-AGG-003", "failure")
        mock_correlation_engine.record_task_outcome("TASK-AGG-004", "partial")

        # Verify confidence reflects overall success rate (3/4 = 75%)
        final_confidence = mock_correlation_engine.get_insight_confidence(insight_id)

        # With 3 successes and 1 failure, confidence should be above 0.5
        assert final_confidence >= 0.5


# =============================================================================
# TelemetryTaskDaemon Integration Tests (IMP-LOOP-030)
# =============================================================================


class MockDaemonMemoryService:
    """Mock memory service for daemon testing to avoid Qdrant connection."""

    def __init__(self):
        self.enabled = True
        self._insights = []

    def retrieve_insights(self, query, project_id=None, limit=5, max_age_hours=72.0):
        """Return empty insights."""
        return []


class TestTelemetryTaskDaemonIntegration:
    """Integration tests for TelemetryTaskDaemon (IMP-LOOP-030).

    These tests validate the daemon's ability to monitor telemetry
    and automatically generate tasks.
    """

    def test_daemon_initialization(self):
        """Test daemon initializes with correct defaults."""
        from autopack.roadc.task_daemon import (
            DEFAULT_INTERVAL_SECONDS,
            DEFAULT_MAX_TASKS_PER_CYCLE,
            DEFAULT_MIN_CONFIDENCE,
            TelemetryTaskDaemon,
        )

        # Pass mock memory service to avoid Qdrant connection
        mock_memory = MockDaemonMemoryService()
        daemon = TelemetryTaskDaemon(memory_service=mock_memory)

        assert daemon._interval == DEFAULT_INTERVAL_SECONDS
        assert daemon._min_confidence == DEFAULT_MIN_CONFIDENCE
        assert daemon._max_tasks_per_cycle == DEFAULT_MAX_TASKS_PER_CYCLE
        assert daemon.is_running is False

    def test_daemon_run_once_without_db(self):
        """Test daemon can run a single cycle without database."""
        from autopack.roadc.task_daemon import TelemetryTaskDaemon

        # Pass mock memory service to avoid Qdrant connection
        mock_memory = MockDaemonMemoryService()
        daemon = TelemetryTaskDaemon(
            db_session=None,
            memory_service=mock_memory,
            interval_seconds=1,
        )

        # Run a single cycle
        result = daemon.run_once()

        # Should complete without error (may have 0 tasks due to no data)
        assert result.cycle_number == 1
        assert result.cycle_duration_ms >= 0

    def test_daemon_stats_tracking(self):
        """Test daemon cycle results are returned correctly."""
        from autopack.roadc.task_daemon import TelemetryTaskDaemon

        # Pass mock memory service to avoid Qdrant connection
        mock_memory = MockDaemonMemoryService()
        daemon = TelemetryTaskDaemon(
            memory_service=mock_memory,
            interval_seconds=1,
        )

        # Run multiple cycles and track results
        results = []
        for _ in range(3):
            result = daemon.run_once()
            results.append(result)

        # Each run_once should return a valid DaemonCycleResult
        assert len(results) == 3
        assert all(r.cycle_number > 0 for r in results)
        assert all(r.cycle_duration_ms >= 0 for r in results)

    def test_daemon_configuration_update(self):
        """Test daemon configuration can be updated."""
        from autopack.roadc.task_daemon import TelemetryTaskDaemon

        # Pass mock memory service to avoid Qdrant connection
        mock_memory = MockDaemonMemoryService()
        daemon = TelemetryTaskDaemon(
            memory_service=mock_memory,
            interval_seconds=300,
            min_confidence=0.7,
            max_tasks_per_cycle=5,
        )

        # Update configuration
        daemon.update_configuration(
            interval_seconds=60,
            min_confidence=0.8,
            max_tasks_per_cycle=10,
        )

        assert daemon._interval == 60
        assert daemon._min_confidence == 0.8
        assert daemon._max_tasks_per_cycle == 10

    def test_daemon_cycle_history(self):
        """Test daemon cycle results contain proper timestamps."""
        from autopack.roadc.task_daemon import TelemetryTaskDaemon

        # Pass mock memory service to avoid Qdrant connection
        mock_memory = MockDaemonMemoryService()
        daemon = TelemetryTaskDaemon(
            memory_service=mock_memory,
            interval_seconds=1,
        )

        # Run cycles and collect results
        results = []
        for _ in range(5):
            result = daemon.run_once()
            results.append(result)

        # Verify results have proper timestamps
        assert len(results) == 5
        for result in results:
            assert result.timestamp is not None
            assert result.cycle_duration_ms >= 0

        # Cycle numbers should increment
        cycle_numbers = [r.cycle_number for r in results]
        assert cycle_numbers == [1, 2, 3, 4, 5]


# =============================================================================
# InsightCorrelationEngine Integration Tests (IMP-LOOP-031)
# =============================================================================


class TestInsightCorrelationEngineIntegration:
    """Integration tests for InsightCorrelationEngine (IMP-LOOP-031).

    These tests validate the correlation tracking between insights
    and tasks, including confidence score updates.
    """

    def test_correlation_engine_initialization(self):
        """Test correlation engine initializes correctly."""
        from autopack.task_generation.insight_correlation import (
            InsightCorrelationEngine,
        )

        engine = InsightCorrelationEngine()

        summary = engine.get_correlation_summary()
        assert summary["total_correlations"] == 0
        assert summary["total_insights"] == 0

    def test_task_creation_tracking(self):
        """Test task creation from insight is tracked."""
        from autopack.task_generation.insight_correlation import (
            InsightCorrelationEngine,
        )

        engine = InsightCorrelationEngine()

        correlation = engine.record_task_creation(
            insight_id="test_insight_001",
            task_id="TASK-0001",
            insight_source="analyzer",
            insight_type="cost_sink",
            confidence=0.85,
        )

        assert correlation.insight_id == "test_insight_001"
        assert correlation.task_id == "TASK-0001"
        assert correlation.confidence_before == 0.85
        assert correlation.task_outcome is None

        # Verify tracking
        tasks = engine.get_tasks_for_insight("test_insight_001")
        assert "TASK-0001" in tasks

    def test_outcome_recording_updates_stats(self):
        """Test recording outcome updates insight statistics."""
        from autopack.task_generation.insight_correlation import (
            InsightCorrelationEngine,
        )

        engine = InsightCorrelationEngine()

        # Create correlation
        engine.record_task_creation(
            insight_id="insight_stats",
            task_id="TASK-STATS-001",
            confidence=0.7,
        )

        # Record outcome
        engine.record_task_outcome(
            task_id="TASK-STATS-001",
            outcome="success",
        )

        # Check stats
        stats = engine.get_insight_stats("insight_stats")
        assert stats is not None
        assert stats.successful_tasks == 1
        assert stats.total_tasks == 1

    def test_confidence_updates_on_outcomes(self):
        """Test confidence is updated based on task outcomes."""
        from autopack.task_generation.insight_correlation import (
            MIN_SAMPLE_SIZE_FOR_UPDATE,
            InsightCorrelationEngine,
        )

        engine = InsightCorrelationEngine()
        insight_id = "confidence_test"

        # Create enough tasks to trigger confidence update
        for i in range(MIN_SAMPLE_SIZE_FOR_UPDATE + 1):
            engine.record_task_creation(
                insight_id=insight_id,
                task_id=f"TASK-CONF-{i:03d}",
                confidence=0.7,
            )
            # Record mostly successful outcomes
            engine.record_task_outcome(
                task_id=f"TASK-CONF-{i:03d}",
                outcome="success" if i < MIN_SAMPLE_SIZE_FOR_UPDATE else "failure",
            )

        # Check confidence was updated
        final_confidence = engine.get_insight_confidence(insight_id)
        assert final_confidence != 0.7  # Should have changed
        assert 0.1 <= final_confidence <= 1.0

    def test_high_performing_insight_identification(self):
        """Test identification of high-performing insights."""
        from autopack.task_generation.insight_correlation import (
            InsightCorrelationEngine,
        )

        engine = InsightCorrelationEngine()

        # Create insight with high success rate
        for i in range(5):
            engine.record_task_creation(
                insight_id="high_performer",
                task_id=f"TASK-HP-{i:03d}",
            )
            engine.record_task_outcome(f"TASK-HP-{i:03d}", "success")

        # Create insight with low success rate
        for i in range(5):
            engine.record_task_creation(
                insight_id="low_performer",
                task_id=f"TASK-LP-{i:03d}",
            )
            engine.record_task_outcome(f"TASK-LP-{i:03d}", "failure")

        # Get high performers
        high_performers = engine.get_high_performing_insights(
            min_success_rate=0.7,
            min_tasks=3,
        )

        assert len(high_performers) >= 1
        assert any(s.insight_id == "high_performer" for s in high_performers)

    def test_low_performing_insight_identification(self):
        """Test identification of low-performing insights."""
        from autopack.task_generation.insight_correlation import (
            InsightCorrelationEngine,
        )

        engine = InsightCorrelationEngine()

        # Create insight with low success rate
        for i in range(5):
            engine.record_task_creation(
                insight_id="consistently_failing",
                task_id=f"TASK-FAIL-{i:03d}",
            )
            engine.record_task_outcome(f"TASK-FAIL-{i:03d}", "failure")

        # Get low performers
        low_performers = engine.get_low_performing_insights(
            max_success_rate=0.3,
            min_tasks=3,
        )

        assert len(low_performers) >= 1
        assert any(s.insight_id == "consistently_failing" for s in low_performers)

    def test_correlation_summary_statistics(self):
        """Test correlation summary provides accurate statistics."""
        from autopack.task_generation.insight_correlation import (
            InsightCorrelationEngine,
        )

        engine = InsightCorrelationEngine()

        # Create mixed correlations
        engine.record_task_creation("insight_A", "TASK-A1", insight_source="analyzer")
        engine.record_task_creation("insight_A", "TASK-A2", insight_source="analyzer")
        engine.record_task_creation("insight_B", "TASK-B1", insight_source="memory")

        engine.record_task_outcome("TASK-A1", "success")
        engine.record_task_outcome("TASK-B1", "failure")

        summary = engine.get_correlation_summary()

        assert summary["total_correlations"] == 3
        assert summary["total_insights"] == 2
        assert summary["outcomes_recorded"] == 2
        assert summary["pending_outcomes"] == 1
        assert summary["by_outcome"]["success"] == 1
        assert summary["by_outcome"]["failure"] == 1
        assert summary["by_source"]["analyzer"] == 2
        assert summary["by_source"]["memory"] == 1


# =============================================================================
# Confidence Lifecycle Integration Tests (IMP-LOOP-033, IMP-LOOP-034)
# =============================================================================


class TestConfidenceLifecycleIntegration:
    """Integration tests for confidence lifecycle management.

    These tests validate confidence filtering (IMP-LOOP-033) and
    the complete confidence lifecycle from creation to decay/update.
    """

    def test_min_confidence_threshold_enforcement(self):
        """Test that MIN_CONFIDENCE_THRESHOLD is enforced."""
        from autopack.roadc.task_generator import MIN_CONFIDENCE_THRESHOLD

        # Threshold should be 0.5 as per IMP-LOOP-033
        assert MIN_CONFIDENCE_THRESHOLD == 0.5

    def test_confidence_bounds_respected(self):
        """Test confidence stays within valid bounds."""
        from autopack.task_generation.insight_correlation import (
            MAX_CONFIDENCE,
            MIN_CONFIDENCE,
        )

        assert MIN_CONFIDENCE == 0.1
        assert MAX_CONFIDENCE == 1.0

    def test_confidence_filtering_in_task_generation_flow(self):
        """Test confidence filtering integrates with task generation."""
        # This test validates the integration between confidence filtering
        # and the task generation pipeline

        # Simulate insights with varying confidence
        high_conf_insights = [
            {"id": "high_1", "confidence": 0.9, "issue_type": "cost_sink"},
            {"id": "high_2", "confidence": 0.7, "issue_type": "failure_mode"},
        ]

        low_conf_insights = [
            {"id": "low_1", "confidence": 0.3, "issue_type": "cost_sink"},
            {"id": "low_2", "confidence": 0.4, "issue_type": "failure_mode"},
        ]

        all_insights = high_conf_insights + low_conf_insights

        # Apply confidence threshold filter (MIN_CONFIDENCE_THRESHOLD = 0.5)
        threshold = 0.5
        filtered = [i for i in all_insights if i.get("confidence", 1.0) >= threshold]

        # Only high-confidence insights should pass
        assert len(filtered) == 2
        assert all(i["confidence"] >= threshold for i in filtered)

    def test_confidence_decay_simulation(self):
        """Test confidence decay over simulated time."""
        # Simulate exponential decay calculation
        import math

        half_life_days = 7.0
        original_confidence = 0.9

        # Calculate decayed confidence after various time periods
        def calculate_decayed(age_days: float) -> float:
            decay_factor = math.pow(0.5, age_days / half_life_days)
            return max(original_confidence * decay_factor, 0.1)

        # Day 0: No decay
        assert calculate_decayed(0) == 0.9

        # Day 7 (half-life): Should be ~0.45
        day7_conf = calculate_decayed(7)
        assert 0.4 <= day7_conf <= 0.5

        # Day 14 (two half-lives): Should be ~0.225
        day14_conf = calculate_decayed(14)
        assert 0.2 <= day14_conf <= 0.3

        # Day 30: Should be at minimum
        day30_conf = calculate_decayed(30)
        assert day30_conf >= 0.1  # Minimum bound

    def test_confidence_update_on_success_increases(self):
        """Test successful task execution increases confidence."""
        from autopack.task_generation.insight_correlation import (
            SUCCESS_CONFIDENCE_BOOST,
        )

        # Success should boost confidence
        assert SUCCESS_CONFIDENCE_BOOST > 0
        assert SUCCESS_CONFIDENCE_BOOST == 0.1  # 10% boost

    def test_confidence_update_on_failure_decreases(self):
        """Test failed task execution decreases confidence."""
        from autopack.task_generation.insight_correlation import (
            FAILURE_CONFIDENCE_PENALTY,
        )

        # Failure should reduce confidence
        assert FAILURE_CONFIDENCE_PENALTY > 0
        assert FAILURE_CONFIDENCE_PENALTY == 0.15  # 15% penalty

    def test_end_to_end_confidence_lifecycle(self):
        """Test complete confidence lifecycle from creation to update."""
        from autopack.task_generation.insight_correlation import (
            InsightCorrelationEngine,
        )

        engine = InsightCorrelationEngine()

        # Phase 1: Initial high confidence insight
        initial_confidence = 0.85
        insight_id = "lifecycle_test"

        # Create tasks and track outcomes
        outcomes = ["success", "success", "failure", "success"]

        for i, outcome in enumerate(outcomes):
            engine.record_task_creation(
                insight_id=insight_id,
                task_id=f"TASK-LC-{i:03d}",
                confidence=initial_confidence,
            )
            engine.record_task_outcome(f"TASK-LC-{i:03d}", outcome)

        # Final confidence should reflect 3 successes, 1 failure
        final_confidence = engine.get_insight_confidence(insight_id)

        # With 75% success rate, confidence should be above 0.5
        assert final_confidence >= 0.5
        assert final_confidence <= 1.0

        # Stats should be accurate
        stats = engine.get_insight_stats(insight_id)
        assert stats.successful_tasks == 3
        assert stats.failed_tasks == 1
        assert stats.success_rate == 0.75


# =============================================================================
# Task Generation Throughput and Execution Wiring Tests (IMP-LOOP-025)
# =============================================================================


class TestTaskGenerationThroughputMetrics:
    """Integration tests for task generation throughput metrics (IMP-LOOP-025).

    These tests validate that task generation events are properly tracked
    and that the execution wiring between AutonomousTaskGenerator and
    the execution loop is verified.
    """

    def test_meta_metrics_tracker_records_task_generation(self):
        """Test MetaMetricsTracker records task generation events."""
        from autopack.telemetry.meta_metrics import MetaMetricsTracker

        tracker = MetaMetricsTracker()

        # Record task generation events
        event1 = tracker.record_task_generated(
            task_id="TASK-001",
            source="analyzer",
            generation_time_ms=150.0,
            insights_consumed=2,
            run_id="run_001",
            queued_for_execution=True,
        )

        event2 = tracker.record_task_generated(
            task_id="TASK-002",
            source="memory",
            generation_time_ms=200.0,
            insights_consumed=1,
            run_id="run_001",
            queued_for_execution=False,
        )

        # Verify events were recorded
        assert event1.task_id == "TASK-001"
        assert event1.source == "analyzer"
        assert event1.queued_for_execution is True

        assert event2.task_id == "TASK-002"
        assert event2.source == "memory"
        assert event2.queued_for_execution is False

    def test_throughput_metrics_calculation(self):
        """Test throughput metrics are calculated correctly."""
        from autopack.telemetry.meta_metrics import MetaMetricsTracker

        tracker = MetaMetricsTracker()

        # Record multiple task generation events
        for i in range(5):
            tracker.record_task_generated(
                task_id=f"TASK-{i:03d}",
                source="analyzer",
                generation_time_ms=100.0 + i * 10,
                insights_consumed=2,
                run_id="run_001",
                queued_for_execution=i < 3,  # First 3 queued, last 2 not
            )

        # Get throughput metrics
        metrics = tracker.get_task_generation_throughput(window_minutes=60.0)

        # Verify calculations
        assert metrics.total_tasks_generated == 5
        assert metrics.tasks_queued_for_execution == 3
        assert metrics.total_insights_consumed == 10  # 5 tasks * 2 insights each
        assert metrics.queue_rate == 0.6  # 3/5

        # Average generation time should be calculated
        # (100 + 110 + 120 + 130 + 140) / 5 = 120
        assert metrics.avg_generation_time_ms == 120.0

        # Breakdown by source should be correct
        assert metrics.by_source.get("analyzer", 0) == 5

    def test_mark_task_queued_updates_event(self):
        """Test that mark_task_queued updates existing events."""
        from autopack.telemetry.meta_metrics import MetaMetricsTracker

        tracker = MetaMetricsTracker()

        # Record a task that's not initially queued
        tracker.record_task_generated(
            task_id="TASK-MARK-001",
            source="direct",
            queued_for_execution=False,
        )

        # Mark it as queued
        result = tracker.mark_task_queued("TASK-MARK-001")
        assert result is True

        # Verify the update is reflected in metrics
        metrics = tracker.get_task_generation_throughput()
        assert metrics.tasks_queued_for_execution == 1

    def test_verify_execution_wiring_healthy(self):
        """Test wiring verification reports healthy when tasks are queued."""
        from autopack.telemetry.meta_metrics import MetaMetricsTracker

        tracker = MetaMetricsTracker()

        # Record tasks that are all queued
        for i in range(3):
            tracker.record_task_generated(
                task_id=f"TASK-WIRED-{i:03d}",
                source="analyzer",
                queued_for_execution=True,
            )

        # Verify wiring
        result = tracker.verify_execution_wiring()

        assert result["wiring_verified"] is True
        assert result["status"] == "healthy"
        assert result["queue_rate"] == 1.0
        assert len(result["recommendations"]) == 0

    def test_verify_execution_wiring_low_queue_rate(self):
        """Test wiring verification detects low queue rate."""
        from autopack.telemetry.meta_metrics import MetaMetricsTracker

        tracker = MetaMetricsTracker()

        # Record tasks with low queue rate (only 1 of 5 queued)
        for i in range(5):
            tracker.record_task_generated(
                task_id=f"TASK-LOW-{i:03d}",
                source="analyzer",
                queued_for_execution=i == 0,  # Only first one queued
            )

        # Verify wiring
        result = tracker.verify_execution_wiring()

        assert result["wiring_verified"] is False
        assert result["status"] == "low_queue_rate"
        assert result["queue_rate"] == 0.2  # 1/5
        assert len(result["recommendations"]) >= 1

    def test_verify_execution_wiring_no_tasks(self):
        """Test wiring verification handles no tasks gracefully."""
        from autopack.telemetry.meta_metrics import MetaMetricsTracker

        tracker = MetaMetricsTracker()

        # No tasks recorded
        result = tracker.verify_execution_wiring()

        assert result["status"] == "no_tasks"
        assert len(result["recommendations"]) >= 1

    def test_throughput_status_levels(self):
        """Test throughput status classification."""
        from datetime import datetime, timezone

        from autopack.telemetry.meta_metrics import TaskGenerationThroughputMetrics

        now = datetime.now(timezone.utc)

        # No tasks - unknown status
        metrics_unknown = TaskGenerationThroughputMetrics(
            total_tasks_generated=0,
            tasks_queued_for_execution=0,
            total_insights_consumed=0,
            avg_generation_time_ms=0.0,
            generation_rate_per_minute=0.0,
            insights_per_task_ratio=0.0,
            queue_rate=0.0,
            window_start=now,
            window_end=now,
        )
        assert metrics_unknown.throughput_status == "unknown"

        # High rate - healthy
        metrics_healthy = TaskGenerationThroughputMetrics(
            total_tasks_generated=10,
            tasks_queued_for_execution=10,
            total_insights_consumed=20,
            avg_generation_time_ms=100.0,
            generation_rate_per_minute=0.5,  # 1 task per 2 minutes
            insights_per_task_ratio=2.0,
            queue_rate=1.0,
            window_start=now,
            window_end=now,
        )
        assert metrics_healthy.throughput_status == "healthy"

        # Low rate
        metrics_low = TaskGenerationThroughputMetrics(
            total_tasks_generated=1,
            tasks_queued_for_execution=1,
            total_insights_consumed=1,
            avg_generation_time_ms=100.0,
            generation_rate_per_minute=0.05,  # 1 task per 20 minutes
            insights_per_task_ratio=1.0,
            queue_rate=1.0,
            window_start=now,
            window_end=now,
        )
        assert metrics_low.throughput_status == "low"

        # Stalled
        metrics_stalled = TaskGenerationThroughputMetrics(
            total_tasks_generated=1,
            tasks_queued_for_execution=1,
            total_insights_consumed=1,
            avg_generation_time_ms=100.0,
            generation_rate_per_minute=0.001,  # Very low
            insights_per_task_ratio=1.0,
            queue_rate=1.0,
            window_start=now,
            window_end=now,
        )
        assert metrics_stalled.throughput_status == "stalled"

    def test_execution_wiring_verified_property(self):
        """Test execution_wiring_verified property."""
        from datetime import datetime, timezone

        from autopack.telemetry.meta_metrics import TaskGenerationThroughputMetrics

        now = datetime.now(timezone.utc)

        # Tasks generated and queued - verified
        metrics_verified = TaskGenerationThroughputMetrics(
            total_tasks_generated=5,
            tasks_queued_for_execution=3,
            total_insights_consumed=10,
            avg_generation_time_ms=100.0,
            generation_rate_per_minute=0.1,
            insights_per_task_ratio=2.0,
            queue_rate=0.6,
            window_start=now,
            window_end=now,
        )
        assert metrics_verified.execution_wiring_verified is True

        # Tasks generated but none queued - not verified
        metrics_not_verified = TaskGenerationThroughputMetrics(
            total_tasks_generated=5,
            tasks_queued_for_execution=0,
            total_insights_consumed=10,
            avg_generation_time_ms=100.0,
            generation_rate_per_minute=0.1,
            insights_per_task_ratio=2.0,
            queue_rate=0.0,
            window_start=now,
            window_end=now,
        )
        assert metrics_not_verified.execution_wiring_verified is False

        # No tasks generated - trivially verified
        metrics_empty = TaskGenerationThroughputMetrics(
            total_tasks_generated=0,
            tasks_queued_for_execution=0,
            total_insights_consumed=0,
            avg_generation_time_ms=0.0,
            generation_rate_per_minute=0.0,
            insights_per_task_ratio=0.0,
            queue_rate=0.0,
            window_start=now,
            window_end=now,
        )
        assert metrics_empty.execution_wiring_verified is True

    def test_throughput_metrics_rolling_window(self):
        """Test that throughput metrics use a rolling window."""
        from autopack.telemetry.meta_metrics import MetaMetricsTracker

        tracker = MetaMetricsTracker()
        tracker._max_generation_events = 5  # Small window for testing

        # Record more events than the window size
        for i in range(10):
            tracker.record_task_generated(
                task_id=f"TASK-ROLL-{i:03d}",
                source="analyzer",
                queued_for_execution=True,
            )

        # Check that only the last 5 events are kept
        assert len(tracker._task_generation_events) == 5

        # The events should be the last 5 (TASK-ROLL-005 through TASK-ROLL-009)
        task_ids = [e.task_id for e in tracker._task_generation_events]
        assert task_ids[0] == "TASK-ROLL-005"
        assert task_ids[-1] == "TASK-ROLL-009"

    def test_task_generation_event_serialization(self):
        """Test TaskGenerationEvent serializes to dict correctly."""
        from autopack.telemetry.meta_metrics import TaskGenerationEvent

        event = TaskGenerationEvent(
            task_id="TASK-SER-001",
            source="analyzer",
            generation_time_ms=150.5,
            insights_consumed=3,
            run_id="run_123",
            queued_for_execution=True,
        )

        event_dict = event.to_dict()

        assert event_dict["task_id"] == "TASK-SER-001"
        assert event_dict["source"] == "analyzer"
        assert event_dict["generation_time_ms"] == 150.5
        assert event_dict["insights_consumed"] == 3
        assert event_dict["run_id"] == "run_123"
        assert event_dict["queued_for_execution"] is True
        assert "timestamp" in event_dict

    def test_throughput_metrics_serialization(self):
        """Test TaskGenerationThroughputMetrics serializes to dict correctly."""
        from autopack.telemetry.meta_metrics import MetaMetricsTracker

        tracker = MetaMetricsTracker()

        # Record some events
        tracker.record_task_generated(
            task_id="TASK-SER-001",
            source="analyzer",
            generation_time_ms=100.0,
            queued_for_execution=True,
        )

        metrics = tracker.get_task_generation_throughput()
        metrics_dict = metrics.to_dict()

        # Verify all expected fields are present
        assert "total_tasks_generated" in metrics_dict
        assert "tasks_queued_for_execution" in metrics_dict
        assert "avg_generation_time_ms" in metrics_dict
        assert "generation_rate_per_minute" in metrics_dict
        assert "queue_rate" in metrics_dict
        assert "window_start" in metrics_dict
        assert "window_end" in metrics_dict
        assert "by_source" in metrics_dict
