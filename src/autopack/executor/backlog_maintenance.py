"""Backlog maintenance for autonomous execution.

Extracted from autonomous_executor.py as part of PR-EXE-12.
Handles backlog cleanup, stuck phase detection, and health monitoring.

IMP-LOOP-001: Added injection verification to ensure generated tasks
properly appear in the execution queue after injection.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from autopack.backlog_maintenance import (create_git_checkpoint,
                                          parse_patch_stats)
from autopack.governed_apply import GovernedApplyPath
from autopack.maintenance_auditor import AuditorInput, DiffStats, TestResult
from autopack.maintenance_auditor import evaluate as audit_evaluate

if TYPE_CHECKING:
    from autopack.autonomous_executor import AutonomousExecutor

logger = logging.getLogger(__name__)


@dataclass
class InjectionResult:
    """Result of a task injection operation (IMP-LOOP-001).

    Tracks which tasks were successfully injected into the execution queue
    and provides verification status.

    Attributes:
        injected_ids: List of task IDs that were successfully injected.
        failed_ids: List of task IDs that failed to inject.
        verified: Whether all injected tasks were verified in queue.
        verification_errors: List of verification error messages.
        timestamp: When the injection occurred.
    """

    injected_ids: List[str] = field(default_factory=list)
    failed_ids: List[str] = field(default_factory=list)
    verified: bool = False
    verification_errors: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def success_count(self) -> int:
        """Number of successfully injected tasks."""
        return len(self.injected_ids)

    @property
    def failure_count(self) -> int:
        """Number of failed injection attempts."""
        return len(self.failed_ids)

    @property
    def total_count(self) -> int:
        """Total number of tasks processed."""
        return self.success_count + self.failure_count

    @property
    def all_succeeded(self) -> bool:
        """Whether all tasks were successfully injected and verified."""
        return self.failure_count == 0 and self.verified

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "injected_ids": self.injected_ids,
            "failed_ids": self.failed_ids,
            "verified": self.verified,
            "verification_errors": self.verification_errors,
            "timestamp": self.timestamp.isoformat(),
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "all_succeeded": self.all_succeeded,
        }


@dataclass
class TaskCandidate:
    """A task candidate for injection into the execution queue (IMP-LOOP-001).

    Attributes:
        task_id: Unique identifier for the task.
        title: Brief description of the task.
        priority: Priority level (critical/high/medium/low).
        source: Origin of the task (e.g., 'telemetry_insights').
        metadata: Additional task metadata.
    """

    task_id: str
    title: str
    priority: str = "medium"
    source: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)


class BacklogMaintenance:
    """Handles backlog maintenance operations.

    Responsibilities:
    1. Detect stuck phases
    2. Clean up stale backlog entries
    3. Monitor health budget
    4. Requeue phases if needed
    """

    def __init__(self, executor: "AutonomousExecutor"):
        self.executor = executor

    def run_maintenance(
        self,
        plan_path: Path,
        patch_dir: Optional[Path] = None,
        apply: bool = False,
        allowed_paths: Optional[List[str]] = None,
        max_files: int = 10,
        max_lines: int = 500,
        checkpoint: bool = True,
        test_commands: Optional[List[str]] = None,
        auto_apply_low_risk: bool = False,
    ) -> None:
        """Run backlog maintenance cycle.

        Checks for stuck phases, cleans up stale entries,
        monitors health budget.

        Run a backlog maintenance plan with diagnostics + optional apply.
        - Diagnostics always run.
        - Apply happens only if:
            * auditor verdict == approve
            * checkpoint creation succeeded
            * patch is present

        Args:
            plan_path: Path to the maintenance plan JSON file
            patch_dir: Directory containing patch files
            apply: Whether to apply approved patches
            allowed_paths: List of allowed paths for patching
            max_files: Maximum files allowed in a patch
            max_lines: Maximum lines allowed in a patch
            checkpoint: Whether to create git checkpoint before applying
            test_commands: List of test commands to run
            auto_apply_low_risk: Whether to auto-apply low-risk changes
        """
        try:
            plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"[Backlog] Failed to load plan {plan_path}: {e}")
            return

        phases = plan.get("phases", [])
        default_allowed = allowed_paths or [
            "src/autopack/",
            "src/frontend/",
            "Dockerfile",
            "docker-compose",
            "README",
            "docs/",
            "scripts/",
            "tests/",
        ]
        protected_paths = ["config/", ".autonomous_runs/", ".git/"]

        diag_dir = Path(".autonomous_runs") / self.executor.run_id / "diagnostics"
        diag_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_hash = None
        if apply and checkpoint:
            ok, checkpoint_hash = create_git_checkpoint(
                Path(self.executor.workspace),
                message=f"[Autopack] Backlog checkpoint {self.executor.run_id}",
            )
            if ok:
                logger.info(f"[Backlog] Checkpoint created: {checkpoint_hash}")
            else:
                logger.warning(f"[Backlog] Checkpoint failed: {checkpoint_hash}")

        summaries = []
        for phase in phases:
            phase_id = phase.get("id")
            desc = phase.get("description")
            logger.info(f"[Backlog] Diagnostics for {phase_id}: {desc}")
            outcome = self.executor.diagnostics_agent.run_diagnostics(
                failure_class="maintenance",
                context={
                    "phase_id": phase_id,
                    "description": desc,
                    "backlog_summary": phase.get("metadata", {}).get("backlog_summary"),
                },
                phase_id=phase_id,
                mode="maintenance",
            )

            test_results = []
            if test_commands:
                try:
                    from autopack.maintenance_runner import run_tests

                    test_results = run_tests(test_commands, workspace=Path(self.executor.workspace))
                except Exception as e:
                    logger.warning(f"[Backlog][Tests] Failed to run tests for {phase_id}: {e}")

            patch_path = None
            if patch_dir:
                candidate = Path(patch_dir) / f"{phase_id}.patch"
                if candidate.exists():
                    patch_path = candidate

            diff_stats = DiffStats(files_changed=[], lines_added=0, lines_deleted=0)
            if patch_path:
                diff_stats = parse_patch_stats(
                    patch_path.read_text(encoding="utf-8", errors="ignore")
                )

            auditor_input = AuditorInput(
                allowed_paths=default_allowed,
                protected_paths=protected_paths,
                diff=diff_stats,
                tests=[TestResult(name=t.name, status=t.status) for t in test_results],
                failure_class="maintenance",
                item_context=phase.get("metadata", {}).get("backlog_summary", "") or desc or "",
                diagnostics_summary=outcome.ledger_summary,
                max_files=max_files,
                max_lines=max_lines,
            )
            decision = audit_evaluate(auditor_input)
            logger.info(
                f"[Backlog][Auditor] {phase_id}: verdict={decision.verdict} reasons={decision.reasons}"
            )

            self.executor._record_decision_entry(
                trigger="backlog_maintenance",
                choice=f"audit:{decision.verdict}",
                rationale="; ".join(decision.reasons)[:500],
                phase_id=phase_id,
                alternatives="approve,require_human,reject",
            )

            apply_result = None
            if apply and patch_path and decision.verdict == "approve" and checkpoint_hash:
                # If auto_apply_low_risk, enforce stricter bounds
                if auto_apply_low_risk:
                    if (
                        len(diff_stats.files_changed) > max_files
                        or (diff_stats.lines_added + diff_stats.lines_deleted) > max_lines
                    ):
                        logger.info(
                            f"[Backlog][Apply] Skipping apply (auto-apply low risk) due to size: files={len(diff_stats.files_changed)}, lines={diff_stats.lines_added + diff_stats.lines_deleted}"
                        )
                        apply_result = {"success": False, "error": "auto_apply_low_risk_size_guard"}
                    elif any(t.status != "passed" for t in test_results):
                        logger.info(
                            "[Backlog][Apply] Skipping apply (auto-apply low risk) due to tests not all passing"
                        )
                        apply_result = {
                            "success": False,
                            "error": "auto_apply_low_risk_tests_guard",
                        }
                    else:
                        # IMP-SAFETY-008: Extract scope_paths from phase for Layer 2 validation
                        scope_config = phase.get("scope", {})
                        scope_paths = (
                            scope_config.get("paths", []) if isinstance(scope_config, dict) else []
                        )
                        gap = GovernedApplyPath(
                            workspace=Path(self.executor.workspace),
                            allowed_paths=default_allowed,
                            protected_paths=protected_paths,
                            run_type="project_build",
                            scope_paths=scope_paths,
                        )
                        success, err = gap.apply_patch(
                            patch_path.read_text(encoding="utf-8", errors="ignore")
                        )
                        apply_result = {"success": success, "error": err}
                        if success:
                            logger.info(f"[Backlog][Apply] Success for {phase_id}")
                        else:
                            logger.warning(f"[Backlog][Apply] Failed for {phase_id}: {err}")
                            if checkpoint_hash:
                                logger.info(
                                    "[Backlog][Apply] Reverting to checkpoint due to failure"
                                )
                                from autopack.backlog_maintenance import \
                                    revert_to_checkpoint

                                revert_to_checkpoint(Path(self.executor.workspace), checkpoint_hash)
                else:
                    # IMP-SAFETY-008: Extract scope_paths from phase for Layer 2 validation
                    scope_config = phase.get("scope", {})
                    scope_paths = (
                        scope_config.get("paths", []) if isinstance(scope_config, dict) else []
                    )
                    gap = GovernedApplyPath(
                        workspace=Path(self.executor.workspace),
                        allowed_paths=default_allowed,
                        protected_paths=protected_paths,
                        run_type="project_build",
                        scope_paths=scope_paths,
                    )
                    success, err = gap.apply_patch(
                        patch_path.read_text(encoding="utf-8", errors="ignore")
                    )
                    apply_result = {"success": success, "error": err}
                    if success:
                        logger.info(f"[Backlog][Apply] Success for {phase_id}")
                    else:
                        logger.warning(f"[Backlog][Apply] Failed for {phase_id}: {err}")
                        if checkpoint_hash:
                            logger.info("[Backlog][Apply] Reverting to checkpoint due to failure")
                            from autopack.backlog_maintenance import \
                                revert_to_checkpoint

                            revert_to_checkpoint(Path(self.executor.workspace), checkpoint_hash)
            elif apply and patch_path is None:
                logger.info(f"[Backlog][Apply] No patch for {phase_id}, skipping apply")
            elif apply and decision.verdict != "approve":
                logger.info(
                    f"[Backlog][Apply] Skipped {phase_id}: auditor verdict {decision.verdict}"
                )
            elif apply and not checkpoint_hash:
                logger.info(f"[Backlog][Apply] Skipped {phase_id}: no checkpoint")

            summaries.append(
                {
                    "phase_id": phase_id,
                    "ledger": outcome.ledger_summary,
                    "auditor_verdict": decision.verdict,
                    "auditor_reasons": decision.reasons,
                    "apply_result": apply_result,
                    "patch_path": str(patch_path) if patch_path else None,
                    "checkpoint": checkpoint_hash,
                    "tests": [t.__dict__ for t in test_results],
                }
            )

        try:
            summary_path = diag_dir / "backlog_executor_summary.json"
            summary_path.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
            logger.info(f"[Backlog] Summary written to {summary_path}")
        except Exception as e:
            logger.warning(f"[Backlog] Failed to write summary: {e}")

        # Learning Pipeline: Load project learned rules (Stage 0B)
        self.executor._load_project_learning_context()

    # =========================================================================
    # IMP-LOOP-001: Task Injection Verification
    # =========================================================================

    def inject_tasks(
        self,
        tasks: List[TaskCandidate],
        on_injection: Optional[Callable[[str], None]] = None,
    ) -> InjectionResult:
        """Inject tasks into the execution queue with verification (IMP-LOOP-001).

        This method validates tasks before injection, performs the injection,
        and verifies that injected tasks appear in the execution queue.

        Args:
            tasks: List of TaskCandidate objects to inject.
            on_injection: Optional callback invoked for each successfully injected task.

        Returns:
            InjectionResult with details of the injection operation.
        """
        result = InjectionResult()

        if not tasks:
            logger.info("[IMP-LOOP-001] No tasks to inject")
            result.verified = True
            return result

        # Step 1: Validate tasks before injection
        validated = self._validate_injection_candidates(tasks)
        if not validated:
            logger.warning("[IMP-LOOP-001] No tasks passed validation")
            result.failed_ids = [t.task_id for t in tasks]
            return result

        # Step 2: Perform injection with tracking
        result = self._perform_injection(validated, on_injection)

        # Step 3: Verify injection success
        self._verify_injection(result)

        logger.info(
            "[IMP-LOOP-001] Injection complete: %d injected, %d failed, verified=%s",
            result.success_count,
            result.failure_count,
            result.verified,
        )

        return result

    def _validate_injection_candidates(self, tasks: List[TaskCandidate]) -> List[TaskCandidate]:
        """Validate task candidates before injection (IMP-LOOP-001).

        Checks that tasks have required fields and valid priorities.
        Filters out invalid or duplicate tasks.

        Args:
            tasks: List of task candidates to validate.

        Returns:
            List of validated task candidates.
        """
        validated: List[TaskCandidate] = []
        seen_ids: set[str] = set()
        valid_priorities = {"critical", "high", "medium", "low"}

        for task in tasks:
            # Check for required fields
            if not task.task_id:
                logger.warning("[IMP-LOOP-001] Task missing task_id, skipping")
                continue

            if not task.title:
                logger.warning("[IMP-LOOP-001] Task %s missing title, skipping", task.task_id)
                continue

            # Check for duplicates
            if task.task_id in seen_ids:
                logger.warning("[IMP-LOOP-001] Duplicate task_id %s, skipping", task.task_id)
                continue

            # Validate priority
            if task.priority.lower() not in valid_priorities:
                logger.warning(
                    "[IMP-LOOP-001] Task %s has invalid priority '%s', defaulting to 'medium'",
                    task.task_id,
                    task.priority,
                )
                task.priority = "medium"

            seen_ids.add(task.task_id)
            validated.append(task)

        logger.debug("[IMP-LOOP-001] Validated %d of %d tasks", len(validated), len(tasks))
        return validated

    def _perform_injection(
        self,
        tasks: List[TaskCandidate],
        on_injection: Optional[Callable[[str], None]] = None,
    ) -> InjectionResult:
        """Perform task injection into the execution queue (IMP-LOOP-001).

        Converts task candidates to phase specs and injects them into
        the executor's phase queue.

        Args:
            tasks: List of validated task candidates.
            on_injection: Optional callback for each injected task.

        Returns:
            InjectionResult with injected and failed task IDs.
        """
        result = InjectionResult()

        for task in tasks:
            try:
                # Convert task to phase spec format
                phase_spec = self._task_to_phase_spec(task)

                # Inject into executor's phase list
                if hasattr(self.executor, "autonomous_loop"):
                    current_phases = getattr(
                        self.executor.autonomous_loop, "_current_run_phases", None
                    )
                    if current_phases is not None:
                        current_phases.append(phase_spec)
                        result.injected_ids.append(task.task_id)
                        logger.debug(
                            "[IMP-LOOP-001] Injected task %s into phase queue",
                            task.task_id,
                        )

                        # Invoke callback if provided
                        if on_injection:
                            on_injection(task.task_id)
                    else:
                        # No active run, store for later injection
                        result.injected_ids.append(task.task_id)
                        logger.debug(
                            "[IMP-LOOP-001] Task %s queued for future injection",
                            task.task_id,
                        )
                else:
                    result.failed_ids.append(task.task_id)
                    logger.warning("[IMP-LOOP-001] No autonomous_loop available for injection")

            except Exception as e:
                result.failed_ids.append(task.task_id)
                logger.error("[IMP-LOOP-001] Failed to inject task %s: %s", task.task_id, e)

        return result

    def _task_to_phase_spec(self, task: TaskCandidate) -> Dict[str, Any]:
        """Convert a TaskCandidate to a phase specification (IMP-LOOP-001).

        Creates a phase spec dictionary that can be processed by the
        autonomous executor's phase execution logic.

        Args:
            task: The task candidate to convert.

        Returns:
            Phase specification dictionary.
        """
        # Map priority to numeric order for sorting
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

        return {
            "phase_id": task.task_id,
            "description": task.title,
            "status": "QUEUED",
            "priority": task.priority,
            "priority_order": priority_order.get(task.priority.lower(), 2),
            "source": task.source,
            "scope": task.metadata.get("scope", {}),
            "metadata": {
                "generated_task": True,
                "injection_source": "backlog_maintenance",
                "original_metadata": task.metadata,
            },
        }

    def _verify_injection(self, result: InjectionResult) -> None:
        """Verify injected tasks appear in the execution queue (IMP-LOOP-001).

        Checks that all successfully injected tasks are present in the
        executor's phase queue. Updates result with verification status.

        Args:
            result: InjectionResult to verify and update.
        """
        if not result.injected_ids:
            result.verified = True
            return

        verification_errors: List[str] = []

        for task_id in result.injected_ids:
            if not self.queue_contains(task_id):
                error_msg = f"Task {task_id} not found in queue after injection"
                verification_errors.append(error_msg)
                logger.error("[IMP-LOOP-001] %s", error_msg)

        result.verification_errors = verification_errors
        result.verified = len(verification_errors) == 0

        if result.verified:
            logger.info("[IMP-LOOP-001] Verified all %d tasks in queue", len(result.injected_ids))
        else:
            logger.warning(
                "[IMP-LOOP-001] Verification failed: %d errors", len(verification_errors)
            )

    def queue_contains(self, task_id: str) -> bool:
        """Check if a task is present in the execution queue (IMP-LOOP-001).

        Searches the executor's current phase list for a task with the
        given ID.

        Args:
            task_id: The task ID to search for.

        Returns:
            True if task is found in queue, False otherwise.
        """
        if not hasattr(self.executor, "autonomous_loop"):
            return False

        current_phases = getattr(self.executor.autonomous_loop, "_current_run_phases", None)
        if current_phases is None:
            return False

        for phase in current_phases:
            if phase.get("phase_id") == task_id:
                return True

        return False

    def get_queue_status(self) -> Dict[str, Any]:
        """Get current status of the execution queue (IMP-LOOP-001).

        Returns:
            Dictionary containing queue statistics:
            - total_phases: Total number of phases in queue
            - queued_count: Number of QUEUED phases
            - in_progress_count: Number of IN_PROGRESS phases
            - completed_count: Number of COMPLETED phases
            - generated_task_count: Number of generated (injected) tasks
        """
        status = {
            "total_phases": 0,
            "queued_count": 0,
            "in_progress_count": 0,
            "completed_count": 0,
            "generated_task_count": 0,
        }

        if not hasattr(self.executor, "autonomous_loop"):
            return status

        current_phases = getattr(self.executor.autonomous_loop, "_current_run_phases", None)
        if current_phases is None:
            return status

        status["total_phases"] = len(current_phases)

        for phase in current_phases:
            phase_status = phase.get("status", "").upper()
            if phase_status == "QUEUED":
                status["queued_count"] += 1
            elif phase_status == "IN_PROGRESS":
                status["in_progress_count"] += 1
            elif phase_status in ("COMPLETED", "DONE"):
                status["completed_count"] += 1

            # Count generated tasks
            metadata = phase.get("metadata", {})
            if metadata.get("generated_task"):
                status["generated_task_count"] += 1

        return status
