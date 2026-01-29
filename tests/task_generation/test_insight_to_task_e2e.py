"""End-to-end tests for IMP-LOOP-001: Insight-to-Task Pipeline Verification.

This module tests the complete flow from telemetry insights to task generation
and injection into the execution queue, verifying that generated tasks properly
appear in the autonomous executor's phase queue.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import Mock, patch

import pytest

from autopack.analytics.telemetry_analyzer import TelemetryAnalyzer
from autopack.executor.backlog_maintenance import BacklogMaintenance, InjectionResult, TaskCandidate
from autopack.task_generation.insight_to_task import InsightToTaskGenerator


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for state files."""
    return tmp_path


@pytest.fixture
def sample_slot_history() -> dict:
    """Sample slot_history.json with problematic slots."""
    return {
        "slots": [
            {"slot_id": 1, "status": "completed", "event_type": "nudge"},
            {
                "slot_id": 2,
                "status": "failed",
                "event_type": "error",
                "escalated": True,
                "escalation_level": 2,
            },
        ],
        "events": [],
    }


@pytest.fixture
def sample_nudge_state() -> dict:
    """Sample nudge_state.json with escalation patterns."""
    return {
        "nudges": [
            {"id": "nudge-1", "phase_type": "build", "status": "resolved"},
            {
                "id": "nudge-2",
                "phase_type": "test",
                "status": "failed",
                "escalated": True,
            },
        ]
    }


@pytest.fixture
def populated_state_dir(
    temp_state_dir: Path,
    sample_slot_history: dict,
    sample_nudge_state: dict,
) -> Path:
    """Create state files in temp directory."""
    (temp_state_dir / "slot_history.json").write_text(json.dumps(sample_slot_history))
    (temp_state_dir / "nudge_state.json").write_text(json.dumps(sample_nudge_state))
    (temp_state_dir / "ci_retry_state.json").write_text(json.dumps({"retries": []}))
    return temp_state_dir


@pytest.fixture
def generator(populated_state_dir: Path) -> InsightToTaskGenerator:
    """Create an InsightToTaskGenerator with populated data."""
    analyzer = TelemetryAnalyzer(populated_state_dir)
    return InsightToTaskGenerator(analyzer)


@pytest.fixture
def mock_executor():
    """Create a mock executor with autonomous_loop."""
    executor = Mock()
    executor.run_id = "test-run-e2e"
    executor.workspace = "/tmp/test-workspace"

    # Mock autonomous_loop with _current_run_phases
    autonomous_loop = Mock()
    autonomous_loop._current_run_phases = []
    executor.autonomous_loop = autonomous_loop

    return executor


@pytest.fixture
def backlog_maintenance(mock_executor) -> BacklogMaintenance:
    """Create BacklogMaintenance instance with mock executor."""
    return BacklogMaintenance(mock_executor)


class TestInsightToTaskPipelineE2E:
    """End-to-end tests for the insight-to-task pipeline."""

    def test_generate_improvements_produces_valid_imps(
        self, generator: InsightToTaskGenerator
    ) -> None:
        """Test that generated improvements have required fields."""
        improvements = generator.generate_improvements_from_insights()

        for imp in improvements:
            assert "id" in imp
            assert imp["id"].startswith("IMP-")
            assert "title" in imp
            assert "priority" in imp
            assert imp["priority"] in {"critical", "high", "medium", "low"}
            assert "status" in imp
            assert imp["status"] == "pending"
            assert "source" in imp
            assert "created_at" in imp

    def test_improvements_can_be_converted_to_task_candidates(
        self, generator: InsightToTaskGenerator
    ) -> None:
        """Test that improvements can be converted to TaskCandidate objects."""
        improvements = generator.generate_improvements_from_insights()

        for imp in improvements:
            candidate = TaskCandidate(
                task_id=imp["id"],
                title=imp["title"],
                priority=imp["priority"],
                source=imp["source"],
                metadata=imp.get("evidence", {}),
            )
            assert candidate.task_id == imp["id"]
            assert candidate.title == imp["title"]
            assert candidate.priority == imp["priority"]

    def test_full_pipeline_generates_and_injects_tasks(
        self,
        generator: InsightToTaskGenerator,
        backlog_maintenance: BacklogMaintenance,
    ) -> None:
        """Test full pipeline from insights to injected tasks."""
        # Step 1: Generate improvements from insights
        improvements = generator.generate_improvements_from_insights()

        # Step 2: Convert to TaskCandidates
        candidates = [
            TaskCandidate(
                task_id=imp["id"],
                title=imp["title"],
                priority=imp["priority"],
                source=imp["source"],
                metadata=imp.get("evidence", {}),
            )
            for imp in improvements
        ]

        # Step 3: Inject tasks
        result = backlog_maintenance.inject_tasks(candidates)

        # Verify injection succeeded
        assert result.success_count == len(candidates)
        assert result.failure_count == 0

    def test_injected_tasks_appear_in_queue(
        self,
        generator: InsightToTaskGenerator,
        backlog_maintenance: BacklogMaintenance,
    ) -> None:
        """Test that injected tasks appear in the execution queue."""
        # Generate and inject
        improvements = generator.generate_improvements_from_insights()
        candidates = [
            TaskCandidate(
                task_id=imp["id"],
                title=imp["title"],
                priority=imp["priority"],
                source=imp["source"],
            )
            for imp in improvements
        ]

        result = backlog_maintenance.inject_tasks(candidates)

        # Verify each task is in queue
        for task_id in result.injected_ids:
            assert backlog_maintenance.queue_contains(task_id)

    def test_injection_verification_detects_missing_tasks(self, mock_executor) -> None:
        """Test that verification correctly detects when tasks are not in queue."""
        # Create a backlog_maintenance with an executor that doesn't add to queue
        broken_executor = Mock()
        broken_executor.autonomous_loop = None  # No queue available

        bm = BacklogMaintenance(broken_executor)

        candidates = [
            TaskCandidate(task_id="IMP-TEST-001", title="Test task"),
        ]

        result = bm.inject_tasks(candidates)

        # Should fail because no queue available
        assert result.failure_count > 0 or not result.verified


