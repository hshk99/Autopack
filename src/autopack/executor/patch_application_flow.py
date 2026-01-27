"""Patch application flow for phase execution.

Extracted from autonomous_executor.py as part of PR-EXE-11.
Handles patch application with structured edits or regular patches, including
YAML validation, goal drift checks, and governance requests.
"""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from autopack.autonomous_executor import AutonomousExecutor
    from autopack.llm_client import BuilderResult

from autopack.governed_apply import GovernedApplyPath
from autopack.memory import should_block_on_drift
from autopack.validators import validate_docker_compose, validate_yaml_syntax

logger = logging.getLogger(__name__)


class PatchApplicationFlow:
    """Orchestrates patch application for phase execution.

    Responsibilities:
    1. Apply structured edits (Stage 2) or regular patches
    2. Validate YAML/Docker Compose files pre-apply
    3. Check for goal drift before applying changes
    4. Handle governance requests for protected paths
    5. Write phase summary with apply stats
    """

    def __init__(self, executor: "AutonomousExecutor"):
        """Initialize with reference to parent executor.

        Args:
            executor: Parent AutonomousExecutor instance for accessing:
                - workspace: Workspace root path
                - run_type: Type of run (project_build, maintenance, etc.)
                - run_layout: For writing phase summaries
                - _run_goal_anchor: Goal anchor for drift detection
                - _try_handle_governance_request(): Governance flow handler
                - _update_phase_status(): Phase status updater
        """
        self.executor = executor
        self.workspace = executor.workspace
        self.run_type = executor.run_type
        self.run_layout = executor.run_layout

    def apply_patch_with_validation(
        self,
        phase_id: str,
        phase: Dict,
        builder_result: "BuilderResult",
        file_context: Optional[Dict],
        allowed_paths: Optional[List[str]] = None,
    ) -> Tuple[bool, str, Optional[Dict]]:
        """Apply patch with pre-validation and governance checks.

        Main entry point for patch application. Handles both structured edits
        and regular patches.

        Args:
            phase_id: Unique phase identifier
            phase: Phase specification dict
            builder_result: BuilderResult with patch_content or edit_plan
            file_context: Repository file context for structured edits
            allowed_paths: Optional list of allowed file paths

        Returns:
            Tuple of (success: bool, error_msg: str, apply_stats: dict)
            apply_stats contains mode, operation counts, touched paths, etc.
        """
        logger.info(f"[{phase_id}] Step 2/5: Applying patch...")

        # Check if this is a structured edit (Stage 2) or regular patch
        if builder_result.edit_plan:
            return self._apply_structured_edits(phase_id, phase, builder_result, file_context)
        else:
            return self._apply_regular_patch(phase_id, phase, builder_result, allowed_paths)

    def _apply_structured_edits(
        self,
        phase_id: str,
        phase: Dict,
        builder_result: "BuilderResult",
        file_context: Optional[Dict],
    ) -> Tuple[bool, str, Optional[Dict]]:
        """Apply structured edit plan (Stage 2).

        Args:
            phase_id: Phase identifier
            phase: Phase spec
            builder_result: BuilderResult with edit_plan
            file_context: Repository file context

        Returns:
            Tuple of (success, error_msg, apply_stats)
        """
        from autopack.structured_edits import StructuredEditApplicator

        ops_planned = len(builder_result.edit_plan.operations)
        touched_paths = sorted(
            {
                getattr(op, "file_path", "")
                for op in builder_result.edit_plan.operations
                if getattr(op, "file_path", "")
            }
        )
        logger.info(f"[{phase_id}] Applying structured edit plan with {ops_planned} operations")

        # Get file contents from context
        file_contents = {}
        if file_context:
            file_contents = file_context.get("existing_files", {})

        # Apply structured edits
        applicator = StructuredEditApplicator(workspace=Path(self.workspace))
        edit_result = applicator.apply_edit_plan(
            plan=builder_result.edit_plan, file_contents=file_contents, dry_run=False
        )

        if not edit_result.success:
            error_msg = (
                edit_result.error_message or f"{edit_result.operations_failed} operations failed"
            )
            logger.error(f"[{phase_id}] Failed to apply structured edits: {error_msg}")
            self.executor._update_phase_status(phase_id, "FAILED")
            return False, "STRUCTURED_EDIT_FAILED", None

        logger.info(
            f"[{phase_id}] Structured edits applied successfully ({edit_result.operations_applied} operations)"
        )

        apply_stats = {
            "mode": "structured_edit",
            "operations_planned": ops_planned,
            "operations_applied": int(edit_result.operations_applied or 0),
            "operations_failed": int(edit_result.operations_failed or 0),
            "touched_paths_count": len(touched_paths),
            "touched_paths": touched_paths[:50],  # cap for logs/summaries
        }

        apply_stats_lines = [
            "Apply mode: structured_edit",
            f"Operations planned: {apply_stats['operations_planned']}",
            f"Operations applied: {apply_stats['operations_applied']}",
            f"Operations failed: {apply_stats['operations_failed']}",
            f"Touched paths (count): {apply_stats['touched_paths_count']}",
        ]

        # Write phase summary
        self._write_phase_summary(phase_id, phase, apply_stats_lines)

        return True, "", apply_stats

    def _apply_regular_patch(
        self,
        phase_id: str,
        phase: Dict,
        builder_result: "BuilderResult",
        allowed_paths: Optional[List[str]],
    ) -> Tuple[bool, str, Optional[Dict]]:
        """Apply regular git diff patch to filesystem.

        Args:
            phase_id: Phase identifier
            phase: Phase spec
            builder_result: BuilderResult with patch_content
            allowed_paths: Allowed file paths

        Returns:
            Tuple of (success, error_msg, apply_stats)
        """
        patch_content = builder_result.patch_content or ""

        # Pre-apply YAML validation
        yaml_valid, yaml_error = self._validate_yaml_in_patch(phase_id, patch_content)
        if not yaml_valid:
            self.executor._update_phase_status(phase_id, "FAILED")
            return False, yaml_error or "YAML_VALIDATION_FAILED", None

        # Goal drift check
        drift_blocked, drift_error = self._check_goal_drift(phase_id, phase)
        if drift_blocked:
            self.executor._update_phase_status(phase_id, "FAILED")
            return False, drift_error or "GOAL_DRIFT_BLOCKED", None

        # Derive allowed_paths from deliverables if not provided
        if not allowed_paths:
            allowed_paths = self._derive_allowed_paths_from_deliverables(phase_id, phase)

        # Extract scope paths
        scope_config = phase.get("scope")
        scope_paths = scope_config.get("paths", []) if scope_config else []

        # Enable internal mode for maintenance run types
        is_maintenance_run = self.run_type in [
            "autopack_maintenance",
            "autopack_upgrade",
            "self_repair",
        ]

        # Apply patch with governance
        governed_apply = GovernedApplyPath(
            workspace=Path(self.workspace),
            run_type=self.run_type,
            autopack_internal_mode=is_maintenance_run,
            scope_paths=scope_paths,
            allowed_paths=allowed_paths or None,
        )

        patch_success, error_msg = governed_apply.apply_patch(patch_content, full_file_mode=True)

        patch_len = len(patch_content)
        apply_stats = {
            "mode": "patch",
            "patch_nonempty": bool(patch_content.strip()),
            "patch_bytes": patch_len,
        }

        apply_stats_lines = [
            "Apply mode: patch",
            f"Patch non-empty: {apply_stats['patch_nonempty']}",
            f"Patch bytes: {apply_stats['patch_bytes']}",
        ]

        if not patch_success:
            # Check if this is a governance request
            governance_handled = self.executor._try_handle_governance_request(
                phase_id, error_msg, patch_content, governed_apply
            )

            if governance_handled:
                # Governance flow succeeded
                logger.info(f"[{phase_id}] Governance request approved, patch applied")
            else:
                # Regular patch failure or governance denied
                logger.error(f"[{phase_id}] Failed to apply patch to filesystem: {error_msg}")
                self.executor._update_phase_status(phase_id, "FAILED")
                return False, "PATCH_FAILED", apply_stats
        else:
            logger.info(f"[{phase_id}] Patch applied successfully to filesystem")

        # Write phase summary
        self._write_phase_summary(phase_id, phase, apply_stats_lines)

        return True, "", apply_stats

    def _validate_yaml_in_patch(
        self, phase_id: str, patch_content: str
    ) -> Tuple[bool, Optional[str]]:
        """Validate YAML/Docker Compose files in patch before applying.

        Args:
            phase_id: Phase identifier for logging
            patch_content: Patch content to validate

        Returns:
            Tuple of (valid: bool, error_msg: Optional[str])
        """
        if not any(keyword in patch_content.lower() for keyword in [".yaml", ".yml", "compose"]):
            return True, None

        try:
            # Extract YAML content from patch (look for full-file JSON)
            try:
                parsed = json.loads(patch_content)
                if isinstance(parsed, dict) and "files" in parsed:
                    for file_entry in parsed.get("files", []):
                        file_path = file_entry.get("path", "")
                        if file_path.endswith((".yaml", ".yml")):
                            content = file_entry.get("content", "")

                            # Choose validator based on file type
                            if "compose" in file_path.lower() or "docker" in file_path.lower():
                                result = validate_docker_compose(content, file_path)
                            else:
                                result = validate_yaml_syntax(content, file_path)

                            if not result.valid:
                                logger.error(
                                    f"[{phase_id}] YAML validation failed for {file_path}: {result.errors}"
                                )
                                return False, f"YAML validation failed for {file_path}"
                            elif result.warnings:
                                logger.warning(
                                    f"[{phase_id}] YAML warnings for {file_path}: {result.warnings}"
                                )
            except json.JSONDecodeError:
                # Not JSON format, skip validation
                pass
        except Exception as yaml_e:
            logger.warning(f"[{phase_id}] YAML validation check failed: {yaml_e}")

        return True, None

    def _check_goal_drift(self, phase_id: str, phase: Dict) -> Tuple[bool, Optional[str]]:
        """Check if change drifts from run's goal anchor.

        Args:
            phase_id: Phase identifier for logging
            phase: Phase specification

        Returns:
            Tuple of (should_block: bool, error_msg: Optional[str])
        """
        goal_anchor = getattr(self.executor, "_run_goal_anchor", None)
        if not goal_anchor:
            return False, None

        change_intent = phase.get("description", "")[:200]
        should_block, drift_message = should_block_on_drift(goal_anchor, change_intent)

        if should_block:
            logger.error(f"[{phase_id}] {drift_message}")
            return True, drift_message
        elif "ADVISORY" in drift_message:
            logger.warning(f"[{phase_id}] {drift_message}")

        return False, None

    def _derive_allowed_paths_from_deliverables(
        self, phase_id: str, phase: Dict
    ) -> Optional[List[str]]:
        """Derive allowed root prefixes from deliverables.

        Critical for research phases that create files under protected roots
        like src/autopack/research/*.

        Args:
            phase_id: Phase identifier for logging
            phase: Phase specification

        Returns:
            List of allowed path prefixes, or None if derivation fails
        """
        try:
            from autopack.executor.deliverables_validator import (
                extract_deliverables_from_scope,
            )

            scope_config = phase.get("scope")
            expected_paths = extract_deliverables_from_scope(scope_config or {})
            expected_set = {p for p in expected_paths if isinstance(p, str)}

            derived_allowed: List[str] = []
            for root in (
                "src/autopack/research/",
                "src/autopack/cli/",
                "tests/research/",
                "docs/research/",
            ):
                if any(p.startswith(root) for p in expected_set):
                    derived_allowed.append(root)

            if derived_allowed:
                return derived_allowed
        except Exception as e:
            logger.debug(f"[{phase_id}] Failed to derive allowed_paths from deliverables: {e}")

        return None

    def _write_phase_summary(
        self, phase_id: str, phase: Dict, apply_stats_lines: Optional[List[str]]
    ):
        """Write apply stats to phase summary markdown.

        Best-effort, non-blocking operation for forensic review.

        Args:
            phase_id: Phase identifier
            phase: Phase specification
            apply_stats_lines: List of summary lines to write
        """
        try:
            phase_index = int(phase.get("phase_index", 0) or 0)
            self.run_layout.write_phase_summary(
                phase_index=phase_index,
                phase_id=phase_id,
                phase_name=str(phase.get("name") or phase_id),
                state="EXECUTING",
                task_category=phase.get("task_category"),
                complexity=phase.get("complexity"),
                execution_lines=apply_stats_lines or None,
            )
        except Exception:
            # Non-blocking: phase summaries are best-effort
            pass
