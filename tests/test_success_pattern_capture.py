"""
Tests for Success Pattern Capture (IMP-LOOP-027).

Tests the success pattern recording functionality that enables positive
reinforcement learning by capturing 'what works' alongside 'what fails'.
"""

from unittest.mock import Mock

from autopack.executor.learning_pipeline import LearningPipeline, SuccessPattern
from autopack.feedback_pipeline import FeedbackPipeline, PhaseOutcome


class TestSuccessPatternDataclass:
    """Tests for SuccessPattern dataclass."""

    def test_success_pattern_creation(self):
        """SuccessPattern should be creatable with required fields."""
        import time

        pattern = SuccessPattern(
            phase_id="test-phase",
            action_taken="Implemented feature successfully",
            context_summary="Build phase completed",
            recorded_at=time.time(),
        )

        assert pattern.phase_id == "test-phase"
        assert pattern.action_taken == "Implemented feature successfully"
        assert pattern.context_summary == "Build phase completed"
        assert pattern.confidence == 0.8  # Default initial confidence
        assert pattern.occurrence_count == 1

    def test_success_pattern_with_task_category(self):
        """SuccessPattern should support task_category field."""
        import time

        pattern = SuccessPattern(
            phase_id="test-phase",
            action_taken="Tests passed",
            context_summary="All unit tests passed",
            recorded_at=time.time(),
            task_category="testing",
        )

        assert pattern.task_category == "testing"

    def test_success_pattern_confidence_calculation(self):
        """SuccessPattern confidence should increase with occurrences."""
        import time

        pattern = SuccessPattern(
            phase_id="test-phase",
            action_taken="Successful action",
            context_summary="Context",
            recorded_at=time.time(),
        )

        # Initial confidence
        assert pattern.confidence == 0.8

        # Increment occurrence and check confidence increases
        pattern.increment_occurrence()
        assert pattern.occurrence_count == 2
        assert pattern.confidence > 0.8

        # Multiple increments
        for _ in range(4):
            pattern.increment_occurrence()

        # Should cap at 1.0
        assert pattern.confidence <= 1.0


class TestLearningPipelineSuccessPatterns:
    """Tests for success pattern recording in LearningPipeline."""

    def test_record_success_pattern(self):
        """LearningPipeline should record success patterns."""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test-phase", "name": "Test Phase"}

        pipeline.record_success_pattern(
            phase=phase,
            action_taken="Phase completed successfully",
            context_summary="Build succeeded",
        )

        patterns = pipeline.get_all_success_patterns()
        assert len(patterns) == 1
        assert patterns[0].phase_id == "test-phase"
        assert patterns[0].action_taken == "Phase completed successfully"

    def test_record_multiple_success_patterns(self):
        """LearningPipeline should record multiple success patterns."""
        pipeline = LearningPipeline(run_id="test-run")

        phase1 = {"phase_id": "phase-1", "name": "Phase 1"}
        phase2 = {"phase_id": "phase-2", "name": "Phase 2"}

        pipeline.record_success_pattern(
            phase=phase1, action_taken="Action 1", context_summary="Context 1"
        )
        pipeline.record_success_pattern(
            phase=phase2, action_taken="Action 2", context_summary="Context 2"
        )

        assert pipeline.get_success_pattern_count() == 2

    def test_duplicate_pattern_boosts_confidence(self):
        """Recording same pattern should boost confidence, not create duplicate."""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test-phase", "name": "Test Phase"}

        # Record same pattern twice
        pipeline.record_success_pattern(
            phase=phase, action_taken="Successful action", context_summary="Context"
        )
        initial_confidence = pipeline.get_all_success_patterns()[0].confidence

        pipeline.record_success_pattern(
            phase=phase, action_taken="Successful action", context_summary="Context"
        )

        # Should still have only 1 pattern, but with boosted confidence
        patterns = pipeline.get_all_success_patterns()
        assert len(patterns) == 1
        assert patterns[0].occurrence_count == 2
        assert patterns[0].confidence > initial_confidence

    def test_get_success_patterns_for_phase(self):
        """Should retrieve relevant success patterns for a phase."""
        pipeline = LearningPipeline(run_id="test-run")

        # Record patterns with different phase_ids
        pipeline.record_success_pattern(
            phase={"phase_id": "build", "task_category": "build"},
            action_taken="Build action",
            context_summary="Build context",
        )
        pipeline.record_success_pattern(
            phase={"phase_id": "test", "task_category": "test"},
            action_taken="Test action",
            context_summary="Test context",
        )

        # Query for build phase
        relevant = pipeline.get_success_patterns_for_phase({"phase_id": "build"})
        assert len(relevant) == 1
        assert relevant[0].phase_id == "build"

    def test_get_success_patterns_by_category(self):
        """Should retrieve patterns by task_category if phase_id doesn't match."""
        pipeline = LearningPipeline(run_id="test-run")

        pipeline.record_success_pattern(
            phase={"phase_id": "build-1", "task_category": "build"},
            action_taken="Build action",
            context_summary="Build context",
        )

        # Query with different phase_id but same category
        relevant = pipeline.get_success_patterns_for_phase(
            {"phase_id": "build-2", "task_category": "build"}
        )
        assert len(relevant) == 1
        assert relevant[0].task_category == "build"

    def test_success_pattern_recording_graceful_failure(self):
        """Should handle errors gracefully when recording patterns."""
        pipeline = LearningPipeline(run_id="test-run")

        # Pass invalid phase (should not crash)
        pipeline.record_success_pattern(
            phase=None, action_taken="Action", context_summary="Context"
        )

        # Should still be operational
        valid_phase = {"phase_id": "valid", "name": "Valid"}
        pipeline.record_success_pattern(
            phase=valid_phase, action_taken="Valid action", context_summary="Valid context"
        )
        assert pipeline.get_success_pattern_count() >= 1


