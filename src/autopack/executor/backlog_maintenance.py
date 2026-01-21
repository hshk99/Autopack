"""Backlog maintenance for autonomous execution.

Extracted from autonomous_executor.py as part of PR-EXE-12.
Handles backlog cleanup, stuck phase detection, and health monitoring.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from autopack.maintenance_auditor import (
    AuditorInput,
    DiffStats,
    TestResult,
    evaluate as audit_evaluate,
)
from autopack.backlog_maintenance import parse_patch_stats, create_git_checkpoint
from autopack.governed_apply import GovernedApplyPath

if TYPE_CHECKING:
    from autopack.autonomous_executor import AutonomousExecutor

logger = logging.getLogger(__name__)


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
                                from autopack.backlog_maintenance import revert_to_checkpoint

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
                            from autopack.backlog_maintenance import revert_to_checkpoint

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