class TestInjectionResultDataclass:
    """Tests for InjectionResult dataclass."""

    def test_empty_result_properties(self) -> None:
        """Test InjectionResult with no data."""
        result = InjectionResult()

        assert result.success_count == 0
        assert result.failure_count == 0
        assert result.total_count == 0
        assert not result.verified
        assert result.all_succeeded is False

    def test_successful_injection_properties(self) -> None:
        """Test InjectionResult with successful injections."""
        result = InjectionResult(
            injected_ids=["task-1", "task-2", "task-3"],
            failed_ids=[],
            verified=True,
        )

        assert result.success_count == 3
        assert result.failure_count == 0
        assert result.total_count == 3
        assert result.verified is True
        assert result.all_succeeded is True

    def test_partial_failure_properties(self) -> None:
        """Test InjectionResult with partial failures."""
        result = InjectionResult(
            injected_ids=["task-1", "task-2"],
            failed_ids=["task-3"],
            verified=True,
        )

        assert result.success_count == 2
        assert result.failure_count == 1
        assert result.total_count == 3
        assert result.all_succeeded is False

    def test_to_dict_serialization(self) -> None:
        """Test InjectionResult serializes to dict correctly."""
        result = InjectionResult(
            injected_ids=["task-1"],
            failed_ids=["task-2"],
            verified=True,
            verification_errors=["error1"],
        )

        d = result.to_dict()

        assert d["injected_ids"] == ["task-1"]
        assert d["failed_ids"] == ["task-2"]
        assert d["verified"] is True
        assert d["verification_errors"] == ["error1"]
        assert d["success_count"] == 1
        assert d["failure_count"] == 1
        assert "timestamp" in d


class TestTaskCandidateDataclass:
    """Tests for TaskCandidate dataclass."""

    def test_minimal_task_candidate(self) -> None:
        """Test TaskCandidate with minimal fields."""
        candidate = TaskCandidate(task_id="IMP-001", title="Test")

        assert candidate.task_id == "IMP-001"
        assert candidate.title == "Test"
        assert candidate.priority == "medium"  # Default
        assert candidate.source == "unknown"  # Default
        assert candidate.metadata == {}  # Default

    def test_full_task_candidate(self) -> None:
        """Test TaskCandidate with all fields."""
        candidate = TaskCandidate(
            task_id="IMP-TST-001",
            title="Fix flaky test",
            priority="high",
            source="telemetry_insights",
            metadata={"test_id": "test_auth", "flakiness": 0.8},
        )

        assert candidate.task_id == "IMP-TST-001"
        assert candidate.title == "Fix flaky test"
        assert candidate.priority == "high"
        assert candidate.source == "telemetry_insights"
        assert candidate.metadata["test_id"] == "test_auth"


