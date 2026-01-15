"""
ROAD-C: Bounded Followup Task Generator

Generates bounded followup tasks from telemetry issues with constraints:
- Strict allowed-file surface
- Required test plan
- Preflight checklist
- Max attempts rule
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class IssueType(str, Enum):
    """Type of telemetry-derived issue."""

    COST_SINK = "cost_sink"
    FAILURE_MODE = "failure_mode"
    RETRY_PATTERN = "retry_pattern"
    FLAKY_TEST = "flaky_test"


@dataclass
class TestPlan:
    """Test plan for a followup task."""

    tests: List[str] = field(default_factory=list)
    description: str = ""

    def add_test(self, test_description: str) -> None:
        """Add test to plan."""
        self.tests.append(test_description)


@dataclass
class PreflightChecklist:
    """Preflight checklist for task execution."""

    items: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Initialize with default items."""
        if not self.items:
            self.items = [
                "Verify allowed_files constraints",
                "Run local tests before push",
                "Check for merge conflicts",
            ]


@dataclass
class FollowupTask:
    """Bounded followup task generated from telemetry issue."""

    task_id: str
    title: str
    issue_type: IssueType
    issue_rank: int
    allowed_files: List[str]
    test_plan: TestPlan
    preflight_checklist: PreflightChecklist
    max_attempts: int = 2
    approval_gate: bool = True
    description: str = ""
    severity: str = "medium"  # low, medium, high, critical

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary."""
        return {
            "id": self.task_id,
            "title": self.title,
            "type": self.issue_type.value,
            "rank": self.issue_rank,
            "allowed_files": self.allowed_files,
            "test_plan": self.test_plan.tests,
            "test_plan_description": self.test_plan.description,
            "preflight_checklist": self.preflight_checklist.items,
            "max_attempts": self.max_attempts,
            "approval_gate": self.approval_gate,
            "description": self.description,
            "severity": self.severity,
        }


class FollowupTaskGenerator:
    """Generate bounded followup tasks from telemetry issues."""

    def __init__(self, top_k: int = 5, max_attempts: int = 2):
        """Initialize generator.

        Args:
            top_k: Generate tasks for top K issues
            max_attempts: Max attempts before escalation
        """
        self.top_k = top_k
        self.max_attempts = max_attempts

    def generate_task_from_cost_sink(
        self,
        rank: int,
        phase_id: str,
        total_tokens: int,
    ) -> FollowupTask:
        """Generate task for cost sink issue.

        Args:
            rank: Issue rank (1 = most critical)
            phase_id: Phase identifier
            total_tokens: Total tokens used

        Returns:
            Bounded followup task
        """
        safe_phase = phase_id.replace("-", "_").replace(".", "_")

        task = FollowupTask(
            task_id=f"COST-SINK-{rank}",
            title=f"Optimize token usage in {phase_id}",
            issue_type=IssueType.COST_SINK,
            issue_rank=rank,
            allowed_files=[
                f"src/autopack/executor/{safe_phase}.py",
                f"tests/executor/test_{safe_phase}.py",
                "src/autopack/utils/token_estimation.py",
            ],
            test_plan=self._build_cost_optimization_tests(phase_id, total_tokens),
            preflight_checklist=PreflightChecklist(),
            severity="high" if total_tokens > 100000 else "medium",
            description=f"Phase {phase_id} used {total_tokens:,} tokens. "
            f"Investigate and optimize token usage.",
        )

        logger.info(f"Generated task: {task.task_id} for {phase_id}")
        return task

    def generate_task_from_failure_mode(
        self,
        rank: int,
        phase_id: str,
        stop_reason: str,
        frequency: int,
    ) -> FollowupTask:
        """Generate task for failure mode issue.

        Args:
            rank: Issue rank
            phase_id: Phase identifier
            stop_reason: Why phase stopped
            frequency: How many times this failure occurred

        Returns:
            Bounded followup task
        """
        safe_phase = phase_id.replace("-", "_").replace(".", "_")

        task = FollowupTask(
            task_id=f"FAILURE-{rank}",
            title=f"Fix {stop_reason} in {phase_id}",
            issue_type=IssueType.FAILURE_MODE,
            issue_rank=rank,
            allowed_files=[
                f"src/autopack/executor/{safe_phase}.py",
                f"tests/executor/test_{safe_phase}.py",
            ],
            test_plan=self._build_failure_fix_tests(phase_id, stop_reason, frequency),
            preflight_checklist=PreflightChecklist(),
            severity="critical" if frequency >= 5 else "high",
            description=f"Phase {phase_id} failed with '{stop_reason}' "
            f"{frequency} times in recent period.",
        )

        logger.info(f"Generated task: {task.task_id} for {phase_id}")
        return task

    def generate_task_from_retry_pattern(
        self,
        rank: int,
        phase_id: str,
        stop_reason: str,
        retry_count: int,
    ) -> FollowupTask:
        """Generate task for retry pattern issue.

        Args:
            rank: Issue rank
            phase_id: Phase identifier
            stop_reason: Why phase needed retries
            retry_count: How many retries occurred

        Returns:
            Bounded followup task
        """
        safe_phase = phase_id.replace("-", "_").replace(".", "_")

        task = FollowupTask(
            task_id=f"RETRY-{rank}",
            title=f"Reduce retries in {phase_id}",
            issue_type=IssueType.RETRY_PATTERN,
            issue_rank=rank,
            allowed_files=[
                f"src/autopack/executor/{safe_phase}.py",
                f"tests/executor/test_{safe_phase}.py",
                "src/autopack/executor/retry_strategy.py",
            ],
            test_plan=self._build_retry_reduction_tests(phase_id, retry_count),
            preflight_checklist=PreflightChecklist(),
            severity="medium",
            description=f"Phase {phase_id} required {retry_count} retries "
            f"due to {stop_reason}. Improve stability.",
        )

        logger.info(f"Generated task: {task.task_id} for {phase_id}")
        return task

    def _build_cost_optimization_tests(
        self,
        phase_id: str,
        total_tokens: int,
    ) -> TestPlan:
        """Build test plan for cost optimization task."""
        plan = TestPlan(description="Verify token usage reduction without degrading quality")
        plan.add_test(f"test_{phase_id}_baseline_tokens: Assert baseline tokens recorded")
        plan.add_test(
            f"test_{phase_id}_optimized_tokens: "
            f"Assert optimized tokens <= {int(total_tokens * 0.7)}"
        )
        plan.add_test(
            f"test_{phase_id}_quality_maintained: " "Assert all existing tests still pass"
        )
        return plan

    def _build_failure_fix_tests(
        self,
        phase_id: str,
        stop_reason: str,
        frequency: int,
    ) -> TestPlan:
        """Build test plan for failure fix task."""
        plan = TestPlan(description=f"Verify fix prevents recurrence of {stop_reason}")
        plan.add_test(f"test_{phase_id}_reproduces_failure: Reproduce original {stop_reason}")
        plan.add_test(f"test_{phase_id}_fix_applied: Verify fix prevents failure")
        plan.add_test(
            f"test_{phase_id}_no_regression: " "Verify fix doesn't break existing functionality"
        )
        return plan

    def _build_retry_reduction_tests(
        self,
        phase_id: str,
        retry_count: int,
    ) -> TestPlan:
        """Build test plan for retry reduction task."""
        plan = TestPlan(description=f"Verify retry count reduced from {retry_count}")
        plan.add_test(f"test_{phase_id}_retry_baseline: Record baseline retry count")
        plan.add_test(
            f"test_{phase_id}_retry_reduced: "
            f"Assert retry count <= {max(1, int(retry_count * 0.5))}"
        )
        plan.add_test(f"test_{phase_id}_stability_improved: Assert pass rate improved")
        return plan

    def generate_tasks(
        self,
        issues: List[Dict[str, Any]],
    ) -> List[FollowupTask]:
        """Generate bounded tasks from issue list.

        Args:
            issues: List of issues from telemetry analysis

        Returns:
            List of bounded followup tasks
        """
        tasks = []

        for rank, issue in enumerate(issues[: self.top_k], start=1):
            issue_type = issue.get("type", "unknown")

            if issue_type == IssueType.COST_SINK.value:
                task = self.generate_task_from_cost_sink(
                    rank=rank,
                    phase_id=issue["phase_id"],
                    total_tokens=issue["total_tokens"],
                )
            elif issue_type == IssueType.FAILURE_MODE.value:
                task = self.generate_task_from_failure_mode(
                    rank=rank,
                    phase_id=issue["phase_id"],
                    stop_reason=issue["stop_reason"],
                    frequency=issue["frequency"],
                )
            elif issue_type == IssueType.RETRY_PATTERN.value:
                task = self.generate_task_from_retry_pattern(
                    rank=rank,
                    phase_id=issue["phase_id"],
                    stop_reason=issue["stop_reason"],
                    retry_count=issue["retry_count"],
                )
            else:
                logger.warning(f"Unknown issue type: {issue_type}")
                continue

            tasks.append(task)

        return tasks
