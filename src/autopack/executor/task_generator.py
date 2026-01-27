"""ROAD-C: Bounded Followup Task Generator.

Generates targeted, bounded followup tasks from telemetry analysis:
- Bounded scope: ≤3 files per task
- Bounded attempts: max_attempts = 2
- Human approval gates for safety
- Auto-generated test plans and preflight checklists

Integrates with:
- ROAD-B: TelemetryAnalyzer (issue source)
- ROAD-D: Governance PR Gateway (approval flow)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from autopack.telemetry.analyzer import RankedIssue

logger = logging.getLogger(__name__)


class IssueType(Enum):
    """Types of issues that can trigger followup tasks."""

    COST_SINK = "cost_sink"  # Excessive token consumption
    FAILURE_MODE = "failure_mode"  # Recurring failures
    RETRY_PATTERN = "retry_pattern"  # Frequent retries
    FLAKY_TEST = "flaky_test"  # Unreliable tests


@dataclass
class TestPlan:
    """Verification test plan for a followup task."""

    description: str
    verification_steps: List[str]
    success_criteria: str


@dataclass
class PreflightChecklist:
    """Safety checklist before task execution."""

    checks: List[str]
    risk_assessment: str  # low, medium, high, critical


@dataclass
class FollowupTask:
    """A bounded, targeted followup task for autonomous execution.

    Constraints:
    - allowed_files: Limited to ≤3 files
    - max_attempts: Limited to 2
    - approval_gate: Requires human approval before execution
    """

    task_id: str
    title: str
    description: str
    issue_type: IssueType
    issue_rank: int  # Priority ranking from telemetry
    source_phase_id: str

    # Bounded scope constraints
    allowed_files: List[str]  # Max 3 files
    max_attempts: int = 2
    approval_gate: bool = True

    # Verification and safety
    test_plan: TestPlan = field(default_factory=lambda: TestPlan("", [], ""))
    preflight_checklist: PreflightChecklist = field(
        default_factory=lambda: PreflightChecklist([], "medium")
    )

    # Metrics and targets
    target_metric: Optional[str] = None  # e.g., "token_reduction", "retry_reduction"
    target_value: Optional[float] = None  # e.g., 0.3 for 30% reduction

    # Metadata
    created_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate constraints after initialization."""
        if len(self.allowed_files) > 3:
            raise ValueError(
                f"FollowupTask constraint violated: allowed_files must be ≤3, got {len(self.allowed_files)}"
            )
        if self.max_attempts > 2:
            logger.warning(
                f"FollowupTask {self.task_id}: max_attempts={self.max_attempts} exceeds recommended limit of 2"
            )


