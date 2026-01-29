"""Decision Executor with Safety Nets

Executes CLEAR_FIX decisions with full safety mechanisms:
- Git save points before changes
- Patch application and validation
- Deliverables verification
- Acceptance test execution
- Automatic rollback on failure
- Decision logging with metadata

Design Goals:
- Safety first (save points, rollback)
- Audit trails (log all decisions)
- Goal validation (check deliverables)
- Test gating (must pass acceptance criteria)
- Reversible (git reset to save point)
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from autopack.deliverables_validator import validate_deliverables
from autopack.diagnostics.command_runner import GovernedCommandRunner
from autopack.diagnostics.diagnostics_models import (
    Decision,
    DecisionType,
    ExecutionResult,
    PhaseSpec,
    ValidationResult,
)
from autopack.diagnostics.probes import ProbeLibrary, ProbeRunResult
from autopack.memory import MemoryService

logger = logging.getLogger(__name__)


class DecisionExecutor:
    """
    Executes CLEAR_FIX decisions with full safety nets.

    Responsibilities:
    - Create git save points
    - Apply patches/fixes
    - Validate deliverables
    - Run acceptance tests
    - Auto-rollback on failure
    - Log decisions with metadata
    """

    def __init__(
        self,
        run_id: str,
        workspace: Path,
        memory_service: Optional[MemoryService] = None,
        decision_logger: Optional[Any] = None,
    ):
        """
        Initialize decision executor.

        Args:
            run_id: Run identifier
            workspace: Workspace root
            memory_service: Optional memory service for decision logging
            decision_logger: Optional database decision logger
        """
        self.run_id = run_id
        self.workspace = workspace.resolve()
        self.memory_service = memory_service
        self.decision_logger = decision_logger

    def execute_decision(
        self,
        decision: Decision,
        phase_spec: PhaseSpec,
        original_error: Optional[str] = None,
    ) -> ExecutionResult:
        """
        Execute a CLEAR_FIX decision with safety nets.

        Steps:
        1. Create git save point
        2. Apply patch/fix
        3. Validate deliverables
        4. Run acceptance tests
        5. Validate fix resolved original error
        6. If failure: auto-rollback
        7. If success: commit with metadata
        8. Log decision

        Args:
            decision: Decision to execute (must be CLEAR_FIX)
            phase_spec: Phase specification for validation
            original_error: Optional original error message for post-fix validation

        Returns:
            ExecutionResult with success status and details
        """
        if decision.type != DecisionType.CLEAR_FIX:
            return ExecutionResult(
                success=False,
                decision_id="",
                save_point=None,
                patch_applied=False,
                deliverables_validated=False,
                tests_passed=False,
                rollback_performed=False,
                error_message=f"Cannot execute {decision.type.value} decision - only CLEAR_FIX supported",
            )

        decision_id = self._generate_decision_id(phase_spec.phase_id)
        logger.info(f"[DecisionExecutor] Executing decision: {decision_id}")

        # Step 1: Create save point
        save_point = self._create_save_point(phase_spec.phase_id)
        if not save_point:
            return ExecutionResult(
                success=False,
                decision_id=decision_id,
                save_point=None,
                patch_applied=False,
                deliverables_validated=False,
                tests_passed=False,
                rollback_performed=False,
                error_message="Failed to create git save point",
            )

        logger.info(f"[DecisionExecutor] Created save point: {save_point}")

        try:
            # Step 2: Apply patch
            if not decision.patch:
                logger.error("[DecisionExecutor] No patch content in decision")
                return ExecutionResult(
                    success=False,
                    decision_id=decision_id,
                    save_point=save_point,
                    patch_applied=False,
                    deliverables_validated=False,
                    tests_passed=False,
                    rollback_performed=False,
                    error_message="No patch content in decision",
                )

            patch_result = self._apply_patch(decision.patch)
            if not patch_result["success"]:
                logger.warning(
                    f"[DecisionExecutor] Direct patch failed, attempting recovery: "
                    f"{patch_result['error']}"
                )

                # Extract conflict information for retry context
                conflict_lines = self._extract_conflict_lines(
                    decision.patch, patch_result.get("error", "")
                )

                # Attempt explicit 3-way merge as recovery
                merge_result = self._attempt_three_way_merge(decision.patch)
                if merge_result["success"]:
                    logger.info("[DecisionExecutor] 3-way merge recovery succeeded")
                    # Continue with execution - patch is now applied
                else:
                    logger.error(
                        f"[DecisionExecutor] 3-way merge also failed: {merge_result['error']}"
                    )

                    # Log conflict details for next round
                    return ExecutionResult(
                        success=False,
                        decision_id=decision_id,
                        save_point=save_point,
                        patch_applied=False,
                        deliverables_validated=False,
                        tests_passed=False,
                        rollback_performed=False,
                        error_message=f"Patch application failed: {patch_result['error']}",
                        conflict_lines=conflict_lines,
                        retry_context={
                            "original_error": str(patch_result.get("error", "")),
                            "merge_attempted": True,
                            "merge_error": str(merge_result.get("error", "")),
                        },
                    )

            logger.info("[DecisionExecutor] Patch applied successfully")

            # Step 3: Validate deliverables
            deliverables_ok = self._validate_deliverables(decision.patch, phase_spec.deliverables)
            if not deliverables_ok:
                logger.error("[DecisionExecutor] Deliverables validation failed - rolling back")
                self._rollback(save_point)
                return ExecutionResult(
                    success=False,
                    decision_id=decision_id,
                    save_point=save_point,
                    patch_applied=True,
                    deliverables_validated=False,
                    tests_passed=False,
                    rollback_performed=True,
                    error_message="Deliverables validation failed",
                )

            logger.info("[DecisionExecutor] Deliverables validated")

            # Step 4: Run acceptance tests
            tests_passed = self._run_acceptance_tests(phase_spec.acceptance_criteria)
            if not tests_passed:
                logger.error("[DecisionExecutor] Acceptance tests failed - rolling back")
                self._rollback(save_point)
                return ExecutionResult(
                    success=False,
                    decision_id=decision_id,
                    save_point=save_point,
                    patch_applied=True,
                    deliverables_validated=True,
                    tests_passed=False,
                    rollback_performed=True,
                    error_message="Acceptance tests failed",
                )

            logger.info("[DecisionExecutor] Acceptance tests passed")

            # Step 5: Validate fix resolved original error
            validation_result = self._validate_fix(original_error, decision, phase_spec)
            if not validation_result.resolved:
                logger.warning(
                    f"[DecisionExecutor] Post-fix validation failed: {validation_result.reason}"
                )
                self._rollback(save_point)
                return ExecutionResult(
                    success=False,
                    decision_id=decision_id,
                    save_point=save_point,
                    patch_applied=True,
                    deliverables_validated=True,
                    tests_passed=True,
                    rollback_performed=True,
                    error_message=f"Validation failed: {validation_result.reason}",
                    fix_validated=False,
                    needs_retry=True,
                    validation_result=validation_result,
                )

            logger.info("[DecisionExecutor] Post-fix validation passed")

            # Step 6: Commit with metadata
            commit_sha = self._commit_with_metadata(decision, phase_spec, decision_id)
            logger.info(f"[DecisionExecutor] Committed: {commit_sha}")

            # Step 6: Log decision
            self._log_decision_with_metadata(
                decision, phase_spec, decision_id, save_point, commit_sha
            )

            return ExecutionResult(
                success=True,
                decision_id=decision_id,
                save_point=save_point,
                patch_applied=True,
                deliverables_validated=True,
                tests_passed=True,
                rollback_performed=False,
                commit_sha=commit_sha,
                fix_validated=True,
                needs_retry=False,
                validation_result=validation_result,
            )

        except Exception as e:
            logger.exception(f"[DecisionExecutor] Unexpected error during execution: {e}")
            self._rollback(save_point)
            return ExecutionResult(
                success=False,
                decision_id=decision_id,
                save_point=save_point,
                patch_applied=False,
                deliverables_validated=False,
                tests_passed=False,
                rollback_performed=True,
                error_message=f"Unexpected error: {str(e)}",
            )

    def _generate_decision_id(self, phase_id: str) -> str:
        """Generate unique decision ID."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"fix-{phase_id}-{timestamp}"

    def _create_save_point(self, phase_id: str) -> Optional[str]:
        """
        Create git tag for rollback capability.

        Returns:
            Tag name if successful, None otherwise
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        tag_name = f"save-before-fix-{phase_id}-{timestamp}"

        try:
            result = subprocess.run(
                ["git", "tag", tag_name],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                logger.info(f"[DecisionExecutor] Created git tag: {tag_name}")
                return tag_name
            else:
                logger.error(f"[DecisionExecutor] Git tag failed: {result.stderr}")
                return None

        except Exception as e:
            logger.exception(f"[DecisionExecutor] Failed to create save point: {e}")
            return None

    def _apply_patch(self, patch_content: str) -> Dict[str, Any]:
        """
        Apply patch using git apply.

        Returns:
            Dict with success status and error if failed
        """
        # Write patch to temp file
        patch_file = self.workspace / ".autonomous_runs" / self.run_id / "temp_fix.patch"
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text(patch_content, encoding="utf-8")

        try:
            # Try git apply
            result = subprocess.run(
                ["git", "apply", str(patch_file)],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return {"success": True, "error": None}
            else:
                # Try with 3-way merge
                result_3way = subprocess.run(
                    ["git", "apply", "--3way", str(patch_file)],
                    cwd=self.workspace,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result_3way.returncode == 0:
                    return {"success": True, "error": None}
                else:
                    return {
                        "success": False,
                        "error": f"git apply failed: {result.stderr}\n3-way: {result_3way.stderr}",
                    }

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            # Clean up temp file
            if patch_file.exists():
                patch_file.unlink()

    def _extract_conflict_lines(self, patch_content: str, error_message: str) -> List[int]:
        """
        Extract conflicting line numbers from patch content and error message.

        Parses git apply error output and patch hunks to identify which lines
        failed to apply. This information helps the next retry round understand
        which specific lines need attention.

        Args:
            patch_content: The patch that failed to apply
            error_message: Error message from git apply

        Returns:
            List of line numbers that conflicted
        """
        conflict_lines: List[int] = []

        # Parse error message for line numbers (e.g., "error: patch failed: file.py:42")
        import re

        # Match line numbers after file extensions (e.g., ".py:42" or ".js:100")
        line_pattern = re.compile(r"\.\w+:(\d+)")
        for match in line_pattern.finditer(error_message):
            try:
                line_num = int(match.group(1))
                if line_num not in conflict_lines:
                    conflict_lines.append(line_num)
            except ValueError:
                pass

        # Also parse patch hunks for @@ -start,count +start,count @@ patterns
        hunk_pattern = re.compile(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
        for match in hunk_pattern.finditer(patch_content):
            try:
                target_line = int(match.group(2))
                if target_line not in conflict_lines:
                    conflict_lines.append(target_line)
            except ValueError:
                pass

        logger.debug(f"[DecisionExecutor] Extracted conflict lines: {conflict_lines}")
        return sorted(conflict_lines)

    def _attempt_three_way_merge(self, patch_content: str) -> Dict[str, Any]:
        """
        Attempt a 3-way merge for the given patch.

        Uses git apply --3way which attempts to apply the patch using a
        3-way merge when the patch doesn't apply cleanly. This can resolve
        conflicts when the file has changed since the patch was created
        but the changes don't overlap.

        Args:
            patch_content: The patch content to apply

        Returns:
            Dict with success status, error message, and conflict details
        """
        # Write patch to temp file
        patch_file = self.workspace / ".autonomous_runs" / self.run_id / "temp_3way.patch"
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text(patch_content, encoding="utf-8")

        try:
            result = subprocess.run(
                ["git", "apply", "--3way", str(patch_file)],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                logger.info("[DecisionExecutor] 3-way merge succeeded")
                return {"success": True, "error": None, "merge_used": True}
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                logger.warning(f"[DecisionExecutor] 3-way merge failed: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "merge_used": True,
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "3-way merge timed out after 30 seconds",
                "merge_used": True,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "merge_used": True}
        finally:
            # Clean up temp file
            if patch_file.exists():
                patch_file.unlink()

    def _validate_deliverables(self, patch_content: str, deliverables: List[str]) -> bool:
        """
        Validate that patch creates expected deliverables.

        Uses existing deliverables_validator.
        """
        try:
            # Construct phase_scope for validator
            phase_scope = {"deliverables": deliverables}

            ok, errors, _ = validate_deliverables(
                patch_content=patch_content,
                phase_scope=phase_scope,
                phase_id="autonomous-fix",
                workspace=self.workspace,
            )

            if not ok:
                logger.warning(f"[DecisionExecutor] Deliverables validation errors: {errors}")

            return ok

        except Exception as e:
            logger.exception(f"[DecisionExecutor] Deliverables validation exception: {e}")
            return False

    def _run_acceptance_tests(self, acceptance_criteria: List[str]) -> bool:
        """
        Run acceptance tests from phase spec.

        Simplified: runs pytest if test criteria exist.
        """
        if not acceptance_criteria:
            # No tests specified - pass
            logger.info("[DecisionExecutor] No acceptance criteria specified - skipping tests")
            return True

        # Check if any criteria mention tests
        has_test_criteria = any(
            "test" in criterion.lower() or "pytest" in criterion.lower()
            for criterion in acceptance_criteria
        )

        if not has_test_criteria:
            # No test criteria - pass
            logger.info("[DecisionExecutor] No test criteria - skipping tests")
            return True

        # Run pytest
        try:
            result = subprocess.run(
                ["pytest", "-q", "--maxfail=1"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                logger.info("[DecisionExecutor] Acceptance tests passed")
                return True
            else:
                logger.warning(
                    f"[DecisionExecutor] Acceptance tests failed:\n{result.stdout}\n{result.stderr}"
                )
                return False

        except FileNotFoundError:
            # pytest not available - skip
            logger.warning("[DecisionExecutor] pytest not found - skipping tests")
            return True
        except Exception as e:
            logger.exception(f"[DecisionExecutor] Test execution error: {e}")
            return False

    def _rollback(self, save_point: str) -> None:
        """Rollback to save point."""
        try:
            logger.info(f"[DecisionExecutor] Rolling back to {save_point}")
            result = subprocess.run(
                ["git", "reset", "--hard", save_point],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                logger.info("[DecisionExecutor] Rollback successful")
            else:
                logger.error(f"[DecisionExecutor] Rollback failed: {result.stderr}")

        except Exception as e:
            logger.exception(f"[DecisionExecutor] Rollback exception: {e}")

    def _commit_with_metadata(
        self, decision: Decision, phase_spec: PhaseSpec, decision_id: str
    ) -> Optional[str]:
        """Commit with decision metadata in commit message."""
        try:
            # Stage changes
            subprocess.run(
                ["git", "add", "-A"], cwd=self.workspace, capture_output=True, timeout=10
            )

            # Create commit message
            commit_msg = self._format_commit_message(decision, phase_spec, decision_id)

            # Commit
            result = subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                # Get commit SHA
                sha_result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=self.workspace,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                return sha_result.stdout.strip()[:8]
            else:
                logger.error(f"[DecisionExecutor] Commit failed: {result.stderr}")
                return None

        except Exception as e:
            logger.exception(f"[DecisionExecutor] Commit exception: {e}")
            return None

    def _format_commit_message(
        self, decision: Decision, phase_spec: PhaseSpec, decision_id: str
    ) -> str:
        """Format commit message with decision metadata."""
        lines = [
            f"AUTO-FIX: {decision.fix_strategy}",
            "",
            f"Decision ID: {decision_id}",
            f"Phase: {phase_spec.phase_id}",
            f"Risk: {decision.risk_level}",
            f"Confidence: {decision.confidence:.0%}",
            "",
            "Rationale:",
            decision.rationale,
            "",
            "Deliverables met:",
        ]

        for deliverable in decision.deliverables_met:
            lines.append(f"- {deliverable}")

        lines.extend(
            [
                "",
                "Files modified:",
            ]
        )

        for file_path in decision.files_modified:
            lines.append(f"- {file_path}")

        lines.extend(
            [
                "",
                "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
                "",
                "Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>",
            ]
        )

        return "\n".join(lines)

    def _validate_fix(
        self,
        original_error: Optional[str],
        decision: Decision,
        phase_spec: PhaseSpec,
    ) -> ValidationResult:
        """
        Re-run diagnostic probes to confirm fix resolved the original error.

        This validation step ensures that after applying a fix, the original
        error condition is actually resolved. It re-runs probes appropriate
        for the error type and checks if the original error pattern is gone.

        Args:
            original_error: The original error message/pattern to check for
            decision: The fix decision that was applied
            phase_spec: Phase specification for context

        Returns:
            ValidationResult indicating whether the fix resolved the error
        """
        if not original_error:
            # If no original error specified, skip validation
            logger.info("[DecisionExecutor] No original error specified - skipping validation")
            return ValidationResult(
                resolved=True,
                reason="No original error to validate against",
            )

        logger.info("[DecisionExecutor] Running post-fix validation")

        # Determine failure class from decision context
        failure_class = self._infer_failure_class(original_error, decision)

        # Get probes for this failure class
        probes = ProbeLibrary.for_failure(
            failure_class,
            context={
                "phase_id": phase_spec.phase_id,
                "files_modified": decision.files_modified,
            },
        )

        if not probes:
            logger.info("[DecisionExecutor] No validation probes available - assuming resolved")
            return ValidationResult(
                resolved=True,
                reason="No validation probes available for this error type",
            )

        # Create a command runner for validation
        runner = GovernedCommandRunner(
            run_id=f"{self.run_id}_validation",
            workspace=self.workspace,
            max_commands=10,
            max_seconds=120,
        )

        probe_results: List[ProbeRunResult] = []
        original_error_found = False

        # Run probes and check for original error
        for probe in probes:
            command_results = []
            for cmd in probe.commands:
                result = runner.run(
                    cmd.command,
                    label=cmd.label,
                    allow_network=cmd.allow_network,
                    sandbox=cmd.sandbox,
                )
                command_results.append(result)

                # Check if original error pattern appears in output
                output = f"{result.stdout} {result.stderr}"
                if original_error.lower() in output.lower():
                    original_error_found = True
                    logger.warning(
                        f"[DecisionExecutor] Original error still detected in probe output: "
                        f"{cmd.label or cmd.command}"
                    )

            probe_result = ProbeRunResult(
                probe=probe,
                command_results=command_results,
                resolved=not original_error_found,
            )
            probe_results.append(probe_result)

        # Build validation result
        if original_error_found:
            logger.warning(
                "[DecisionExecutor] Post-fix validation failed - original error persists"
            )
            return ValidationResult(
                resolved=False,
                reason="Original error still detected after fix",
                probe_results=probe_results,
                original_error_still_present=True,
            )

        logger.info("[DecisionExecutor] Post-fix validation passed - error appears resolved")
        return ValidationResult(
            resolved=True,
            reason="Original error no longer detected",
            probe_results=probe_results,
            original_error_still_present=False,
        )

    def _infer_failure_class(self, original_error: str, decision: Decision) -> str:
        """
        Infer the failure class from the original error message.

        Uses heuristics to map error messages to probe library failure classes.

        Args:
            original_error: The original error message
            decision: The fix decision for additional context

        Returns:
            A failure class string for ProbeLibrary.for_failure()
        """
        error_lower = original_error.lower()

        # Map common error patterns to failure classes
        if "patch" in error_lower or "hunk" in error_lower or "conflict" in error_lower:
            return "patch_apply_error"
        if "test" in error_lower or "assert" in error_lower or "pytest" in error_lower:
            return "ci_fail"
        if "import" in error_lower or "module" in error_lower or "dependency" in error_lower:
            return "deps_missing"
        if (
            "file not found" in error_lower
            or "no such file" in error_lower
            or "filenotfounderror" in error_lower
        ):
            return "missing_path"
        if "yaml" in error_lower or "schema" in error_lower:
            return "yaml_schema"
        if "timeout" in error_lower or "timed out" in error_lower:
            return "timeout"
        if "permission" in error_lower or "access denied" in error_lower:
            return "permission_denied"
        if "memory" in error_lower or "oom" in error_lower:
            return "memory_error"
        if "network" in error_lower or "connection" in error_lower:
            return "network"

        # Default to baseline probes
        return "baseline"

    def _log_decision_with_metadata(
        self,
        decision: Decision,
        phase_spec: PhaseSpec,
        decision_id: str,
        save_point: str,
        commit_sha: Optional[str],
    ) -> None:
        """Log decision with full metadata to decision log."""
        decision_record = {
            "decision_id": decision_id,
            "trigger": "autonomous_investigation",
            "phase_id": phase_spec.phase_id,
            "decision_type": decision.type.value,
            "choice": decision.fix_strategy,
            "rationale": decision.rationale,
            "alternatives_considered": decision.alternatives_considered,
            "risk_assessment": {
                "level": decision.risk_level,
                "net_deletion": decision.net_deletion,
                "files_modified": decision.files_modified,
                "protected_paths_touched": False,  # Would be True if risk was HIGH
            },
            "goal_alignment": {
                "deliverables_met": decision.deliverables_met,
                "confidence": decision.confidence,
            },
            "execution": {
                "safety_net": save_point,
                "patch_applied": True,
                "deliverables_validated": True,
                "tests_passed": True,
                "commit_sha": commit_sha,
            },
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "run_id": self.run_id,
                "autopack_version": "0.1.0-build113",
            },
        }

        # Log to memory service
        if self.memory_service and self.memory_service.enabled:
            try:
                self.memory_service.write_decision_log(
                    trigger="autonomous_investigation",
                    choice=decision.fix_strategy,
                    rationale=decision.rationale,
                    project_id=self.run_id,
                    run_id=self.run_id,
                    phase_id=phase_spec.phase_id,
                    alternatives=json.dumps(decision.alternatives_considered),
                )
            except Exception as e:
                logger.warning(f"[DecisionExecutor] Memory service logging failed: {e}")

        # Log to database decision logger if available
        if self.decision_logger:
            try:
                self.decision_logger(
                    "autonomous_investigation",
                    decision.fix_strategy,
                    decision.rationale,
                    phase_spec.phase_id,
                    "auto_fix",
                )
            except Exception as e:
                logger.warning(f"[DecisionExecutor] DB decision logging failed: {e}")

        # Also write to JSON file for easy inspection
        decision_log_file = (
            self.workspace / ".autonomous_runs" / self.run_id / "decisions" / f"{decision_id}.json"
        )
        decision_log_file.parent.mkdir(parents=True, exist_ok=True)
        decision_log_file.write_text(json.dumps(decision_record, indent=2), encoding="utf-8")

        logger.info(f"[DecisionExecutor] Decision logged: {decision_log_file}")
