"""Tests for IMP-LOOP-021: Task Execution Verification Mechanism.

Tests cover:
- RegisteredTask dataclass
- TaskEffectivenessTracker.register_task()
- TaskEffectivenessTracker.record_execution()
- TaskEffectivenessTracker.get_unexecuted_tasks()
- TaskEffectivenessTracker.get_execution_verification_summary()
- Integration with autonomous loop task generation
"""

from datetime import datetime

from autopack.task_generation.task_effectiveness_tracker import (
    RegisteredTask, TaskEffectivenessTracker)


class TestRegisteredTask:
    """Tests for RegisteredTask dataclass."""

    def test_registered_task_creation(self):
        """RegisteredTask should be creatable with required fields."""
        task = RegisteredTask(task_id="IMP-TEST-001")

        assert task.task_id == "IMP-TEST-001"
        assert task.priority == ""
        assert task.category == ""
        assert task.executed is False
        assert task.executed_at is None
        assert task.execution_success is None
        assert isinstance(task.registered_at, datetime)

    def test_registered_task_with_metadata(self):
        """RegisteredTask should accept priority and category."""
        task = RegisteredTask(
            task_id="IMP-TEST-002",
            priority="critical",
            category="telemetry",
        )

        assert task.task_id == "IMP-TEST-002"
        assert task.priority == "critical"
        assert task.category == "telemetry"

    def test_registered_task_to_dict(self):
        """RegisteredTask.to_dict should serialize all fields."""
        task = RegisteredTask(
            task_id="IMP-TEST-003",
            priority="high",
            category="memory",
        )

        data = task.to_dict()

        assert data["task_id"] == "IMP-TEST-003"
        assert data["priority"] == "high"
        assert data["category"] == "memory"
        assert data["executed"] is False
        assert data["executed_at"] is None
        assert data["execution_success"] is None
        assert "registered_at" in data


class TestRegisterTask:
    """Tests for TaskEffectivenessTracker.register_task."""

    def test_register_task_basic(self):
        """register_task should create a RegisteredTask entry."""
        tracker = TaskEffectivenessTracker()

        result = tracker.register_task("IMP-TEST-001")

        assert result.task_id == "IMP-TEST-001"
        assert "IMP-TEST-001" in tracker._registered_tasks

    def test_register_task_with_metadata(self):
        """register_task should store priority and category."""
        tracker = TaskEffectivenessTracker()

        result = tracker.register_task(
            task_id="IMP-TEST-002",
            priority="critical",
            category="telemetry",
        )

        assert result.priority == "critical"
        assert result.category == "telemetry"

    def test_register_task_duplicate_updates_metadata(self):
        """register_task for existing task should update metadata."""
        tracker = TaskEffectivenessTracker()

        # First registration
        tracker.register_task("IMP-TEST-003", priority="low", category="")

        # Second registration with updated metadata
        result = tracker.register_task("IMP-TEST-003", priority="high", category="memory")

        assert result.priority == "high"
        assert result.category == "memory"
        # Should still be only one entry
        assert len(tracker._registered_tasks) == 1

    def test_register_multiple_tasks(self):
        """register_task should handle multiple distinct tasks."""
        tracker = TaskEffectivenessTracker()

        tracker.register_task("IMP-TEST-001", priority="critical")
        tracker.register_task("IMP-TEST-002", priority="high")
        tracker.register_task("IMP-TEST-003", priority="medium")

        assert len(tracker._registered_tasks) == 3


class TestRecordExecution:
    """Tests for TaskEffectivenessTracker.record_execution."""

    def test_record_execution_success(self):
        """record_execution should mark task as executed with success."""
        tracker = TaskEffectivenessTracker()
        tracker.register_task("IMP-TEST-001")

        result = tracker.record_execution("IMP-TEST-001", success=True)

        assert result is True
        task = tracker._registered_tasks["IMP-TEST-001"]
        assert task.executed is True
        assert task.execution_success is True
        assert task.executed_at is not None

    def test_record_execution_failure(self):
        """record_execution should mark task as executed with failure."""
        tracker = TaskEffectivenessTracker()
        tracker.register_task("IMP-TEST-002")

        result = tracker.record_execution("IMP-TEST-002", success=False)

        assert result is True
        task = tracker._registered_tasks["IMP-TEST-002"]
        assert task.executed is True
        assert task.execution_success is False

    def test_record_execution_unregistered_task(self):
        """record_execution for unregistered task should return False."""
        tracker = TaskEffectivenessTracker()

        result = tracker.record_execution("IMP-UNKNOWN", success=True)

        assert result is False

    def test_record_execution_timestamps(self):
        """record_execution should set executed_at timestamp."""
        tracker = TaskEffectivenessTracker()
        tracker.register_task("IMP-TEST-003")

        before = datetime.now()
        tracker.record_execution("IMP-TEST-003", success=True)
        after = datetime.now()

        task = tracker._registered_tasks["IMP-TEST-003"]
        assert before <= task.executed_at <= after


