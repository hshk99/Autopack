"""Tests for IMP-LOOP-028 End-to-End Task Attribution System.

This module tests the task attribution tracking functionality that links
generated tasks to their phase executions and outcomes for closed-loop learning.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from autopack.feedback_pipeline import FeedbackPipeline, PhaseOutcome
from autopack.task_generation.task_effectiveness_tracker import (
    TaskAttributionOutcome, TaskEffectivenessTracker, TaskExecutionMapping)


class TestTaskExecutionMapping:
    """Tests for TaskExecutionMapping dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating a basic TaskExecutionMapping."""
        mapping = TaskExecutionMapping(
            task_id="IMP-LOOP-028",
            phase_id="phase-123",
        )
        assert mapping.task_id == "IMP-LOOP-028"
        assert mapping.phase_id == "phase-123"
        assert mapping.outcome_recorded is False
        assert mapping.outcome_recorded_at is None
        assert isinstance(mapping.registered_at, datetime)

    def test_to_dict(self) -> None:
        """Test converting TaskExecutionMapping to dict."""
        mapping = TaskExecutionMapping(
            task_id="IMP-LOOP-028",
            phase_id="phase-123",
        )
        data = mapping.to_dict()

        assert data["task_id"] == "IMP-LOOP-028"
        assert data["phase_id"] == "phase-123"
        assert data["outcome_recorded"] is False
        assert data["outcome_recorded_at"] is None
        assert "registered_at" in data

    def test_to_dict_with_outcome(self) -> None:
        """Test to_dict when outcome has been recorded."""
        mapping = TaskExecutionMapping(
            task_id="IMP-LOOP-028",
            phase_id="phase-123",
        )
        mapping.outcome_recorded = True
        mapping.outcome_recorded_at = datetime.now()

        data = mapping.to_dict()
        assert data["outcome_recorded"] is True
        assert data["outcome_recorded_at"] is not None


class TestTaskAttributionOutcome:
    """Tests for TaskAttributionOutcome dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating a basic TaskAttributionOutcome."""
        outcome = TaskAttributionOutcome(
            task_id="IMP-LOOP-028",
            phase_id="phase-123",
            success=True,
            execution_time_seconds=45.0,
            tokens_used=5000,
        )
        assert outcome.task_id == "IMP-LOOP-028"
        assert outcome.phase_id == "phase-123"
        assert outcome.success is True
        assert outcome.execution_time_seconds == 45.0
        assert outcome.tokens_used == 5000
        assert outcome.error_message is None

    def test_creation_with_error(self) -> None:
        """Test creating TaskAttributionOutcome with error."""
        outcome = TaskAttributionOutcome(
            task_id="IMP-LOOP-028",
            phase_id="phase-123",
            success=False,
            error_message="Build failed",
        )
        assert outcome.success is False
        assert outcome.error_message == "Build failed"

    def test_to_dict(self) -> None:
        """Test converting TaskAttributionOutcome to dict."""
        outcome = TaskAttributionOutcome(
            task_id="IMP-LOOP-028",
            phase_id="phase-123",
            success=True,
            execution_time_seconds=30.0,
            tokens_used=8000,
            effectiveness_score=0.9,
            metadata={"phase_type": "build"},
        )
        data = outcome.to_dict()

        assert data["task_id"] == "IMP-LOOP-028"
        assert data["phase_id"] == "phase-123"
        assert data["success"] is True
        assert data["execution_time_seconds"] == 30.0
        assert data["tokens_used"] == 8000
        assert data["effectiveness_score"] == 0.9
        assert data["metadata"] == {"phase_type": "build"}
        assert "recorded_at" in data


class TestRegisterTaskExecution:
    """Tests for register_task_execution method."""

    @pytest.fixture
    def tracker(self) -> TaskEffectivenessTracker:
        """Create a tracker for testing."""
        return TaskEffectivenessTracker()

    def test_register_new_mapping(self, tracker: TaskEffectivenessTracker) -> None:
        """Test registering a new task-to-phase mapping."""
        mapping = tracker.register_task_execution(
            task_id="IMP-LOOP-028",
            phase_id="phase-123",
        )

        assert mapping.task_id == "IMP-LOOP-028"
        assert mapping.phase_id == "phase-123"
        assert mapping.outcome_recorded is False

    def test_register_updates_existing_mapping(self, tracker: TaskEffectivenessTracker) -> None:
        """Test that registering updates existing mapping."""
        mapping1 = tracker.register_task_execution(
            task_id="IMP-LOOP-028",
            phase_id="phase-123",
        )
        mapping2 = tracker.register_task_execution(
            task_id="IMP-LOOP-028",
            phase_id="phase-456",
        )

        # Should return the same mapping object with updated phase_id
        assert mapping1 is mapping2
        assert mapping2.phase_id == "phase-456"

    def test_register_multiple_tasks(self, tracker: TaskEffectivenessTracker) -> None:
        """Test registering multiple different tasks."""
        tracker.register_task_execution("IMP-LOOP-028", "phase-1")
        tracker.register_task_execution("IMP-LOOP-029", "phase-2")
        tracker.register_task_execution("IMP-LOOP-030", "phase-3")

        summary = tracker.get_task_attribution_summary()
        assert summary["total_mappings"] == 3

    def test_get_mapping_after_register(self, tracker: TaskEffectivenessTracker) -> None:
        """Test retrieving mapping after registration."""
        tracker.register_task_execution("IMP-LOOP-028", "phase-123")

        mapping = tracker.get_task_execution_mapping("IMP-LOOP-028")
        assert mapping is not None
        assert mapping.task_id == "IMP-LOOP-028"
        assert mapping.phase_id == "phase-123"

    def test_get_mapping_nonexistent(self, tracker: TaskEffectivenessTracker) -> None:
        """Test getting mapping for non-existent task returns None."""
        mapping = tracker.get_task_execution_mapping("NONEXISTENT")
        assert mapping is None


class TestRecordTaskAttributionOutcome:
    """Tests for record_task_attribution_outcome method."""

    @pytest.fixture
    def tracker(self) -> TaskEffectivenessTracker:
        """Create a tracker for testing."""
        return TaskEffectivenessTracker()

    def test_record_successful_outcome(self, tracker: TaskEffectivenessTracker) -> None:
        """Test recording a successful outcome."""
        outcome = tracker.record_task_attribution_outcome(
            task_id="IMP-LOOP-028",
            phase_id="phase-123",
            success=True,
            execution_time_seconds=30.0,
            tokens_used=5000,
        )

        assert outcome.task_id == "IMP-LOOP-028"
        assert outcome.success is True
        # Fast execution + low tokens: 0.8 + 0.1 + 0.1 = 1.0
        assert outcome.effectiveness_score == pytest.approx(1.0)

    def test_record_failed_outcome(self, tracker: TaskEffectivenessTracker) -> None:
        """Test recording a failed outcome."""
        outcome = tracker.record_task_attribution_outcome(
            task_id="IMP-LOOP-028",
            phase_id="phase-123",
            success=False,
            error_message="Build failed",
        )

        assert outcome.success is False
        assert outcome.effectiveness_score == 0.0
        assert outcome.error_message == "Build failed"

    def test_record_updates_mapping(self, tracker: TaskEffectivenessTracker) -> None:
        """Test that recording outcome updates the mapping."""
        # Register first
        tracker.register_task_execution("IMP-LOOP-028", "phase-123")

        # Record outcome
        tracker.record_task_attribution_outcome(
            task_id="IMP-LOOP-028",
            phase_id="phase-123",
            success=True,
        )

        # Check mapping was updated
        mapping = tracker.get_task_execution_mapping("IMP-LOOP-028")
        assert mapping is not None
        assert mapping.outcome_recorded is True
        assert mapping.outcome_recorded_at is not None

    def test_record_without_prior_mapping(self, tracker: TaskEffectivenessTracker) -> None:
        """Test recording outcome without prior mapping."""
        # Record without registering first
        outcome = tracker.record_task_attribution_outcome(
            task_id="IMP-LOOP-028",
            phase_id="phase-123",
            success=True,
        )

        # Should still work
        assert outcome.task_id == "IMP-LOOP-028"

        # Mapping should not exist (was never created)
        mapping = tracker.get_task_execution_mapping("IMP-LOOP-028")
        assert mapping is None

    def test_record_with_metadata(self, tracker: TaskEffectivenessTracker) -> None:
        """Test recording outcome with metadata."""
        outcome = tracker.record_task_attribution_outcome(
            task_id="IMP-LOOP-028",
            phase_id="phase-123",
            success=True,
            metadata={"phase_type": "build", "category": "loop"},
        )

        assert outcome.metadata["phase_type"] == "build"
        assert outcome.metadata["category"] == "loop"

    def test_effectiveness_calculation_slow_execution(
        self, tracker: TaskEffectivenessTracker
    ) -> None:
        """Test effectiveness calculation for slow execution."""
        outcome = tracker.record_task_attribution_outcome(
            task_id="IMP-LOOP-028",
            phase_id="phase-123",
            success=True,
            execution_time_seconds=120.0,  # Slow (> 60s)
            tokens_used=5000,  # Low tokens
        )

        # 0.8 + 0.0 (slow) + 0.1 (low tokens) = 0.9
        assert outcome.effectiveness_score == pytest.approx(0.9)

    def test_effectiveness_calculation_high_tokens(self, tracker: TaskEffectivenessTracker) -> None:
        """Test effectiveness calculation for high token usage."""
        outcome = tracker.record_task_attribution_outcome(
            task_id="IMP-LOOP-028",
            phase_id="phase-123",
            success=True,
            execution_time_seconds=30.0,  # Fast
            tokens_used=15000,  # High tokens (> 10000)
        )

        # 0.8 + 0.1 (fast) + 0.0 (high tokens) = 0.9
        assert outcome.effectiveness_score == pytest.approx(0.9)


class TestGetAttributionOutcomes:
    """Tests for getting attribution outcomes."""

    @pytest.fixture
    def tracker(self) -> TaskEffectivenessTracker:
        """Create a tracker with some outcomes."""
        tracker = TaskEffectivenessTracker()
        tracker.record_task_attribution_outcome(
            task_id="IMP-LOOP-028",
            phase_id="phase-1",
            success=True,
        )
        tracker.record_task_attribution_outcome(
            task_id="IMP-LOOP-028",
            phase_id="phase-2",
            success=False,
        )
        tracker.record_task_attribution_outcome(
            task_id="IMP-LOOP-029",
            phase_id="phase-3",
            success=True,
        )
        return tracker

    def test_get_outcomes_for_task(self, tracker: TaskEffectivenessTracker) -> None:
        """Test getting outcomes for a specific task."""
        outcomes = tracker.get_attribution_outcomes_for_task("IMP-LOOP-028")

        assert len(outcomes) == 2
        assert all(o.task_id == "IMP-LOOP-028" for o in outcomes)

    def test_get_outcomes_for_task_nonexistent(self, tracker: TaskEffectivenessTracker) -> None:
        """Test getting outcomes for non-existent task returns empty list."""
        outcomes = tracker.get_attribution_outcomes_for_task("NONEXISTENT")
        assert outcomes == []

    def test_get_outcomes_for_phase(self, tracker: TaskEffectivenessTracker) -> None:
        """Test getting outcomes for a specific phase."""
        outcomes = tracker.get_attribution_outcomes_for_phase("phase-1")

        assert len(outcomes) == 1
        assert outcomes[0].phase_id == "phase-1"

    def test_get_outcomes_for_phase_nonexistent(self, tracker: TaskEffectivenessTracker) -> None:
        """Test getting outcomes for non-existent phase returns empty list."""
        outcomes = tracker.get_attribution_outcomes_for_phase("nonexistent-phase")
        assert outcomes == []


class TestGetTaskAttributionSummary:
    """Tests for get_task_attribution_summary method."""

    @pytest.fixture
    def tracker(self) -> TaskEffectivenessTracker:
        """Create a tracker for testing."""
        return TaskEffectivenessTracker()

    def test_empty_summary(self, tracker: TaskEffectivenessTracker) -> None:
        """Test summary with no mappings or outcomes."""
        summary = tracker.get_task_attribution_summary()

        assert summary["total_mappings"] == 0
        assert summary["mappings_with_outcomes"] == 0
        assert summary["total_outcomes"] == 0
        assert summary["successful_outcomes"] == 0
        assert summary["success_rate"] == 0.0
        assert summary["avg_effectiveness"] == 0.0
        assert summary["unmapped_tasks"] == []

    def test_summary_with_mappings(self, tracker: TaskEffectivenessTracker) -> None:
        """Test summary with mappings and outcomes."""
        # Register and record some outcomes
        tracker.register_task_execution("IMP-001", "phase-1")
        tracker.record_task_attribution_outcome(
            "IMP-001", "phase-1", success=True, execution_time_seconds=30, tokens_used=5000
        )

        tracker.register_task_execution("IMP-002", "phase-2")
        tracker.record_task_attribution_outcome("IMP-002", "phase-2", success=False)

        summary = tracker.get_task_attribution_summary()

        assert summary["total_mappings"] == 2
        assert summary["mappings_with_outcomes"] == 2
        assert summary["total_outcomes"] == 2
        assert summary["successful_outcomes"] == 1
        assert summary["success_rate"] == 0.5

    def test_summary_unmapped_tasks(self, tracker: TaskEffectivenessTracker) -> None:
        """Test summary shows unmapped registered tasks."""
        # Register a task (old style)
        tracker.register_task("IMP-UNMAPPED", priority="high")

        # Register with execution mapping
        tracker.register_task_execution("IMP-MAPPED", "phase-1")

        summary = tracker.get_task_attribution_summary()

        # IMP-UNMAPPED should be in unmapped_tasks
        assert "IMP-UNMAPPED" in summary["unmapped_tasks"]
        # IMP-MAPPED should not be in unmapped_tasks
        assert "IMP-MAPPED" not in summary["unmapped_tasks"]


class TestFeedbackPipelineTaskAttribution:
    """Tests for task attribution integration in FeedbackPipeline."""

    @pytest.fixture
    def mock_tracker(self) -> MagicMock:
        """Create a mock effectiveness tracker."""
        return MagicMock(spec=TaskEffectivenessTracker)

    @pytest.fixture
    def pipeline(self, mock_tracker: MagicMock) -> FeedbackPipeline:
        """Create a FeedbackPipeline with mock tracker."""
        pipeline = FeedbackPipeline(enabled=True)
        pipeline._effectiveness_tracker = mock_tracker
        return pipeline

    def test_track_attribution_with_task_id(
        self, pipeline: FeedbackPipeline, mock_tracker: MagicMock
    ) -> None:
        """Test that attribution is tracked when generated_task_id is present."""
        outcome = PhaseOutcome(
            phase_id="phase-123",
            phase_type="build",
            success=True,
            status="Build completed",
            execution_time_seconds=45.0,
            tokens_used=8000,
            generated_task_id="IMP-LOOP-028",
        )

        pipeline._track_task_attribution(outcome)

        # Verify register_task_execution was called
        mock_tracker.register_task_execution.assert_called_once_with(
            task_id="IMP-LOOP-028",
            phase_id="phase-123",
        )

        # Verify record_task_attribution_outcome was called
        mock_tracker.record_task_attribution_outcome.assert_called_once()
        call_kwargs = mock_tracker.record_task_attribution_outcome.call_args[1]
        assert call_kwargs["task_id"] == "IMP-LOOP-028"
        assert call_kwargs["phase_id"] == "phase-123"
        assert call_kwargs["success"] is True

    def test_track_attribution_without_task_id(
        self, pipeline: FeedbackPipeline, mock_tracker: MagicMock
    ) -> None:
        """Test that attribution is skipped when no generated_task_id."""
        outcome = PhaseOutcome(
            phase_id="phase-123",
            phase_type="build",
            success=True,
            status="Build completed",
            # No generated_task_id
        )

        pipeline._track_task_attribution(outcome)

        # Verify no tracking methods were called
        mock_tracker.register_task_execution.assert_not_called()
        mock_tracker.record_task_attribution_outcome.assert_not_called()

    def test_track_attribution_no_tracker(self) -> None:
        """Test that attribution tracking handles missing tracker gracefully."""
        pipeline = FeedbackPipeline(enabled=True)
        pipeline._effectiveness_tracker = None

        outcome = PhaseOutcome(
            phase_id="phase-123",
            phase_type="build",
            success=True,
            status="Build completed",
            generated_task_id="IMP-LOOP-028",
        )

        # Should not raise
        pipeline._track_task_attribution(outcome)

    def test_track_attribution_with_error(
        self, pipeline: FeedbackPipeline, mock_tracker: MagicMock
    ) -> None:
        """Test that attribution tracking handles errors gracefully."""
        mock_tracker.register_task_execution.side_effect = Exception("Test error")

        outcome = PhaseOutcome(
            phase_id="phase-123",
            phase_type="build",
            success=True,
            status="Build completed",
            generated_task_id="IMP-LOOP-028",
        )

        # Should not raise, just log warning
        pipeline._track_task_attribution(outcome)

    def test_get_task_attribution_summary(
        self, pipeline: FeedbackPipeline, mock_tracker: MagicMock
    ) -> None:
        """Test getting attribution summary from pipeline."""
        mock_tracker.get_task_attribution_summary.return_value = {
            "total_mappings": 5,
            "total_outcomes": 5,
            "success_rate": 0.8,
        }

        summary = pipeline.get_task_attribution_summary()

        assert summary["total_mappings"] == 5
        mock_tracker.get_task_attribution_summary.assert_called_once()

    def test_get_task_attribution_summary_no_tracker(self) -> None:
        """Test getting summary when no tracker."""
        pipeline = FeedbackPipeline(enabled=True)
        pipeline._effectiveness_tracker = None

        summary = pipeline.get_task_attribution_summary()

        assert "error" in summary


class TestPhaseOutcomeGeneratedTaskId:
    """Tests for generated_task_id field in PhaseOutcome."""

    def test_phase_outcome_with_task_id(self) -> None:
        """Test creating PhaseOutcome with generated_task_id."""
        outcome = PhaseOutcome(
            phase_id="phase-123",
            phase_type="build",
            success=True,
            status="Completed",
            generated_task_id="IMP-LOOP-028",
        )

        assert outcome.generated_task_id == "IMP-LOOP-028"

    def test_phase_outcome_without_task_id(self) -> None:
        """Test PhaseOutcome defaults generated_task_id to None."""
        outcome = PhaseOutcome(
            phase_id="phase-123",
            phase_type="build",
            success=True,
            status="Completed",
        )

        assert outcome.generated_task_id is None


class TestEndToEndAttribution:
    """Integration tests for end-to-end task attribution flow."""

    def test_full_attribution_flow(self) -> None:
        """Test complete flow: register -> execute -> record outcome."""
        tracker = TaskEffectivenessTracker()

        # 1. Register the task
        tracker.register_task("IMP-LOOP-028", priority="critical", category="loop")

        # 2. Link task to phase execution
        mapping = tracker.register_task_execution(
            task_id="IMP-LOOP-028",
            phase_id="phase-abc-123",
        )

        assert mapping.outcome_recorded is False

        # 3. Record the outcome
        outcome = tracker.record_task_attribution_outcome(
            task_id="IMP-LOOP-028",
            phase_id="phase-abc-123",
            success=True,
            execution_time_seconds=45.0,
            tokens_used=7500,
            metadata={"category": "loop"},
        )

        # 4. Verify the attribution chain is complete
        assert outcome.effectiveness_score > 0.8

        # Check mapping was updated
        updated_mapping = tracker.get_task_execution_mapping("IMP-LOOP-028")
        assert updated_mapping is not None
        assert updated_mapping.outcome_recorded is True

        # Check outcomes are retrievable
        task_outcomes = tracker.get_attribution_outcomes_for_task("IMP-LOOP-028")
        assert len(task_outcomes) == 1

        phase_outcomes = tracker.get_attribution_outcomes_for_phase("phase-abc-123")
        assert len(phase_outcomes) == 1

        # Check summary reflects the data
        summary = tracker.get_task_attribution_summary()
        assert summary["total_mappings"] == 1
        assert summary["mappings_with_outcomes"] == 1
        assert summary["total_outcomes"] == 1
        assert summary["successful_outcomes"] == 1

    def test_multiple_executions_same_task(self) -> None:
        """Test tracking multiple executions of the same task."""
        tracker = TaskEffectivenessTracker()

        # First execution fails
        tracker.register_task_execution("IMP-LOOP-028", "phase-1")
        tracker.record_task_attribution_outcome(
            task_id="IMP-LOOP-028",
            phase_id="phase-1",
            success=False,
            error_message="Build failed",
        )

        # Second execution succeeds (new phase)
        tracker.register_task_execution("IMP-LOOP-028", "phase-2")
        tracker.record_task_attribution_outcome(
            task_id="IMP-LOOP-028",
            phase_id="phase-2",
            success=True,
        )

        # Should have 2 outcomes for this task
        outcomes = tracker.get_attribution_outcomes_for_task("IMP-LOOP-028")
        assert len(outcomes) == 2

        # First failed, second succeeded
        assert outcomes[0].success is False
        assert outcomes[1].success is True

        # Mapping should point to the latest phase
        mapping = tracker.get_task_execution_mapping("IMP-LOOP-028")
        assert mapping is not None
        assert mapping.phase_id == "phase-2"
