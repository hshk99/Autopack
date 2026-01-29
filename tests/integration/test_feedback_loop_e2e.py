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
            enabled=True,
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
            enabled=True,
        )

        assert bridge.enabled is True
        assert bridge.memory_service == mock_memory_service

    def test_bridge_disabled_returns_zero(self, mock_memory_service):
        """Disabled bridge should return zero persisted."""
        bridge = TelemetryToMemoryBridge(
            memory_service=mock_memory_service,
            enabled=False,
        )

        result = bridge.persist_insights([{"test": "issue"}], "run_001")

        assert result == 0

    def test_bridge_no_memory_service_returns_zero(self):
        """Bridge without memory service should return zero."""
        bridge = TelemetryToMemoryBridge(
            memory_service=None,
            enabled=True,
        )

        result = bridge.persist_insights([{"test": "issue"}], "run_001")

        assert result == 0

    def test_bridge_deduplication(self, mock_memory_service):
        """Bridge should deduplicate insights."""
        bridge = TelemetryToMemoryBridge(
            memory_service=mock_memory_service,
            enabled=True,
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
            enabled=True,
        )

        issues = [{"issue_type": "test", "rank": 1}]
        bridge.persist_insights(issues, "run_001")

        bridge.clear_cache()

        # Should be able to persist again after clear
        result = bridge.persist_insights(issues, "run_001")
        assert result == 1
