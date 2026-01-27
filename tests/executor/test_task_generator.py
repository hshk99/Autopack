"""Tests for ROAD-C bounded followup task generator."""

import pytest

from autopack.executor.task_generator import (
    FollowupTask,
    FollowupTaskGenerator,
    IssueType,
    PreflightChecklist,
    TestPlan,
)
from autopack.telemetry.analyzer import RankedIssue


@pytest.fixture
def generator():
    """Create task generator with default settings."""
    return FollowupTaskGenerator(top_k=5, max_files_per_task=3)


@pytest.fixture
def cost_sink_issue():
    """Sample cost sink issue."""
    return RankedIssue(
        rank=1,
        issue_type="cost_sink",
        phase_id="code-generation-phase",
        phase_type="implementation",
        metric_value=150000.0,  # 150K tokens
        details={"total_tokens": 150000, "occurrence_count": 10},
    )


@pytest.fixture
def failure_mode_issue():
    """Sample failure mode issue."""
    return RankedIssue(
        rank=2,
        issue_type="failure_mode",
        phase_id="test-execution-phase",
        phase_type="testing",
        metric_value=25.0,  # 25 failures
        details={"stop_reason": "max_tokens", "failure_count": 25},
    )


@pytest.fixture
def retry_pattern_issue():
    """Sample retry pattern issue."""
    return RankedIssue(
        rank=3,
        issue_type="retry_cause",
        phase_id="build-phase",
        phase_type="building",
        metric_value=15.0,  # 15 retries
        details={"retry_count": 15, "avg_retries_per_run": 1.5},
    )


def test_generator_initialization():
    """Test FollowupTaskGenerator initialization."""
    generator = FollowupTaskGenerator(top_k=10, max_files_per_task=5)

    assert generator.top_k == 10
    assert generator.max_files_per_task == 5


def test_followup_task_constraint_validation():
    """Test FollowupTask enforces ≤3 file constraint."""
    # Valid task with 3 files
    task = FollowupTask(
        task_id="TEST_001",
        title="Test task",
        description="Test description",
        issue_type=IssueType.COST_SINK,
        issue_rank=1,
        source_phase_id="test-phase",
        allowed_files=["file1.py", "file2.py", "file3.py"],
    )
    assert len(task.allowed_files) == 3

    # Invalid task with >3 files should raise ValueError
    with pytest.raises(ValueError, match="allowed_files must be ≤3"):
        FollowupTask(
            task_id="TEST_002",
            title="Test task",
            description="Test description",
            issue_type=IssueType.COST_SINK,
            issue_rank=1,
            source_phase_id="test-phase",
            allowed_files=["file1.py", "file2.py", "file3.py", "file4.py"],
        )


def test_generate_task_from_cost_sink(generator, cost_sink_issue):
    """Test task generation from cost sink issue."""
    task = generator.generate_task_from_cost_sink(cost_sink_issue)

    assert task is not None
    assert task.task_id == "COST_code-generation-phase_1"
    assert task.issue_type == IssueType.COST_SINK
    assert task.issue_rank == 1
    assert task.source_phase_id == "code-generation-phase"
    assert len(task.allowed_files) <= 3
    assert task.max_attempts == 2
    assert task.approval_gate is True
    assert task.target_metric == "token_reduction"
    assert task.target_value == 0.30  # 30% reduction
    assert task.metadata["baseline_tokens"] == 150000


def test_generate_task_from_failure_mode(generator, failure_mode_issue):
    """Test task generation from failure mode issue."""
    task = generator.generate_task_from_failure_mode(failure_mode_issue)

    assert task is not None
    assert task.task_id == "FAIL_test-execution-phase_2"
    assert task.issue_type == IssueType.FAILURE_MODE
    assert task.issue_rank == 2
    assert task.source_phase_id == "test-execution-phase"
    assert len(task.allowed_files) <= 3
    assert task.max_attempts == 2
    assert task.approval_gate is True
    assert task.target_metric == "failure_elimination"
    assert task.target_value == 1.0  # 100% fix
    assert task.metadata["baseline_failures"] == 25
    assert task.metadata["stop_reason"] == "max_tokens"