class FollowupTaskGenerator:
    """Generate bounded followup tasks from telemetry analysis.

    Implements ROAD-C bounded task generation:
    1. Consumes RankedIssue from ROAD-B analysis
    2. Creates bounded FollowupTask with ≤3 files, max 2 attempts
    3. Auto-generates TestPlan and PreflightChecklist
    4. Sets improvement targets (30% token reduction, 50% retry reduction)
    """

    def __init__(self, top_k: int = 5, max_files_per_task: int = 3):
        """
        Args:
            top_k: Generate tasks for top K issues per category
            max_files_per_task: Maximum files per task (default: 3)
        """
        self.top_k = top_k
        self.max_files_per_task = max_files_per_task

    def generate_tasks(self, ranked_issues: Dict[str, List[RankedIssue]]) -> List[FollowupTask]:
        """Generate bounded followup tasks from ranked issues.

        Args:
            ranked_issues: Dictionary from TelemetryAnalyzer.aggregate_telemetry()
                          Keys: top_cost_sinks, top_failure_modes, top_retry_causes

        Returns:
            List of FollowupTask instances ready for approval and execution
        """
        tasks = []

        # Generate tasks from cost sinks
        for issue in ranked_issues.get("top_cost_sinks", [])[: self.top_k]:
            task = self.generate_task_from_cost_sink(issue)
            if task:
                tasks.append(task)

        # Generate tasks from failure modes
        for issue in ranked_issues.get("top_failure_modes", [])[: self.top_k]:
            task = self.generate_task_from_failure_mode(issue)
            if task:
                tasks.append(task)

        # Generate tasks from retry patterns
        for issue in ranked_issues.get("top_retry_causes", [])[: self.top_k]:
            task = self.generate_task_from_retry_pattern(issue)
            if task:
                tasks.append(task)

        logger.info(
            f"[ROAD-C] Generated {len(tasks)} followup tasks from {sum(len(v) for v in ranked_issues.values())} ranked issues"
        )

        return tasks

    def generate_task_from_cost_sink(self, issue: RankedIssue) -> Optional[FollowupTask]:
        """Generate optimization task for token cost sink.

        Target: 30% token reduction
        """
        if issue.issue_type != "cost_sink":
            return None

        task_id = f"COST_{issue.phase_id}_{issue.rank}"
        tokens_used = int(issue.metric_value)

        # Identify files to optimize (bounded to 3)
        allowed_files = self._identify_files_for_phase(
            issue.phase_id, limit=self.max_files_per_task
        )

        if not allowed_files:
            logger.warning(
                f"[ROAD-C] Cannot generate task for {issue.phase_id}: no identifiable files"
            )
            return None

        # Create test plan
        test_plan = TestPlan(
            description=f"Verify token usage reduction for {issue.phase_id}",
            verification_steps=[
                f"Run phase {issue.phase_id} with token tracking enabled",
                "Compare token usage before/after optimization",
                "Verify phase still completes successfully",
                "Ensure output quality is maintained",
            ],
            success_criteria=f"Token usage reduced by ≥30% (baseline: {tokens_used} tokens)",
        )

        # Create preflight checklist
        preflight_checklist = PreflightChecklist(
            checks=[
                "Verify token measurement baseline is accurate",
                "Ensure changes don't affect phase correctness",
                "Check that optimizations are generalizable",
                f"Confirm scope limited to {len(allowed_files)} files",
            ],
            risk_assessment="medium",
        )

        return FollowupTask(
            task_id=task_id,
            title=f"Optimize token usage in {issue.phase_id}",
            description=(
                f"Phase {issue.phase_id} consumes {tokens_used} tokens (rank #{issue.rank} cost sink). "
                "Investigate opportunities for prompt optimization, context pruning, or caching. "
                "Target 30% reduction while maintaining output quality."
            ),
            issue_type=IssueType.COST_SINK,
            issue_rank=issue.rank,
            source_phase_id=issue.phase_id,
            allowed_files=allowed_files,
            max_attempts=2,
            approval_gate=True,
            test_plan=test_plan,
            preflight_checklist=preflight_checklist,
            target_metric="token_reduction",
            target_value=0.30,  # 30% reduction
            metadata={
                "baseline_tokens": tokens_used,
                "phase_type": issue.phase_type,
                "details": issue.details,
            },
        )

    def generate_task_from_failure_mode(self, issue: RankedIssue) -> Optional[FollowupTask]:
        """Generate fix task for recurring failure pattern."""
        if issue.issue_type != "failure_mode":
            return None

        task_id = f"FAIL_{issue.phase_id}_{issue.rank}"
        failure_count = int(issue.metric_value)

        # Identify files related to failure
        allowed_files = self._identify_files_for_phase(
            issue.phase_id, limit=self.max_files_per_task
        )

        if not allowed_files:
            logger.warning(
                f"[ROAD-C] Cannot generate task for {issue.phase_id}: no identifiable files"
            )
            return None

        # Extract failure reason from details
        stop_reason = issue.details.get("stop_reason", "unknown")

        # Create test plan with reproduction test
        test_plan = TestPlan(
            description=f"Verify failure fix for {issue.phase_id}",
            verification_steps=[
                f"Create reproduction test for '{stop_reason}' failure",
                "Verify test fails on current code (confirms reproduction)",
                "Apply proposed fix",
                "Verify reproduction test now passes",
                "Run full test suite to check for regressions",
            ],
            success_criteria=f"Reproduction test passes, no new test failures, phase {issue.phase_id} succeeds",
        )

        # Create preflight checklist
        preflight_checklist = PreflightChecklist(
            checks=[
                "Verify root cause analysis is correct",
                "Ensure fix doesn't introduce new edge cases",
                "Check for similar failure patterns in other phases",
                f"Confirm scope limited to {len(allowed_files)} files",
            ],
            risk_assessment="medium",
        )

        return FollowupTask(
            task_id=task_id,
            title=f"Fix recurring failure in {issue.phase_id}",
            description=(
                f"Phase {issue.phase_id} fails {failure_count} times (rank #{issue.rank} failure mode). "
                f"Stop reason: '{stop_reason}'. "
                "Analyze root cause, create reproduction test, and implement fix."
            ),
            issue_type=IssueType.FAILURE_MODE,
            issue_rank=issue.rank,
            source_phase_id=issue.phase_id,
            allowed_files=allowed_files,
            max_attempts=2,
            approval_gate=True,
            test_plan=test_plan,
            preflight_checklist=preflight_checklist,
            target_metric="failure_elimination",
            target_value=1.0,  # 100% fix (no more failures)
            metadata={
                "baseline_failures": failure_count,
                "stop_reason": stop_reason,
                "phase_type": issue.phase_type,
                "details": issue.details,
            },
        )

    def generate_task_from_retry_pattern(self, issue: RankedIssue) -> Optional[FollowupTask]:
        """Generate stability task for retry pattern.

        Target: 50% retry reduction
        """
        if issue.issue_type != "retry_cause":
            return None

        task_id = f"RETRY_{issue.phase_id}_{issue.rank}"
        retry_count = int(issue.metric_value)

        # Identify files related to retry pattern
        allowed_files = self._identify_files_for_phase(
            issue.phase_id, limit=self.max_files_per_task
        )

        if not allowed_files:
            logger.warning(
                f"[ROAD-C] Cannot generate task for {issue.phase_id}: no identifiable files"
            )
            return None

        # Create test plan
        test_plan = TestPlan(
            description=f"Verify retry reduction for {issue.phase_id}",
            verification_steps=[
                f"Measure baseline retry rate for {issue.phase_id}",
                "Implement stability improvements (error handling, validation, etc.)",
                "Re-run phase multiple times to measure new retry rate",
                "Verify success rate is maintained or improved",
            ],
            success_criteria=f"Retry count reduced by ≥50% (baseline: {retry_count} retries)",
        )

        # Create preflight checklist
        preflight_checklist = PreflightChecklist(
            checks=[
                "Verify retry measurement baseline is accurate",
                "Ensure improvements address root cause, not symptoms",
                "Check that changes don't hide legitimate errors",
                f"Confirm scope limited to {len(allowed_files)} files",
            ],
            risk_assessment="medium",
        )

        return FollowupTask(
            task_id=task_id,
            title=f"Improve stability of {issue.phase_id}",
            description=(
                f"Phase {issue.phase_id} requires {retry_count} retries (rank #{issue.rank} retry pattern). "
                "Investigate instability causes (transient errors, race conditions, validation issues) "
                "and implement improvements. Target 50% retry reduction."
            ),
            issue_type=IssueType.RETRY_PATTERN,
            issue_rank=issue.rank,
            source_phase_id=issue.phase_id,
            allowed_files=allowed_files,
            max_attempts=2,
            approval_gate=True,
            test_plan=test_plan,
            preflight_checklist=preflight_checklist,
            target_metric="retry_reduction",
            target_value=0.50,  # 50% reduction
            metadata={
                "baseline_retries": retry_count,
                "phase_type": issue.phase_type,
                "details": issue.details,
            },
        )

    def _identify_files_for_phase(self, phase_id: str, limit: int = 3) -> List[str]:
        """Identify files associated with a phase (bounded to limit).

        In a full implementation, this would:
        1. Query execution context for phase_id
        2. Extract file paths from phase definition
        3. Rank by relevance/frequency
        4. Return top N files

        For now, returns placeholder based on naming convention.
        """
        # Heuristic file identification (placeholder logic)
        # In production, would query phase execution history for actual files touched

        # Common patterns based on phase naming
        phase_lower = phase_id.lower().replace("-", "_")

        candidate_files = []

        # Executor phases
        if "executor" in phase_lower or "orchestrat" in phase_lower:
            candidate_files.extend(
                [
                    f"src/autopack/executor/{phase_lower}.py",
                    "src/autopack/executor/phase_orchestrator.py",
                    f"tests/executor/test_{phase_lower}.py",
                ]
            )

        # Builder phases
        elif "build" in phase_lower or "construct" in phase_lower:
            candidate_files.extend(
                [
                    f"src/autopack/builder/{phase_lower}.py",
                    "src/autopack/builder/builder_agent.py",
                    f"tests/builder/test_{phase_lower}.py",
                ]
            )

        # Auditor phases
        elif "audit" in phase_lower or "review" in phase_lower:
            candidate_files.extend(
                [
                    f"src/autopack/auditor/{phase_lower}.py",
                    "src/autopack/auditor/auditor_agent.py",
                    f"tests/auditor/test_{phase_lower}.py",
                ]
            )

        # Default fallback
        else:
            candidate_files.extend(
                [
                    f"src/autopack/{phase_lower}.py",
                    "src/autopack/executor/phase_orchestrator.py",
                    f"tests/test_{phase_lower}.py",
                ]
            )

        # Return top N candidates (bounded)
        return candidate_files[:limit]

    def validate_task_constraints(self, task: FollowupTask) -> bool:
        """Validate that task meets ROAD-C constraints.

        Returns:
            True if task is valid, False otherwise
        """
        errors = []

        # Check file count constraint
        if len(task.allowed_files) > self.max_files_per_task:
            errors.append(
                f"File count {len(task.allowed_files)} exceeds max {self.max_files_per_task}"
            )

        # Check max attempts constraint
        if task.max_attempts > 2:
            errors.append(f"Max attempts {task.max_attempts} exceeds recommended limit of 2")

        # Check approval gate is enabled
        if not task.approval_gate:
            errors.append("Approval gate must be enabled for safety")

        # Check test plan is provided
        if not task.test_plan.verification_steps:
            errors.append("Test plan verification steps are required")

        # Check preflight checklist is provided
        if not task.preflight_checklist.checks:
            errors.append("Preflight checklist is required")

        if errors:
            logger.error(f"[ROAD-C] Task {task.task_id} validation failed: {', '.join(errors)}")
            return False

        return True
