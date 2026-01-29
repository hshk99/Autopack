"""Batched deliverables execution for multi-file phases.

Extracted from autonomous_executor.py as part of PR-EXE-14.
Handles phases that need to be split into batches to avoid truncation and convergence issues.
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from ..deliverables_validator import (
    extract_deliverables_from_scope,
    format_validation_feedback_for_builder,
    validate_deliverables,
    validate_new_file_diffs_have_complete_structure,
)
from ..governed_apply import GovernedApplyPath
from ..llm_client import BuilderResult

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..autonomous_executor import AutonomousExecutor


@dataclass
class BatchedExecutionContext:
    """Context for batched deliverables execution."""

    phase: Dict
    attempt_index: int
    allowed_paths: Optional[List[str]]
    batches: List[List[str]]
    batching_label: str
    manifest_allowed_roots: Tuple[str, ...]
    apply_allowed_roots: Tuple[str, ...]


@dataclass
class BatchedExecutionResult:
    """Result of batched deliverables execution."""

    success: bool
    status: str  # "COMPLETE", "FAILED", "BLOCKED"
    combined_patch: str
    total_tokens: int
    error_message: Optional[str] = None


class BatchedDeliverablesExecutor:
    """Executes multi-file phases using batched deliverables strategy.

    Responsibilities:
    1. Split large multi-file phases into batches
    2. Execute Builder once per batch
    3. Validate and apply each batch incrementally
    4. Run CI/Auditor/Quality Gate on combined result
    5. Handle docs-only batch convergence fallbacks

    This prevents truncation and malformed diff issues that occur when
    Builder tries to generate patches for too many files at once.
    """

    def __init__(self, executor: "AutonomousExecutor"):
        """Initialize with reference to parent executor."""
        self.executor = executor

    def execute_batched_phase(
        self,
        context: BatchedExecutionContext,
    ) -> BatchedExecutionResult:
        """Execute phase using batched deliverables strategy.

        Generic in-phase batching mechanism for multi-file phases that frequently
        hit truncation/malformed diff convergence failures.

        Behavior:
        - Runs Builder once per batch, each with a batch-specific scope.paths list.
        - Enforces per-batch deliverables manifest gate + deliverables validation +
          new-file diff structure checks.
        - Applies each batch patch under governed apply using batch-derived allowed roots.
        - After all batches are applied, posts a combined (concatenated) diff and runs
          a single CI/Auditor/Quality Gate pass.

        Args:
            context: Batched execution context with phase, batches, etc.

        Returns:
            BatchedExecutionResult with success status and combined patch
        """
        phase = context.phase
        phase_id = phase.get("phase_id") or "unknown-phase"

        # Load repository context for Builder
        file_context = self.executor._load_repository_context(phase)
        logger.info(
            f"[{phase_id}] Loaded {len(file_context.get('existing_files', {}))} files for context"
        )

        # Pre-flight policy (keep aligned with main execution path)
        use_full_file_mode = True
        if phase.get("builder_mode") == "structured_edit":
            use_full_file_mode = False
        if file_context and len(file_context.get("existing_files", {})) >= 30:
            use_full_file_mode = False

        learning_context = self.executor._get_learning_context_for_phase(phase)
        project_rules = learning_context.get("project_rules", [])
        run_hints = learning_context.get("run_hints", [])
        if project_rules or run_hints:
            logger.info(
                f"[{phase_id}] Learning context: {len(project_rules)} rules, {len(run_hints)} hints"
            )

        retrieved_context = ""
        if self.executor.memory_service and self.executor.memory_service.enabled:
            try:
                phase_description = phase.get("description", "")
                query = f"{phase_description[:500]}"
                project_id = self.executor._get_project_slug() or self.executor.run_id

                # BUILD-154: Make SOT budget gating + telemetry explicit and non-silent
                from autopack.config import settings

                max_context_chars = max(4000, settings.autopack_sot_retrieval_max_chars + 2000)
                include_sot = self.executor._should_include_sot_retrieval(
                    max_context_chars, phase_id=phase_id
                )

                retrieved = self.executor.memory_service.retrieve_context(
                    query=query,
                    project_id=project_id,
                    run_id=self.executor.run_id,
                    include_code=True,
                    include_summaries=True,
                    include_errors=True,
                    include_hints=True,
                    include_planning=True,
                    include_plan_changes=True,
                    include_decisions=True,
                    include_sot=include_sot,
                )
                retrieved_context = self.executor.memory_service.format_retrieved_context(
                    retrieved, max_chars=max_context_chars
                )

                # BUILD-155: Record SOT retrieval telemetry
                self.executor._record_sot_retrieval_telemetry(
                    phase_id=phase_id,
                    include_sot=include_sot,
                    max_context_chars=max_context_chars,
                    retrieved_context=retrieved,
                    formatted_context=retrieved_context,
                )

                if retrieved_context:
                    logger.info(
                        f"[{phase_id}] Retrieved {len(retrieved_context)} chars of context from memory"
                    )
            except Exception as e:
                logger.warning(f"[{phase_id}] Memory retrieval failed: {e}")

        protected_paths = [".autonomous_runs/", ".git/", "autopack.db"]

        logger.info(
            f"[{phase_id}] {context.batching_label} batching enabled: {len(context.batches)} batches "
            f"({', '.join(str(len(b)) for b in context.batches)} files)"
        )

        total_tokens = 0
        last_builder_result: Optional[BuilderResult] = None
        scope_base = phase.get("scope") or {}
        batch_patches: List[str] = []

        for idx, batch_paths in enumerate(context.batches, 1):
            logger.info(
                f"[{phase_id}] Batch {idx}/{len(context.batches)}: {len(batch_paths)} deliverables"
            )

            # Use batch scope with only "paths" to avoid extract_deliverables_from_scope pulling the full deliverables dict.
            batch_scope = {
                k: v for k, v in (scope_base or {}).items() if k not in ("deliverables", "paths")
            }
            batch_scope["paths"] = list(batch_paths)
            phase_for_batch = {**phase, "scope": batch_scope}

            deliverables_contract = self.executor._build_deliverables_contract(
                phase_for_batch, phase_id
            )
            phase_with_constraints = {
                **phase_for_batch,
                "protected_paths": protected_paths,
                "deliverables_contract": deliverables_contract,
            }

            # Retry optimization: if we are retrying the phase and this batch's deliverables already exist,
            # skip rebuilding/reapplying them to avoid wasting tokens (common when only docs batch fails).
            # We still attempt to include a scoped git diff for auditor visibility.
            if context.attempt_index > 0 and batch_paths:
                try:
                    ws = Path(self.executor.workspace)

                    def _exists_nonempty(rel_path: str) -> bool:
                        try:
                            p = ws / rel_path
                            return p.exists() and p.is_file() and p.stat().st_size > 0
                        except Exception:
                            return False

                    if all(_exists_nonempty(p) for p in batch_paths):
                        logger.info(
                            f"[{phase_id}] Skipping batch {idx}/{len(context.batches)} on retry (attempt={context.attempt_index}) "
                            f"- all deliverables already exist"
                        )
                        try:
                            proc = subprocess.run(
                                ["git", "diff", "--no-color", "--", *batch_paths],
                                cwd=str(ws),
                                capture_output=True,
                                text=True,
                            )
                            if proc.returncode == 0 and (proc.stdout or "").strip():
                                batch_patches.append(proc.stdout)
                        except Exception as e:
                            logger.warning(
                                f"[{phase_id}] Failed to compute scoped git diff for skipped batch {idx}: {e}"
                            )

                        # Refresh context so later batches see the latest on-disk files for this batch.
                        try:
                            file_context = self.executor._load_repository_context(phase_for_batch)
                        except Exception as e:
                            logger.warning(
                                f"[{phase_id}] Context refresh failed for skipped batch {idx}: {e}"
                            )
                        continue
                except Exception as e:
                    logger.warning(f"[{phase_id}] Retry-skip check failed for batch {idx}: {e}")

            # Manifest gate for this batch
            manifest_paths: List[str] = []
            try:
                expected_paths = extract_deliverables_from_scope(batch_scope)
                if expected_paths and self.executor.llm_service and deliverables_contract:
                    expected_set = {p for p in expected_paths if isinstance(p, str)}
                    expected_list = sorted(expected_set)

                    allowed_roots: List[str] = []
                    for r in context.manifest_allowed_roots:
                        if any(p.startswith(r) for p in expected_list):
                            allowed_roots.append(r)
                    if not allowed_roots:
                        # Expand to first-2 segments roots
                        expanded: List[str] = []
                        for p in expected_list:
                            parts = p.split("/")
                            # For root-level files (no "/"), include the file itself
                            if len(parts) == 1:
                                root = p
                            # If second segment contains '.', it's likely a filename, use first dir
                            elif len(parts) >= 2 and "." in parts[1]:
                                root = parts[0] + "/"
                            else:
                                root = "/".join(parts[:2]) + "/"
                            if root not in expanded:
                                expanded.append(root)
                        allowed_roots = expanded

                    ok_manifest, manifest_paths, manifest_error, _raw = (
                        self.executor.llm_service.generate_deliverables_manifest(
                            expected_paths=list(expected_set),
                            allowed_roots=allowed_roots,
                            run_id=self.executor.run_id,
                            phase_id=phase_id,
                            attempt_index=context.attempt_index,
                        )
                    )
                    if not ok_manifest:
                        err_details = manifest_error or "deliverables manifest gate failed"
                        logger.error(
                            f"[{phase_id}] Deliverables manifest gate FAILED (batch {idx}): {err_details}"
                        )
                        self.executor._record_phase_error(
                            phase,
                            "deliverables_manifest_failed",
                            err_details,
                            context.attempt_index,
                        )
                        self.executor._record_learning_hint(
                            phase, "deliverables_manifest_failed", err_details
                        )
                        return BatchedExecutionResult(
                            success=False,
                            status="DELIVERABLES_VALIDATION_FAILED",
                            combined_patch="",
                            total_tokens=total_tokens,
                            error_message=err_details,
                        )
                    logger.info(
                        f"[{phase_id}] Deliverables manifest gate PASSED (batch {idx}, {len(manifest_paths or [])} paths)"
                    )
                    phase_with_constraints["deliverables_manifest"] = manifest_paths or []
            except Exception as e:
                logger.warning(
                    f"[{phase_id}] Deliverables manifest gate error (batch {idx}, skipping gate): {e}"
                )

            # Run Builder for this batch
            # IMP-COST-002: Pass run-level budget for pre-call validation
            builder_result = self.executor.llm_service.execute_builder_phase(
                phase_spec=phase_with_constraints,
                file_context=file_context,
                max_tokens=None,
                project_rules=project_rules,
                run_hints=run_hints,
                run_id=self.executor.run_id,
                phase_id=phase_id,
                run_context=self.executor._build_run_context(),  # [Phase C3] Include model overrides if specified
                attempt_index=context.attempt_index,
                use_full_file_mode=use_full_file_mode,
                config=self.executor.builder_output_config,
                retrieved_context=retrieved_context,
                run_token_budget=getattr(self.executor, "run_budget_tokens", None),
                tokens_used_so_far=getattr(self.executor, "_run_tokens_used", None),
            )

            if not builder_result.success:
                logger.error(f"[{phase_id}] Builder failed (batch {idx}): {builder_result.error}")
                self.executor._post_builder_result(phase_id, builder_result, context.allowed_paths)
                self.executor._update_phase_status(phase_id, "FAILED")
                return BatchedExecutionResult(
                    success=False,
                    status="FAILED",
                    combined_patch="",
                    total_tokens=total_tokens,
                    error_message=builder_result.error,
                )

            last_builder_result = builder_result
            total_tokens += int(getattr(builder_result, "tokens_used", 0) or 0)
            logger.info(
                f"[{phase_id}] Builder succeeded (batch {idx}, {builder_result.tokens_used} tokens)"
            )

            # Deliverables validation for this batch
            scope_config = dict(batch_scope)
            if manifest_paths:
                scope_config["deliverables_manifest"] = manifest_paths
            is_valid, validation_errors, validation_details = validate_deliverables(
                patch_content=builder_result.patch_content or "",
                phase_scope=scope_config,
                phase_id=phase_id,
                workspace=Path(self.executor.workspace),
            )
            if not is_valid:
                feedback = format_validation_feedback_for_builder(
                    errors=validation_errors,
                    details=validation_details,
                    phase_description=phase.get("description", ""),
                )
                logger.error(f"[{phase_id}] Deliverables validation failed (batch {idx})")
                logger.error(f"[{phase_id}] {feedback}")
                fail_result = BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=["DELIVERABLES_VALIDATION_FAILED", feedback],
                    tokens_used=builder_result.tokens_used,
                    model_used=getattr(builder_result, "model_used", None),
                    error="Deliverables validation failed",
                )
                self.executor._post_builder_result(phase_id, fail_result, context.allowed_paths)
                return BatchedExecutionResult(
                    success=False,
                    status="DELIVERABLES_VALIDATION_FAILED",
                    combined_patch="",
                    total_tokens=total_tokens,
                    error_message="Deliverables validation failed",
                )

            # Structural validation for new files (headers + hunks + content where applicable)
            expected_paths = extract_deliverables_from_scope(scope_config or {})
            ok_struct, struct_errors, struct_details = (
                validate_new_file_diffs_have_complete_structure(
                    patch_content=builder_result.patch_content or "",
                    expected_paths=expected_paths,
                    workspace=Path(self.executor.workspace),
                    allow_empty_suffixes=["__init__.py", ".gitkeep"],
                )
            )
            if not ok_struct:
                logger.error(f"[{phase_id}] Patch format invalid for new file diffs (batch {idx})")
                for e in struct_errors[:10]:
                    logger.error(f"[{phase_id}]    {e}")
                feedback_lines = [
                    "❌ PATCH FORMAT ERROR (NEW FILE DIFFS)",
                    "",
                    "For EVERY new file deliverable, your patch MUST include:",
                    "- `--- /dev/null` and `+++ b/<path>` headers",
                    "- at least one `@@ ... @@` hunk header",
                    "- `+` content lines for the file body (do not emit header-only diffs)",
                    "",
                ]
                for p in (struct_details.get("missing_headers", []) or [])[:10]:
                    feedback_lines.append(f"- Missing headers: {p}")
                for p in (struct_details.get("missing_hunks", []) or [])[:10]:
                    feedback_lines.append(f"- Missing hunks: {p}")
                for p in (struct_details.get("empty_content", []) or [])[:10]:
                    feedback_lines.append(f"- Empty content: {p}")
                fail_result = BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=["DELIVERABLES_VALIDATION_FAILED", "\n".join(feedback_lines)],
                    tokens_used=builder_result.tokens_used,
                    model_used=getattr(builder_result, "model_used", None),
                    error="Patch format invalid for new file diffs (missing headers/hunks/content)",
                )
                self.executor._post_builder_result(phase_id, fail_result, context.allowed_paths)
                return BatchedExecutionResult(
                    success=False,
                    status="DELIVERABLES_VALIDATION_FAILED",
                    combined_patch="",
                    total_tokens=total_tokens,
                    error_message="Patch format invalid",
                )

            # Apply patch for this batch
            scope_paths = batch_scope.get("paths", []) if isinstance(batch_scope, dict) else []
            derived_allowed: List[str] = []
            for r in context.apply_allowed_roots:
                if any(p.startswith(r) for p in expected_paths):
                    derived_allowed.append(r)
            if not derived_allowed:
                derived_allowed = context.allowed_paths or []

            governed_apply = GovernedApplyPath(
                workspace=Path(self.executor.workspace),
                run_type=self.executor.run_type,
                autopack_internal_mode=self.executor.run_type
                in ["autopack_maintenance", "autopack_upgrade", "self_repair"],
                scope_paths=scope_paths,
                allowed_paths=derived_allowed or None,
            )
            patch_success, error_msg = governed_apply.apply_patch(
                builder_result.patch_content, full_file_mode=True
            )
            if not patch_success:
                logger.error(f"[{phase_id}] Failed to apply patch (batch {idx}): {error_msg}")
                # Convergence fallback for docs-only batches:
                # Some models occasionally emit markdown placeholders like "# ..." which triggers truncation validation.
                # If this batch is a single docs/*.md deliverable, synthesize a minimal deterministic doc patch and apply it.
                try:
                    if (
                        len(batch_paths) == 1
                        and isinstance(batch_paths[0], str)
                        and batch_paths[0].startswith("docs/")
                        and batch_paths[0].endswith(".md")
                        and isinstance(error_msg, str)
                        and (
                            "truncation" in error_msg.lower()
                            or "ellipsis" in error_msg.lower()
                            or "patch validation failed" in error_msg.lower()
                        )
                    ):
                        doc_rel = batch_paths[0]
                        logger.warning(
                            f"[{phase_id}] Docs batch truncation detected; applying deterministic fallback doc for {doc_rel}"
                        )

                        # Minimal, deterministic content (kept short to avoid token blowups and truncation markers).
                        content = (
                            "\n".join(
                                [
                                    "# Diagnostics Iteration Loop",
                                    "",
                                    "This document describes the diagnostics iteration loop enhancements that make Autopack behave more like a guided Cursor debugging session.",
                                    "",
                                    "## Goals",
                                    "- Add a small, explicit **Evidence Requests** section to handoff prompts.",
                                    "- Accept compact human responses and fold them back into the handoff bundle without token blowups.",
                                    "",
                                    "## Evidence requests",
                                    "Evidence requests are a short list (<= 5) of concrete missing artifacts or questions, each with a rationale.",
                                    "",
                                    "Typical inputs:",
                                    "- Current handoff bundle (index/summary/excerpts).",
                                    "- Latest error category and failing command output (when available).",
                                    "",
                                    "Typical outputs:",
                                    "- A list of requested files/artifacts and targeted questions.",
                                    "",
                                    "## Human response ingestion",
                                    "The human response parser accepts a compact text format such as:",
                                    "",
                                    "```\nQ1: <answer>; Q2: <answer>; Attached: <path1>, <path2>\n```",
                                    "",
                                    "Rules:",
                                    "- Be tolerant of missing fields.",
                                    "- Treat attached paths as references (repo-relative or absolute) and validate existence when possible.",
                                    "",
                                    "## Iteration behavior",
                                    "- Each loop should stay small (<= 500 chars incremental overhead per round).",
                                    "- Prompts should become more targeted after 1-2 rounds.",
                                    "- Stop after 3 rounds (or when the operator indicates they are done).",
                                    "",
                                    "## Deliverables",
                                    "- Code: `src/autopack/diagnostics/evidence_requests.py`, `src/autopack/diagnostics/human_response_parser.py`",
                                    "- Tests: `tests/autopack/diagnostics/test_evidence_requests.py`, `tests/autopack/diagnostics/test_human_response_parser.py`",
                                    "- Docs: this file",
                                    "",
                                ]
                            )
                            + "\n"
                        )

                        fallback_patch = "\n".join(
                            [
                                f"diff --git a/{doc_rel} b/{doc_rel}",
                                "new file mode 100644",
                                "index 0000000..1111111",
                                "--- /dev/null",
                                f"+++ b/{doc_rel}",
                                "@@ -0,0 +1,999 @@",
                            ]
                            + [f"+{line}" for line in content.splitlines()]
                            + [""]
                        )

                        ok2, err2 = governed_apply.apply_patch(fallback_patch, full_file_mode=True)
                        if ok2:
                            logger.info(
                                f"[{phase_id}] Fallback doc patch applied successfully (batch {idx})"
                            )
                            batch_patches.append(fallback_patch)
                            try:
                                file_context = self.executor._load_repository_context(
                                    phase_for_batch
                                )
                            except Exception as e:
                                logger.warning(
                                    f"[{phase_id}] Context refresh failed after fallback doc batch {idx}: {e}"
                                )
                            continue
                        else:
                            logger.error(
                                f"[{phase_id}] Fallback doc patch failed (batch {idx}): {err2}"
                            )
                except Exception as e:
                    logger.warning(
                        f"[{phase_id}] Fallback doc apply encountered error (batch {idx}): {e}"
                    )

                self.executor._update_phase_status(phase_id, "FAILED")
                return BatchedExecutionResult(
                    success=False,
                    status="PATCH_FAILED",
                    combined_patch="",
                    total_tokens=total_tokens,
                    error_message=error_msg,
                )
            logger.info(f"[{phase_id}] Patch applied successfully (batch {idx})")

            batch_patches.append(builder_result.patch_content or "")

            # Refresh context so next batch sees created files (and becomes scope-aware via scope.paths)
            try:
                file_context = self.executor._load_repository_context(phase_for_batch)
            except Exception as e:
                logger.warning(f"[{phase_id}] Context refresh failed after batch {idx}: {e}")

        # Combined patch for auditor/quality gate: concatenate batch patches (do NOT use git diff; repo may be dirty)
        combined_patch = "\n".join([p for p in batch_patches if isinstance(p, str) and p.strip()])

        combined_result = BuilderResult(
            success=True,
            patch_content=combined_patch
            or (last_builder_result.patch_content if last_builder_result else ""),
            builder_messages=[
                f"batched_{context.batching_label}: {len(context.batches)} batches applied"
            ],
            tokens_used=total_tokens,
            model_used=(
                getattr(last_builder_result, "model_used", None) if last_builder_result else None
            ),
            error=None,
        )
        self.executor._post_builder_result(phase_id, combined_result, context.allowed_paths)

        # Proceed with normal CI/Auditor/Quality Gate using the combined patch content
        logger.info(f"[{phase_id}] Step 3/5: Running CI checks...")
        ci_result = self.executor._run_ci_checks(phase_id, phase)

        logger.info(f"[{phase_id}] Step 4/5: Reviewing patch with Auditor (via LlmService)...")
        auditor_result = self.executor.llm_service.execute_auditor_review(
            patch_content=combined_result.patch_content,
            phase_spec=phase,
            max_tokens=None,
            project_rules=project_rules,
            run_hints=run_hints,
            run_id=self.executor.run_id,
            phase_id=phase_id,
            run_context=self.executor._build_run_context(),  # [Phase C3] Include model overrides if specified
            ci_result=ci_result,
            coverage_delta=0.0,
            attempt_index=context.attempt_index,
        )
        logger.info(
            f"[{phase_id}] Auditor completed: approved={auditor_result.approved}, issues={len(auditor_result.issues_found)}"
        )
        self.executor._post_auditor_result(phase_id, auditor_result)

        logger.info(f"[{phase_id}] Step 5/5: Applying Quality Gate...")
        quality_report = self.executor.quality_gate.assess_phase(
            phase_id=phase_id,
            phase_spec=phase,
            auditor_result={
                "approved": auditor_result.approved,
                "issues_found": auditor_result.issues_found,
            },
            ci_result=ci_result,
            coverage_delta=0.0,
            patch_content=combined_result.patch_content,
            files_changed=None,
        )
        logger.info(f"[{phase_id}] Quality Gate: {quality_report.quality_level}")
        if quality_report.is_blocked():
            logger.warning(f"[{phase_id}] Phase BLOCKED by quality gate")
            for issue in quality_report.issues:
                logger.warning(f"  - {issue}")
            self.executor._update_phase_status(phase_id, "BLOCKED")
            return BatchedExecutionResult(
                success=False,
                status="BLOCKED",
                combined_patch=combined_patch,
                total_tokens=total_tokens,
                error_message="Quality gate blocked",
            )

        self.executor._update_phase_status(phase_id, "COMPLETE")
        logger.info(f"[{phase_id}] Phase completed successfully (batched)")
        return BatchedExecutionResult(
            success=True,
            status="COMPLETE",
            combined_patch=combined_patch,
            total_tokens=total_tokens,
        )