def test_generate_task_from_retry_pattern(generator, retry_pattern_issue):
    """Test task generation from retry pattern issue."""
    task = generator.generate_task_from_retry_pattern(retry_pattern_issue)

    assert task is not None
    assert task.task_id == "RETRY_build-phase_3"
    assert task.issue_type == IssueType.RETRY_PATTERN
    assert task.issue_rank == 3
    assert task.source_phase_id == "build-phase"
    assert len(task.allowed_files) <= 3
    assert task.max_attempts == 2
    assert task.approval_gate is True
    assert task.target_metric == "retry_reduction"
    assert task.target_value == 0.50  # 50% reduction
    assert task.metadata["baseline_retries"] == 15


def test_generate_tasks_from_ranked_issues(
    generator, cost_sink_issue, failure_mode_issue, retry_pattern_issue
):
    """Test generating tasks from multiple ranked issues."""
    ranked_issues = {
        "top_cost_sinks": [cost_sink_issue],
        "top_failure_modes": [failure_mode_issue],
        "top_retry_causes": [retry_pattern_issue],
    }

    tasks = generator.generate_tasks(ranked_issues)

    assert len(tasks) == 3
    assert any(t.issue_type == IssueType.COST_SINK for t in tasks)
    assert any(t.issue_type == IssueType.FAILURE_MODE for t in tasks)
    assert any(t.issue_type == IssueType.RETRY_PATTERN for t in tasks)


def test_generate_tasks_respects_top_k(generator):
    """Test that generate_tasks respects top_k limit."""
    # Create 10 cost sink issues
    cost_sinks = [
        RankedIssue(
            rank=i,
            issue_type="cost_sink",
            phase_id=f"phase-{i}",
            phase_type="implementation",
            metric_value=10000.0 * i,
            details={},
        )
        for i in range(1, 11)
    ]

    generator_top_3 = FollowupTaskGenerator(top_k=3)
    tasks = generator_top_3.generate_tasks({"top_cost_sinks": cost_sinks})

    # Should only generate 3 tasks (top_k=3)
    assert len(tasks) == 3
    assert all(t.issue_rank <= 3 for t in tasks)


def test_test_plan_generation_for_cost_sink(generator, cost_sink_issue):
    """Test that test plan is properly generated for cost sink tasks."""
    task = generator.generate_task_from_cost_sink(cost_sink_issue)

    assert task.test_plan is not None
    assert task.test_plan.description
    assert len(task.test_plan.verification_steps) > 0
    assert task.test_plan.success_criteria
    assert "30%" in task.test_plan.success_criteria
    assert "150000 tokens" in task.test_plan.success_criteria


def test_test_plan_generation_for_failure_mode(generator, failure_mode_issue):
    """Test that test plan includes reproduction test for failures."""
    task = generator.generate_task_from_failure_mode(failure_mode_issue)

    assert task.test_plan is not None
    assert len(task.test_plan.verification_steps) > 0
    assert any("reproduction test" in step.lower() for step in task.test_plan.verification_steps)
    assert task.test_plan.success_criteria


def test_preflight_checklist_generation(generator, cost_sink_issue):
    """Test that preflight checklist is generated for all tasks."""
    task = generator.generate_task_from_cost_sink(cost_sink_issue)

    assert task.preflight_checklist is not None
    assert len(task.preflight_checklist.checks) > 0
    assert task.preflight_checklist.risk_assessment in ["low", "medium", "high", "critical"]
    assert any(
        "scope limited" in check.lower() or "files" in check.lower()
        for check in task.preflight_checklist.checks
    )


def test_validate_task_constraints_valid_task(generator):
    """Test validation of valid task."""
    task = FollowupTask(
        task_id="VALID_001",
        title="Valid task",
        description="Valid description",
        issue_type=IssueType.COST_SINK,
        issue_rank=1,
        source_phase_id="test-phase",
        allowed_files=["file1.py", "file2.py"],
        max_attempts=2,
        approval_gate=True,
        test_plan=TestPlan(
            description="Test plan",
            verification_steps=["Step 1", "Step 2"],
            success_criteria="Success",
        ),
        preflight_checklist=PreflightChecklist(
            checks=["Check 1", "Check 2"], risk_assessment="medium"
        ),
    )

    assert generator.validate_task_constraints(task) is True


