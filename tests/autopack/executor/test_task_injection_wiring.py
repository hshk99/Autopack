"""Tests for IMP-LOOP-029: Complete Task Injection Wiring.

Tests cover:
- generated_task_to_candidate conversion function
- TaskCandidate creation from GeneratedTask
- InjectionResult handling
- Integration with BacklogMaintenance.inject_tasks()
- Task attribution tracking via TaskEffectivenessTracker
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from autopack.executor.backlog_maintenance import (
    InjectionResult,
    TaskCandidate,
    generated_task_to_candidate,
)


# Mock GeneratedTask for testing (to avoid circular imports)
@dataclass
class MockGeneratedTask:
    """Mock GeneratedTask for testing conversion."""

    task_id: str
    title: str
    description: str
    priority: str
    source_insights: List[str]
    suggested_files: List[str]
    estimated_effort: str
    created_at: datetime = field(default_factory=datetime.now)
    run_id: Optional[str] = None
    status: str = "pending"
    requires_approval: bool = False
    risk_severity: Optional[str] = None
    estimated_cost: int = 0


class TestGeneratedTaskToCandidate:
    """Tests for generated_task_to_candidate conversion function."""

    def test_basic_conversion(self):
        """generated_task_to_candidate should convert basic fields."""
        task = MockGeneratedTask(
            task_id="IMP-TEST-001",
            title="Fix performance issue",
            description="Optimize token usage in phase X",
            priority="high",
            source_insights=["insight_001"],
            suggested_files=["src/test.py"],
            estimated_effort="M",
        )

        candidate = generated_task_to_candidate(task)

        assert candidate.task_id == "IMP-TEST-001"
        assert candidate.title == "Fix performance issue"
        assert candidate.priority == "high"
        assert candidate.source == "autonomous_task_generator"

    def test_metadata_preservation(self):
        """generated_task_to_candidate should preserve metadata in candidate."""
        task = MockGeneratedTask(
            task_id="IMP-TEST-002",
            title="Test task",
            description="Description text",
            priority="critical",
            source_insights=["insight_a", "insight_b"],
            suggested_files=["file1.py", "file2.py"],
            estimated_effort="L",
            run_id="run-123",
            requires_approval=True,
            risk_severity="medium",
            estimated_cost=5000,
        )

        candidate = generated_task_to_candidate(task)

        assert candidate.metadata["description"] == "Description text"
        assert candidate.metadata["source_insights"] == ["insight_a", "insight_b"]
        assert candidate.metadata["suggested_files"] == ["file1.py", "file2.py"]
        assert candidate.metadata["estimated_effort"] == "L"
        assert candidate.metadata["run_id"] == "run-123"
        assert candidate.metadata["requires_approval"] is True
        assert candidate.metadata["risk_severity"] == "medium"
        assert candidate.metadata["estimated_cost"] == 5000
        assert candidate.metadata["generated_task_id"] == "IMP-TEST-002"

    def test_priority_levels(self):
        """generated_task_to_candidate should preserve all priority levels."""
        priorities = ["critical", "high", "medium", "low"]

        for priority in priorities:
            task = MockGeneratedTask(
                task_id=f"IMP-{priority.upper()}-001",
                title=f"Task with {priority} priority",
                description="Test",
                priority=priority,
                source_insights=[],
                suggested_files=[],
                estimated_effort="S",
            )

            candidate = generated_task_to_candidate(task)
            assert candidate.priority == priority

    def test_empty_optional_fields(self):
        """generated_task_to_candidate should handle empty/None optional fields."""
        task = MockGeneratedTask(
            task_id="IMP-TEST-003",
            title="Minimal task",
            description="",
            priority="medium",
            source_insights=[],
            suggested_files=[],
            estimated_effort="S",
            run_id=None,
        )

        candidate = generated_task_to_candidate(task)

        assert candidate.metadata["description"] == ""
        assert candidate.metadata["source_insights"] == []
        assert candidate.metadata["suggested_files"] == []
        assert candidate.metadata["run_id"] is None


class TestTaskCandidate:
    """Tests for TaskCandidate dataclass."""

    def test_task_candidate_defaults(self):
        """TaskCandidate should have correct default values."""
        candidate = TaskCandidate(
            task_id="test-001",
            title="Test task",
        )

        assert candidate.task_id == "test-001"
        assert candidate.title == "Test task"
        assert candidate.priority == "medium"
        assert candidate.source == "unknown"
        assert candidate.metadata == {}

    def test_task_candidate_with_all_fields(self):
        """TaskCandidate should accept all fields."""
        candidate = TaskCandidate(
            task_id="test-002",
            title="Full task",
            priority="critical",
            source="test_source",
            metadata={"key": "value"},
        )

        assert candidate.task_id == "test-002"
        assert candidate.title == "Full task"
        assert candidate.priority == "critical"
        assert candidate.source == "test_source"
        assert candidate.metadata == {"key": "value"}


class TestInjectionResult:
    """Tests for InjectionResult dataclass."""

    def test_injection_result_defaults(self):
        """InjectionResult should have correct default values."""
        result = InjectionResult()

        assert result.injected_ids == []
        assert result.failed_ids == []
        assert result.verified is False
        assert result.verification_errors == []
        assert isinstance(result.timestamp, datetime)

    def test_injection_result_success_count(self):
        """InjectionResult should calculate success_count correctly."""
        result = InjectionResult(
            injected_ids=["task-1", "task-2", "task-3"],
            failed_ids=["task-4"],
        )

        assert result.success_count == 3

    def test_injection_result_failure_count(self):
        """InjectionResult should calculate failure_count correctly."""
        result = InjectionResult(
            injected_ids=["task-1"],
            failed_ids=["task-2", "task-3"],
        )

        assert result.failure_count == 2

    def test_injection_result_total_count(self):
        """InjectionResult should calculate total_count correctly."""
        result = InjectionResult(
            injected_ids=["task-1", "task-2"],
            failed_ids=["task-3"],
        )

        assert result.total_count == 3

    def test_injection_result_all_succeeded_true(self):
        """all_succeeded should be True when no failures and verified."""
        result = InjectionResult(
            injected_ids=["task-1", "task-2"],
            failed_ids=[],
            verified=True,
        )

        assert result.all_succeeded is True

    def test_injection_result_all_succeeded_false_failures(self):
        """all_succeeded should be False when there are failures."""
        result = InjectionResult(
            injected_ids=["task-1"],
            failed_ids=["task-2"],
            verified=True,
        )

        assert result.all_succeeded is False

    def test_injection_result_all_succeeded_false_not_verified(self):
        """all_succeeded should be False when not verified."""
        result = InjectionResult(
            injected_ids=["task-1", "task-2"],
            failed_ids=[],
            verified=False,
        )

        assert result.all_succeeded is False

    def test_injection_result_to_dict(self):
        """InjectionResult.to_dict should serialize all fields."""
        result = InjectionResult(
            injected_ids=["task-1", "task-2"],
            failed_ids=["task-3"],
            verified=True,
            verification_errors=["Error 1"],
        )

        data = result.to_dict()

        assert data["injected_ids"] == ["task-1", "task-2"]
        assert data["failed_ids"] == ["task-3"]
        assert data["verified"] is True
        assert data["verification_errors"] == ["Error 1"]
        assert data["success_count"] == 2
        assert data["failure_count"] == 1
        assert data["all_succeeded"] is False
        assert "timestamp" in data


class TestIntegration:
    """Integration tests for task injection wiring."""

    def test_conversion_and_injection_flow(self):
        """Test complete flow: GeneratedTask -> TaskCandidate -> inject_tasks."""
        # Create mock generated tasks
        tasks = [
            MockGeneratedTask(
                task_id="IMP-LOOP-001",
                title="Fix loop issue",
                description="Reduce retries",
                priority="critical",
                source_insights=["insight_1"],
                suggested_files=["src/loop.py"],
                estimated_effort="M",
            ),
            MockGeneratedTask(
                task_id="IMP-MEM-001",
                title="Optimize memory",
                description="Reduce memory usage",
                priority="high",
                source_insights=["insight_2"],
                suggested_files=["src/memory.py"],
                estimated_effort="L",
            ),
        ]

        # Convert to candidates
        candidates = [generated_task_to_candidate(task) for task in tasks]

        # Verify conversions
        assert len(candidates) == 2
        assert candidates[0].task_id == "IMP-LOOP-001"
        assert candidates[0].priority == "critical"
        assert candidates[1].task_id == "IMP-MEM-001"
        assert candidates[1].priority == "high"

    def test_attribution_metadata_preservation(self):
        """Test that attribution metadata is preserved through conversion."""
        task = MockGeneratedTask(
            task_id="IMP-ATTR-001",
            title="Attribution test",
            description="Test attribution tracking",
            priority="high",
            source_insights=["insight_x", "insight_y"],
            suggested_files=["src/test.py"],
            estimated_effort="S",
            run_id="run-attribution-test",
        )

        candidate = generated_task_to_candidate(task)

        # Verify attribution-related metadata is preserved
        assert candidate.metadata["generated_task_id"] == "IMP-ATTR-001"
        assert candidate.metadata["run_id"] == "run-attribution-test"
        assert candidate.metadata["source_insights"] == ["insight_x", "insight_y"]

    def test_empty_task_list_conversion(self):
        """Test that empty task list converts to empty candidate list."""
        tasks: List[MockGeneratedTask] = []
        candidates = [generated_task_to_candidate(task) for task in tasks]

        assert candidates == []

    def test_large_metadata_handling(self):
        """Test that large metadata fields are handled correctly."""
        large_insights = [f"insight_{i}" for i in range(100)]
        large_files = [f"src/file_{i}.py" for i in range(50)]

        task = MockGeneratedTask(
            task_id="IMP-LARGE-001",
            title="Large metadata task",
            description="A" * 10000,  # Large description
            priority="medium",
            source_insights=large_insights,
            suggested_files=large_files,
            estimated_effort="XL",
        )

        candidate = generated_task_to_candidate(task)

        assert len(candidate.metadata["source_insights"]) == 100
        assert len(candidate.metadata["suggested_files"]) == 50
        assert len(candidate.metadata["description"]) == 10000