class TestFeedbackPipelineSuccessPatterns:
    """Tests for success pattern integration in FeedbackPipeline."""

    def test_success_outcome_records_success_pattern(self):
        """Successful outcome should trigger success pattern recording."""
        mock_learning = Mock()
        mock_learning.record_success_pattern = Mock()

        pipeline = FeedbackPipeline(
            learning_pipeline=mock_learning,
            run_id="test-run",
        )

        outcome = PhaseOutcome(
            phase_id="test-phase",
            phase_type="build",
            success=True,
            status="Build completed successfully",
        )

        pipeline.process_phase_outcome(outcome)

        # Verify record_success_pattern was called
        mock_learning.record_success_pattern.assert_called_once()
        call_args = mock_learning.record_success_pattern.call_args
        assert call_args[1]["phase"]["phase_id"] == "test-phase"

    def test_failure_outcome_records_hint_not_success_pattern(self):
        """Failed outcome should record hint, not success pattern."""
        mock_learning = Mock()
        mock_learning.record_hint = Mock()
        mock_learning.record_success_pattern = Mock()

        pipeline = FeedbackPipeline(
            learning_pipeline=mock_learning,
            run_id="test-run",
        )

        outcome = PhaseOutcome(
            phase_id="test-phase",
            phase_type="build",
            success=False,
            status="Build failed",
            error_message="Compilation error",
        )

        pipeline.process_phase_outcome(outcome)

        # Verify record_hint was called (for failure)
        mock_learning.record_hint.assert_called_once()
        # Verify record_success_pattern was NOT called
        mock_learning.record_success_pattern.assert_not_called()

    def test_build_success_context_summary(self):
        """_build_success_context_summary should create meaningful summaries."""
        pipeline = FeedbackPipeline(run_id="test-run")

        outcome = PhaseOutcome(
            phase_id="test-phase",
            phase_type="build",
            success=True,
            status="Build completed",
            execution_time_seconds=30.5,
            tokens_used=1000,
            learnings=["Learned item 1", "Learned item 2"],
        )

        summary = pipeline._build_success_context_summary(outcome)

        assert "build" in summary.lower()
        assert "30.5" in summary
        assert "1000" in summary

    def test_success_pattern_stats_tracking(self):
        """FeedbackPipeline should track success pattern stats."""
        mock_learning = Mock()
        mock_learning.record_success_pattern = Mock()

        pipeline = FeedbackPipeline(
            learning_pipeline=mock_learning,
            run_id="test-run",
        )

        outcome = PhaseOutcome(
            phase_id="test-phase",
            phase_type="build",
            success=True,
            status="completed",
        )

        pipeline.process_phase_outcome(outcome)

        # Check stats were updated
        assert pipeline._stats.get("success_patterns_recorded", 0) == 1


class TestSuccessPatternPersistence:
    """Tests for success pattern persistence to memory service."""

    def test_success_pattern_persisted_to_memory(self):
        """Success patterns should be persisted to memory service."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock(return_value=True)

        pipeline = LearningPipeline(
            run_id="test-run", memory_service=mock_memory, project_id="test-project"
        )

        phase = {"phase_id": "test-phase", "name": "Test Phase"}
        pipeline.record_success_pattern(
            phase=phase,
            action_taken="Successful action",
            context_summary="Context summary",
        )

        # Verify write_telemetry_insight was called
        mock_memory.write_telemetry_insight.assert_called_once()
        call_args = mock_memory.write_telemetry_insight.call_args

        # Verify the insight has correct type
        insight = call_args[1]["insight"]
        assert insight["insight_type"] == "success_pattern"
        assert "test-phase" in insight["description"]

    def test_success_pattern_not_persisted_if_memory_disabled(self):
        """Success patterns should not be persisted if memory is disabled."""
        mock_memory = Mock()
        mock_memory.enabled = False

        pipeline = LearningPipeline(
            run_id="test-run", memory_service=mock_memory, project_id="test-project"
        )

        phase = {"phase_id": "test-phase", "name": "Test Phase"}
        pipeline.record_success_pattern(
            phase=phase,
            action_taken="Successful action",
            context_summary="Context summary",
        )

        # Verify write_telemetry_insight was NOT called
        mock_memory.write_telemetry_insight.assert_not_called()
