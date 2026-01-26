"""Tests for IMP-LOOP-005: Task Status Feedback Loop.

Tests the retry logic and failure tracking for improvement tasks:
- Tasks that fail should be returned to pending with incremented retry count
- Tasks that exceed max retries should be marked as failed
- Failure run IDs should be tracked in failure_runs list
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from autopack.roadc.task_generator import AutonomousTaskGenerator, GeneratedTask


class TestTaskStatusFeedbackLoop:
    """Test suite for IMP-LOOP-005: Task Status Feedback Loop."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = Mock()
        session.commit = Mock()
        session.rollback = Mock()
        session.close = Mock()
        return session

    @pytest.fixture
    def mock_task_model(self):
        """Create a mock GeneratedTaskModel instance."""
        task = Mock()
        task.task_id = "TASK-001"
        task.status = "in_progress"
        task.retry_count = 0
        task.max_retries = 3
        task.failure_runs = []
        task.failure_reason = None
        task.updated_at = None
        task.completed_at = None
        task.executed_in_run_id = None
        return task

    def test_mark_task_status_retry_increments_retry_count(self, mock_session, mock_task_model):
        """Test that increment_retry=True increments retry_count."""
        with patch("autopack.database.SessionLocal", return_value=mock_session):
            mock_session.query.return_value.filter_by.return_value.first.return_value = (
                mock_task_model
            )

            generator = AutonomousTaskGenerator()
            result = generator.mark_task_status(
                "TASK-001",
                status=None,
                increment_retry=True,
                failure_run_id="run-123",
            )

            assert result == "retry"
            assert mock_task_model.retry_count == 1
            assert mock_task_model.status == "pending"
            assert "run-123" in mock_task_model.failure_runs
            mock_session.commit.assert_called_once()

    def test_mark_task_status_exceeds_max_retries_marks_failed(self, mock_session, mock_task_model):
        """Test that task is marked failed when exceeding max retries."""
        mock_task_model.retry_count = 2  # Will become 3, which equals max_retries
        mock_task_model.max_retries = 3

        with patch("autopack.database.SessionLocal", return_value=mock_session):
            mock_session.query.return_value.filter_by.return_value.first.return_value = (
                mock_task_model
            )

            generator = AutonomousTaskGenerator()
            result = generator.mark_task_status(
                "TASK-001",
                status=None,
                increment_retry=True,
                failure_run_id="run-456",
            )

            assert result == "failed"
            assert mock_task_model.retry_count == 3
            assert mock_task_model.status == "failed"
            assert mock_task_model.failure_reason is not None
            assert "Exceeded max retries" in mock_task_model.failure_reason

    def test_mark_task_status_tracks_multiple_failure_runs(self, mock_session, mock_task_model):
        """Test that multiple failure run IDs are tracked."""
        mock_task_model.failure_runs = ["run-100"]
        mock_task_model.retry_count = 1

        with patch("autopack.database.SessionLocal", return_value=mock_session):
            mock_session.query.return_value.filter_by.return_value.first.return_value = (
                mock_task_model
            )

            generator = AutonomousTaskGenerator()
            generator.mark_task_status(
                "TASK-001",
                status=None,
                increment_retry=True,
                failure_run_id="run-200",
            )

            assert len(mock_task_model.failure_runs) == 2
            assert "run-100" in mock_task_model.failure_runs
            assert "run-200" in mock_task_model.failure_runs

    def test_mark_task_status_does_not_duplicate_failure_run(self, mock_session, mock_task_model):
        """Test that same failure run ID is not added twice."""
        mock_task_model.failure_runs = ["run-123"]

        with patch("autopack.database.SessionLocal", return_value=mock_session):
            mock_session.query.return_value.filter_by.return_value.first.return_value = (
                mock_task_model
            )

            generator = AutonomousTaskGenerator()
            generator.mark_task_status(
                "TASK-001",
                status=None,
                increment_retry=True,
                failure_run_id="run-123",  # Same as existing
            )

            assert len(mock_task_model.failure_runs) == 1

    def test_mark_task_status_completed_still_works(self, mock_session, mock_task_model):
        """Test that marking task as completed still works."""
        with patch("autopack.database.SessionLocal", return_value=mock_session):
            mock_session.query.return_value.filter_by.return_value.first.return_value = (
                mock_task_model
            )

            generator = AutonomousTaskGenerator()
            result = generator.mark_task_status(
                "TASK-001",
                status="completed",
                executed_in_run_id="run-789",
            )

            assert result == "updated"
            assert mock_task_model.status == "completed"
            assert mock_task_model.completed_at is not None
            assert mock_task_model.executed_in_run_id == "run-789"

    def test_mark_task_status_not_found(self, mock_session):
        """Test handling when task is not found."""
        with patch("autopack.database.SessionLocal", return_value=mock_session):
            mock_session.query.return_value.filter_by.return_value.first.return_value = None

            generator = AutonomousTaskGenerator()
            result = generator.mark_task_status(
                "NONEXISTENT",
                status="completed",
            )

            assert result == "not_found"

    def test_mark_task_status_handles_none_failure_runs(self, mock_session, mock_task_model):
        """Test handling when failure_runs is None."""
        mock_task_model.failure_runs = None

        with patch("autopack.database.SessionLocal", return_value=mock_session):
            mock_session.query.return_value.filter_by.return_value.first.return_value = (
                mock_task_model
            )

            generator = AutonomousTaskGenerator()
            result = generator.mark_task_status(
                "TASK-001",
                status=None,
                increment_retry=True,
                failure_run_id="run-123",
            )

            assert result == "retry"
            assert mock_task_model.failure_runs == ["run-123"]


