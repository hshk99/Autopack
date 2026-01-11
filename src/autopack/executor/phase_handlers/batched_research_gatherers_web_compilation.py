"""Phase handler for research-gatherers-web-compilation batched execution.

Specialized in-phase batching for Chunk 2B (research-gatherers-web-compilation).

Why:
- Chunk 2B often produces truncated/incomplete patches (e.g., unclosed triple quotes in tests)
  and/or malformed header-only new file diffs for docs, which blocks convergence.
- Splitting deliverables into smaller, prefix-based batches materially reduces truncation
  probability and yields earlier, tighter feedback.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


def execute(
    executor: Any,
    *,
    phase: dict,
    attempt_index: int,
    allowed_paths: Optional[List[str]],
) -> Tuple[bool, str]:
    """Execute research-gatherers-web-compilation phase with batched deliverables.

    Args:
        executor: AutonomousExecutor instance.
        phase: Phase specification dictionary.
        attempt_index: Current 0-based attempt number.
        allowed_paths: List of allowed file paths for scope enforcement, or None.

    Returns:
        Tuple of (success, status) where status is "COMPLETE", "FAILED", etc.
    """
    # Imports inside function to avoid circular imports and reduce import-time weight
    from autopack.llm_client import BuilderResult
    from autopack.governed_apply import GovernedApplyPath
    from autopack.deliverables_validator import (
        extract_deliverables_from_scope,
        validate_new_file_diffs_have_complete_structure,
        validate_deliverables,
        format_validation_feedback_for_builder,
    )

    phase_id = phase.get("phase_id") or "research-gatherers-web-compilation"

    # Load repository context for Builder
    file_context = executor._load_repository_context(phase)
    logger.info(
        f"[{phase_id}] Loaded {len(file_context.get('existing_files', {}))} files for context"
    )

    # Pre-flight policy (keep aligned with main execution path)
    use_full_file_mode = True
    if phase.get("builder_mode") == "structured_edit":
        use_full_file_mode = False
    if file_context and len(file_context.get("existing_files", {})) >= 30:
        use_full_file_mode = False

    learning_context = executor._get_learning_context_for_phase(phase)
    project_rules = learning_context.get("project_rules", [])
    run_hints = learning_context.get("run_hints", [])
    if project_rules or run_hints:
        logger.info(
            f"[{phase_id}] Learning context: {len(project_rules)} rules, {len(run_hints)} hints"
        )

    retrieved_context = ""
    if executor.memory_service and executor.memory_service.enabled:
        try:
            phase_description = phase.get("description", "")
            query = f"{phase_description[:500]}"
            project_id = executor._get_project_slug() or executor.run_id

            # BUILD-154: Make SOT budget gating + telemetry explicit and non-silent
            from autopack.config import settings

            max_context_chars = max(4000, settings.autopack_sot_retrieval_max_chars + 2000)
            include_sot = executor._should_include_sot_retrieval(
                max_context_chars, phase_id=phase_id
            )

            retrieved = executor.memory_service.retrieve_context(
                query=query,
                project_id=project_id,
                run_id=executor.run_id,
                include_code=True,
                include_summaries=True,
                include_errors=True,
                include_hints=True,
                include_planning=True,
                include_plan_changes=True,
                include_decisions=True,
                include_sot=include_sot,
            )
            retrieved_context = executor.memory_service.format_retrieved_context(
                retrieved, max_chars=max_context_chars
            )

            # BUILD-155: Record SOT retrieval telemetry
            executor._record_sot_retrieval_telemetry(
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

    scope_base = phase.get("scope") or {}
    all_paths = [
        p for p in extract_deliverables_from_scope(scope_base) if isinstance(p, str) and p.strip()
    ]

    # Suggested batches:
    # - src/research/gatherers/*
    # - src/research/agents/*
    # - tests/research/gatherers/* + tests/research/agents/*
    # - docs/research/*
    batch_gatherers = sorted([p for p in all_paths if p.startswith("src/research/gatherers/")])
    batch_agents = sorted([p for p in all_paths if p.startswith("src/research/agents/")])
    batch_tests = sorted(
        [
            p
            for p in all_paths
            if p.startswith("tests/research/gatherers/") or p.startswith("tests/research/agents/")
        ]
    )
    batch_docs = sorted([p for p in all_paths if p.startswith("docs/research/")])
    batches = [b for b in [batch_gatherers, batch_agents, batch_tests, batch_docs] if b]
    if not batches:
        batches = [sorted(set(all_paths))]
    logger.info(
        f"[{phase_id}] Chunk2B batching enabled: {len(batches)} batches ({', '.join(str(len(b)) for b in batches)} files)"
    )

    total_tokens = 0
    last_builder_result: Optional[BuilderResult] = None

    for idx, batch_paths in enumerate(batches, 1):
        logger.info(f"[{phase_id}] Batch {idx}/{len(batches)}: {len(batch_paths)} deliverables")

        # Use batch scope with only "paths" to avoid extract_deliverables_from_scope pulling the full deliverables dict.
        batch_scope = {
            k: v for k, v in (scope_base or {}).items() if k not in ("deliverables", "paths")
        }
        batch_scope["paths"] = list(batch_paths)
        phase_for_batch = {**phase, "scope": batch_scope}

        deliverables_contract = executor._build_deliverables_contract(phase_for_batch, phase_id)
        phase_with_constraints = {
            **phase_for_batch,
            "protected_paths": protected_paths,
            "deliverables_contract": deliverables_contract,
        }

        # Manifest gate for this batch
        manifest_paths: List[str] = []
        try:
            expected_paths = extract_deliverables_from_scope(batch_scope)
            if expected_paths and executor.llm_service and deliverables_contract:
                expected_set = {p for p in expected_paths if isinstance(p, str)}
                expected_list = sorted(expected_set)
                allowed_roots: List[str] = []
                for r in ("src/research/", "tests/research/", "docs/research/", "examples/"):
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
                    executor.llm_service.generate_deliverables_manifest(
                        expected_paths=list(expected_set),
                        allowed_roots=allowed_roots,
                        run_id=executor.run_id,
                        phase_id=phase_id,
                        attempt_index=attempt_index,
                    )
                )
                if not ok_manifest:
                    err_details = manifest_error or "deliverables manifest gate failed"
                    logger.error(
                        f"[{phase_id}] Deliverables manifest gate FAILED (batch {idx}): {err_details}"
                    )
                    executor._record_phase_error(
                        phase, "deliverables_manifest_failed", err_details, attempt_index
                    )
                    executor._record_learning_hint(
                        phase, "deliverables_manifest_failed", err_details
                    )
                    return False, "DELIVERABLES_VALIDATION_FAILED"
                logger.info(
                    f"[{phase_id}] Deliverables manifest gate PASSED (batch {idx}, {len(manifest_paths or [])} paths)"
                )
                phase_with_constraints["deliverables_manifest"] = manifest_paths or []
        except Exception as e:
            logger.warning(
                f"[{phase_id}] Deliverables manifest gate error (batch {idx}, skipping gate): {e}"
            )

        # Run Builder for this batch
        builder_result = executor.llm_service.execute_builder_phase(
            phase_spec=phase_with_constraints,
            file_context=file_context,
            max_tokens=None,
            project_rules=project_rules,
            run_hints=run_hints,
            run_id=executor.run_id,
            phase_id=phase_id,
            run_context=executor._build_run_context(),
            attempt_index=attempt_index,
            use_full_file_mode=use_full_file_mode,
            config=executor.builder_output_config,
            retrieved_context=retrieved_context,
        )

        if not builder_result.success:
            logger.error(f"[{phase_id}] Builder failed (batch {idx}): {builder_result.error}")
            executor._post_builder_result(phase_id, builder_result, allowed_paths)
            executor._update_phase_status(phase_id, "FAILED")
            return False, "FAILED"

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
            workspace=Path(executor.workspace),
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
            executor._post_builder_result(phase_id, fail_result, allowed_paths)
            return False, "DELIVERABLES_VALIDATION_FAILED"

        # Structural validation for new files (headers + hunks + content where applicable)
        expected_paths = extract_deliverables_from_scope(scope_config or {})
        ok_struct, struct_errors, struct_details = validate_new_file_diffs_have_complete_structure(
            patch_content=builder_result.patch_content or "",
            expected_paths=expected_paths,
            workspace=Path(executor.workspace),
            allow_empty_suffixes=["__init__.py", ".gitkeep"],
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
            executor._post_builder_result(phase_id, fail_result, allowed_paths)
            return False, "DELIVERABLES_VALIDATION_FAILED"

        # Apply patch for this batch
        # Derive scope_paths and allowed_paths for governed apply from this batch scope
        scope_paths = batch_scope.get("paths", []) if isinstance(batch_scope, dict) else []
        derived_allowed: List[str] = []
        for r in ("src/research/", "tests/research/", "docs/research/"):
            if any(p.startswith(r) for p in expected_paths):
                derived_allowed.append(r)
        if not derived_allowed:
            derived_allowed = allowed_paths or []

        governed_apply = GovernedApplyPath(
            workspace=Path(executor.workspace),
            run_type=executor.run_type,
            autopack_internal_mode=executor.run_type
            in ["autopack_maintenance", "autopack_upgrade", "self_repair"],
            scope_paths=scope_paths,
            allowed_paths=derived_allowed or None,
        )
        patch_success, error_msg = governed_apply.apply_patch(
            builder_result.patch_content, full_file_mode=True
        )
        if not patch_success:
            logger.error(f"[{phase_id}] Failed to apply patch (batch {idx}): {error_msg}")
            executor._update_phase_status(phase_id, "FAILED")
            return False, "PATCH_FAILED"
        logger.info(f"[{phase_id}] Patch applied successfully (batch {idx})")

        # Refresh context so next batch sees created files
        try:
            file_context = executor._load_repository_context(phase_for_batch)
        except Exception as e:
            logger.warning(f"[{phase_id}] Context refresh failed after batch {idx}: {e}")

    # Build combined patch for auditor/quality gate
    combined_patch = ""
    try:
        proc = subprocess.run(
            ["git", "diff", "--no-color"],
            cwd=str(executor.workspace),
            capture_output=True,
            text=True,
        )
        combined_patch = proc.stdout or ""
    except Exception as e:
        logger.warning(f"[{phase_id}] Failed to compute combined patch after batching: {e}")

    # Post a single combined builder result to API for phase-level visibility
    combined_result = BuilderResult(
        success=True,
        patch_content=combined_patch
        or (last_builder_result.patch_content if last_builder_result else ""),
        builder_messages=[f"batched_chunk2b: {len(batches)} batches applied"],
        tokens_used=total_tokens,
        model_used=(
            getattr(last_builder_result, "model_used", None) if last_builder_result else None
        ),
        error=None,
    )
    executor._post_builder_result(phase_id, combined_result, allowed_paths)

    # Proceed with normal CI/Auditor/Quality Gate using the combined patch content
    logger.info(f"[{phase_id}] Step 3/5: Running CI checks...")
    ci_result = executor._run_ci_checks(phase_id, phase)

    logger.info(f"[{phase_id}] Step 4/5: Reviewing patch with Auditor (via LlmService)...")
    auditor_result = executor.llm_service.execute_auditor_review(
        patch_content=combined_result.patch_content,
        phase_spec=phase,
        max_tokens=None,
        project_rules=project_rules,
        run_hints=run_hints,
        run_id=executor.run_id,
        phase_id=phase_id,
        run_context=executor._build_run_context(),
        ci_result=ci_result,
        coverage_delta=0.0,
        attempt_index=attempt_index,
    )
    logger.info(
        f"[{phase_id}] Auditor completed: approved={auditor_result.approved}, issues={len(auditor_result.issues_found)}"
    )
    executor._post_auditor_result(phase_id, auditor_result)

    logger.info(f"[{phase_id}] Step 5/5: Applying Quality Gate...")
    quality_report = executor.quality_gate.assess_phase(
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
        executor._update_phase_status(phase_id, "BLOCKED")
        return False, "BLOCKED"

    executor._update_phase_status(phase_id, "COMPLETE")
    logger.info(f"[{phase_id}] Phase completed successfully (batched)")
    return True, "COMPLETE"
