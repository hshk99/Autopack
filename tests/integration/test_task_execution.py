"""Integration tests for IMP-LOOP-025: Task Execution Integration.

Tests the integration between ROAD-C task generation and executor task queue consumption.
"""

import json
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from autopack.roadc import AutonomousTaskGenerator, GeneratedTask


class TestTaskExecutionIntegration:
    """Integration tests for ROAD-C to executor task queue flow."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create a mock memory service."""
        service = Mock()
        service.retrieve_insights = Mock(return_value=[])
        return service

    @pytest.fixture
    def temp_autopack_dir(self, tmp_path):
        """Create temporary .autopack directory."""
        autopack_dir = tmp_path / ".autopack"
        autopack_dir.mkdir(parents=True, exist_ok=True)
        return autopack_dir

    @pytest.fixture
    def sample_generated_tasks(self):
        """Create sample generated tasks for testing."""
        return [
            GeneratedTask(
                task_id="TASK-INTEG001",
                title="Fix timeout issues in API module",
                description="Multiple timeout errors detected in API calls",
                priority="critical",
                source_insights=["insight-1", "insight-2"],
                suggested_files=["src/api/client.py", "src/api/timeout.py"],
                estimated_effort="M",
                created_at=datetime.now(timezone.utc),
                requires_approval=False,
                risk_severity=None,
                estimated_cost=15000,
            ),
            GeneratedTask(
                task_id="TASK-INTEG002",
                title="Optimize database queries",
                description="Cost sink detected in database operations",
                priority="high",
                source_insights=["insight-3"],
                suggested_files=["src/db/queries.py"],
                estimated_effort="L",
                created_at=datetime.now(timezone.utc),
                requires_approval=True,
                risk_severity="medium",
                estimated_cost=30000,
            ),
        ]

    def test_end_to_end_task_queue_flow(
        self, mock_memory_service, temp_autopack_dir, sample_generated_tasks
    ):
        """Test complete flow from task generation to queue file creation."""
        queue_file = temp_autopack_dir / "ROADC_TASK_QUEUE.json"

        # Create generator and emit tasks
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)
        count = generator._emit_to_executor_queue(
            sample_generated_tasks,
            queue_file=queue_file,
        )

        # Verify tasks were emitted
        assert count == 2
        assert queue_file.exists()

        # Verify queue file contents
        queue_data = json.loads(queue_file.read_text())
        assert len(queue_data["tasks"]) == 2

        # Verify first task (critical priority)
        task1 = queue_data["tasks"][0]
        assert task1["task_id"] == "TASK-INTEG001"
        assert task1["priority"] == "critical"
        assert task1["estimated_cost"] == 15000
        assert task1["requires_approval"] is False

        # Verify second task (with approval required)
        task2 = queue_data["tasks"][1]
        assert task2["task_id"] == "TASK-INTEG002"
        assert task2["priority"] == "high"
        assert task2["requires_approval"] is True
        assert task2["risk_severity"] == "medium"

    def test_queue_file_format_compatibility(
        self, mock_memory_service, temp_autopack_dir, sample_generated_tasks
    ):
        """Test that queue file format is compatible with executor consumption."""
        queue_file = temp_autopack_dir / "ROADC_TASK_QUEUE.json"

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)
        generator._emit_to_executor_queue(sample_generated_tasks, queue_file=queue_file)

        queue_data = json.loads(queue_file.read_text())

        # Verify all required fields for executor consumption are present
        for task in queue_data["tasks"]:
            # Required fields for phase spec conversion
            assert "task_id" in task
            assert "title" in task
            assert "description" in task
            assert "priority" in task
            assert "suggested_files" in task
            assert "estimated_effort" in task

            # Optional but expected fields
            assert "source_insights" in task
            assert "queued_at" in task
            assert "created_at" in task
            assert "requires_approval" in task
            assert "estimated_cost" in task

    def test_multiple_emission_cycles(self, mock_memory_service, temp_autopack_dir):
        """Test multiple task emission cycles with queue persistence."""
        queue_file = temp_autopack_dir / "ROADC_TASK_QUEUE.json"
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        # First emission cycle
        tasks_cycle1 = [
            GeneratedTask(
                task_id="TASK-CYCLE1-001",
                title="Task from cycle 1",
                description="Description",
                priority="high",
                source_insights=[],
                suggested_files=[],
                estimated_effort="S",
                created_at=datetime.now(timezone.utc),
            ),
        ]
        count1 = generator._emit_to_executor_queue(tasks_cycle1, queue_file=queue_file)
        assert count1 == 1

        # Second emission cycle
        tasks_cycle2 = [
            GeneratedTask(
                task_id="TASK-CYCLE2-001",
                title="Task from cycle 2",
                description="Description",
                priority="medium",
                source_insights=[],
                suggested_files=[],
                estimated_effort="M",
                created_at=datetime.now(timezone.utc),
            ),
        ]
        count2 = generator._emit_to_executor_queue(tasks_cycle2, queue_file=queue_file)
        assert count2 == 1

        # Verify both cycles' tasks are in queue
        queue_data = json.loads(queue_file.read_text())
        assert len(queue_data["tasks"]) == 2

        task_ids = {t["task_id"] for t in queue_data["tasks"]}
        assert "TASK-CYCLE1-001" in task_ids
        assert "TASK-CYCLE2-001" in task_ids

    def test_queue_consumption_simulation(
        self, mock_memory_service, temp_autopack_dir, sample_generated_tasks
    ):
        """Simulate queue consumption by reading and modifying queue file."""
        queue_file = temp_autopack_dir / "ROADC_TASK_QUEUE.json"

        # Generator emits tasks
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)
        generator._emit_to_executor_queue(sample_generated_tasks, queue_file=queue_file)

        # Simulate executor consuming tasks
        queue_data = json.loads(queue_file.read_text())
        original_count = len(queue_data["tasks"])
        assert original_count == 2

        # Consume first task (remove it from queue)
        _consumed_task = queue_data["tasks"].pop(0)  # noqa: F841
        queue_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        queue_data["last_consumption"] = {
            "consumed_count": 1,
            "remaining_count": len(queue_data["tasks"]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        queue_file.write_text(json.dumps(queue_data, indent=2))

        # Verify queue state after consumption
        updated_data = json.loads(queue_file.read_text())
        assert len(updated_data["tasks"]) == 1
        assert "last_consumption" in updated_data
        assert updated_data["last_consumption"]["consumed_count"] == 1

    def test_empty_queue_handling(self, mock_memory_service, temp_autopack_dir):
        """Test handling of empty task queue."""
        queue_file = temp_autopack_dir / "ROADC_TASK_QUEUE.json"

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        # Emit empty list
        count = generator._emit_to_executor_queue([], queue_file=queue_file)
        assert count == 0

    def test_corrupted_queue_recovery(
        self, mock_memory_service, temp_autopack_dir, sample_generated_tasks
    ):
        """Test recovery from corrupted queue file."""
        queue_file = temp_autopack_dir / "ROADC_TASK_QUEUE.json"

        # Create corrupted queue file
        queue_file.write_text("{ invalid json content }")

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        # Should recover and create fresh queue
        count = generator._emit_to_executor_queue(
            sample_generated_tasks,
            queue_file=queue_file,
        )

        assert count == 2
        queue_data = json.loads(queue_file.read_text())
        assert len(queue_data["tasks"]) == 2

    def test_task_priority_preservation(self, mock_memory_service, temp_autopack_dir):
        """Test that task priorities are preserved through queue."""
        queue_file = temp_autopack_dir / "ROADC_TASK_QUEUE.json"

        tasks = [
            GeneratedTask(
                task_id=f"TASK-PRIO-{prio.upper()}",
                title=f"{prio.capitalize()} priority task",
                description="Test description",
                priority=prio,
                source_insights=[],
                suggested_files=[],
                estimated_effort="S",
                created_at=datetime.now(timezone.utc),
            )
            for prio in ["critical", "high", "medium", "low"]
        ]

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)
        generator._emit_to_executor_queue(tasks, queue_file=queue_file)

        queue_data = json.loads(queue_file.read_text())

        # Verify all priorities are preserved
        priorities = {t["priority"] for t in queue_data["tasks"]}
        assert priorities == {"critical", "high", "medium", "low"}


class TestTaskGenerationToExecutionPath:
    """Tests for the complete path from task generation to execution readiness."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create a mock memory service with sample insights."""
        service = Mock()
        service.retrieve_insights = Mock(
            return_value=[
                {
                    "issue_type": "cost_sink",
                    "content": "High token usage in build phase",
                    "id": "insight-1",
                    "severity": "high",
                    "metric_value": 50000.0,
                },
                {
                    "issue_type": "cost_sink",
                    "content": "Excessive context loading",
                    "id": "insight-2",
                    "severity": "high",
                    "metric_value": 75000.0,
                },
                {
                    "issue_type": "failure_mode",
                    "content": "Timeout in API calls",
                    "id": "insight-3",
                    "severity": "high",
                    "metric_value": 5.0,
                },
                {
                    "issue_type": "failure_mode",
                    "content": "Connection refused errors",
                    "id": "insight-4",
                    "severity": "high",
                    "metric_value": 3.0,
                },
            ]
        )
        return service

    def test_insights_to_queue_flow(self, mock_memory_service, tmp_path):
        """Test flow from insights to queue-ready tasks."""
        queue_file = tmp_path / ".autopack" / "ROADC_TASK_QUEUE.json"
        queue_file.parent.mkdir(parents=True, exist_ok=True)

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        # Override queue file path temporarily
        original_queue_file = AutonomousTaskGenerator.ROADC_TASK_QUEUE_FILE
        try:
            AutonomousTaskGenerator.ROADC_TASK_QUEUE_FILE = queue_file

            # Generate tasks from insights
            result = generator.generate_tasks(
                max_tasks=5,
                min_confidence=0.0,
            )

            # If tasks were generated, verify queue integration
            if result.tasks_generated:
                assert queue_file.exists()
                queue_data = json.loads(queue_file.read_text())

                # All generated tasks should be in queue
                task_ids_generated = {t.task_id for t in result.tasks_generated}
                task_ids_queued = {t["task_id"] for t in queue_data["tasks"]}

                assert task_ids_generated == task_ids_queued

        finally:
            AutonomousTaskGenerator.ROADC_TASK_QUEUE_FILE = original_queue_file