class TestGeneratedTaskDataclass:
    """Test GeneratedTask dataclass with new retry fields."""

    def test_generated_task_default_retry_fields(self):
        """Test that GeneratedTask has correct default retry fields."""
        task = GeneratedTask(
            task_id="TASK-001",
            title="Test Task",
            description="Test Description",
            priority="medium",
            source_insights=["insight-1"],
            suggested_files=["file.py"],
            estimated_effort="M",
            created_at=datetime.now(),
        )

        assert task.retry_count == 0
        assert task.max_retries == 3
        assert task.failure_runs == []

    def test_generated_task_custom_retry_fields(self):
        """Test that GeneratedTask accepts custom retry field values."""
        task = GeneratedTask(
            task_id="TASK-002",
            title="Test Task",
            description="Test Description",
            priority="high",
            source_insights=["insight-1"],
            suggested_files=["file.py"],
            estimated_effort="L",
            created_at=datetime.now(),
            retry_count=2,
            max_retries=5,
            failure_runs=["run-1", "run-2"],
        )

        assert task.retry_count == 2
        assert task.max_retries == 5
        assert task.failure_runs == ["run-1", "run-2"]


class TestAutonomousLoopIntegration:
    """Test integration with autonomous_loop._mark_improvement_tasks_failed."""

    @pytest.fixture
    def mock_executor(self):
        """Create a mock executor with improvement tasks."""
        executor = Mock()
        executor.run_id = "test-run-123"
        executor._improvement_tasks = [
            {"task_id": "TASK-001"},
            {"task_id": "TASK-002"},
        ]
        executor.db_session = None
        return executor

    def test_mark_improvement_tasks_failed_calls_mark_task_status(self, mock_executor):
        """Test that _mark_improvement_tasks_failed calls mark_task_status for each task."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        with patch.object(
            AutonomousTaskGenerator,
            "mark_task_status",
            return_value="retry",
        ) as mock_mark:
            loop = AutonomousLoop.__new__(AutonomousLoop)
            loop.executor = mock_executor

            loop._mark_improvement_tasks_failed(phases_failed=2)

            assert mock_mark.call_count == 2
            # Check first call
            mock_mark.assert_any_call(
                "TASK-001",
                status=None,
                increment_retry=True,
                failure_run_id="test-run-123",
            )
            # Check second call
            mock_mark.assert_any_call(
                "TASK-002",
                status=None,
                increment_retry=True,
                failure_run_id="test-run-123",
            )

    def test_mark_improvement_tasks_failed_handles_empty_tasks(self, mock_executor):
        """Test that _mark_improvement_tasks_failed handles empty task list."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_executor._improvement_tasks = []

        with patch.object(
            AutonomousTaskGenerator,
            "mark_task_status",
        ) as mock_mark:
            loop = AutonomousLoop.__new__(AutonomousLoop)
            loop.executor = mock_executor

            # Should not raise, should just return
            loop._mark_improvement_tasks_failed(phases_failed=1)

            mock_mark.assert_not_called()

    def test_mark_improvement_tasks_failed_handles_none_tasks(self, mock_executor):
        """Test that _mark_improvement_tasks_failed handles None task list."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_executor._improvement_tasks = None

        with patch.object(
            AutonomousTaskGenerator,
            "mark_task_status",
        ) as mock_mark:
            loop = AutonomousLoop.__new__(AutonomousLoop)
            loop.executor = mock_executor

            # Should not raise, should just return
            loop._mark_improvement_tasks_failed(phases_failed=1)

            mock_mark.assert_not_called()

    def test_mark_improvement_tasks_failed_logs_mixed_results(self, mock_executor):
        """Test that logging correctly reports retry vs failed counts."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        # Set up to return different results for different tasks
        side_effects = ["retry", "failed"]

        with patch.object(
            AutonomousTaskGenerator,
            "mark_task_status",
            side_effect=side_effects,
        ):
            with patch("autopack.executor.autonomous_loop.logger") as mock_logger:
                loop = AutonomousLoop.__new__(AutonomousLoop)
                loop.executor = mock_executor

                loop._mark_improvement_tasks_failed(phases_failed=2)

                # Check that info log was called with correct counts
                mock_logger.info.assert_called_once()
                call_args = mock_logger.info.call_args[0][0]
                assert "1 tasks returned to pending" in call_args
                assert "1 tasks marked as failed" in call_args