class TestPipelineIntegration:
    """Integration tests for the complete pipeline."""

    def test_improvement_to_phase_spec_conversion(
        self, backlog_maintenance: BacklogMaintenance
    ) -> None:
        """Test conversion of TaskCandidate to phase spec."""
        candidate = TaskCandidate(
            task_id="IMP-TST-001",
            title="Fix authentication bug",
            priority="high",
            source="telemetry_insights",
            metadata={"error_count": 5},
        )

        phase_spec = backlog_maintenance._task_to_phase_spec(candidate)

        assert phase_spec["phase_id"] == "IMP-TST-001"
        assert phase_spec["description"] == "Fix authentication bug"
        assert phase_spec["status"] == "QUEUED"
        assert phase_spec["priority"] == "high"
        assert phase_spec["priority_order"] == 1  # high = 1
        assert phase_spec["source"] == "telemetry_insights"
        assert phase_spec["metadata"]["generated_task"] is True
        assert phase_spec["metadata"]["injection_source"] == "backlog_maintenance"

    def test_priority_ordering_in_phase_spec(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test priority to priority_order mapping."""
        priorities = [
            ("critical", 0),
            ("high", 1),
            ("medium", 2),
            ("low", 3),
        ]

        for priority, expected_order in priorities:
            candidate = TaskCandidate(
                task_id=f"IMP-{priority.upper()}-001",
                title=f"{priority} priority task",
                priority=priority,
            )
            phase_spec = backlog_maintenance._task_to_phase_spec(candidate)
            assert phase_spec["priority_order"] == expected_order

    def test_queue_status_tracking(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test queue status tracking after injection."""
        candidates = [
            TaskCandidate(task_id="IMP-001", title="Task 1", priority="high"),
            TaskCandidate(task_id="IMP-002", title="Task 2", priority="medium"),
        ]

        backlog_maintenance.inject_tasks(candidates)

        status = backlog_maintenance.get_queue_status()

        assert status["total_phases"] == 2
        assert status["queued_count"] == 2
        assert status["generated_task_count"] == 2

    def test_callback_invoked_on_injection(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test that on_injection callback is invoked for each task."""
        injected_ids: List[str] = []

        def callback(task_id: str) -> None:
            injected_ids.append(task_id)

        candidates = [
            TaskCandidate(task_id="IMP-001", title="Task 1"),
            TaskCandidate(task_id="IMP-002", title="Task 2"),
        ]

        backlog_maintenance.inject_tasks(candidates, on_injection=callback)

        assert "IMP-001" in injected_ids
        assert "IMP-002" in injected_ids


class TestValidationLogic:
    """Tests for task validation before injection."""

    def test_validate_filters_empty_task_id(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test validation filters tasks with empty task_id."""
        candidates = [
            TaskCandidate(task_id="", title="No ID task"),
            TaskCandidate(task_id="IMP-001", title="Valid task"),
        ]

        validated = backlog_maintenance._validate_injection_candidates(candidates)

        assert len(validated) == 1
        assert validated[0].task_id == "IMP-001"

    def test_validate_filters_empty_title(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test validation filters tasks with empty title."""
        candidates = [
            TaskCandidate(task_id="IMP-001", title=""),
            TaskCandidate(task_id="IMP-002", title="Valid title"),
        ]

        validated = backlog_maintenance._validate_injection_candidates(candidates)

        assert len(validated) == 1
        assert validated[0].task_id == "IMP-002"

    def test_validate_filters_duplicate_ids(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test validation filters duplicate task_ids."""
        candidates = [
            TaskCandidate(task_id="IMP-001", title="First task"),
            TaskCandidate(task_id="IMP-001", title="Duplicate task"),
            TaskCandidate(task_id="IMP-002", title="Unique task"),
        ]

        validated = backlog_maintenance._validate_injection_candidates(candidates)

        assert len(validated) == 2
        task_ids = [t.task_id for t in validated]
        assert task_ids.count("IMP-001") == 1  # Only one IMP-001

    def test_validate_corrects_invalid_priority(
        self, backlog_maintenance: BacklogMaintenance
    ) -> None:
        """Test validation corrects invalid priority to medium."""
        candidates = [
            TaskCandidate(task_id="IMP-001", title="Task", priority="invalid"),
        ]

        validated = backlog_maintenance._validate_injection_candidates(candidates)

        assert len(validated) == 1
        assert validated[0].priority == "medium"

    def test_validate_preserves_valid_priorities(
        self, backlog_maintenance: BacklogMaintenance
    ) -> None:
        """Test validation preserves valid priority values."""
        candidates = [
            TaskCandidate(task_id="IMP-001", title="Task", priority="critical"),
            TaskCandidate(task_id="IMP-002", title="Task", priority="HIGH"),  # Case
            TaskCandidate(task_id="IMP-003", title="Task", priority="Low"),
        ]

        validated = backlog_maintenance._validate_injection_candidates(candidates)

        assert len(validated) == 3
        # Priority validation is case-insensitive but preserves original
        priorities = [t.priority.lower() for t in validated]
        assert "critical" in priorities
        assert "high" in priorities
        assert "low" in priorities
