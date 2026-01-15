"""Tests for ROAD-C: Bounded Followup Task Generator"""

import pytest
from src.autopack.executor.task_generator import (
    FollowupTaskGenerator,
    IssueType,
)


class TestFollowupTaskGenerator:
    """Test bounded task generation from telemetry issues."""

    def setup_method(self):
        """Create generator for each test."""
        self.generator = FollowupTaskGenerator(top_k=5, max_attempts=2)

    def test_generate_cost_sink_task(self):
        """Test generating task for cost sink issue."""
        task = self.generator.generate_task_from_cost_sink(
            rank=1,
            phase_id="auth-service",
            total_tokens=150000,
        )

        assert task.task_id == "COST-SINK-1"
        assert task.issue_type == IssueType.COST_SINK
        assert task.issue_rank == 1
        assert task.max_attempts == 2
        assert task.approval_gate is True
        assert "auth_service" in task.allowed_files[0]
        assert len(task.test_plan.tests) > 0
        assert task.severity == "high"

    def test_generate_failure_mode_task(self):
        """Test generating task for failure mode issue."""
        task = self.generator.generate_task_from_failure_mode(
            rank=2,
            phase_id="database-migration",
            stop_reason="timeout",
            frequency=5,
        )

        assert task.task_id == "FAILURE-2"
        assert task.issue_type == IssueType.FAILURE_MODE
        assert task.severity == "critical"  # frequency >= 5
        assert "timeout" in task.description.lower()
        assert len(task.test_plan.tests) == 3

    def test_generate_retry_pattern_task(self):
        """Test generating task for retry pattern issue."""
        task = self.generator.generate_task_from_retry_pattern(
            rank=3,
            phase_id="network-request",
            stop_reason="connection_reset",
            retry_count=8,
        )

        assert task.task_id == "RETRY-3"
        assert task.issue_type == IssueType.RETRY_PATTERN
        assert task.severity == "medium"
        assert 8 in [int(s) for s in task.description.split() if s.isdigit()]

    def test_task_constraints(self):
        """Test that generated tasks respect constraints."""
        task = self.generator.generate_task_from_cost_sink(
            rank=1,
            phase_id="phase-001",
            total_tokens=100000,
        )

        # Verify allowed files are bounded
        assert len(task.allowed_files) <= 3
        assert all("phase_001" in f or "token_estimation" in f for f in task.allowed_files)

        # Verify preflight checklist exists
        assert len(task.preflight_checklist.items) > 0

        # Verify max attempts is set
        assert task.max_attempts == 2

    def test_generate_multiple_tasks(self):
        """Test generating multiple tasks from issue list."""
        issues = [
            {
                "type": IssueType.COST_SINK.value,
                "phase_id": "phase-1",
                "total_tokens": 100000,
            },
            {
                "type": IssueType.FAILURE_MODE.value,
                "phase_id": "phase-2",
                "stop_reason": "crash",
                "frequency": 3,
            },
            {
                "type": IssueType.RETRY_PATTERN.value,
                "phase_id": "phase-3",
                "stop_reason": "timeout",
                "retry_count": 5,
            },
        ]

        tasks = self.generator.generate_tasks(issues)

        assert len(tasks) == 3
        assert tasks[0].issue_rank == 1
        assert tasks[1].issue_rank == 2
        assert tasks[2].issue_rank == 3
        assert tasks[0].task_id == "COST-SINK-1"
        assert tasks[1].task_id == "FAILURE-2"
        assert tasks[2].task_id == "RETRY-3"

    def test_task_to_dict(self):
        """Test task serialization to dict."""
        task = self.generator.generate_task_from_cost_sink(
            rank=1,
            phase_id="test-phase",
            total_tokens=50000,
        )

        task_dict = task.to_dict()

        assert "id" in task_dict
        assert "title" in task_dict
        assert "allowed_files" in task_dict
        assert "test_plan" in task_dict
        assert "preflight_checklist" in task_dict
        assert task_dict["max_attempts"] == 2
        assert task_dict["approval_gate"] is True

    def test_test_plan_generation(self):
        """Test that test plans are properly generated."""
        task = self.generator.generate_task_from_failure_mode(
            rank=1,
            phase_id="critical-phase",
            stop_reason="out_of_memory",
            frequency=10,
        )

        tests = task.test_plan.tests
        assert len(tests) == 3
        assert any("reproduces" in t.lower() for t in tests)
        assert any("fix" in t.lower() for t in tests)
        assert any("regression" in t.lower() for t in tests)

    def test_top_k_limit(self):
        """Test that generator respects top_k limit."""
        generator = FollowupTaskGenerator(top_k=3, max_attempts=2)

        issues = [
            {
                "type": IssueType.COST_SINK.value,
                "phase_id": f"phase-{i}",
                "total_tokens": 100000,
            }
            for i in range(10)
        ]

        tasks = generator.generate_tasks(issues)

        assert len(tasks) == 3  # Should be limited to top_k


class TestIssueType:
    """Test IssueType enum."""

    def test_issue_type_values(self):
        """Test that all issue types are defined."""
        assert IssueType.COST_SINK.value == "cost_sink"
        assert IssueType.FAILURE_MODE.value == "failure_mode"
        assert IssueType.RETRY_PATTERN.value == "retry_pattern"
        assert IssueType.FLAKY_TEST.value == "flaky_test"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
