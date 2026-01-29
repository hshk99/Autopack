"""Tests for DynamicTaskGenerator class."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.automation.anomaly_detector import Anomaly
from src.automation.dynamic_task_generator import (DynamicTaskGenerator,
                                                   GeneratedTask)


class TestDynamicTaskGenerator:
    """Test suite for DynamicTaskGenerator."""

    def test_generator_initialization(self, tmp_path: Path) -> None:
        """Test generator initializes with correct output path."""
        output_path = tmp_path / "tasks.json"
        generator = DynamicTaskGenerator(output_path=str(output_path))
        assert generator.output_path == output_path

    def test_generate_tasks_creates_tasks_from_anomalies(self, tmp_path: Path) -> None:
        """Test task generation from anomalies."""
        generator = DynamicTaskGenerator(output_path=str(tmp_path / "tasks.json"))

        anomalies = [
            Anomaly(
                anomaly_id="ci_fail_123_202601261200",
                anomaly_type="repeated_ci_failure",
                severity="high",
                detected_at=datetime.now(),
                affected_components=["PR#123"],
                evidence={"retry_count": 5, "last_error": "lint failure"},
                suggested_action="Investigate CI failure in PR#123",
            ),
            Anomaly(
                anomaly_id="stuck_slot_1_202601261200",
                anomaly_type="stuck_slot",
                severity="medium",
                detected_at=datetime.now(),
                affected_components=["slot_1"],
                evidence={"hours_stuck": 3.5},
                suggested_action="Reset slot 1",
            ),
        ]

        tasks = generator.generate_tasks(anomalies)

        assert len(tasks) == 2
        assert tasks[0].task_id == "TASK-ci_fail_123_202601261200"
        assert tasks[0].title == "Fix repeated CI failure in PR#123"
        assert tasks[0].priority == "P1"
        assert tasks[0].auto_executable is False

        assert tasks[1].task_id == "TASK-stuck_slot_1_202601261200"
        assert tasks[1].title == "Resolve stuck slot slot_1"
        assert tasks[1].priority == "P2"
        assert tasks[1].auto_executable is True

    def test_generate_tasks_saves_to_file(self, tmp_path: Path) -> None:
        """Test tasks are saved to output file."""
        output_path = tmp_path / "tasks.json"
        generator = DynamicTaskGenerator(output_path=str(output_path))

        anomalies = [
            Anomaly(
                anomaly_id="test_001",
                anomaly_type="stuck_slot",
                severity="medium",
                detected_at=datetime.now(),
                affected_components=["slot_1"],
                evidence={"hours_stuck": 3.0},
                suggested_action="Reset slot",
            )
        ]

        generator.generate_tasks(anomalies)

        assert output_path.exists()
        data = json.loads(output_path.read_text())
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["task_id"] == "TASK-test_001"
        assert data["tasks"][0]["status"] == "pending"

    def test_generate_tasks_appends_to_existing(self, tmp_path: Path) -> None:
        """Test tasks are appended to existing file."""
        output_path = tmp_path / "tasks.json"
        output_path.write_text(
            json.dumps({"tasks": [{"task_id": "TASK-existing", "title": "Existing task"}]})
        )

        generator = DynamicTaskGenerator(output_path=str(output_path))

        anomalies = [
            Anomaly(
                anomaly_id="new_002",
                anomaly_type="stuck_slot",
                severity="high",
                detected_at=datetime.now(),
                affected_components=["slot_2"],
                evidence={"hours_stuck": 5.0},
                suggested_action="Reset slot",
            )
        ]

        generator.generate_tasks(anomalies)

        data = json.loads(output_path.read_text())
        assert len(data["tasks"]) == 2
        ids = [t["task_id"] for t in data["tasks"]]
        assert "TASK-existing" in ids
        assert "TASK-new_002" in ids

    def test_generate_tasks_skips_unknown_anomaly_types(self, tmp_path: Path) -> None:
        """Test unknown anomaly types are skipped."""
        generator = DynamicTaskGenerator(output_path=str(tmp_path / "tasks.json"))

        anomalies = [
            Anomaly(
                anomaly_id="unknown_001",
                anomaly_type="pattern_break",  # Not in task_templates
                severity="low",
                detected_at=datetime.now(),
                affected_components=["component_x"],
                evidence={},
                suggested_action="Investigate pattern break",
            )
        ]

        tasks = generator.generate_tasks(anomalies)
        assert len(tasks) == 0

    def test_generate_tasks_returns_empty_for_no_anomalies(self, tmp_path: Path) -> None:
        """Test empty list returned when no anomalies."""
        generator = DynamicTaskGenerator(output_path=str(tmp_path / "tasks.json"))
        tasks = generator.generate_tasks([])
        assert tasks == []

    def test_severity_to_priority_mapping(self) -> None:
        """Test severity to priority mapping."""
        generator = DynamicTaskGenerator()
        assert generator._map_severity_to_priority("critical") == "P0"
        assert generator._map_severity_to_priority("high") == "P1"
        assert generator._map_severity_to_priority("medium") == "P2"
        assert generator._map_severity_to_priority("low") == "P3"
        assert generator._map_severity_to_priority("unknown") == "P2"

    def test_generate_description_includes_all_fields(self) -> None:
        """Test description includes all anomaly fields."""
        generator = DynamicTaskGenerator()
        anomaly = Anomaly(
            anomaly_id="test_123",
            anomaly_type="stuck_slot",
            severity="high",
            detected_at=datetime(2026, 1, 26, 12, 0, 0),
            affected_components=["slot_1"],
            evidence={"hours_stuck": 5.5, "last_phase": "phase_3"},
            suggested_action="Reset slot 1 or investigate",
        )

        description = generator._generate_description(anomaly)

        assert "stuck_slot" in description
        assert "high" in description
        assert "2026-01-26" in description
        assert "hours_stuck" in description
        assert "Reset slot 1 or investigate" in description

    def test_execute_auto_tasks_for_stuck_slots(self, tmp_path: Path) -> None:
        """Test auto-execution of stuck slot tasks."""
        generator = DynamicTaskGenerator(output_path=str(tmp_path / "tasks.json"))

        tasks = [
            GeneratedTask(
                task_id="TASK-stuck_slot_1",
                title="Resolve stuck slot",
                description="Test",
                priority="P2",
                source_anomaly_id="stuck_slot_1_202601261200",
                suggested_files=["scripts/auto_fill_empty_slots.ps1"],
                auto_executable=True,
            ),
            GeneratedTask(
                task_id="TASK-ci_fail_123",
                title="Fix CI failure",
                description="Test",
                priority="P1",
                source_anomaly_id="ci_fail_123_202601261200",
                suggested_files=["scripts/check_pr_status.ps1"],
                auto_executable=False,
            ),
        ]

        results = generator.execute_auto_tasks(tasks)

        # Only auto-executable tasks should be in results
        assert "TASK-stuck_slot_1" in results
        assert "TASK-ci_fail_123" not in results
        # Placeholder returns False
        assert results["TASK-stuck_slot_1"] is False

    def test_execute_auto_tasks_empty_list(self) -> None:
        """Test auto-execution with empty task list."""
        generator = DynamicTaskGenerator()
        results = generator.execute_auto_tasks([])
        assert results == {}


class TestGeneratedTaskDataclass:
    """Test suite for GeneratedTask dataclass."""

    def test_generated_task_creation(self) -> None:
        """Test GeneratedTask dataclass creation."""
        task = GeneratedTask(
            task_id="TASK-test_123",
            title="Test task",
            description="Test description",
            priority="P1",
            source_anomaly_id="test_123",
            suggested_files=["file1.py", "file2.py"],
            auto_executable=False,
        )
        assert task.task_id == "TASK-test_123"
        assert task.priority == "P1"
        assert len(task.suggested_files) == 2
        assert task.auto_executable is False