class TestGetUnexecutedTasks:
    """Tests for TaskEffectivenessTracker.get_unexecuted_tasks."""

    def test_get_unexecuted_tasks_empty(self):
        """get_unexecuted_tasks should return empty list when no tasks."""
        tracker = TaskEffectivenessTracker()

        result = tracker.get_unexecuted_tasks()

        assert result == []

    def test_get_unexecuted_tasks_all_registered(self):
        """get_unexecuted_tasks should return all unexecuted tasks."""
        tracker = TaskEffectivenessTracker()
        tracker.register_task("IMP-TEST-001")
        tracker.register_task("IMP-TEST-002")
        tracker.register_task("IMP-TEST-003")

        result = tracker.get_unexecuted_tasks()

        assert len(result) == 3
        task_ids = {t.task_id for t in result}
        assert task_ids == {"IMP-TEST-001", "IMP-TEST-002", "IMP-TEST-003"}

    def test_get_unexecuted_tasks_some_executed(self):
        """get_unexecuted_tasks should exclude executed tasks."""
        tracker = TaskEffectivenessTracker()
        tracker.register_task("IMP-TEST-001")
        tracker.register_task("IMP-TEST-002")
        tracker.register_task("IMP-TEST-003")

        tracker.record_execution("IMP-TEST-002", success=True)

        result = tracker.get_unexecuted_tasks()

        assert len(result) == 2
        task_ids = {t.task_id for t in result}
        assert task_ids == {"IMP-TEST-001", "IMP-TEST-003"}

    def test_get_unexecuted_tasks_all_executed(self):
        """get_unexecuted_tasks should return empty when all executed."""
        tracker = TaskEffectivenessTracker()
        tracker.register_task("IMP-TEST-001")
        tracker.register_task("IMP-TEST-002")

        tracker.record_execution("IMP-TEST-001", success=True)
        tracker.record_execution("IMP-TEST-002", success=False)

        result = tracker.get_unexecuted_tasks()

        assert result == []


class TestGetExecutionVerificationSummary:
    """Tests for TaskEffectivenessTracker.get_execution_verification_summary."""

    def test_summary_empty(self):
        """Summary should handle empty tracker."""
        tracker = TaskEffectivenessTracker()

        summary = tracker.get_execution_verification_summary()

        assert summary["total_registered"] == 0
        assert summary["executed_count"] == 0
        assert summary["unexecuted_count"] == 0
        assert summary["execution_rate"] == 0.0
        assert summary["success_rate"] == 0.0
        assert summary["by_priority"] == {}
        assert summary["unexecuted_tasks"] == []

    def test_summary_with_registered_tasks(self):
        """Summary should count registered tasks."""
        tracker = TaskEffectivenessTracker()
        tracker.register_task("IMP-TEST-001", priority="critical")
        tracker.register_task("IMP-TEST-002", priority="high")
        tracker.register_task("IMP-TEST-003", priority="high")

        summary = tracker.get_execution_verification_summary()

        assert summary["total_registered"] == 3
        assert summary["unexecuted_count"] == 3
        assert summary["execution_rate"] == 0.0

    def test_summary_with_mixed_execution(self):
        """Summary should accurately track execution status."""
        tracker = TaskEffectivenessTracker()
        tracker.register_task("IMP-TEST-001", priority="critical")
        tracker.register_task("IMP-TEST-002", priority="high")
        tracker.register_task("IMP-TEST-003", priority="high")

        tracker.record_execution("IMP-TEST-001", success=True)
        tracker.record_execution("IMP-TEST-002", success=False)

        summary = tracker.get_execution_verification_summary()

        assert summary["total_registered"] == 3
        assert summary["executed_count"] == 2
        assert summary["unexecuted_count"] == 1
        assert summary["execution_rate"] == 2 / 3
        assert summary["success_rate"] == 0.5  # 1 of 2 executed succeeded
        assert summary["unexecuted_tasks"] == ["IMP-TEST-003"]

    def test_summary_by_priority(self):
        """Summary should break down by priority."""
        tracker = TaskEffectivenessTracker()
        tracker.register_task("IMP-TEST-001", priority="critical")
        tracker.register_task("IMP-TEST-002", priority="critical")
        tracker.register_task("IMP-TEST-003", priority="high")
        tracker.register_task("IMP-TEST-004", priority="high")

        tracker.record_execution("IMP-TEST-001", success=True)
        tracker.record_execution("IMP-TEST-003", success=True)
        tracker.record_execution("IMP-TEST-004", success=False)

        summary = tracker.get_execution_verification_summary()

        assert summary["by_priority"]["critical"]["registered"] == 2
        assert summary["by_priority"]["critical"]["executed"] == 1
        assert summary["by_priority"]["critical"]["successful"] == 1

        assert summary["by_priority"]["high"]["registered"] == 2
        assert summary["by_priority"]["high"]["executed"] == 2
        assert summary["by_priority"]["high"]["successful"] == 1