def test_validate_task_constraints_too_many_files(generator):
    """Test validation fails with >3 files."""
    # Note: This task creation should already raise ValueError in __post_init__
    # But if we bypass that, validation should also catch it
    task = FollowupTask(
        task_id="INVALID_001",
        title="Invalid task",
        description="Invalid description",
        issue_type=IssueType.COST_SINK,
        issue_rank=1,
        source_phase_id="test-phase",
        allowed_files=["file1.py"],  # Will be replaced
        test_plan=TestPlan(
            description="Test plan",
            verification_steps=["Step 1"],
            success_criteria="Success",
        ),
        preflight_checklist=PreflightChecklist(checks=["Check 1"], risk_assessment="medium"),
    )

    # Manually override to bypass __post_init__ check
    task.allowed_files = ["file1.py", "file2.py", "file3.py", "file4.py"]

    assert generator.validate_task_constraints(task) is False


def test_validate_task_constraints_missing_test_plan(generator):
    """Test validation fails with missing test plan."""
    task = FollowupTask(
        task_id="INVALID_002",
        title="Invalid task",
        description="Invalid description",
        issue_type=IssueType.COST_SINK,
        issue_rank=1,
        source_phase_id="test-phase",
        allowed_files=["file1.py"],
        test_plan=TestPlan(description="", verification_steps=[], success_criteria=""),
        preflight_checklist=PreflightChecklist(checks=["Check 1"], risk_assessment="medium"),
    )

    assert generator.validate_task_constraints(task) is False


def test_validate_task_constraints_approval_gate_disabled(generator):
    """Test validation fails when approval gate is disabled."""
    task = FollowupTask(
        task_id="INVALID_003",
        title="Invalid task",
        description="Invalid description",
        issue_type=IssueType.COST_SINK,
        issue_rank=1,
        source_phase_id="test-phase",
        allowed_files=["file1.py"],
        approval_gate=False,  # Disabled - should fail validation
        test_plan=TestPlan(
            description="Test plan",
            verification_steps=["Step 1"],
            success_criteria="Success",
        ),
        preflight_checklist=PreflightChecklist(checks=["Check 1"], risk_assessment="medium"),
    )

    assert generator.validate_task_constraints(task) is False


def test_issue_type_enum():
    """Test IssueType enum values."""
    assert IssueType.COST_SINK.value == "cost_sink"
    assert IssueType.FAILURE_MODE.value == "failure_mode"
    assert IssueType.RETRY_PATTERN.value == "retry_pattern"
    assert IssueType.FLAKY_TEST.value == "flaky_test"


def test_task_metadata_preservation(generator, cost_sink_issue):
    """Test that task metadata includes issue details."""
    task = generator.generate_task_from_cost_sink(cost_sink_issue)

    assert task.metadata["baseline_tokens"] == 150000
    assert task.metadata["phase_type"] == "implementation"
    assert "details" in task.metadata
    assert task.metadata["details"]["total_tokens"] == 150000


def test_task_title_and_description_clarity(generator, cost_sink_issue):
    """Test that generated tasks have clear titles and descriptions."""
    task = generator.generate_task_from_cost_sink(cost_sink_issue)

    assert "code-generation-phase" in task.title
    assert "Optimize" in task.title or "optimize" in task.title.lower()
    assert "150000" in task.description or "150K" in task.description
    assert "30%" in task.description
    assert task.issue_rank == 1


def test_generate_tasks_with_empty_input(generator):
    """Test generating tasks from empty ranked issues."""
    tasks = generator.generate_tasks({})

    assert len(tasks) == 0


def test_followup_task_default_values():
    """Test FollowupTask default values."""
    task = FollowupTask(
        task_id="TEST_DEFAULT",
        title="Test",
        description="Test",
        issue_type=IssueType.COST_SINK,
        issue_rank=1,
        source_phase_id="test",
        allowed_files=["file.py"],
    )

    assert task.max_attempts == 2
    assert task.approval_gate is True
    assert task.target_metric is None
    assert task.target_value is None
    assert task.created_at is None
    assert task.metadata == {}