class TestGeneratedTaskPhaseIdParsing:
    """Tests for parsing generated task phase IDs."""

    def test_generated_task_prefix_extraction(self):
        """Should correctly extract task ID from generated phase ID."""
        phase_id = "generated-task-execution-IMP-ARCH-004"
        prefix = "generated-task-execution-"

        assert phase_id.startswith(prefix)
        original_task_id = phase_id[len(prefix) :]
        assert original_task_id == "IMP-ARCH-004"

    def test_non_generated_task_phase_id(self):
        """Should not match non-generated task phase IDs."""
        phase_id = "build-phase-123"
        prefix = "generated-task-execution-"

        assert not phase_id.startswith(prefix)


class TestIntegration:
    """Integration tests for task verification flow."""

    def test_full_verification_flow(self):
        """Test complete flow: register -> execute -> verify."""
        tracker = TaskEffectivenessTracker()

        # Step 1: Register tasks (simulating task generation)
        tracker.register_task("IMP-LOOP-001", priority="critical", category="loop")
        tracker.register_task("IMP-MEM-001", priority="high", category="memory")
        tracker.register_task("IMP-TELE-001", priority="medium", category="telemetry")

        # Verify registration
        summary = tracker.get_execution_verification_summary()
        assert summary["total_registered"] == 3
        assert summary["executed_count"] == 0

        # Step 2: Record execution for some tasks
        tracker.record_execution("IMP-LOOP-001", success=True)
        tracker.record_execution("IMP-MEM-001", success=False)

        # Verify partial execution
        summary = tracker.get_execution_verification_summary()
        assert summary["executed_count"] == 2
        assert summary["unexecuted_count"] == 1
        assert "IMP-TELE-001" in summary["unexecuted_tasks"]

        # Step 3: Get unexecuted tasks for follow-up
        unexecuted = tracker.get_unexecuted_tasks()
        assert len(unexecuted) == 1
        assert unexecuted[0].task_id == "IMP-TELE-001"

    def test_verification_with_effectiveness_tracking(self):
        """Test that verification works alongside effectiveness tracking."""
        tracker = TaskEffectivenessTracker()

        # Register a task
        tracker.register_task("IMP-TEST-001", priority="high", category="test")

        # Record task outcome (existing functionality)
        report = tracker.record_task_outcome(
            task_id="generated-task-execution-IMP-TEST-001",
            success=True,
            execution_time_seconds=30.0,
            tokens_used=5000,
            category="test",
        )

        # Record execution verification (new functionality)
        tracker.record_execution("IMP-TEST-001", success=True)

        # Both should work independently
        assert report.effectiveness_score > 0.0
        verification = tracker.get_execution_verification_summary()
        assert verification["executed_count"] == 1
        assert verification["success_rate"] == 1.0
