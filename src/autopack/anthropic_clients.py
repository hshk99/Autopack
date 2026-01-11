"""Anthropic Claude-based Builder and Auditor implementations

Per models.yaml configuration:
- Claude Opus 4.5 for high-risk auditing
- Claude Sonnet 4.5 for progressive strategy auditing
- Complementary to OpenAI models for dual auditing

This module provides Anthropic API integration for when
ModelRouter selects Claude models based on category/quota.
"""

import os
import json
import logging
import yaml
import copy
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

try:
    from anthropic import Anthropic
except ImportError:
    # Graceful degradation if anthropic package not installed
    Anthropic = None

from .llm_client import BuilderResult, AuditorResult
from .journal_reader import get_prevention_prompt_injection
from .llm_service import estimate_tokens
from .repair_helpers import JsonRepairHelper, save_repair_debug

# BUILD-129 Phase 1: Deliverable-based token estimation
from .token_estimator import TokenEstimator

# BUILD-129 Phase 2: Continuation-based recovery
from .continuation_recovery import ContinuationRecovery

# BUILD-129 Phase 3: NDJSON truncation-tolerant format
from .ndjson_format import NDJSONParser, NDJSONApplier

logger = logging.getLogger(__name__)


def _write_token_estimation_v2_telemetry(
    run_id: str,
    phase_id: str,
    category: str,
    complexity: str,
    deliverables: List[str],
    predicted_output_tokens: int,
    actual_output_tokens: int,
    selected_budget: int,
    success: bool,
    truncated: bool,
    stop_reason: Optional[str],
    model: str,
    # BUILD-129 Phase 3: Feature tracking for DOC_SYNTHESIS analysis
    is_truncated_output: bool = False,
    api_reference_required: Optional[bool] = None,
    examples_required: Optional[bool] = None,
    research_required: Optional[bool] = None,
    usage_guide_required: Optional[bool] = None,
    context_quality: Optional[str] = None,
    # BUILD-129 Phase 3 P3: SOT file tracking
    is_sot_file: Optional[bool] = None,
    sot_file_name: Optional[str] = None,
    sot_entry_count_hint: Optional[int] = None,
    # BUILD-142 PARITY: Separate estimator intent from final ceiling
    actual_max_tokens: Optional[int] = None,
) -> None:
    """Write TokenEstimationV2 event to database for validation.

    Feature flag: TELEMETRY_DB_ENABLED (default: false for backwards compat)

    BUILD-129 Phase 3: Now captures feature flags for DOC_SYNTHESIS tasks to enable
    phase-based estimation analysis and truncation-aware calibration.

    BUILD-129 Phase 3 P3: Now captures SOT (Source of Truth) file metadata for
    specialized estimation of BUILD_LOG.md, BUILD_HISTORY.md, etc.

    BUILD-142 PARITY: Now captures actual_max_tokens (final ceiling after P4 enforcement)
    separately from selected_budget (estimator intent) for accurate waste calculation.
    """
    # Feature flag check
    if os.environ.get("TELEMETRY_DB_ENABLED", "").lower() not in ["1", "true", "yes"]:
        return

    # BUILD-129 Phase 3: Telemetry validity guard
    # Reject anomalous events with suspiciously low actual_output_tokens (<50)
    # These are likely parser errors, API failures, or other edge cases that corrupt metrics
    if actual_output_tokens < 50:
        logger.warning(
            f"[TELEMETRY] Skipping invalid event for {phase_id}: actual_output_tokens={actual_output_tokens} < 50 (likely error)"
        )
        return

    try:
        from .database import SessionLocal
        from .models import TokenEstimationV2Event
        from .models import Phase as PhaseModel

        # Calculate metrics
        if actual_output_tokens > 0 and predicted_output_tokens > 0:
            denom = (abs(actual_output_tokens) + abs(predicted_output_tokens)) / 2
            smape = abs(actual_output_tokens - predicted_output_tokens) / max(1, denom) * 100.0
            waste_ratio = predicted_output_tokens / actual_output_tokens
            underestimated = actual_output_tokens > predicted_output_tokens
        else:
            smape = None
            waste_ratio = None
            underestimated = None

        # Sanitize deliverables (max 20, truncate long paths)
        deliverables_clean = []
        for d in deliverables[:20]:  # Cap at 20
            if len(str(d)) > 200:
                deliverables_clean.append(str(d)[:197] + "...")
            else:
                deliverables_clean.append(str(d))

        deliverables_json = json.dumps(deliverables_clean)

        # Try to resolve run_id if caller passed "unknown"/empty.
        # In most flows, the executor has the true run_id; but some legacy call paths
        # may not populate phase_spec["run_id"]. Use the phases table as a best-effort lookup.
        if not run_id or run_id == "unknown":
            session_lookup = SessionLocal()
            try:
                phase_row = (
                    session_lookup.query(PhaseModel)
                    .filter(PhaseModel.phase_id == phase_id)
                    .order_by(PhaseModel.run_id.desc())
                    .first()
                )
                if phase_row and getattr(phase_row, "run_id", None):
                    run_id = phase_row.run_id
            finally:
                try:
                    session_lookup.close()
                except Exception:
                    pass

        # Write to DB
        session = SessionLocal()
        try:
            event = TokenEstimationV2Event(
                run_id=run_id,
                phase_id=phase_id,
                category=category,
                complexity=complexity,
                deliverable_count=len(deliverables),
                deliverables_json=deliverables_json,
                predicted_output_tokens=predicted_output_tokens,
                actual_output_tokens=actual_output_tokens,
                selected_budget=selected_budget,
                success=success,
                truncated=truncated,
                stop_reason=stop_reason,
                model=model,
                # Keep DB semantics aligned with migrations/views:
                # - smape_percent is a percent (float)
                # - waste_ratio is predicted/actual (float ratio, not percent)
                smape_percent=float(smape) if smape is not None else None,
                waste_ratio=float(waste_ratio) if waste_ratio is not None else None,
                underestimated=underestimated,
                # BUILD-129 Phase 3: Feature tracking for DOC_SYNTHESIS
                is_truncated_output=is_truncated_output,
                api_reference_required=api_reference_required,
                examples_required=examples_required,
                research_required=research_required,
                usage_guide_required=usage_guide_required,
                context_quality=context_quality,
                # BUILD-129 Phase 3 P3: SOT file tracking
                is_sot_file=is_sot_file,
                sot_file_name=sot_file_name,
                sot_entry_count_hint=sot_entry_count_hint,
                # BUILD-142 PARITY: Final ceiling after P4 enforcement
                actual_max_tokens=actual_max_tokens,
            )
            session.add(event)
            session.commit()
        finally:
            session.close()
    except Exception as e:
        # Don't fail the build on telemetry errors
        logger.warning(f"[TokenEstimationV2] Failed to write DB telemetry: {e}")


# Per GPT_RESPONSE24 C1: Normalize complexity to handle variations
ALLOWED_COMPLEXITIES = {"low", "medium", "high", "maintenance"}


def normalize_complexity(value: str | None) -> str:
    """
    Normalize complexity value to canonical form.

    Per GPT_RESPONSE24 C1: Handle case variations, common suffixes, and aliases.
    Per GPT_RESPONSE25 C1: Log DATA_INTEGRITY for unknown values and fallback to "medium".

    Args:
        value: Raw complexity value from phase_spec

    Returns:
        Normalized complexity value (always one of ALLOWED_COMPLEXITIES)
    """
    if value is None:
        return "medium"  # Default

    v = value.strip().lower()

    # Strip common suffixes (per GPT1 and GPT2)
    for suffix in (
        "_complexity",
        "-complexity",
        "_level",
        "-level",
        "_mode",
        "-mode",
        "_task",
        "_tier",
    ):
        if v.endswith(suffix):
            v = v[: -len(suffix)]

    # Map common aliases (per GPT1 and GPT2)
    alias_map = {
        "low": "low",
        "medium": "medium",
        "med": "medium",
        "high": "high",
        "maint": "maintenance",
        "maintain": "maintenance",
        "maintenance": "maintenance",
        "maintenance_mode": "maintenance",
    }

    normalized = alias_map.get(v, v)

    # Per GPT_RESPONSE25 C1: Guard for unknown values - log and fallback to "medium"
    if normalized not in ALLOWED_COMPLEXITIES:
        logger.warning(
            "[DATA_INTEGRITY] Unknown complexity value %r (normalized to %r); "
            "falling back to 'medium'. Consider adding to alias_map if valid.",
            value,
            normalized,
        )
        return "medium"

    return normalized


class AnthropicBuilderClient:
    """Builder implementation using Anthropic Claude API

    Currently used for:
    - Test generation (claude-sonnet-4-5 per models.yaml)
    - Escalation scenarios when OpenAI quota exhausted
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Anthropic client

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
        """
        if Anthropic is None:
            raise ImportError(
                "anthropic package not installed. " "Install with: pip install anthropic"
            )

        self.client = Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))

    def execute_phase(
        self,
        phase_spec: Dict,
        file_context: Optional[Dict] = None,
        max_tokens: Optional[int] = None,
        model: str = "claude-sonnet-4-5",
        project_rules: Optional[List] = None,
        run_hints: Optional[List] = None,
        use_full_file_mode: bool = True,
        config=None,  # NEW: BuilderOutputConfig for consistency
        retrieved_context: Optional[str] = None,  # NEW: Vector memory context
    ) -> BuilderResult:
        """Execute a phase using Claude

        Args:
            phase_spec: Phase specification
            file_context: Repository file context
            max_tokens: Token budget
            model: Claude model (claude-opus-4-5, claude-sonnet-4-5, etc.)
            project_rules: Persistent learned rules
            run_hints: Within-run hints
            use_full_file_mode: If True, use new full-file replacement format (GPT_RESPONSE10).
                               If False, use legacy git diff format (deprecated).
            config: BuilderOutputConfig instance (per IMPLEMENTATION_PLAN2.md)
            retrieved_context: Retrieved context from vector memory (formatted string)

        Returns:
            BuilderResult with patch and metadata
        """
        # Defensive: ensure phase_spec is always a dict
        if phase_spec is None:
            phase_spec = {}
        scope_cfg = phase_spec.get("scope") or {}
        scope_paths = scope_cfg.get("paths", []) if isinstance(scope_cfg, dict) else []
        scope_paths = [p for p in scope_paths if isinstance(p, str)]

        # Heuristic: lockfile / manifest phases need larger outputs and should be treated as large refactors
        lockfile_phase = any("package-lock" in p or "yarn.lock" in p for p in scope_paths)
        manifest_phase = any("package.json" in p for p in scope_paths)
        pack_phase = any("/packs/" in p or p.endswith((".yaml", ".yml")) for p in scope_paths)

        # Apply safe defaults based on scope
        if pack_phase:
            phase_spec.setdefault("allow_mass_addition", True)
        if lockfile_phase or manifest_phase:
            phase_spec.setdefault("change_size", "large_refactor")

        # BUILD-129 Phase 1: Use deliverable-based token estimation if available
        task_category = phase_spec.get("task_category", "")
        complexity = phase_spec.get("complexity", "medium")
        # Deliverables may be stored either at the top-level (preferred) or under scope.deliverables.
        # Use either so token estimation + telemetry work through abstraction layers.
        deliverables = phase_spec.get("deliverables")
        if not deliverables:
            scope_cfg = phase_spec.get("scope") or {}
            if isinstance(scope_cfg, dict):
                deliverables = scope_cfg.get("deliverables")
        # BUILD-129 Phase 3: Normalize nested deliverables structures (dict-of-lists) into List[str]
        deliverables = TokenEstimator.normalize_deliverables(deliverables)

        # BUILD-129 Phase 3: Extract task description for DOC_SYNTHESIS detection
        task_description = phase_spec.get("description", "")

        token_estimate = None
        token_selected_budget = None

        if deliverables:
            # BUILD-129 Phase 1: Use TokenEstimator for deliverable-based estimation.
            # If manifest_generator already populated _estimated_output_tokens we still recompute here,
            # because workspace-aware complexity analysis is only available at execution time.
            try:
                estimator = TokenEstimator(workspace=Path.cwd())
                # If category metadata is missing, infer documentation for pure-doc phases so
                # DOC_SYNTHESIS detection can activate.
                effective_category = task_category or (
                    "documentation"
                    if estimator._all_doc_deliverables(deliverables)
                    else "implementation"
                )
                token_estimate = estimator.estimate(
                    deliverables=deliverables,
                    category=effective_category,
                    complexity=complexity,
                    scope_paths=scope_paths,
                    task_description=task_description,
                )
                token_selected_budget = estimator.select_budget(token_estimate, complexity)

                # Persist estimator output into the phase for downstream telemetry/reporting.
                phase_spec["_estimated_output_tokens"] = token_estimate.estimated_tokens

                # BUILD-129 Phase 3: Extract and persist DOC_SYNTHESIS features for telemetry
                # Use estimator output category (may be doc_synthesis) rather than input task_category,
                # because many production phases have no category metadata.
                doc_features = {}
                context_quality_value = None
                if token_estimate.category in ["documentation", "docs", "doc_synthesis"]:
                    doc_features = estimator._extract_doc_features(deliverables, task_description)
                    # Determine context quality from scope_paths
                    if not scope_paths:
                        context_quality_value = "none"
                    elif len(scope_paths) > 10:
                        context_quality_value = "strong"
                    else:
                        context_quality_value = "some"

                # BUILD-129 Phase 3 P3: Detect and persist SOT file metadata for telemetry
                is_sot_file_value = None
                sot_file_name_value = None
                sot_entry_count_hint_value = None
                if token_estimate.category == "doc_sot_update":
                    is_sot_file_value = True
                    # Extract SOT file name from deliverables
                    for d in deliverables:
                        if estimator._is_sot_file(d):
                            sot_file_name_value = Path(d.lower().replace("\\", "/")).name
                            break
                    # Proxy entry count from deliverable count
                    sot_entry_count_hint_value = len(deliverables)

                phase_spec.setdefault("metadata", {}).setdefault("token_prediction", {}).update(
                    {
                        "predicted_output_tokens": token_estimate.estimated_tokens,
                        "selected_budget": token_selected_budget,
                        "confidence": token_estimate.confidence,
                        "source": "token_estimator",
                        # BUILD-129 Phase 3 P5: Store estimated category for telemetry
                        "estimated_category": token_estimate.category,
                        # BUILD-129 Phase 3: Feature tracking
                        "api_reference_required": doc_features.get("api_reference_required"),
                        "examples_required": doc_features.get("examples_required"),
                        "research_required": doc_features.get("research_required"),
                        "usage_guide_required": doc_features.get("usage_guide_required"),
                        "context_quality": context_quality_value,
                        # BUILD-129 Phase 3 P3: SOT file tracking
                        "is_sot_file": is_sot_file_value,
                        "sot_file_name": sot_file_name_value,
                        "sot_entry_count_hint": sot_entry_count_hint_value,
                    }
                )

                logger.info(
                    f"[BUILD-129] Token estimate: {token_estimate.estimated_tokens} output tokens "
                    f"({token_estimate.deliverable_count} deliverables, confidence={token_estimate.confidence:.2f}), "
                    f"selected budget: {token_selected_budget} (P4 enforcement applied before API call)"
                )
            except Exception as e:
                logger.warning(f"[BUILD-129] Token estimation failed, using fallback: {e}")
                token_estimate = None
                token_selected_budget = None

        # BUILD-042: Apply complexity-based token scaling FIRST (before special case overrides)
        # This ensures the base token budget is set correctly before task-specific increases
        # This serves as fallback if token estimation is not available
        # BUILD-142: If TokenEstimator provided a category-aware budget, use that instead of complexity fallback
        if max_tokens is None:
            if token_selected_budget:
                # Use category-aware budget from TokenEstimator
                max_tokens = token_selected_budget
            elif complexity == "low":
                max_tokens = 8192  # BUILD-042: Increased from 4096
            elif complexity == "medium":
                max_tokens = 12288  # BUILD-042: Complexity-based scaling
            elif complexity == "high":
                max_tokens = 16384  # BUILD-042: Complexity-based scaling
            else:
                max_tokens = 8192  # Default fallback

        # Increase token budget when emitting larger artifacts (lockfiles, docker configs, packs)
        # These override the complexity-based defaults if they need more
        if lockfile_phase or manifest_phase:
            max_tokens = max(max_tokens, 12000)
        if task_category in ("deployment", "frontend"):
            max_tokens = max(max_tokens, 16384)
            # Deployment/frontends often touch multiple files; treat as large refactor
            phase_spec.setdefault("change_size", "large_refactor")
        if task_category == "backend" and len(scope_paths) >= 3:
            # Backend multi-file phases (e.g., API + services + tests) need larger budget
            max_tokens = max(max_tokens, 12000)

        # Adaptive: if small scope and all files are small, treat as large_refactor and allow mass addition
        if file_context:
            files = file_context.get("existing_files", {})
            if isinstance(files, dict):
                scoped_files = []
                for fp, fc in files.items():
                    if not isinstance(fp, str):
                        continue
                    if any(fp.startswith(sp) for sp in scope_paths):
                        if isinstance(fc, str):
                            scoped_files.append(fc)
                max_lines = max((c.count("\n") + 1 for c in scoped_files), default=0)
                if len(scope_paths) <= 6 and max_lines <= 500:
                    phase_spec.setdefault("change_size", "large_refactor")
                    phase_spec.setdefault("allow_mass_addition", True)

        # Adaptive mode selection: keep full-file mode for small scopes; avoid only for large multi-file scopes
        use_full_file_mode_flag = use_full_file_mode
        multi_file_scope = len(scope_paths) >= 3
        if task_category in ("deployment", "frontend"):
            multi_file_scope = True
        if multi_file_scope and use_full_file_mode_flag and len(scope_paths) > 6:
            logger.info(
                "[Builder] Disabling full-file mode due to large multi-file scope (paths=%d, category=%s)",
                len(scope_paths),
                task_category,
            )
            use_full_file_mode_flag = False
        try:
            # Check if we need structured edit mode before building prompt
            # Structured edit should ONLY be used if files being MODIFIED exceed the limit
            # NOT if any file in context exceeds the limit
            use_structured_edit = False
            if file_context and config:
                files = file_context.get("existing_files", {})
                # Safety check: ensure files is a dict
                if not isinstance(files, dict):
                    logger.warning(
                        f"[Builder] file_context.get('existing_files') returned non-dict: {type(files)}, using empty dict"
                    )
                    files = {}

                # Get explicit scope paths from phase_spec (guard None/empty)
                scope_config = phase_spec.get("scope") or {}
                scope_paths = (
                    scope_config.get("paths", []) if isinstance(scope_config, dict) else []
                )
                # Safety check: ensure scope_paths is a list of strings
                if not isinstance(scope_paths, list):
                    logger.warning(
                        f"[Builder] scope_paths is not a list: {type(scope_paths)}, using empty list"
                    )
                    scope_paths = []
                # Filter out non-string items
                scope_paths = [sp for sp in scope_paths if isinstance(sp, str)]

                # If no explicit scope, try to infer from file context
                # Only check files that will actually be modified
                if not scope_paths:
                    # If no scope defined, assume all files ≤ max_lines_for_full_file are modifiable
                    # and files > max_lines_for_full_file are read-only context
                    # Structured edit mode should NOT be triggered unless explicitly scoped
                    logger.debug(
                        "[Builder] No scope_paths defined; assuming small files are modifiable, large files are read-only"
                    )
                    use_structured_edit = False
                else:
                    # Check only files in scope
                    for file_path, content in files.items():
                        # Safety check: ensure file_path is a string
                        if not isinstance(file_path, str):
                            logger.warning(
                                f"[Builder] Skipping non-string file_path: {file_path} (type: {type(file_path)})"
                            )
                            continue

                        # Only check if file is in scope
                        if any(file_path.startswith(sp) for sp in scope_paths):
                            if isinstance(content, str):
                                line_count = content.count("\n") + 1
                                if line_count > config.max_lines_hard_limit:
                                    logger.info(
                                        f"[Builder] File {file_path} ({line_count} lines) exceeds hard limit; enabling structured edit mode"
                                    )
                                    use_structured_edit = True
                                    break

            # Explicit override: honor builder_mode=structured_edit from phase spec
            if phase_spec.get("builder_mode") == "structured_edit":
                use_structured_edit = True

            # BUILD-043: Hybrid mode optimization - use full_file for multi-file creation
            # Structured edit JSON overhead (~500-1000 tokens) wastes budget for simple tasks
            if use_structured_edit:
                phase_name = phase_spec.get("name", "").lower()
                phase_desc = phase_spec.get("description", "").lower()

                # Detect multi-file creation phases (country templates, feature scaffolding, etc.)
                creates_multiple_files = (
                    "template" in phase_name
                    or "multiple files" in phase_desc
                    or "create" in phase_desc
                    and ("files" in phase_desc or "modules" in phase_desc)
                )

                if creates_multiple_files:
                    # Override to full_file mode for better token efficiency
                    use_full_file_mode_flag = True
                    use_structured_edit = False
                    logger.info(
                        "[Builder] Using full_file mode for multi-file creation phase (BUILD-043 optimization)"
                    )

            # BUILD-129 Phase 3: NDJSON format selection for truncation tolerance
            # Per TOKEN_BUDGET_ANALYSIS_REVISED.md Layer 3: Use NDJSON for multi-file scopes (≥5 deliverables)
            # Note: Use already-normalized 'deliverables' from line 291 (don't reassign)
            use_ndjson_format = False
            if deliverables and len(deliverables) >= 5:
                # NDJSON provides truncation tolerance: only last incomplete line lost, not entire output
                use_ndjson_format = True
                # NDJSON is a variant of structured output, not full-file or diff
                use_full_file_mode_flag = False
                use_structured_edit = False
                logger.info(
                    f"[BUILD-129:Layer3] Using NDJSON format for {len(deliverables)} deliverables "
                    f"(truncation-tolerant mode)"
                )

            # BUILD-043: Build context-aware system prompt (trim for simple phases)
            system_prompt = self._build_system_prompt(
                use_full_file_mode=use_full_file_mode_flag,
                use_structured_edit=use_structured_edit,
                use_ndjson_format=use_ndjson_format,
                phase_spec=phase_spec,  # Pass phase info for context-aware prompts
            )

            # Build user prompt (includes full file content for full-file mode or line numbers for structured edit)
            # Hard prompt-limit protection: we may need to cap/summarize file_context to avoid provider errors.
            model_prompt_limit = (
                200_000 if isinstance(model, str) and model.startswith("claude") else 128_000
            )
            prompt_margin = int(os.getenv("AUTOPACK_PROMPT_MAX_TOKENS_MARGIN", "8000"))
            max_prompt_tokens = max(20_000, model_prompt_limit - prompt_margin)

            user_prompt = self._build_user_prompt(
                phase_spec,
                file_context,
                project_rules,
                run_hints,
                use_full_file_mode=use_full_file_mode_flag,
                config=config,  # NEW: Pass config for read-only markers and structured edit detection
                retrieved_context=retrieved_context,  # NEW: Vector memory context
                context_budget_tokens=int(os.getenv("AUTOPACK_CONTEXT_BUDGET_TOKENS", "120000")),
            )

            # Per GPT_RESPONSE23 Q2: Add sanity checks for max_tokens
            # Note: None is expected when ModelRouter decides - use default based on phase config
            builder_mode = phase_spec.get("builder_mode", "")
            change_size = phase_spec.get("change_size", "")

            # BUILD-142: Category-aware conditional override for special modes
            # Only apply 16384 floor for non-docs categories or when selected_budget already >= 16384
            # This preserves category-aware base budget reductions (e.g., docs/low=4096) while maintaining
            # safety overrides for high-risk code phases
            if builder_mode == "full_file" or change_size == "large_refactor":
                # Normalize category for consistent comparison
                normalized_category = task_category.lower() if task_category else ""
                is_docs_like = normalized_category in [
                    "docs",
                    "documentation",
                    "doc_synthesis",
                    "doc_sot_update",
                ]

                # Only force 16384 floor if:
                # 1. No selected budget available (None), OR
                # 2. Selected budget is already >= 16384 (not an intentional reduction), OR
                # 3. Category is NOT docs-like (preserve safety for code phases)
                should_apply_floor = (
                    not token_selected_budget or token_selected_budget >= 16384 or not is_docs_like
                )

                if should_apply_floor:
                    max_tokens = max(max_tokens, 16384)
                    logger.debug(
                        "[TOKEN_EST] Using increased max_tokens=%d for builder_mode=%s change_size=%s "
                        "(category=%s, selected_budget=%s)",
                        max_tokens,
                        builder_mode,
                        change_size,
                        task_category,
                        token_selected_budget,
                    )
                else:
                    logger.debug(
                        "[BUILD-142] Preserving category-aware budget=%d for docs-like category=%s "
                        "(skipping 16384 floor override)",
                        token_selected_budget,
                        task_category,
                    )
            elif max_tokens <= 0:
                logger.warning(
                    "[TOKEN_EST] max_tokens invalid (%s); falling back to default 4096", max_tokens
                )
                max_tokens = 4096

            # Per GPT_RESPONSE21 Q2: Estimate tokens on final prompt text (as sent to provider)
            # Build full prompt text for estimation (system + user)
            full_prompt_text = system_prompt + "\n" + user_prompt
            estimated_prompt_tokens = estimate_tokens(full_prompt_text)
            call_max_tokens = max_tokens or 64000  # Keep existing default as final fallback
            estimated_completion_tokens = int(
                call_max_tokens * 0.7
            )  # Conservative estimate (70% of max)
            estimated_total_tokens = estimated_prompt_tokens + estimated_completion_tokens

            # Per GPT_RESPONSE22 Q1: Breakdown at DEBUG, INFO/WARNING for cap events
            phase_id = phase_spec.get("phase_id") or "unknown"
            run_id = phase_spec.get("run_id") or "unknown"

            # Always log breakdown at DEBUG for telemetry
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "[TOKEN_EST] run_id=%s phase_id=%s total=%d prompt=%d completion=%d max_tokens=%d",
                    run_id,
                    phase_id,
                    estimated_total_tokens,
                    estimated_prompt_tokens,
                    estimated_completion_tokens,
                    call_max_tokens,
                )

            # Per GPT_RESPONSE24 C1: Normalize complexity to handle variations
            # Per GPT_RESPONSE24 Q2 (GPT2): Use "medium" as fallback, no default tier in Phase 1
            # Per GPT_RESPONSE22 C1: Check soft cap with buffer bands (no safety margin on estimate)
            raw_complexity = phase_spec.get("complexity")
            complexity = normalize_complexity(raw_complexity)
            soft_cap = None
            try:
                # Load token_soft_caps from config
                config_path = Path(__file__).parent.parent.parent / "config" / "models.yaml"
                if config_path.exists():
                    with open(config_path) as f:
                        models_config = yaml.safe_load(f)
                        token_caps_config = models_config.get("token_soft_caps", {})
                        if token_caps_config.get("enabled", False):
                            per_phase_caps = token_caps_config.get("per_phase_soft_caps", {})
                            soft_cap = per_phase_caps.get(complexity)

                            # Per GPT_RESPONSE24 Q2 (GPT2): Fallback to "medium" if complexity not found
                            if soft_cap is None:
                                if "medium" in per_phase_caps:
                                    logger.debug(
                                        "[TOKEN_SOFT_CAP] Unknown complexity %r (normalized %r) for run_id=%s phase_id=%s; "
                                        "falling back to 'medium' tier (%s tokens)",
                                        raw_complexity,
                                        complexity,
                                        run_id,
                                        phase_id,
                                        per_phase_caps["medium"],
                                    )
                                    soft_cap = per_phase_caps["medium"]
                                else:
                                    # Config is inconsistent; skip soft cap advisory
                                    logger.warning(
                                        "[TOKEN_SOFT_CAP] No soft cap for %r and no 'medium' tier in config; "
                                        "skipping soft cap check for this phase",
                                        raw_complexity,
                                    )
                                    soft_cap = None
            except Exception:
                # If config loading fails, skip soft cap check (non-fatal)
                pass

            # Log INFO/WARNING when soft cap is exceeded or approached
            if soft_cap:
                if estimated_total_tokens >= soft_cap:
                    # Clearly over soft cap
                    logger.warning(
                        "[TOKEN_SOFT_CAP] run_id=%s phase_id=%s est_total=%d soft_cap=%d "
                        "(prompt=%d completion=%d complexity=%s)",
                        run_id,
                        phase_id,
                        estimated_total_tokens,
                        soft_cap,
                        estimated_prompt_tokens,
                        estimated_completion_tokens,
                        complexity,
                    )
                elif estimated_total_tokens >= int(soft_cap * 0.9):  # ≥90% of cap
                    # Approaching soft cap
                    logger.info(
                        "[TOKEN_SOFT_CAP] run_id=%s phase_id=%s est_total=%d soft_cap=%d (approaching, complexity=%s)",
                        run_id,
                        phase_id,
                        estimated_total_tokens,
                        soft_cap,
                        complexity,
                    )

            # If our prompt estimate exceeds the model limit, rebuild prompt with an aggressive budget.
            if estimated_prompt_tokens > max_prompt_tokens:
                logger.warning(
                    "[PROMPT_BUDGET] Prompt too large (est_prompt=%d > limit=%d). Rebuilding with aggressive context budget.",
                    estimated_prompt_tokens,
                    max_prompt_tokens,
                )
                user_prompt = self._build_user_prompt(
                    phase_spec,
                    file_context,
                    project_rules,
                    run_hints,
                    use_full_file_mode=use_full_file_mode_flag,
                    config=config,
                    retrieved_context=retrieved_context,
                    context_budget_tokens=int(
                        os.getenv("AUTOPACK_CONTEXT_BUDGET_TOKENS_AGGRESSIVE", "80000")
                    ),
                )
                full_prompt_text = system_prompt + "\n" + user_prompt
                estimated_prompt_tokens = estimate_tokens(full_prompt_text)

            # BUILD-142: Store selected_budget (estimator intent) BEFORE P4 enforcement
            # This ensures telemetry records the category-aware budget decision, not the final ceiling
            if token_selected_budget:
                phase_spec.setdefault("metadata", {}).setdefault("token_prediction", {})[
                    "selected_budget"
                ] = token_selected_budget

            # BUILD-129 Phase 3 P4+P8: Final enforcement of max_tokens before API call
            # Ensures max_tokens >= token_selected_budget even after all overrides (builder_mode, change_size, etc)
            if token_selected_budget:
                max_tokens = max(max_tokens or 0, token_selected_budget)
                # BUILD-142: Store actual_max_tokens (final ceiling) AFTER P4 enforcement
                phase_spec.setdefault("metadata", {}).setdefault("token_prediction", {})[
                    "actual_max_tokens"
                ] = max_tokens
                logger.info(
                    f"[BUILD-129:P4] Final max_tokens enforcement: {max_tokens} (token_selected_budget={token_selected_budget})"
                )

            # Call Anthropic API with streaming for long operations
            # Use Claude's max output capacity (64K) to avoid truncation of large patches
            # Enable streaming to avoid 10-minute timeout for complex generations
            with self.client.messages.stream(
                model=model,
                max_tokens=min(max_tokens or 64000, 64000),
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=0.2,
            ) as stream:
                # Collect streaming response
                content = ""
                for text in stream.text_stream:
                    content += text

                # Get final message for token usage
                response = stream.get_final_message()

            # BUILD-043: Comprehensive token budget logging
            actual_input_tokens = response.usage.input_tokens
            actual_output_tokens = response.usage.output_tokens
            total_tokens_used = actual_input_tokens + actual_output_tokens
            output_utilization = (actual_output_tokens / max_tokens * 100) if max_tokens else 0

            logger.info(
                f"[TOKEN_BUDGET] phase={phase_id} complexity={complexity} "
                f"input={actual_input_tokens} output={actual_output_tokens}/{max_tokens} "
                f"total={total_tokens_used} utilization={output_utilization:.1f}% "
                f"model={model}"
            )

            # Track truncation (stop_reason from Anthropic API)
            stop_reason = getattr(response, "stop_reason", None)
            was_truncated = stop_reason == "max_tokens"

            # BUILD-129 Phase 3 P10: Store utilization and actual tokens for escalate-once logic
            # Store in metadata so autonomous_executor can decide whether to escalate
            token_budget_metadata = phase_spec.setdefault("metadata", {}).setdefault(
                "token_budget", {}
            )
            token_budget_metadata["output_utilization"] = output_utilization
            token_budget_metadata["actual_output_tokens"] = (
                actual_output_tokens  # For P10 base calculation
            )

            if was_truncated:
                logger.warning("[Builder] Output was truncated (stop_reason=max_tokens)")
                logger.warning(
                    f"[TOKEN_BUDGET] TRUNCATION: phase={phase_id} used {actual_output_tokens}/{max_tokens} tokens "
                    f"(100% utilization) - consider increasing max_tokens for this complexity level"
                )
            elif output_utilization >= 95.0:
                logger.warning(
                    f"[TOKEN_BUDGET] HIGH UTILIZATION: phase={phase_id} used {actual_output_tokens}/{max_tokens} tokens "
                    f"({output_utilization:.1f}% utilization) - may benefit from escalation on retry"
                )

            format_error_codes = {
                "full_file_parse_failed_diff_detected",
                "full_file_schema_invalid",
                "full_file_parse_failed",
            }

            def _parse_once(text: str):
                if use_ndjson_format:
                    return self._parse_ndjson_output(
                        text,
                        file_context,
                        response,
                        model,
                        phase_spec,
                        config=config,
                        stop_reason=stop_reason,
                        was_truncated=was_truncated,
                    )
                elif use_structured_edit:
                    return self._parse_structured_edit_output(
                        text,
                        file_context,
                        response,
                        model,
                        phase_spec,
                        config=config,
                        stop_reason=stop_reason,
                        was_truncated=was_truncated,
                    )
                elif use_full_file_mode_flag:
                    return self._parse_full_file_output(
                        text,
                        file_context,
                        response,
                        model,
                        phase_spec,
                        config=config,
                        stop_reason=stop_reason,
                        was_truncated=was_truncated,
                    )
                else:
                    return self._parse_legacy_diff_output(
                        text, response, model, stop_reason=stop_reason, was_truncated=was_truncated
                    )

            result = _parse_once(content)

            # BUILD-129 Phase 2: Continuation-based recovery for truncated outputs
            # NOTE: Skip continuation for NDJSON mode. NDJSON is already truncation-tolerant and continuation
            # merging can produce invalid mixed-format output (e.g., JSON lists) that breaks NDJSON parsing.
            if was_truncated and deliverables and not use_ndjson_format:
                logger.info("[BUILD-129] Truncation detected, attempting continuation recovery...")
                try:
                    recovery = ContinuationRecovery()
                    continuation_context = recovery.detect_truncation_context(
                        raw_output=content,
                        deliverables=deliverables,
                        stop_reason=stop_reason,
                        tokens_used=actual_output_tokens,
                    )

                    if continuation_context:
                        logger.info(
                            f"[BUILD-129] Continuation context: {len(continuation_context.completed_files)} completed, "
                            f"{len(continuation_context.remaining_deliverables)} remaining, format={continuation_context.format_type}"
                        )

                        # Build continuation prompt
                        continuation_prompt = recovery.build_continuation_prompt(
                            continuation_context,
                            user_prompt,  # Original prompt from earlier in this method
                        )

                        # BUILD-129 Phase 3 P4: Enforce max_tokens before continuation
                        if token_selected_budget:
                            max_tokens = max(max_tokens or 0, token_selected_budget)
                            logger.info(
                                f"[BUILD-129:P4] Continuation max_tokens enforcement: {max_tokens}"
                            )

                        # Execute continuation request
                        logger.info(
                            f"[BUILD-129] Executing continuation request for {len(continuation_context.remaining_deliverables)} remaining deliverables..."
                        )
                        with self.client.messages.stream(
                            model=model,
                            max_tokens=min(max_tokens or 64000, 64000),
                            system=system_prompt,
                            messages=[{"role": "user", "content": continuation_prompt}],
                            temperature=0.2,
                        ) as cont_stream:
                            continuation_content = ""
                            for text in cont_stream.text_stream:
                                continuation_content += text

                            continuation_response = cont_stream.get_final_message()

                        # Log continuation token usage
                        cont_input_tokens = continuation_response.usage.input_tokens
                        cont_output_tokens = continuation_response.usage.output_tokens
                        logger.info(
                            f"[BUILD-129] Continuation tokens: input={cont_input_tokens} output={cont_output_tokens}"
                        )

                        # Merge outputs
                        merged_content = recovery.merge_outputs(
                            partial_output=content,
                            continuation_output=continuation_content,
                            format_type=continuation_context.format_type,
                        )

                        logger.info(
                            f"[BUILD-129] Merged output: original={len(content)} chars, "
                            f"continuation={len(continuation_content)} chars, merged={len(merged_content)} chars"
                        )

                        # Re-parse merged output
                        result = _parse_once(merged_content)

                        # Update token usage to include continuation
                        if result and result.tokens_used:
                            result.tokens_used = (
                                actual_input_tokens
                                + actual_output_tokens
                                + cont_input_tokens
                                + cont_output_tokens
                            )

                        logger.info(
                            "[BUILD-129] Continuation recovery complete, re-parsed merged output"
                        )
                    else:
                        logger.warning(
                            "[BUILD-129] Truncation detected but no continuation context extracted"
                        )

                except Exception as e:
                    logger.error(f"[BUILD-129] Continuation recovery failed: {e}", exc_info=True)
                    # Fall through to original result if continuation fails

            # Adaptive churn relaxation: if only churn_limit_exceeded and small scope, retry once with relaxed threshold
            if (
                result is not None
                and not result.success
                and isinstance(result.error, str)
                and "churn_limit_exceeded" in result.error
                and file_context
            ):
                files = file_context.get("existing_files", {})
                scope_cfg = phase_spec.get("scope") or {}
                scope_paths = scope_cfg.get("paths", []) if isinstance(scope_cfg, dict) else []
                scope_paths = [p for p in scope_paths if isinstance(p, str)]
                # Small-scope heuristic: only when ≤6 scoped paths and all files ≤ hard limit
                small_scope = len(scope_paths) <= 6
                if small_scope and isinstance(files, dict):
                    all_small = True
                    for fp, fc in files.items():
                        if isinstance(fp, str) and any(fp.startswith(sp) for sp in scope_paths):
                            if isinstance(fc, str):
                                line_count = fc.count("\n") + 1
                                if line_count > config.max_lines_hard_limit:
                                    all_small = False
                                    break
                    if all_small:
                        # Relax churn threshold for this parse retry
                        relaxed_config = copy.deepcopy(config)
                        relaxed_config.max_churn_percent_for_small_fix = max(
                            config.max_churn_percent_for_small_fix, 60
                        )
                        logger.warning(
                            "[Builder] Relaxing small-fix churn guard to %s%% for this phase/run (single retry)",
                            relaxed_config.max_churn_percent_for_small_fix,
                        )
                        # Add prompt nudge for minimal change
                        correction_content = content + (
                            "\n\n# CHURN CORRECTION\n"
                            "Minimize changes; only add the necessary import/path fix. Keep churn under 60%."
                        )
                        try:
                            return self._parse_full_file_output(
                                correction_content,
                                file_context,
                                response,
                                model,
                                phase_spec,
                                config=relaxed_config,
                                stop_reason=stop_reason,
                                was_truncated=was_truncated,
                            )
                        except Exception:
                            # Fall through to original result if retry parse fails
                            pass

            # BUILD-129 Phase 1+: Token estimation telemetry
            # NOTE: This compares TokenEstimator's predicted *output* tokens to actual *output* tokens.
            if result and phase_spec:
                predicted_output_tokens = None
                if isinstance(token_estimate, object) and token_estimate is not None:
                    predicted_output_tokens = getattr(token_estimate, "estimated_tokens", None)
                if not predicted_output_tokens:
                    predicted_output_tokens = phase_spec.get("_estimated_output_tokens")

                actual_out = actual_output_tokens if "actual_output_tokens" in locals() else None
                stop_reason_local = stop_reason if "stop_reason" in locals() else None
                was_truncated_local = was_truncated if "was_truncated" in locals() else None

                if predicted_output_tokens and actual_out:
                    # Symmetric error (SMAPE-like) avoids metric bias toward overestimation.
                    denom = max(1, (abs(actual_out) + abs(predicted_output_tokens)) / 2)
                    smape = abs(actual_out - predicted_output_tokens) / denom

                    logger.info(
                        "[TokenEstimationV2] predicted_output=%s actual_output=%s smape=%.1f%% "
                        "selected_budget=%s category=%s complexity=%s deliverables=%s success=%s "
                        "stop_reason=%s truncated=%s model=%s",
                        predicted_output_tokens,
                        actual_out,
                        smape * 100.0,
                        token_selected_budget
                        or phase_spec.get("metadata", {})
                        .get("token_prediction", {})
                        .get("selected_budget"),
                        task_category or "implementation",
                        complexity,
                        len(deliverables) if isinstance(deliverables, list) else 0,
                        getattr(result, "success", None),
                        stop_reason_local,
                        was_truncated_local,
                        model,
                    )

                    # BUILD-129 Phase 3: Write telemetry to DB for validation
                    token_pred_meta = phase_spec.get("metadata", {}).get("token_prediction", {})
                    _write_token_estimation_v2_telemetry(
                        run_id=phase_spec.get("run_id", "unknown"),
                        phase_id=phase_spec.get("phase_id", "unknown"),
                        # BUILD-129 Phase 3 P5: Use estimated_category from token estimator
                        category=token_pred_meta.get("estimated_category")
                        or task_category
                        or "implementation",
                        complexity=complexity,
                        deliverables=deliverables if isinstance(deliverables, list) else [],
                        predicted_output_tokens=predicted_output_tokens,
                        actual_output_tokens=actual_out,
                        # BUILD-142: Record estimator intent (selected_budget), not final ceiling (actual_max_tokens)
                        # This preserves category-aware budget decisions in telemetry for calibration
                        selected_budget=token_pred_meta.get("selected_budget")
                        or token_selected_budget
                        or 0,
                        success=getattr(result, "success", False),
                        truncated=was_truncated_local or False,
                        stop_reason=stop_reason_local,
                        model=model,
                        # BUILD-129 Phase 3: Feature tracking
                        is_truncated_output=was_truncated_local or False,
                        api_reference_required=token_pred_meta.get("api_reference_required"),
                        examples_required=token_pred_meta.get("examples_required"),
                        research_required=token_pred_meta.get("research_required"),
                        usage_guide_required=token_pred_meta.get("usage_guide_required"),
                        context_quality=token_pred_meta.get("context_quality"),
                        # BUILD-129 Phase 3 P3: SOT file tracking
                        is_sot_file=token_pred_meta.get("is_sot_file"),
                        sot_file_name=token_pred_meta.get("sot_file_name"),
                        sot_entry_count_hint=token_pred_meta.get("sot_entry_count_hint"),
                        # BUILD-142 PARITY: Final ceiling after P4 enforcement
                        actual_max_tokens=token_pred_meta.get("actual_max_tokens"),
                    )
                elif predicted_output_tokens and result.tokens_used:
                    # Fallback: if we don't have output tokens separately, log total tokens
                    logger.info(
                        "[TokenEstimationV2] predicted_output=%s actual_total=%s "
                        "selected_budget=%s category=%s complexity=%s deliverables=%s success=%s model=%s",
                        predicted_output_tokens,
                        result.tokens_used,
                        token_selected_budget
                        or phase_spec.get("metadata", {})
                        .get("token_prediction", {})
                        .get("selected_budget"),
                        task_category or "implementation",
                        complexity,
                        len(deliverables) if isinstance(deliverables, list) else 0,
                        getattr(result, "success", None),
                        model,
                    )

                    # BUILD-129 Phase 3: Write telemetry to DB (fallback case)
                    token_pred_meta_fallback = phase_spec.get("metadata", {}).get(
                        "token_prediction", {}
                    )
                    _write_token_estimation_v2_telemetry(
                        run_id=phase_spec.get("run_id", "unknown"),
                        phase_id=phase_spec.get("phase_id", "unknown"),
                        # BUILD-129 Phase 3 P5: Use estimated_category from token estimator
                        category=token_pred_meta_fallback.get("estimated_category")
                        or task_category
                        or "implementation",
                        complexity=complexity,
                        deliverables=deliverables if isinstance(deliverables, list) else [],
                        predicted_output_tokens=predicted_output_tokens,
                        actual_output_tokens=result.tokens_used,  # Using total tokens as fallback
                        # BUILD-142: Record estimator intent (selected_budget), not final ceiling (actual_max_tokens)
                        # This preserves category-aware budget decisions in telemetry for calibration
                        selected_budget=token_pred_meta_fallback.get("selected_budget")
                        or token_selected_budget
                        or 0,
                        success=getattr(result, "success", False),
                        truncated=False,  # Unknown in fallback
                        stop_reason=None,
                        model=model,
                        # BUILD-129 Phase 3: Feature tracking (fallback)
                        is_truncated_output=False,  # Unknown in fallback
                        api_reference_required=token_pred_meta_fallback.get(
                            "api_reference_required"
                        ),
                        examples_required=token_pred_meta_fallback.get("examples_required"),
                        research_required=token_pred_meta_fallback.get("research_required"),
                        usage_guide_required=token_pred_meta_fallback.get("usage_guide_required"),
                        context_quality=token_pred_meta_fallback.get("context_quality"),
                        # BUILD-129 Phase 3 P3: SOT file tracking (fallback)
                        is_sot_file=token_pred_meta_fallback.get("is_sot_file"),
                        sot_file_name=token_pred_meta_fallback.get("sot_file_name"),
                        sot_entry_count_hint=token_pred_meta_fallback.get("sot_entry_count_hint"),
                        # BUILD-142 PARITY: Final ceiling after P4 enforcement
                        actual_max_tokens=token_pred_meta_fallback.get("actual_max_tokens"),
                    )

            return result

        except Exception as e:
            # Log full traceback for debugging (critical to diagnose silent failures)
            import traceback

            error_traceback = traceback.format_exc()
            error_msg = str(e)
            logger.error(
                "[Builder] Unhandled exception during execute_phase: %s\nTraceback:\n%s",
                error_msg,
                error_traceback,
            )

            # Retry once on "prompt too long" with minimal context budget.
            msg_l = error_msg.lower()
            if "prompt is too long" in msg_l or (
                "tokens" in msg_l and "maximum" in msg_l and "too long" in msg_l
            ):
                try:
                    logger.warning(
                        "[PROMPT_BUDGET] Provider rejected prompt as too long; retrying with minimal context."
                    )
                    user_prompt_retry = self._build_user_prompt(
                        phase_spec,
                        file_context,
                        project_rules,
                        run_hints,
                        use_full_file_mode=use_full_file_mode_flag,
                        config=config,
                        retrieved_context=retrieved_context,
                        context_budget_tokens=int(
                            os.getenv("AUTOPACK_CONTEXT_BUDGET_TOKENS_MINIMAL", "50000")
                        ),
                    )

                    # BUILD-129 Phase 3 P4: Enforce max_tokens before retry
                    if token_selected_budget:
                        max_tokens = max(max_tokens or 0, token_selected_budget)
                        logger.info(f"[BUILD-129:P4] Retry max_tokens enforcement: {max_tokens}")

                    with self.client.messages.stream(
                        model=model,
                        max_tokens=min(max_tokens or 64000, 64000),
                        system=system_prompt,
                        messages=[{"role": "user", "content": user_prompt_retry}],
                        temperature=0.2,
                    ) as stream:
                        retry_content = ""
                        for text in stream.text_stream:
                            retry_content += text
                        retry_response = stream.get_final_message()

                    retry_stop_reason = getattr(retry_response, "stop_reason", None)
                    retry_was_truncated = retry_stop_reason == "max_tokens"

                    if use_ndjson_format:
                        return self._parse_ndjson_output(
                            retry_content,
                            file_context,
                            retry_response,
                            model,
                            phase_spec,
                            config=config,
                            stop_reason=retry_stop_reason,
                            was_truncated=retry_was_truncated,
                        )
                    if use_structured_edit:
                        return self._parse_structured_edit_output(
                            retry_content,
                            file_context,
                            retry_response,
                            model,
                            phase_spec,
                            config=config,
                            stop_reason=retry_stop_reason,
                            was_truncated=retry_was_truncated,
                        )
                    if use_full_file_mode_flag:
                        return self._parse_full_file_output(
                            retry_content,
                            file_context,
                            retry_response,
                            model,
                            phase_spec,
                            config=config,
                            stop_reason=retry_stop_reason,
                            was_truncated=retry_was_truncated,
                        )
                    return self._parse_legacy_diff_output(
                        retry_content,
                        retry_response,
                        model,
                        stop_reason=retry_stop_reason,
                        was_truncated=retry_was_truncated,
                    )
                except Exception as retry_exc:
                    logger.warning(f"[PROMPT_BUDGET] Minimal-context retry failed: {retry_exc}")

            # Check if this is the Path/list error we're tracking
            if "unsupported operand type(s) for /" in error_msg and "list" in error_msg:
                logger.error(
                    f"[Builder] Path/list TypeError detected:\n{error_msg}\nTraceback:\n{error_traceback}"
                )

            # Return error result
            return BuilderResult(
                success=False,
                patch_content="",
                builder_messages=[f"Builder error: {error_msg}"],
                tokens_used=0,
                model_used=model,
                error=error_msg,
            )

    def _extract_diff_from_text(self, text: str) -> str:
        """Extract git diff content from text that may contain explanations.

        Args:
            text: Raw text that may contain diff content

        Returns:
            Extracted diff content or empty string
        """
        import re

        lines = text.split("\n")
        diff_lines = []
        in_diff = False

        for line in lines:
            # Start of diff
            if line.startswith("diff --git"):
                in_diff = True
                diff_lines.append(line)
            # Continuation of diff
            elif in_diff:
                # Clean up malformed hunk headers (remove trailing context)
                if line.startswith("@@"):
                    # Extract the valid hunk header part only
                    match = re.match(r"^(@@\s+-\d+,\d+\s+\+\d+,\d+\s+@@)", line)
                    if match:
                        # Use only the valid hunk header, discard anything after
                        clean_line = match.group(1)
                        diff_lines.append(clean_line)
                    else:
                        # Malformed hunk header, skip it
                        logger.warning(f"Skipping malformed hunk header: {line[:80]}")
                        continue
                # Check if still in diff (various diff markers)
                elif (
                    line.startswith(("index ", "---", "+++", "+", "-", " "))
                    or line.startswith("new file mode")
                    or line.startswith("deleted file mode")
                    or line.startswith("similarity index")
                    or line.startswith("rename from")
                    or line.startswith("rename to")
                    or line == ""
                ):
                    diff_lines.append(line)
                # Next diff section
                elif line.startswith("diff --git"):
                    diff_lines.append(line)
                # End of diff (explanatory text or other content)
                else:
                    # Stop if we hit markdown fence or explanatory text
                    if line.startswith("```") or line.startswith("#"):
                        break

        return "\n".join(diff_lines) if diff_lines else ""

    def _parse_full_file_output(
        self,
        content: str,
        file_context: Optional[Dict],
        response,
        model: str,
        phase_spec: Optional[Dict] = None,
        config=None,  # NEW: BuilderOutputConfig for thresholds
        stop_reason: Optional[str] = None,  # NEW: Anthropic stop_reason
        was_truncated: bool = False,  # NEW: Truncation flag
    ) -> "BuilderResult":
        """Parse full-file replacement output and generate git diff locally.

        Per GPT_RESPONSE10: LLM outputs complete file content, we generate diff.
        Per GPT_RESPONSE11: Added guards for large files, churn, and symbol validation.
        Per IMPLEMENTATION_PLAN2.md Phase 4: Added read-only enforcement and shrinkage/growth detection.

        Args:
            content: Raw LLM output (should be JSON)
            file_context: Original file contents for diff generation
            response: API response object for token usage
            model: Model identifier
            phase_spec: Phase specification for churn classification
            config: BuilderOutputConfig for thresholds (per IMPLEMENTATION_PLAN2.md)

        Returns:
            BuilderResult with generated patch
        """
        # Load config if not provided
        if config is None:
            from autopack.builder_config import BuilderOutputConfig

            config = BuilderOutputConfig()

        def _escape_newlines_in_json_strings(raw: str) -> str:
            """
            Make JSON more robust by escaping bare newlines inside string literals.

            Some models emit multi-line strings with literal newlines inside quotes,
            which is invalid JSON and causes 'Unterminated string' errors.
            This helper walks the text and replaces '\n' with '\\n' only while
            inside a JSON string, preserving semantics but making the JSON valid.
            """
            out: list[str] = []
            in_string = False
            escape = False

            for ch in raw:
                if not in_string:
                    if ch == '"':
                        in_string = True
                    out.append(ch)
                    continue

                # We are inside a string
                if escape:
                    out.append(ch)
                    escape = False
                    continue

                if ch == "\\":
                    out.append(ch)
                    escape = True
                elif ch == '"':
                    out.append(ch)
                    in_string = False
                elif ch == "\n":
                    out.append("\\n")
                else:
                    out.append(ch)

            return "".join(out)

        def _attempt_json_parse(candidate: Optional[str]) -> Optional[Dict[str, Any]]:
            if not candidate:
                return None
            try:
                return json.loads(candidate.strip())
            except json.JSONDecodeError:
                repaired = _escape_newlines_in_json_strings(candidate.strip())
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    return None

        def _decode_placeholder_string(raw_segment: str) -> str:
            """Decode a pseudo-JSON string segment without trusting malformed escapes."""
            result_chars: list[str] = []
            idx = 0
            length = len(raw_segment)

            while idx < length:
                ch = raw_segment[idx]
                if ch == "\\" and idx + 1 < length:
                    nxt = raw_segment[idx + 1]
                    if nxt == "n":
                        result_chars.append("\n")
                        idx += 2
                        continue
                    if nxt == "r":
                        result_chars.append("\r")
                        idx += 2
                        continue
                    if nxt == "t":
                        result_chars.append("\t")
                        idx += 2
                        continue
                    if nxt in ('"', "\\", "/"):
                        result_chars.append(nxt)
                        idx += 2
                        continue
                    if nxt == "u" and idx + 5 < length:
                        hex_value = raw_segment[idx + 2 : idx + 6]
                        try:
                            result_chars.append(chr(int(hex_value, 16)))
                            idx += 6
                            continue
                        except ValueError:
                            # Fall back to literal output
                            result_chars.append("\\")
                            idx += 1
                            continue
                    # Unknown escape - keep the backslash and reprocess next char normally
                    result_chars.append("\\")
                    idx += 1
                    continue

                result_chars.append(ch)
                idx += 1

            return "".join(result_chars)

        def _sanitize_full_file_output(raw_text: Optional[str]) -> tuple[str, Dict[str, str]]:
            """
            Replace problematic new_content blobs with safe placeholders so json.loads succeeds.
            Returns sanitized text plus a mapping of placeholder -> raw segment.
            """
            if not raw_text or '"new_content":"' not in raw_text:
                return raw_text or "", {}

            placeholders: Dict[str, str] = {}
            output_chars: list[str] = []
            idx = 0
            placeholder_idx = 0
            target = raw_text

            sentinel = '"new_content":"'

            while idx < len(target):
                if target.startswith(sentinel, idx):
                    output_chars.append(sentinel)
                    idx += len(sentinel)
                    segment_chars: list[str] = []

                    while idx < len(target):
                        ch = target[idx]

                        # Preserve escaped sequences verbatim
                        if ch == "\\" and idx + 1 < len(target):
                            segment_chars.append(target[idx : idx + 2])
                            idx += 2
                            continue

                        if ch == '"':
                            probe = idx + 1
                            while probe < len(target) and target[probe] in " \t\r\n":
                                probe += 1
                            if probe < len(target) and target[probe] == "}":
                                probe2 = probe + 1
                                while probe2 < len(target) and target[probe2] in " \t\r\n":
                                    probe2 += 1
                                if probe2 >= len(target) or target[probe2] in ",]}":
                                    break

                        segment_chars.append(ch)
                        idx += 1

                    content_raw = "".join(segment_chars)
                    placeholder = f"__FULLFILE_CONTENT_{placeholder_idx}__"
                    placeholder_idx += 1
                    placeholders[placeholder] = content_raw
                    output_chars.append(placeholder)
                    output_chars.append('"')

                    if idx < len(target) and target[idx] == '"':
                        idx += 1
                    continue

                    output_chars.append(target[idx])
                    idx += 1

                else:
                    output_chars.append(target[idx])
                    idx += 1

            return "".join(output_chars), placeholders

        def _balance_json_brackets(raw_text: str) -> str:
            """
            Ensure any unterminated braces/brackets are closed in LIFO order.
            Helps when the LLM truncates output before emitting final ]}.
            """
            stack: list[str] = []
            in_string = False
            escape = False

            for ch in raw_text:
                if in_string:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_string = False
                    continue

                if ch == '"':
                    in_string = True
                elif ch == "{":
                    stack.append("}")
                elif ch == "[":
                    stack.append("]")
                elif ch in ("}", "]"):
                    if stack and stack[-1] == ch:
                        stack.pop()

            if not stack:
                return raw_text

            # Append missing closers in reverse order (LIFO)
            closing = "".join(reversed(stack))
            return raw_text + closing

        def _restore_placeholder_content(
            payload: Dict[str, Any], placeholder_map: Dict[str, str]
        ) -> None:
            files = payload.get("files")
            if not isinstance(files, list):
                return

            for file_entry in files:
                if not isinstance(file_entry, dict):
                    continue
                content = file_entry.get("new_content")
                if isinstance(content, str) and content in placeholder_map:
                    raw_segment = placeholder_map[content]
                    file_entry["new_content"] = _decode_placeholder_string(raw_segment)

        def _extract_code_fence(raw_text: str, fence: str) -> Optional[str]:
            start = raw_text.find(fence)
            if start == -1:
                return None
            start += len(fence)
            end = raw_text.find("```", start)
            if end == -1:
                return None
            return raw_text[start:end].strip()

        def _extract_first_json_object(raw_text: str) -> Optional[str]:
            start = raw_text.find("{")
            if start == -1:
                return None
            depth = 0
            in_string = False
            escape = False
            for idx in range(start, len(raw_text)):
                ch = raw_text[idx]
                if in_string:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_string = False
                    continue
                if ch == '"':
                    in_string = True
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return raw_text[start : idx + 1]
            return None

        try:
            # Try to parse JSON directly, with newline repair fallback
            result_json: Optional[Dict[str, Any]] = None
            placeholder_map: Dict[str, str] = {}
            raw = content.strip()

            candidates: list[str] = [raw]

            # Format guard: if the raw output looks like a git diff, bail out early
            # and request regeneration instead of trying to parse/apply malformed diffs.
            if "diff --git" in raw and "{" not in raw:  # heuristic: no JSON object present
                error_msg = (
                    "Detected git diff output; expected JSON with 'files' array. "
                    "Regenerate a JSON full-file response (no diff, no markdown fences)."
                )
                logger.error(error_msg)
                return BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=[error_msg],
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                    prompt_tokens=response.usage.input_tokens,
                    completion_tokens=response.usage.output_tokens,
                    model_used=model,
                    error="full_file_parse_failed_diff_detected",
                )
            if "```json" in content:
                fenced = _extract_code_fence(content, "```json")
                if fenced:
                    candidates.append(fenced)
            if "```" in content:
                fenced_generic = _extract_code_fence(content, "```")
                if fenced_generic:
                    candidates.append(fenced_generic)
            extracted = _extract_first_json_object(raw)
            if extracted:
                candidates.append(extracted)

            for candidate in candidates:
                sanitized_candidate, placeholders = _sanitize_full_file_output(candidate)
                balanced_candidate = _balance_json_brackets(sanitized_candidate)
                result_json = _attempt_json_parse(balanced_candidate)
                if result_json:
                    placeholder_map = placeholders
                    break

            if not result_json:
                # Do NOT fall back to legacy git-diff; request regeneration instead
                logger.warning(
                    "[Builder] WARNING: Full-file JSON parse failed; requesting regeneration (no legacy diff fallback)"
                )
                debug_path = Path("builder_fullfile_failure_latest.json")
                try:
                    debug_path.write_text(content, encoding="utf-8")
                    logger.warning(f"[Builder] Wrote failing full-file output to {debug_path}")
                except Exception as write_exc:
                    logger.error(f"[Builder] Failed to write debug output: {write_exc}")
                # Attempt JSON repair before giving up (per ref2.md recommendations)
                logger.info("[Builder] Attempting JSON repair on malformed output...")
                json_repair = JsonRepairHelper()
                initial_error = "Failed to parse JSON with 'files' array"
                repaired_json, repair_method = json_repair.attempt_repair(content, initial_error)

                if repaired_json is not None:
                    logger.info(f"[Builder] JSON repair succeeded via {repair_method}")
                    # Save debug info for telemetry
                    save_repair_debug(
                        file_path="builder_output.json",
                        original="",
                        attempted=content,
                        repaired=json.dumps(repaired_json),
                        error=initial_error,
                        method=repair_method,
                    )
                    # Use the repaired JSON
                    result_json = repaired_json
                    placeholder_map = {}  # Placeholders already processed in raw content
                else:
                    # Save failed repair attempt for debugging
                    save_repair_debug(
                        file_path="builder_output.json",
                        original="",
                        attempted=content,
                        repaired=None,
                        error=initial_error,
                        method=repair_method,
                    )
                    error_msg = "LLM output invalid format - expected JSON with 'files' array (repair also failed)"
                    # Include truncation info so autonomous_executor can trigger structured_edit fallback
                    if was_truncated:
                        error_msg += " (stop_reason=max_tokens)"
                    logger.error(f"{error_msg}\nFirst 500 chars: {content[:500]}")
                    return BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[
                            error_msg,
                            "Regenerate a valid JSON full-file response; diff fallback is disabled.",
                        ],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        model_used=model,
                        error=(
                            "full_file_parse_failed"
                            if not was_truncated
                            else "full_file_parse_failed (stop_reason=max_tokens)"
                        ),
                        stop_reason=stop_reason,
                        was_truncated=was_truncated,
                    )

            summary = result_json.get("summary", "Generated by Claude")
            if placeholder_map:
                _restore_placeholder_content(result_json, placeholder_map)
            files = result_json.get("files", [])

            if not files:
                error_msg = "LLM returned empty files array"
                if was_truncated:
                    error_msg += " (stop_reason=max_tokens)"
                return BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=[error_msg],
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                    prompt_tokens=response.usage.input_tokens,
                    completion_tokens=response.usage.output_tokens,
                    model_used=model,
                    error=error_msg,
                    stop_reason=stop_reason,
                    was_truncated=was_truncated,
                )

            # Schema validation for file entries
            required_keys = {"path", "mode", "new_content"}
            for entry in files:
                if not isinstance(entry, dict) or not required_keys.issubset(entry.keys()):
                    error_msg = (
                        "LLM output invalid format - each file entry must include "
                        "`path`, `mode`, and `new_content`. Regenerate JSON."
                    )
                    if was_truncated:
                        error_msg += " (stop_reason=max_tokens)"
                    logger.error(f"{error_msg}\nFirst 500 chars: {content[:500]}")
                    return BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[error_msg],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        model_used=model,
                        error=(
                            "full_file_schema_invalid"
                            if not was_truncated
                            else "full_file_schema_invalid (stop_reason=max_tokens)"
                        ),
                        stop_reason=stop_reason,
                        was_truncated=was_truncated,
                    )

            # Determine change type for churn validation (per GPT_RESPONSE11 Q4)
            change_type = self._classify_change_type(phase_spec)

            # Generate unified diff for each file
            diff_parts = []
            attempted_file_paths = []  # BUILD-141 Part 8: Track files Builder attempted to modify
            existing_files = {}
            if file_context:
                existing_files = file_context.get("existing_files", file_context)
                # Safety check: ensure existing_files is a dict
                if not isinstance(existing_files, dict):
                    existing_files = {}

            def _validate_pack_fullfile(file_path: str, content: str) -> Optional[str]:
                """
                Lightweight preflight for pack YAMLs in full-file mode.
                Reject obviously incomplete/truncated outputs before diff generation so the Builder can retry.
                """
                if not (file_path.endswith((".yaml", ".yml")) and "backend/packs/" in file_path):
                    return None

                stripped = content.lstrip()
                if not stripped:
                    return f"pack_fullfile_empty: {file_path} returned empty content"

                # YAML allows comments (#) before document marker (---) or keys
                # The --- document marker is optional in YAML, so we don't enforce it
                lines = stripped.split("\n")

                # Check that required top-level keys appear in the first ~50 lines
                # This catches patches that only include partial content
                first_lines = "\n".join(lines[:50])
                required_top_level = ["name:", "description:", "version:", "country:", "domain:"]
                missing_top = [k for k in required_top_level if k not in first_lines]
                if missing_top:
                    return (
                        f"pack_fullfile_incomplete_header: {file_path} is missing top-level keys in header: {', '.join(missing_top)}. "
                        f"First 200 chars: {stripped[:200]}... "
                        "You must emit the COMPLETE YAML file with ALL top-level keys, not a patch."
                    )

                # Check that required sections appear somewhere in the file
                required_sections = ["categories:", "official_sources:"]
                missing_sections = [s for s in required_sections if s not in content]
                if missing_sections:
                    return (
                        f"pack_fullfile_missing_sections: {file_path} missing required sections: {', '.join(missing_sections)}. "
                        "You must emit the COMPLETE YAML file with all required sections."
                    )

                return None

            for file_entry in files:
                file_path = file_entry.get("path", "")
                mode = file_entry.get("mode", "modify")
                new_content = file_entry.get("new_content", "")

                if not file_path:
                    continue

                # BUILD-141 Part 8: Track attempted file paths for no-op detection
                attempted_file_paths.append(file_path)

                # Get original content
                old_content = existing_files.get(file_path, "")
                old_line_count = old_content.count("\n") + 1 if old_content else 0
                new_line_count = new_content.count("\n") + 1 if new_content else 0

                # Pack YAML preflight validation (per ref2.md - pack quality improvements)
                pack_validation_error = _validate_pack_fullfile(file_path, new_content)
                if pack_validation_error:
                    logger.error(f"[Builder] {pack_validation_error}")
                    return BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[pack_validation_error],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        model_used=model,
                        error=pack_validation_error,
                    )

                # ============================================================================
                # NEW: Read-only file enforcement (per IMPLEMENTATION_PLAN2.md Phase 4.1)
                # This is the PARSER-LEVEL enforcement - LLM violated the contract
                # ============================================================================
                if mode == "modify" and old_line_count > config.max_lines_for_full_file:
                    error_msg = (
                        f"readonly_violation: {file_path} has {old_line_count} lines "
                        f"(limit: {config.max_lines_for_full_file}). This file was marked as READ-ONLY CONTEXT. "
                        f"The LLM should not have attempted to modify it."
                    )
                    logger.error(f"[Builder] {error_msg}")

                    # Record telemetry (if available in context)
                    # Note: We don't have run_id/phase_id here, so we log for manual review
                    logger.warning(
                        f"[TELEMETRY] readonly_violation: file={file_path}, lines={old_line_count}, model={model}"
                    )

                    return BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[error_msg],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        model_used=model,
                        error=error_msg,
                    )

                # ============================================================================
                # NEW: Shrinkage detection (per IMPLEMENTATION_PLAN2.md Phase 4.2)
                # Reject >60% shrinkage unless phase allows mass deletion
                # ============================================================================
                if mode == "modify" and old_content and new_content:
                    shrinkage_percent = ((old_line_count - new_line_count) / old_line_count) * 100

                    if shrinkage_percent > config.max_shrinkage_percent:
                        # Check if phase allows mass deletion
                        allow_mass_deletion = (
                            phase_spec.get("allow_mass_deletion", False) if phase_spec else False
                        )

                        if not allow_mass_deletion:
                            error_msg = (
                                f"suspicious_shrinkage: {file_path} shrank by {shrinkage_percent:.1f}% "
                                f"({old_line_count} → {new_line_count} lines). "
                                f"Limit: {config.max_shrinkage_percent}%. "
                                f"This may indicate truncation. Set allow_mass_deletion=true to override."
                            )
                            logger.error(f"[Builder] {error_msg}")
                            logger.warning(
                                f"[TELEMETRY] suspicious_shrinkage: file={file_path}, old={old_line_count}, new={new_line_count}, shrinkage={shrinkage_percent:.1f}%"
                            )

                            return BuilderResult(
                                success=False,
                                patch_content="",
                                builder_messages=[error_msg],
                                tokens_used=response.usage.input_tokens
                                + response.usage.output_tokens,
                                prompt_tokens=response.usage.input_tokens,
                                completion_tokens=response.usage.output_tokens,
                                model_used=model,
                                error=error_msg,
                            )

                # ============================================================================
                # NEW: Growth detection (per IMPLEMENTATION_PLAN2.md Phase 4.2)
                # Reject >3x growth unless phase allows mass addition
                # ============================================================================
                if mode == "modify" and old_content and new_content and old_line_count > 0:
                    growth_multiplier = new_line_count / old_line_count

                    # Optional: skip growth guard for YAML packs where large expansions are expected
                    if getattr(
                        config, "disable_growth_guard_for_yaml", False
                    ) and file_path.endswith((".yaml", ".yml")):
                        logger.info(
                            f"[Builder] Skipping growth guard for YAML file {file_path} (growth {growth_multiplier:.1f}x)"
                        )
                    else:
                        if growth_multiplier > config.max_growth_multiplier:
                            # Check if phase allows mass addition
                            allow_mass_addition = (
                                phase_spec.get("allow_mass_addition", False)
                                if phase_spec
                                else False
                            )

                            if not allow_mass_addition:
                                error_msg = (
                                    f"suspicious_growth: {file_path} grew by {growth_multiplier:.1f}x "
                                    f"({old_line_count} → {new_line_count} lines). "
                                    f"Limit: {config.max_growth_multiplier}x. "
                                    f"This may indicate duplication. Set allow_mass_addition=true to override."
                                )
                                logger.error(f"[Builder] {error_msg}")
                                logger.warning(
                                    f"[TELEMETRY] suspicious_growth: file={file_path}, old={old_line_count}, "
                                    f"new={new_line_count}, growth={growth_multiplier:.1f}x"
                                )

                                return BuilderResult(
                                    success=False,
                                    patch_content="",
                                    builder_messages=[error_msg],
                                    tokens_used=response.usage.input_tokens
                                    + response.usage.output_tokens,
                                    prompt_tokens=response.usage.input_tokens,
                                    completion_tokens=response.usage.output_tokens,
                                    model_used=model,
                                    error=error_msg,
                                )

                # Q4: Churn detection for small fixes
                if mode == "modify" and change_type == "small_fix" and old_content:
                    # Optional: skip small-fix churn guard for YAML packs where high churn is expected
                    if file_path.endswith(("package-lock.json", "yarn.lock", "package.json")):
                        logger.info(
                            f"[Builder] Skipping small-fix churn guard for manifest/lockfile {file_path}"
                        )
                    elif getattr(
                        config, "disable_small_fix_churn_for_yaml", False
                    ) and file_path.endswith((".yaml", ".yml")):
                        logger.info(
                            f"[Builder] Skipping small-fix churn guard for YAML file {file_path}"
                        )
                    else:
                        churn_percent = self._calculate_churn_percent(old_content, new_content)
                        if churn_percent > config.max_churn_percent_for_small_fix:
                            error_msg = f"churn_limit_exceeded: {churn_percent:.1f}% (small_fix limit {config.max_churn_percent_for_small_fix}%) on {file_path}"
                            logger.error(f"[Builder] {error_msg}")
                            return BuilderResult(
                                success=False,
                                patch_content="",
                                builder_messages=[error_msg],
                                tokens_used=response.usage.input_tokens
                                + response.usage.output_tokens,
                                prompt_tokens=response.usage.input_tokens,
                                completion_tokens=response.usage.output_tokens,
                                model_used=model,
                                error=error_msg,
                            )

                # Q5: Symbol validation for small fixes
                if mode == "modify" and change_type == "small_fix" and old_content:
                    missing_symbols = self._check_missing_symbols(
                        old_content, new_content, file_path
                    )
                    if missing_symbols:
                        error_msg = f"symbol_missing_after_full_file_replacement: lost {missing_symbols} in {file_path}"
                        logger.error(f"[Builder] {error_msg}")
                        return BuilderResult(
                            success=False,
                            patch_content="",
                            builder_messages=[error_msg],
                            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                            prompt_tokens=response.usage.input_tokens,
                            completion_tokens=response.usage.output_tokens,
                            model_used=model,
                            error=error_msg,
                        )

                # Generate diff based on mode
                if mode == "delete":
                    # Generate delete diff
                    diff = self._generate_unified_diff(file_path, old_content, "")
                elif mode == "create":
                    # Generate create diff
                    diff = self._generate_unified_diff(file_path, "", new_content)
                else:  # modify
                    # Generate modify diff
                    diff = self._generate_unified_diff(file_path, old_content, new_content)

                if diff:
                    diff_parts.append(diff)

            if not diff_parts:
                # BUILD-141 Part 8: Treat "no diffs" as no-op success if deliverables already exist
                # This handles idempotent phases where Builder generates content matching existing files

                # Check if all attempted files exist on disk
                # If Builder tried to modify files that already match the generated content,
                # this is a successful no-op (idempotent phase)
                from pathlib import Path

                repo_root = Path.cwd()  # Workspace root where autonomous executor runs

                all_files_exist = False
                if attempted_file_paths:
                    existing_count = 0
                    for path in attempted_file_paths:
                        file_path = repo_root / path
                        if file_path.exists() and file_path.is_file():
                            existing_count += 1

                    all_files_exist = existing_count == len(attempted_file_paths)

                if all_files_exist:
                    # Idempotent phase: Builder regenerated content matching existing files
                    # This is a success - treat as no-op
                    no_op_msg = (
                        f"Full-file produced no diffs; treating as no-op success "
                        f"(all {len(attempted_file_paths)} file(s) already exist and match generated content)"
                    )
                    logger.info(f"[Builder] {no_op_msg}")

                    return BuilderResult(
                        success=True,  # Success, not failure!
                        patch_content="",  # Empty patch is OK for no-op
                        builder_messages=[no_op_msg],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        model_used=model,
                        stop_reason=stop_reason,
                        was_truncated=was_truncated,
                    )
                else:
                    # Deliverables don't exist or couldn't be determined - this is a real failure
                    error_msg = "No valid file changes generated"
                    return BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[error_msg],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        model_used=model,
                        error=error_msg,
                    )

            # Join diffs defensively. Some `git apply` versions are picky about
            # patch boundaries; ensure each diff starts on a fresh line and the
            # overall patch ends with a newline to avoid "patch fragment without header".
            patch_content = "\n\n".join(d.rstrip("\n") for d in diff_parts).rstrip("\n") + "\n"
            logger.info(
                f"[Builder] Generated {len(diff_parts)} file diffs locally from full-file content"
            )

            return BuilderResult(
                success=True,
                patch_content=patch_content,
                builder_messages=[summary],
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                model_used=model,
                stop_reason=stop_reason,
                was_truncated=was_truncated,
            )

        except Exception as e:
            error_msg = f"Failed to parse full-file output: {str(e)}"
            logger.error(f"{error_msg}\nFirst 500 chars: {content[:500]}")
            return BuilderResult(
                success=False,
                patch_content="",
                builder_messages=[error_msg],
                tokens_used=(
                    response.usage.input_tokens + response.usage.output_tokens if response else 0
                ),
                model_used=model,
                error=error_msg,
            )

    def _generate_unified_diff(self, file_path: str, old_content: str, new_content: str) -> str:
        """Generate a unified diff from old and new file content.

        Per GPT_RESPONSE10: Generate git-compatible diff locally, not by LLM.
        Per GPT_RESPONSE12 Q3: Fixed format for new/deleted files with /dev/null.

        Args:
            file_path: Path to the file
            old_content: Original file content (empty for new files)
            new_content: New file content (empty for deleted files)

        Returns:
            Unified diff string in git format
        """
        import subprocess
        import tempfile

        from pathlib import Path

        # Determine file mode: new, deleted, or modified
        is_new_file = not old_content and bool(new_content)
        is_deleted_file = bool(old_content) and not new_content

        # Safety: if we think this is a "new file" but it already exists on disk,
        # treat this as a modification instead of emitting `new file mode`.
        # This avoids governed-apply rejecting the patch as unsafe.
        if is_new_file:
            try:
                existing_path = Path(file_path)
                if existing_path.exists():
                    logger.warning(
                        f"[Builder] Diff generation: {file_path} exists but old_content empty; "
                        "treating as modify (not new file mode)"
                    )
                    old_content = existing_path.read_text(encoding="utf-8", errors="ignore")
                    is_new_file = False
                    is_deleted_file = False
            except Exception as e:
                logger.warning(
                    f"[Builder] Diff generation: could not read existing file {file_path} to avoid new-file mode: {e}"
                )

        # Construct git-format diff header (per GPT_RESPONSE12 Q3)
        # Order matters: diff --git, new/deleted file mode, index, ---, +++
        git_header = [f"diff --git a/{file_path} b/{file_path}"]

        if is_new_file:
            git_header.extend(
                [
                    "new file mode 100644",
                    "index 0000000..1111111",
                    "--- /dev/null",
                    f"+++ b/{file_path}",
                ]
            )
        elif is_deleted_file:
            git_header.extend(
                [
                    "deleted file mode 100644",
                    "index 1111111..0000000",
                    f"--- a/{file_path}",
                    "+++ /dev/null",
                ]
            )
        else:
            git_header.extend(
                [
                    "index 1111111..2222222 100644",
                    f"--- a/{file_path}",
                    f"+++ b/{file_path}",
                ]
            )

        # Generate reliable diff body via git --no-index to avoid malformed hunks
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir)
            old_file = temp_dir / "old_file"
            new_file = temp_dir / "new_file"

            old_file.write_text(old_content, encoding="utf-8")
            new_file.write_text(new_content, encoding="utf-8")

            diff_cmd = [
                "git",
                "--no-pager",
                "diff",
                "--no-index",
                "--text",
                "--unified=3",
                "--",
                str(old_file),
                str(new_file),
            ]

            proc = subprocess.run(
                diff_cmd,
                capture_output=True,
                text=False,  # Decode manually to avoid locale-dependent errors
            )

            stderr_text = ""
            if proc.stderr:
                stderr_text = proc.stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode not in (0, 1):
                logger.error(f"[BuilderDiff] git diff failed: {stderr_text}")
                raise RuntimeError("git diff --no-index failed while generating builder patch")

            diff_stdout = proc.stdout.decode("utf-8", errors="replace")
            diff_output = diff_stdout.strip()
            if not diff_output:
                return ""

        diff_lines = diff_output.splitlines()

        # Drop git's own metadata lines (diff --git, index, ---/+++)
        body_lines = []
        started = False
        for line in diff_lines:
            if line.startswith("@@") or started:
                started = True
                body_lines.append(line)

        if not body_lines:
            return ""

        full_diff = git_header + body_lines

        return "\n".join(full_diff)

    def _classify_change_type(self, phase_spec: Optional[Dict]) -> str:
        """Classify whether a phase is a small fix or large refactor.

        Per GPT_RESPONSE11 Q4: Use phase metadata to classify.

        Args:
            phase_spec: Phase specification

        Returns:
            "small_fix" or "large_refactor"
        """
        if not phase_spec:
            return "small_fix"  # Default to conservative

        complexity = phase_spec.get("complexity", "medium")
        num_criteria = len(phase_spec.get("acceptance_criteria", []) or [])
        scope_cfg = phase_spec.get("scope") or {}
        scope_paths = scope_cfg.get("paths", []) if isinstance(scope_cfg, dict) else []
        scope_paths = [p for p in scope_paths if isinstance(p, str)]

        # Scope-driven overrides
        if any("package-lock" in p or "yarn.lock" in p for p in scope_paths):
            return "large_refactor"
        if any("package.json" in p for p in scope_paths):
            return "large_refactor"
        if any("/packs/" in p or p.endswith((".yaml", ".yml")) for p in scope_paths):
            return "large_refactor"

        # Explicit override
        if phase_spec.get("change_size") == "large_refactor":
            return "large_refactor"
        if phase_spec.get("allow_symbol_removal"):
            return "large_refactor"

        # Heuristic per GPT2
        if complexity == "low":
            return "small_fix"
        elif complexity == "medium" and num_criteria <= 3:
            return "small_fix"
        else:
            return "large_refactor"

    def _calculate_churn_percent(self, old_content: str, new_content: str) -> float:
        """Calculate the percentage of lines changed between old and new content.

        Per GPT_RESPONSE11 Q4: Compute churn from patch characteristics.

        Args:
            old_content: Original file content
            new_content: New file content

        Returns:
            Percentage of lines changed (0-100)
        """
        import difflib

        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()

        if not old_lines:
            return 100.0  # All new content

        # Use SequenceMatcher to count changed lines
        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)

        # Count lines that are different
        changed_lines = 0
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                changed_lines += max(i2 - i1, j2 - j1)
            elif tag == "delete":
                changed_lines += i2 - i1
            elif tag == "insert":
                changed_lines += j2 - j1

        churn_percent = 100.0 * changed_lines / max(len(old_lines), 1)
        return churn_percent

    def _check_missing_symbols(
        self, old_content: str, new_content: str, file_path: str
    ) -> Optional[str]:
        """Check if any required top-level symbols are missing after full-file replacement.

        Per GPT_RESPONSE11 Q5: Symbol validation for small fixes.

        Args:
            old_content: Original file content
            new_content: New file content
            file_path: Path to the file (for language detection)

        Returns:
            Comma-separated list of missing symbols, or None if all present
        """
        import re

        # Only validate Python files for now
        if not file_path.endswith(".py"):
            return None

        # Extract top-level function and class definitions
        def extract_symbols(content: str) -> set:
            symbols = set()
            # Match top-level def and class (not indented)
            for match in re.finditer(r"^(def|class)\s+(\w+)", content, re.MULTILINE):
                symbols.add(match.group(2))
            return symbols

        old_symbols = extract_symbols(old_content)
        new_symbols = extract_symbols(new_content)

        # Find missing symbols
        missing = old_symbols - new_symbols

        if missing:
            # Log warning for large refactors, error for small fixes
            logger.warning(f"[Builder] Symbols removed from {file_path}: {missing}")
            return ", ".join(sorted(missing))

        return None

    def _parse_legacy_diff_output(
        self,
        content: str,
        response,
        model: str,
        stop_reason=None,
        was_truncated: bool = False,
    ) -> "BuilderResult":
        """Parse legacy git diff output from LLM.

        This is the deprecated mode where LLM generates raw git diffs.
        Kept for backward compatibility.

        Args:
            content: Raw LLM output
            response: API response object for token usage
            model: Model identifier

        Returns:
            BuilderResult with extracted patch
        """
        patch_content = ""
        summary = "Generated by Claude"

        try:
            # Try to parse as direct JSON first
            result_json = json.loads(content)
            patch_content = result_json.get("patch_content", "")
            summary = result_json.get("summary", "Generated by Claude")
        except json.JSONDecodeError:
            # Check if wrapped in markdown code fence
            if "```json" in content:
                # Extract JSON from markdown code block
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                if json_end > json_start:
                    json_str = content[json_start:json_end].strip()
                    try:
                        result_json = json.loads(json_str)
                        patch_content = result_json.get("patch_content", "")
                        summary = result_json.get("summary", "Generated by Claude")
                    except json.JSONDecodeError:
                        pass

            # If still no patch, try to extract raw diff content
            if not patch_content:
                patch_content = self._extract_diff_from_text(content)
                if not patch_content:
                    # Format validation failed - return error
                    error_msg = "LLM output invalid format - no git diff markers found. Output must start with 'diff --git'"
                    # Include truncation info so autonomous_executor can trigger structured_edit fallback
                    if was_truncated:
                        error_msg += " (stop_reason=max_tokens)"
                    logger.error(f"{error_msg}\nFirst 500 chars: {content[:500]}")
                    return BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[error_msg],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        model_used=model,
                        error=error_msg,
                        stop_reason=stop_reason,
                        was_truncated=was_truncated,
                    )

        return BuilderResult(
            success=True,
            patch_content=patch_content,
            builder_messages=[summary],
            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            model_used=model,
            stop_reason=stop_reason,
            was_truncated=was_truncated,
        )

    def _parse_structured_edit_output(
        self,
        content: str,
        file_context: Optional[Dict],
        response,
        model: str,
        phase_spec: Dict,
        config=None,
        stop_reason=None,
        was_truncated: bool = False,
    ) -> "BuilderResult":
        """Parse LLM's structured edit JSON output (Stage 2)

        Per IMPLEMENTATION_PLAN3.md Phase 2.2
        """
        import json
        from autopack.structured_edits import EditPlan, EditOperation, EditOperationType
        from autopack.builder_config import BuilderOutputConfig

        if config is None:
            config = BuilderOutputConfig()

        # Extract existing files from context for format conversion
        files = {}
        if file_context:
            files = file_context.get("existing_files", {})
            if not isinstance(files, dict):
                logger.warning(
                    f"[Builder] file_context.get('existing_files') returned non-dict: {type(files)}, using empty dict"
                )
                files = {}

        try:
            # Parse JSON
            result_json = None
            initial_parse_error = None
            try:
                result_json = json.loads(content.strip())
            except json.JSONDecodeError as e:
                initial_parse_error = str(e)
                # Try extracting from markdown code fence
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    if json_end > json_start:
                        json_str = content[json_start:json_end].strip()
                        try:
                            result_json = json.loads(json_str)
                            initial_parse_error = None  # Fence extraction succeeded
                        except json.JSONDecodeError as e2:
                            initial_parse_error = str(e2)

            if not result_json:
                # BUILD-039: Apply JSON repair to structured_edit mode (same as full-file mode)
                logger.info(
                    "[Builder] Attempting JSON repair on malformed structured_edit output..."
                )
                from autopack.repair_helpers import JsonRepairHelper, save_repair_debug

                json_repair = JsonRepairHelper()
                error_msg = initial_parse_error or "Failed to parse JSON with 'operations' array"
                repaired_json, repair_method = json_repair.attempt_repair(content, error_msg)

                if repaired_json is not None:
                    logger.info(
                        f"[Builder] Structured edit JSON repair succeeded via {repair_method}"
                    )
                    save_repair_debug(
                        file_path="builder_structured_edit.json",
                        original="",
                        attempted=content,
                        repaired=json.dumps(repaired_json),
                        error=error_msg,
                        method=repair_method,
                    )
                    result_json = repaired_json
                else:
                    # JSON repair failed - return error
                    error_msg = "LLM output invalid format - expected JSON with 'operations' array"
                    if was_truncated:
                        error_msg += " (stop_reason=max_tokens)"
                    logger.error(f"{error_msg}\nFirst 500 chars: {content[:500]}")
                    return BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[error_msg],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        model_used=model,
                        error=error_msg,
                        stop_reason=stop_reason,
                        was_truncated=was_truncated,
                    )

            # Extract summary and operations
            summary = result_json.get("summary", "Structured edits")
            operations_json = result_json.get("operations", [])

            # BUILD-040: Auto-convert full-file format to structured_edit format
            # If LLM produced {"files": [...]} instead of {"operations": [...]}, convert it
            if not operations_json and "files" in result_json:
                logger.info(
                    "[Builder] Detected full-file format in structured_edit mode - auto-converting to operations"
                )
                files_json = result_json.get("files", [])
                operations_json = []

                for file_entry in files_json:
                    file_path = file_entry.get("path")
                    mode = file_entry.get("mode", "modify")
                    new_content = file_entry.get("new_content")

                    if not file_path:
                        continue

                    if mode == "create" and new_content:
                        # Convert "create" to prepend operation (which creates file if missing)
                        # Using prepend instead of insert to handle non-existent files
                        operations_json.append(
                            {"type": "prepend", "file_path": file_path, "content": new_content}
                        )
                        logger.info(
                            f"[Builder] Converted create file '{file_path}' to prepend operation"
                        )
                    elif mode == "delete":
                        # For delete, we need to know file line count
                        # Since we don't have it here, skip delete conversions
                        # DELETE mode is rare for restoration tasks anyway
                        logger.warning(
                            f"[Builder] Skipping delete mode conversion for '{file_path}' (not supported)"
                        )
                        continue
                    elif mode == "modify" and new_content:
                        # Convert "modify" to replace operation (whole file)
                        # Check if file exists in context to get line count
                        file_exists = file_path in files
                        if file_exists:
                            # Get actual line count from existing file
                            existing_content = files.get(file_path, "")
                            if isinstance(existing_content, str):
                                line_count = existing_content.count("\n") + 1
                                operations_json.append(
                                    {
                                        "type": "replace",
                                        "file_path": file_path,
                                        "start_line": 1,
                                        "end_line": line_count,
                                        "content": new_content,
                                    }
                                )
                                logger.info(
                                    f"[Builder] Converted modify file '{file_path}' to replace operation (lines 1-{line_count})"
                                )
                            else:
                                logger.warning(
                                    f"[Builder] Skipping modify for '{file_path}' (existing content not string)"
                                )
                        else:
                            # File doesn't exist, treat as create (use prepend)
                            operations_json.append(
                                {"type": "prepend", "file_path": file_path, "content": new_content}
                            )
                            logger.info(
                                f"[Builder] Converted modify non-existent file '{file_path}' to prepend operation (create)"
                            )

                if operations_json:
                    logger.info(
                        f"[Builder] Format conversion successful: {len(operations_json)} operations generated"
                    )
                else:
                    logger.warning("[Builder] Format conversion produced no operations")

            if not operations_json:
                # Treat empty structured edits as a safe no-op rather than a hard failure.
                info_msg = "Structured edit produced no operations; treating as no-op"
                logger.warning(f"[Builder] {info_msg}")
                return BuilderResult(
                    success=True,
                    patch_content="",
                    builder_messages=[info_msg],
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                    prompt_tokens=response.usage.input_tokens,
                    completion_tokens=response.usage.output_tokens,
                    model_used=model,
                    error=None,
                )

            # Parse operations
            operations = []
            for i, op_json in enumerate(operations_json):
                try:
                    op = EditOperation(
                        type=EditOperationType(op_json.get("type")),
                        file_path=op_json.get("file_path"),
                        line=op_json.get("line"),
                        content=op_json.get("content"),
                        start_line=op_json.get("start_line"),
                        end_line=op_json.get("end_line"),
                        context_before=op_json.get("context_before"),
                        context_after=op_json.get("context_after"),
                    )

                    # Validate operation
                    is_valid, error = op.validate()
                    if not is_valid:
                        error_msg = f"Operation {i} invalid: {error}"
                        logger.error(f"[Builder] {error_msg}")
                        return BuilderResult(
                            success=False,
                            patch_content="",
                            builder_messages=[error_msg],
                            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                            prompt_tokens=response.usage.input_tokens,
                            completion_tokens=response.usage.output_tokens,
                            model_used=model,
                            error=error_msg,
                        )

                    operations.append(op)

                except Exception as e:
                    error_msg = f"Failed to parse operation {i}: {str(e)}"
                    logger.error(f"[Builder] {error_msg}")
                    return BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[error_msg],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        model_used=model,
                        error=error_msg,
                    )

            # Create edit plan
            edit_plan = EditPlan(summary=summary, operations=operations)

            # Validate plan
            is_valid, error = edit_plan.validate()
            if not is_valid:
                error_msg = f"Invalid edit plan: {error}"
                logger.error(f"[Builder] {error_msg}")
                return BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=[error_msg],
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                    prompt_tokens=response.usage.input_tokens,
                    completion_tokens=response.usage.output_tokens,
                    model_used=model,
                    error=error_msg,
                )

            # Store edit plan in BuilderResult
            logger.info(
                f"[Builder] Generated structured edit plan with {len(operations)} operations"
            )

            return BuilderResult(
                success=True,
                patch_content="",  # No patch content for structured edits
                builder_messages=[f"Generated {len(operations)} edit operations"],
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                model_used=model,
                edit_plan=edit_plan,  # NEW: Store edit plan
                stop_reason=stop_reason,
                was_truncated=was_truncated,
            )

        except Exception as e:
            logger.error(f"[Builder] Error parsing structured edit output: {e}")
            return BuilderResult(
                success=False,
                patch_content="",
                builder_messages=[str(e)],
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                model_used=model,
                error=str(e),
            )

    def _parse_ndjson_output(
        self,
        content: str,
        file_context: Optional[Dict],
        response: Any,
        model: str,
        phase_spec: Dict,
        config: Optional[Any] = None,
        stop_reason: Optional[str] = None,
        was_truncated: bool = False,
    ) -> BuilderResult:
        """
        Parse NDJSON format output (BUILD-129 Phase 3).

        NDJSON is truncation-tolerant: each line is a complete JSON object,
        so if truncation occurs, all complete lines are still usable.

        Args:
            content: Raw LLM output in NDJSON format
            file_context: Repository file context
            response: API response object
            model: Model name
            phase_spec: Phase specification
            config: Builder configuration
            stop_reason: Stop reason from API
            was_truncated: Whether output was truncated

        Returns:
            BuilderResult with success/failure status
        """
        try:
            # Pre-sanitize: strip common markdown fences that break NDJSON line parsing.
            raw = content or ""
            lines = []
            for ln in raw.splitlines():
                s = ln.strip()
                if s.startswith("```"):
                    continue
                lines.append(ln)
            sanitized = "\n".join(lines).strip()

            # If the model ignored NDJSON and returned a single structured-edit JSON object (often pretty-printed),
            # route to the structured-edit parser instead of failing with ndjson_no_operations.
            # This shows up as lines like "{" and "}" (pretty JSON) and a top-level "operations" array.
            try:
                import json as _json

                if (
                    sanitized.startswith("{")
                    and '"operations"' in sanitized
                    and "diff --git" not in sanitized
                ):
                    obj = _json.loads(sanitized)
                    if isinstance(obj, dict) and isinstance(obj.get("operations"), list):
                        logger.warning(
                            "[BUILD-129:NDJSON] Detected structured-edit JSON; falling back to structured-edit parser"
                        )
                        return self._parse_structured_edit_output(
                            sanitized,
                            file_context,
                            response,
                            model,
                            phase_spec,
                            config=config,
                            stop_reason=stop_reason,
                            was_truncated=bool(was_truncated),
                        )
            except Exception:
                pass

            # Parse NDJSON
            parser = NDJSONParser()
            parse_result = parser.parse(sanitized)

            logger.info(
                f"[BUILD-129:NDJSON] Parsed {parse_result.lines_parsed} lines, "
                f"{len(parse_result.operations)} operations, "
                f"truncated={parse_result.was_truncated}"
            )

            # Some providers may not report stop_reason=max_tokens even when the NDJSON stream is cut mid-line.
            # Use utilization as the tie-breaker: only treat NDJSON-level truncation as token truncation when we're
            # near the completion ceiling.
            output_utilization = 0.0
            try:
                tb = (phase_spec.get("metadata") or {}).get("token_budget") or {}
                output_utilization = float(tb.get("output_utilization") or 0.0)
            except Exception:
                output_utilization = 0.0
            effective_truncation = bool(
                was_truncated or (parse_result.was_truncated and output_utilization >= 95.0)
            )

            if not parse_result.operations:
                # Fallback: model sometimes ignores NDJSON and returns a normal diff.
                # If so, parse as legacy diff to avoid wasting the whole attempt.
                if "diff --git" in sanitized or sanitized.startswith("*** Begin Patch"):
                    logger.warning(
                        "[BUILD-129:NDJSON] No NDJSON operations found; falling back to legacy diff parse"
                    )
                    return self._parse_legacy_diff_output(
                        sanitized,
                        response,
                        model,
                        stop_reason=stop_reason,
                        was_truncated=effective_truncation,
                    )

                # Fallback: model sometimes returns a structured-edit JSON object (often pretty-printed and/or truncated).
                # Try to recover *any* decodable JSON value from the payload by scanning for the first '{' or '[' that
                # can be parsed with JSONDecoder.raw_decode. This is truncation-tolerant and ignores leading "{" fragments.
                try:
                    import json as _json
                    from json import JSONDecoder as _JSONDecoder
                    import ast as _ast

                    def _scan_decode_any_json(text: str):
                        decoder = _JSONDecoder()
                        idx = 0
                        while True:
                            # Find next plausible JSON start
                            m1 = text.find("{", idx)
                            m2 = text.find("[", idx)
                            starts = [p for p in (m1, m2) if p != -1]
                            if not starts:
                                return None
                            start = min(starts)
                            try:
                                obj, end = decoder.raw_decode(text[start:])
                                return obj
                            except Exception:
                                # If it looks like a Python literal, try literal_eval at this position
                                try:
                                    obj = _ast.literal_eval(text[start:])
                                    return obj
                                except Exception:
                                    idx = start + 1

                    obj = _scan_decode_any_json(sanitized)

                    if isinstance(obj, dict) and isinstance(obj.get("operations"), list):
                        logger.warning(
                            "[BUILD-129:NDJSON] Decoded structured-edit plan; routing to structured-edit parser"
                        )
                        plan_json = _json.dumps(obj, ensure_ascii=False)
                        return self._parse_structured_edit_output(
                            plan_json,
                            file_context,
                            response,
                            model,
                            phase_spec,
                            config=config,
                            stop_reason=stop_reason,
                            was_truncated=effective_truncation,
                        )
                except Exception:
                    pass

                # Fallback: model may return a JSON array of operations instead of NDJSON.
                try:
                    import json as _json

                    obj = _json.loads(sanitized)
                    if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
                        logger.warning(
                            "[BUILD-129:NDJSON] Detected JSON array; converting to NDJSON operations"
                        )
                        converted = "\n".join(_json.dumps(x, ensure_ascii=False) for x in obj)
                        parse_result = parser.parse(converted)
                    elif isinstance(obj, dict) and obj.get("type") in (
                        "create",
                        "modify",
                        "delete",
                        "meta",
                    ):
                        logger.warning(
                            "[BUILD-129:NDJSON] Detected single JSON op; converting to NDJSON"
                        )
                        converted = _json.dumps(obj, ensure_ascii=False)
                        parse_result = parser.parse(converted)
                except Exception:
                    pass

                if parse_result.operations:
                    logger.info(
                        f"[BUILD-129:NDJSON] Salvaged {len(parse_result.operations)} operations after fallback conversion"
                    )
                else:
                    error_msg = "NDJSON parsing produced no valid operations"
                if effective_truncation:
                    error_msg += " (truncated)"
                logger.error(error_msg)

                # Persist a small debug sample of the raw/sanitized output so we can diagnose format drift.
                # This is intentionally bounded to avoid huge files.
                try:
                    from datetime import datetime
                    from pathlib import Path as _Path

                    phase_id = str(
                        phase_spec.get("phase_id")
                        or phase_spec.get("id")
                        or phase_spec.get("name")
                        or "unknown_phase"
                    )
                    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                    out_dir = _Path(".autonomous_runs") / "autopack" / "ndjson_failures"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_path = out_dir / f"{stamp}_{phase_id}_ndjson_no_ops.txt"

                    head = sanitized[:8000]
                    tail = sanitized[-2000:] if len(sanitized) > 9000 else ""
                    payload = (
                        f"phase_id={phase_id}\n"
                        f"model={model}\n"
                        f"stop_reason={stop_reason}\n"
                        f"was_truncated={was_truncated}\n"
                        f"effective_truncation={effective_truncation}\n"
                        f"lines={len((sanitized or '').splitlines())}\n"
                        f"--- BEGIN HEAD (<=8000 chars) ---\n{head}\n"
                        f"--- END HEAD ---\n"
                    )
                    if tail:
                        payload += f"--- BEGIN TAIL (<=2000 chars) ---\n{tail}\n--- END TAIL ---\n"
                    out_path.write_text(payload, encoding="utf-8", errors="replace")
                    logger.warning(
                        f"[BUILD-129:NDJSON] Wrote debug sample for ndjson_no_operations to {out_path}"
                    )
                except Exception as e:
                    logger.warning(f"[BUILD-129:NDJSON] Failed to write debug sample: {e}")

                return BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=[error_msg],
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                    prompt_tokens=response.usage.input_tokens,
                    completion_tokens=response.usage.output_tokens,
                    model_used=model,
                    error="ndjson_no_operations",
                    stop_reason=stop_reason,
                    was_truncated=effective_truncation,
                    raw_output=content,
                )

            # Apply operations using NDJSONApplier
            workspace = Path(file_context.get("workspace", ".")) if file_context else Path(".")
            applier = NDJSONApplier(workspace=workspace)

            # HARD RUNTIME GUARD: If a deliverables manifest exists, do NOT apply any NDJSON operation
            # whose file_path is outside the manifest/prefixes. This prevents workspace drift even when
            # the model violates path constraints.
            manifest_paths_raw = None
            if isinstance(phase_spec, dict):
                scope_cfg = phase_spec.get("scope") or {}
                if isinstance(scope_cfg, dict):
                    manifest_paths_raw = scope_cfg.get("deliverables_manifest")
                if manifest_paths_raw is None:
                    manifest_paths_raw = phase_spec.get("deliverables_manifest")

            if isinstance(manifest_paths_raw, list) and manifest_paths_raw:
                manifest_set = set()
                manifest_prefixes = []
                for p in manifest_paths_raw:
                    if isinstance(p, str) and p.strip():
                        norm = p.strip().replace("\\", "/")
                        while "//" in norm:
                            norm = norm.replace("//", "/")
                        manifest_set.add(norm)
                        if norm.endswith("/"):
                            manifest_prefixes.append(norm)

                def _in_manifest(path: str) -> bool:
                    if path in manifest_set:
                        return True
                    return any(path.startswith(prefix) for prefix in manifest_prefixes)

                # Canonicalize common wrong-root prefixes into repo-root paths.
                # Example observed in research-system-v9: "code/src/research/..." should be "src/research/..."
                # Only rewrite if the rewritten path is actually allowed by the manifest.
                def _canonicalize_to_manifest(path: str) -> str:
                    candidates = [path]
                    if path.startswith("./"):
                        candidates.append(path[2:])
                    if path.startswith("code/"):
                        candidates.append(path[len("code/") :])
                    if path.startswith("code/src/"):
                        candidates.append("src/" + path[len("code/src/") :])
                    if path.startswith("code/docs/"):
                        candidates.append("docs/" + path[len("code/docs/") :])
                    if path.startswith("code/tests/"):
                        candidates.append("tests/" + path[len("code/tests/") :])

                    for c in candidates:
                        c2 = c.replace("\\", "/")
                        while "//" in c2:
                            c2 = c2.replace("//", "/")
                        if _in_manifest(c2):
                            return c2
                    return path

                outside = []
                for op in parse_result.operations:
                    fp = (op.file_path or "").replace("\\", "/")
                    while "//" in fp:
                        fp = fp.replace("//", "/")
                    if not fp:
                        continue
                    canon = _canonicalize_to_manifest(fp)
                    if canon != fp:
                        op.file_path = canon
                        fp = canon
                    if not _in_manifest(fp):
                        outside.append(fp)

                if outside:
                    outside = sorted(set(outside))
                    msg = (
                        "NDJSON operations contained file paths outside deliverables_manifest; "
                        "skipping apply to prevent workspace drift."
                    )
                    logger.error(
                        f"[BUILD-129:NDJSON] {msg} outside_count={len(outside)} sample={outside[:10]}"
                    )
                    return BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[
                            msg,
                            f"outside_count={len(outside)}",
                            f"outside_sample={outside[:10]}",
                        ],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        model_used=model,
                        error="ndjson_outside_manifest",
                        stop_reason=stop_reason,
                        was_truncated=effective_truncation,
                        raw_output=content,
                    )

            apply_result = applier.apply(parse_result.operations)

            logger.info(
                f"[BUILD-129:NDJSON] Applied {len(apply_result['applied'])} operations, "
                f"{len(apply_result['failed'])} failed"
            )

            # IMPORTANT: Deliverables validation expects patch_content to mention file paths via diff markers.
            # NDJSON operations are applied directly to disk, so we generate a lightweight "synthetic diff header"
            # that includes `+++ b/<path>` for each applied file so downstream validators can see what was created.
            applied_paths = list(apply_result.get("applied") or [])
            patch_lines = [f"# NDJSON Operations Applied ({len(applied_paths)} files)"]
            for p in applied_paths:
                patch_lines.append(f"diff --git a/{p} b/{p}")
                patch_lines.append(f"+++ b/{p}")
            if apply_result.get("failed"):
                patch_lines.append(f"\n# Failed operations ({len(apply_result['failed'])}):")
                for failed in apply_result["failed"]:
                    patch_lines.append(f"# - {failed['file_path']}: {failed['error']}")
            patch_content = "\n".join(patch_lines) + "\n"

            # Determine success
            success = len(apply_result["applied"]) > 0 and len(apply_result["failed"]) == 0

            # Build messages
            messages = []
            if parse_result.was_truncated and parse_result.total_expected:
                completed = len(parse_result.operations)
                expected = parse_result.total_expected
                messages.append(
                    f"Output truncated: completed {completed}/{expected} operations. "
                    f"Continuation recovery can complete remaining {expected - completed} operations."
                )

            return BuilderResult(
                success=success,
                patch_content=patch_content,
                builder_messages=messages,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                model_used=model,
                stop_reason=stop_reason,
                was_truncated=effective_truncation,
                raw_output=content,  # Store raw output for continuation recovery
            )

        except Exception as e:
            logger.error(f"[BUILD-129:NDJSON] Error parsing NDJSON output: {e}")
            error_msg = f"NDJSON parsing failed: {str(e)}"
            if was_truncated:
                error_msg += " (stop_reason=max_tokens)"

            return BuilderResult(
                success=False,
                patch_content="",
                builder_messages=[error_msg],
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                model_used=model,
                error="ndjson_parse_error",
                stop_reason=stop_reason,
                was_truncated=was_truncated,
                raw_output=content,
            )

    def _build_system_prompt(
        self,
        use_full_file_mode: bool = True,
        use_structured_edit: bool = False,
        use_ndjson_format: bool = False,
        phase_spec: Optional[Dict] = None,
    ) -> str:
        """Build system prompt for Claude Builder

        Args:
            use_full_file_mode: If True, use new full-file replacement format (GPT_RESPONSE10).
                               If False, use legacy git diff format (deprecated).
            use_structured_edit: If True, use structured edit mode for large files (Stage 2).
            use_ndjson_format: If True, use NDJSON format for truncation tolerance (BUILD-129 Phase 3).
            phase_spec: Phase specification for context-aware prompt optimization (BUILD-043).
        """
        # BUILD-043: Use minimal prompt for simple phases to save tokens
        if phase_spec:
            complexity = phase_spec.get("complexity", "medium")
            task_category = phase_spec.get("task_category", "")

            # Simple file creation phases don't need complex instructions
            if complexity == "low" and task_category in ("feature", "bugfix"):
                return self._build_minimal_system_prompt(
                    use_structured_edit, use_ndjson_format, phase_spec
                )

        if use_ndjson_format:
            # BUILD-129 Phase 3: NDJSON format for truncation tolerance
            parser = NDJSONParser()
            deliverables = []
            if phase_spec:
                deliverables = phase_spec.get("deliverables")
                if not deliverables:
                    scope_cfg = phase_spec.get("scope") or {}
                    if isinstance(scope_cfg, dict):
                        deliverables = scope_cfg.get("deliverables")
            deliverables = deliverables or []
            summary = (
                phase_spec.get("description", "Implement changes")
                if phase_spec
                else "Implement changes"
            )

            base_prompt = """You are an expert software engineer working on an autonomous build system.

**OUTPUT FORMAT: NDJSON (Newline-Delimited JSON) - TRUNCATION-TOLERANT**

Generate output in NDJSON format - one complete JSON object per line.
This format is truncation-tolerant: if output is cut off mid-generation, all complete lines are still valid.

"""
            # Add format instructions from NDJSONParser
            base_prompt += parser.format_for_prompt(deliverables, summary)

            base_prompt += """

**CRITICAL REQUIREMENTS**:
1. Each line MUST be a complete, valid JSON object
2. NO line breaks within JSON objects (use \\n for newlines in content strings)
3. First line: meta object with summary and total_operations
4. Subsequent lines: one operation per line

**OPERATION TYPES**:
- create: Full file content for new files
- modify: Structured edit operations for existing files
- delete: Remove files

**TRUNCATION TOLERANCE**:
This format ensures that if generation is truncated, all complete operation lines are preserved and usable.
Only the last incomplete line is lost."""

            # BUILD-129 Phase 3: Tighten path correctness using deliverables_manifest (when present).
            # Many failures were due to writing outside the manifest or using wrong file paths (e.g. docs/* vs docs/research/*).
            # When a manifest is present, it is the authoritative allowlist for file_path values.
            if phase_spec:
                scope_cfg = phase_spec.get("scope") or {}
                manifest = None
                if isinstance(scope_cfg, dict):
                    manifest = scope_cfg.get("deliverables_manifest")
                # Executor often attaches deliverables_manifest at the top-level phase spec.
                if manifest is None:
                    manifest = phase_spec.get("deliverables_manifest")
                if isinstance(manifest, list) and manifest:
                    # Keep prompt compact: list first N entries; rule remains "only these paths/prefixes".
                    manifest_strs = [
                        str(p).strip() for p in manifest if isinstance(p, str) and str(p).strip()
                    ]
                    preview = manifest_strs[:60]
                    base_prompt += (
                        "\n\n**FILE PATH CONSTRAINT (DELIVERABLES MANIFEST - STRICT)**:\n"
                    )
                    base_prompt += "- For EVERY operation line, `file_path` MUST be exactly one of the approved paths below.\n"
                    base_prompt += "- If an approved entry ends with `/`, it is a directory prefix; then `file_path` MUST be under that prefix.\n"
                    base_prompt += "- DO NOT create/modify/delete any file outside this manifest.\n"
                    base_prompt += "- DO NOT improvise alternate locations (e.g. `docs/API.md` when `docs/research/API_REFERENCE.md` is required).\n"
                    base_prompt += "\nApproved manifest (preview):\n"
                    for p in preview:
                        base_prompt += f"- {p}\n"
                    if len(manifest_strs) > len(preview):
                        base_prompt += f"- ... ({len(manifest_strs) - len(preview)} more)\n"

            return base_prompt
        elif use_structured_edit:
            # NEW: Structured edit mode for large files (Stage 2) - per IMPLEMENTATION_PLAN3.md Phase 2.1
            base_prompt = """You are a code modification assistant. Generate targeted edit operations for large files.

Your task is to output a structured JSON edit plan with specific operations.

Output format:
{
  "summary": "Brief description of changes",
  "operations": [
    {
      "type": "insert",
      "file_path": "src/example.py",
      "line": 100,
      "content": "new code here\\n"
    },
    {
      "type": "replace",
      "file_path": "src/example.py",
      "start_line": 50,
      "end_line": 55,
      "content": "updated code here\\n"
    },
    {
      "type": "delete",
      "file_path": "src/example.py",
      "start_line": 200,
      "end_line": 210
    }
  ]
}

Operation Types:
1. "insert" - Insert new lines at a specific position
   Required: type, file_path, line, content
   
2. "replace" - Replace a range of lines
   Required: type, file_path, start_line, end_line, content
   Optional: context_before, context_after (for validation)
   
3. "delete" - Delete a range of lines
   Required: type, file_path, start_line, end_line
   
4. "append" - Append lines to end of file
   Required: type, file_path, content
   
5. "prepend" - Prepend lines to start of file
   Required: type, file_path, content

CRITICAL RULES:
- Line numbers are 1-indexed (first line is line 1)
- Ranges are inclusive (start_line to end_line, both included)
- Content should include newlines (\\n) where appropriate
- Do NOT output full file contents
- Do NOT use ellipses (...) or placeholders
- Make targeted, minimal changes
- Include context_before and context_after for validation when replacing critical sections

Example - Add a new function:
{
  "summary": "Add telemetry recording function",
  "operations": [
    {
      "type": "insert",
      "file_path": "src/autopack/autonomous_executor.py",
      "line": 500,
      "content": "    def record_telemetry(self, event):\\n        self.telemetry.record_event(event)\\n"
    }
  ]
}

Do NOT:
- Output complete file contents
- Use placeholders or ellipses
- Make unnecessary changes
- Modify lines outside the specified ranges"""
        elif use_full_file_mode:
            # Per GPT_RESPONSE10: Full-file replacement mode (Option A)
            # LLM outputs complete file content, executor generates diff locally
            base_prompt = """You are an expert software engineer working on an autonomous build system.

Your task is to generate code changes based on phase specifications.

OUTPUT FORMAT - CRITICAL:
You MUST output a valid JSON object with this exact structure:
{
  "summary": "Brief description of changes made",
  "files": [
    {
      "path": "full/path/to/file.py",
      "mode": "modify" or "create" or "delete",
      "new_content": "Complete file content here..."
    }
  ]
}

RULES:
1. Output ONLY the JSON object - no markdown fences, no explanations before/after
2. For "modify" mode: provide the COMPLETE new file content (not a diff, not a snippet)
3. For "create" mode: provide the COMPLETE new file content
4. For "delete" mode: set new_content to null
5. Use COMPLETE file paths from repository root (e.g., src/autopack/health_checks.py)
6. Preserve all existing code that should not change - do NOT accidentally delete functions
7. Maintain consistent formatting with the existing codebase
8. Include all imports, docstrings, and type hints

IMPORTANT:
- You are generating COMPLETE file content, not patches or diffs
- The system will compute the diff automatically from your output
- Do NOT include line numbers, @@ markers, or +/- prefixes
- Do NOT truncate or abbreviate - output the FULL file"""
        else:
            # Diff mode for medium files (501-1000 lines) - per IMPLEMENTATION_PLAN2.md Phase 3.1
            base_prompt = """You are a code modification assistant. Generate ONLY a git-compatible unified diff patch.

Output format:
- Start with `diff --git a/path/to/file.py b/path/to/file.py`
- Include `index`, `---`, and `+++` headers
- Use `@@ -OLD_START,OLD_COUNT +NEW_START,NEW_COUNT @@` hunk headers
- Use `-` for removed lines, `+` for added lines, and a leading space for context lines
- Include at least 3 lines of context around each change
- Use COMPLETE repository-relative paths (e.g., `src/autopack/error_recovery.py`)

Do NOT:
- Output JSON
- Output full file contents outside hunks
- Wrap the diff in markdown fences (```)
- Add explanations before or after the diff
- Modify files that are not shown in the context
- Include any text that is not part of the unified diff format

CRITICAL REQUIREMENTS:
1. Output ONLY a raw git diff format patch
2. Do NOT wrap it in JSON, markdown code blocks, or any other format
3. Do NOT add explanatory text before or after the patch
4. Start directly with: diff --git a/path/to/file.py b/path/to/file.py

GIT DIFF FORMAT RULES:
- Each file change MUST start with: diff --git a/PATH b/PATH
- Followed by: index HASH..HASH
- Then: --- a/PATH and +++ b/PATH
- Then: @@ -LINE,COUNT +LINE,COUNT @@ CONTEXT
- Then the actual changes with +/- prefixes
- Use COMPLETE file paths from repository root (e.g., src/autopack/main.py)
- Do NOT use relative or partial paths (e.g., autopack/main.py is WRONG)

Requirements:
- Generate clean, production-quality code
- Follow best practices (type hints, docstrings, tests)
- Apply learned rules from project history
- Output ONLY the raw git diff format patch (no JSON, no markdown fences, no explanations)"""

        # BUILD-044: Add protected path isolation guidance
        if phase_spec:
            # Get protected paths from phase spec (passed from executor)
            protected_paths = phase_spec.get("protected_paths", [])
            if protected_paths:
                isolation_guidance = """

CRITICAL ISOLATION RULES:
The following paths are PROTECTED and MUST NOT be modified under any circumstances:
"""
                for path in protected_paths:
                    isolation_guidance += f"  - {path}\n"

                isolation_guidance += """
If your task requires functionality from these protected modules:
1. USE their existing APIs via imports (import statements)
2. CREATE NEW files in different directories outside protected paths
3. EXTEND functionality by creating wrapper/adapter modules
4. DO NOT modify, extend, or touch any protected files directly

VIOLATION CONSEQUENCES:
Any attempt to modify protected paths will cause immediate patch rejection.
Your changes will be lost and the phase will fail.

ALLOWED APPROACH:
✓ Import from protected modules: from src.autopack.embeddings import EmbeddingModel
✓ Create new files: src/my_feature/search.py
✓ Use APIs: embedding_model = EmbeddingModel(); results = embedding_model.search(query)

FORBIDDEN APPROACH:
✗ Modify protected files: src/autopack/embeddings/model.py
✗ Extend protected classes in-place
✗ Add methods to protected modules
"""
                base_prompt += isolation_guidance

        # Inject prevention rules from debug journal
        try:
            prevention_rules = get_prevention_prompt_injection()
            if prevention_rules:
                base_prompt += "\n\n" + prevention_rules
        except Exception:
            # Gracefully continue if prevention rules can't be loaded
            pass

        # BUILD-127 Phase 3: Request deliverables manifest from Builder
        if phase_spec and phase_spec.get("deliverables"):
            manifest_request = """

**DELIVERABLES MANIFEST (BUILD-127 Phase 3)**:
After implementing the changes, provide a deliverables manifest at the end of your response (after the main output):

DELIVERABLES_MANIFEST:
```json
{
  "created": [
    {"path": "src/autopack/example.py", "symbols": ["ExampleClass", "example_function"]},
    {"path": "tests/test_example.py", "symbols": ["test_example_creation", "test_example_validation"]}
  ],
  "modified": [
    {"path": "src/autopack/main.py", "changes": "Added example import and initialization"}
  ]
}
```

This manifest will be validated to ensure all required deliverables are created with expected symbols.

MANIFEST REQUIREMENTS:
1. Include ALL created files with their key symbols (classes, functions, constants)
2. Include ALL modified files with a brief description of changes
3. Use complete paths from repository root
4. For test files, list test function names
5. For source files, list public classes and functions
"""
            base_prompt += manifest_request

        return base_prompt

    def _build_minimal_system_prompt(
        self,
        use_structured_edit: bool = False,
        use_ndjson_format: bool = False,
        phase_spec: Optional[Dict] = None,
    ) -> str:
        """Build minimal system prompt for simple phases (BUILD-043)

        Trimmed version saves ~3K tokens for low-complexity tasks.

        Args:
            use_structured_edit: If True, use structured edit JSON format.
            use_ndjson_format: If True, use NDJSON format (BUILD-129 Phase 3).
            phase_spec: Phase specification for protected path guidance (BUILD-044).

        Returns:
            Minimal system prompt optimized for token efficiency.
        """
        if use_structured_edit:
            base_prompt = """You are a code modification assistant. Generate structured JSON edit operations.

Output format:
{
  "summary": "Brief description",
  "operations": [
    {
      "type": "insert|replace|delete|append|prepend",
      "file_path": "path/to/file",
      "line": 100,  // for insert
      "start_line": 50, "end_line": 55,  // for replace/delete
      "content": "code here\\n"  // for insert/replace/append/prepend
    }
  ]
}

Rules:
- Line numbers are 1-indexed
- Use targeted, minimal changes
- Do NOT output full file contents
- Include \\n in content where needed
"""
        else:
            base_prompt = """You are a code modification assistant. Generate git diff format patches.

Rules:
- Use standard git diff format
- Start with 'diff --git a/path b/path'
- Include proper @@ hunk headers
- Use +/- for added/removed lines
- Context lines have no prefix
- Be precise and complete

Example:
diff --git a/src/example.py b/src/example.py
index abc123..def456 100644
--- a/src/example.py
+++ b/src/example.py
@@ -10,3 +10,4 @@ def example():
     print("existing")
+    print("new line")
"""

        # BUILD-044: Add protected path isolation guidance
        if phase_spec:
            protected_paths = phase_spec.get("protected_paths", [])
            if protected_paths:
                isolation_guidance = """

CRITICAL: The following paths are PROTECTED - DO NOT modify them:
"""
                for path in protected_paths:
                    isolation_guidance += f"  - {path}\n"

                isolation_guidance += """
Instead: Use their APIs via imports, create new files elsewhere.
"""
                base_prompt += isolation_guidance

        return base_prompt

    def _build_user_prompt(
        self,
        phase_spec: Dict,
        file_context: Optional[Dict],
        project_rules: Optional[List],
        run_hints: Optional[List],
        use_full_file_mode: bool = True,
        config=None,  # NEW: BuilderOutputConfig for thresholds
        retrieved_context: Optional[str] = None,  # NEW: Vector memory context
        context_budget_tokens: Optional[
            int
        ] = None,  # NEW: Hard cap for file_context inclusion (approx tokens)
    ) -> str:
        """Build user prompt with phase details

        Args:
            phase_spec: Phase specification
            file_context: Repository file context
            project_rules: Persistent learned rules
            run_hints: Within-run hints
            use_full_file_mode: If True, include FULL file content for accurate editing
            config: BuilderOutputConfig instance (per IMPLEMENTATION_PLAN2.md)
            retrieved_context: Retrieved context from vector memory (formatted string)
        """
        # Load config if not provided
        if config is None:
            from autopack.builder_config import BuilderOutputConfig

            config = BuilderOutputConfig()
        prompt_parts = [
            "# Phase Specification",
            f"Description: {phase_spec.get('description', '')}",
            f"Category: {phase_spec.get('task_category', 'general')}",
            f"Complexity: {phase_spec.get('complexity', 'medium')}",
        ]

        # Detect country pack phases (pack YAMLs in scope) to inject a schema contract
        scope_config = phase_spec.get("scope") or {}
        scope_paths = scope_config.get("paths") or []
        readonly_entries = scope_config.get("read_only_context") or []

        scope_paths_for_detection = scope_paths or []
        is_pack_phase = any(
            isinstance(p, str) and "backend/packs/" in p and p.endswith((".yaml", ".yml"))
            for p in scope_paths_for_detection
        )
        if is_pack_phase:
            prompt_parts.append("\n# PACK SCHEMA CONTRACT (country packs)")
            prompt_parts.append(
                "You are generating complete country pack YAML files. You MUST output full, well-formed YAML with these keys:"
            )
            prompt_parts.append(
                "- Required top-level keys: name, description, version, country, domain, categories, checklists, official_sources"
            )
            prompt_parts.append(
                "- categories: non-empty list; each category has name, description, examples (list, non-empty). No duplicate category names."
            )
            prompt_parts.append(
                "- checklists: non-empty list; each checklist has name, required_documents (non-empty list)."
            )
            prompt_parts.append("- official_sources: non-empty list of URLs or source strings.")
            prompt_parts.append(
                "- Do NOT emit header-only or stub content (e.g., just version or a 4-line file). If unsure, leave content unchanged rather than emitting partial YAML."
            )
            prompt_parts.append(
                "- Use only the allowed files in scope. Do NOT introduce new files outside scope."
            )
            prompt_parts.append(
                "- If you cannot satisfy the schema confidently, return the previous content unchanged."
            )

            # Grounding hint: encourage use of curated research snippets if present in read-only context
            prompt_parts.append(
                "\nGrounding: Prefer facts from the provided research/reference files in read-only context (e.g., research_report_tax_immigration_legal_packs.md, research briefs). Do not invent thresholds or categories; align with those sources."
            )

        if phase_spec.get("acceptance_criteria"):
            prompt_parts.append("\nAcceptance Criteria:")
            for criteria in phase_spec["acceptance_criteria"]:
                prompt_parts.append(f"- {criteria}")
        else:
            # Universal output contract (goal/criteria prompting; refuse partials)
            prompt_parts.append("\nAcceptance Criteria (universal):")
            prompt_parts.append(
                "- Emit COMPLETE, well-formed output for every file you touch; no stubs or truncated content."
            )
            prompt_parts.append(
                "- For YAML/JSON/TOML, include required top-level keys/sections; do not omit document starts when applicable."
            )
            prompt_parts.append(
                "- Do not emit patches that reference files outside the allowed scope."
            )
            prompt_parts.append(
                "- If unsure or lacking context, leave the file unchanged rather than emitting partial output."
            )

        # Explicit format contract (applies to all modes)
        prompt_parts.append("\n# Output Format (strict)")
        prompt_parts.append("- Output JSON ONLY with a top-level `files` array.")
        prompt_parts.append(
            "- Each entry MUST include: path, mode (replace|create|modify), new_content."
        )
        prompt_parts.append("- Do NOT output git diff, markdown fences, or prose.")
        prompt_parts.append("- No code fences, no surrounding text. Return only JSON.")

        # Inject scope constraints if provided
        if scope_paths:
            prompt_parts.append("\n## File Modification Constraints")
            prompt_parts.append("CRITICAL: You may ONLY modify these files:\n")
            for allowed in scope_paths:
                # BUILD-141 Telemetry Unblock: Clarify directory prefix semantics
                if allowed.endswith("/"):
                    prompt_parts.append(
                        f"- {allowed} (directory prefix - creating/modifying files under this path is ALLOWED)"
                    )
                else:
                    prompt_parts.append(f"- {allowed}")
            prompt_parts.append(
                "\nIf you touch any other file your patch will be rejected immediately."
            )

            if readonly_entries:
                prompt_parts.append("\nRead-only context (reference only, do NOT modify):")
                for entry in readonly_entries:
                    prompt_parts.append(f"- {entry}")

            prompt_parts.append(
                "\nDo not add new files or edit files outside this list. "
                "All other paths are strictly forbidden."
            )

        # BUILD-141 Telemetry Unblock: Add explicit deliverables contract
        # Extract deliverables from phase_spec (same logic as token estimation)
        deliverables_list = phase_spec.get("deliverables")
        if not deliverables_list:
            scope_cfg = phase_spec.get("scope") or {}
            if isinstance(scope_cfg, dict):
                deliverables_list = scope_cfg.get("deliverables")

        if deliverables_list and isinstance(deliverables_list, list):
            prompt_parts.append("\n## REQUIRED DELIVERABLES")
            prompt_parts.append("Your output MUST include at least these files:\n")
            for deliverable in deliverables_list:
                prompt_parts.append(f"- {deliverable}")
            prompt_parts.append(
                "\n⚠️ CRITICAL: The 'files' array in your JSON output MUST contain at least one file "
                "and MUST cover all deliverables listed above. Empty files array is NOT allowed."
            )

        if project_rules:
            prompt_parts.append("\n# Learned Rules (must follow):")
            for rule in project_rules[:10]:  # Top 10 rules
                # Support both dict-based rules and LearnedRule dataclasses
                if isinstance(rule, dict):
                    text = rule.get("rule_text") or rule.get("constraint") or ""
                else:
                    text = getattr(rule, "constraint", str(rule))
                if text:
                    prompt_parts.append(f"- {text}")

        if run_hints:
            prompt_parts.append("\n# Hints from earlier phases:")
            for hint in run_hints[:5]:  # Recent hints
                # Support both dict-based hints and RunRuleHint dataclasses
                if isinstance(hint, dict):
                    text = hint.get("hint_text", "")
                else:
                    text = getattr(hint, "hint_text", str(hint))
                if text:
                    prompt_parts.append(f"- {text}")

        # Milestone 2: Inject intention anchor (canonical project goal)
        if run_id := phase_spec.get("run_id"):
            from .intention_anchor import load_and_render_for_builder

            anchor_section = load_and_render_for_builder(
                run_id=run_id,
                phase_id=phase_spec.get("phase_id", "unknown"),
                base_dir=".",  # Use current directory (.autonomous_runs/<run_id>/)
            )
            if anchor_section:
                prompt_parts.append("\n")
                prompt_parts.append(anchor_section)

        # NEW: Include retrieved context from vector memory (per IMPLEMENTATION_PLAN_MEMORY_AND_CONTEXT.md)
        if retrieved_context:
            prompt_parts.append("\n# Retrieved Context (from previous runs/phases):")
            prompt_parts.append(retrieved_context)

        if file_context:
            # Extract existing_files dict (autonomous_executor returns {"existing_files": {path: content}})
            files = file_context.get("existing_files", file_context)
            scope_metadata = file_context.get("scope_metadata", {})
            missing_scope_files = file_context.get("missing_scope_files", [])

            # Safety check: ensure files is a dict, not a list or other type
            if not isinstance(files, dict):
                logger.warning(
                    f"[Builder] file_context.get('existing_files') returned non-dict type: {type(files)}, using empty dict"
                )
                files = {}

            # ------------------------------------------------------------------
            # Hard context budgeting: keep prompt under provider limits even when
            # scope expansion loads hundreds of files (e.g., research phases).
            # We prefer deliverables, then small modifiable files, then read-only.
            # ------------------------------------------------------------------
            if context_budget_tokens is not None and context_budget_tokens > 0 and files:
                try:
                    scope_cfg = phase_spec.get("scope") or {}
                    try:
                        from autopack.deliverables_validator import extract_deliverables_from_scope

                        deliverables_list = (
                            extract_deliverables_from_scope(scope_cfg)
                            if isinstance(scope_cfg, dict)
                            else []
                        )
                    except Exception:
                        deliverables_list = []
                    if not deliverables_list and isinstance(scope_cfg, dict):
                        deliverables_list = scope_cfg.get("deliverables") or []
                    from autopack.context_budgeter import select_files_for_context

                    query = " ".join(
                        [
                            str(phase_spec.get("description") or ""),
                            str(phase_spec.get("name") or ""),
                            "Deliverables: "
                            + ", ".join([d for d in deliverables_list if isinstance(d, str)][:20]),
                        ]
                    ).strip()

                    selection = select_files_for_context(
                        files=files,
                        scope_metadata=scope_metadata,
                        deliverables=[d for d in deliverables_list if isinstance(d, str)],
                        query=query,
                        budget_tokens=int(context_budget_tokens),
                        semantic=os.getenv("AUTOPACK_CONTEXT_SEMANTIC_RELEVANCE", "1")
                        in ("1", "true", "True"),
                    )

                    if selection.omitted:
                        prompt_parts.append("\n# Context Budgeting (Autopack)")
                        prompt_parts.append(
                            f"Autopack kept {len(selection.kept)} files (mode={selection.mode}) "
                            f"and omitted {len(selection.omitted)} files to stay within budget."
                        )
                        prompt_parts.append(
                            "If you need a missing file, proceed with best effort; do NOT invent its contents."
                        )
                        prompt_parts.append("Omitted files (sample):")
                        for fp in selection.omitted[:40]:
                            prompt_parts.append(f"- {fp}")

                    files = selection.kept
                except Exception as exc:
                    logger.warning(f"[Builder] Context budgeting failed (non-fatal): {exc}")

            # Check if we need structured edit mode (files >1000 lines IN SCOPE)
            # NOTE: This should match the logic in execute_phase() above
            use_structured_edit_mode = False
            if config:
                # Get explicit scope paths from phase_spec
                scope_config = phase_spec.get("scope") or {}
                scope_paths = (
                    scope_config.get("paths", []) if isinstance(scope_config, dict) else []
                )
                if not isinstance(scope_paths, list):
                    scope_paths = []
                scope_paths = [sp for sp in scope_paths if isinstance(sp, str)]

                # Only check files in scope (or skip if no scope defined)
                if scope_paths:
                    for file_path, content in files.items():
                        if isinstance(content, str) and isinstance(file_path, str):
                            # Only check if file is in scope
                            if any(file_path.startswith(sp) for sp in scope_paths):
                                line_count = content.count("\n") + 1
                                if line_count > config.max_lines_hard_limit:
                                    use_structured_edit_mode = True
                                    break

            if missing_scope_files:
                prompt_parts.append("\n# Missing Scoped Files")
                prompt_parts.append(
                    "The following scoped files are within scope but do not exist yet. You may create them:"
                )
                for missing_path in missing_scope_files:
                    prompt_parts.append(f"- {missing_path}")

            if use_structured_edit_mode:
                # NEW: Structured edit mode - show files with line numbers (per IMPLEMENTATION_PLAN3.md Phase 5)
                prompt_parts.append("\n# Files in Context (for structured edits):")
                prompt_parts.append("Use line numbers to specify where to make changes.")
                prompt_parts.append("Line numbers are 1-indexed (first line is line 1).\n")

                for file_path, content in files.items():
                    if not isinstance(content, str):
                        continue

                    line_count = content.count("\n") + 1
                    prompt_parts.append(f"\n## {file_path} ({line_count} lines)")

                    # Show file with line numbers
                    lines = content.split("\n")

                    # For very large files, show first 100, middle section, last 100
                    if line_count > 300:
                        # First 100 lines
                        for i, line in enumerate(lines[:100], 1):
                            prompt_parts.append(f"{i:4d} | {line}")

                        prompt_parts.append(f"\n... [{line_count - 200} lines omitted] ...\n")

                        # Last 100 lines
                        for i, line in enumerate(lines[-100:], line_count - 99):
                            prompt_parts.append(f"{i:4d} | {line}")
                    else:
                        # Show all lines with numbers
                        for i, line in enumerate(lines, 1):
                            prompt_parts.append(f"{i:4d} | {line}")

            elif use_full_file_mode:
                # NEW: Separate files into modifiable vs read-only using scope metadata
                modifiable_files: List[Tuple[str, str, int, Dict[str, Any]]] = []
                readonly_files: List[Tuple[str, str, int, Dict[str, Any]]] = []
                fallback_readonly: List[Tuple[str, str, int]] = []

                for file_path, content in files.items():
                    if not isinstance(content, str):
                        continue
                    meta = scope_metadata.get(file_path)
                    line_count = content.count("\n") + 1

                    if meta:
                        category = meta.get("category")
                        if category == "modifiable":
                            modifiable_files.append((file_path, content, line_count, meta))
                        elif category == "read_only":
                            readonly_files.append((file_path, content, line_count, meta))
                        else:
                            fallback_readonly.append((file_path, content, line_count))
                    else:
                        fallback_readonly.append((file_path, content, line_count))

                # Add explicit contract (per GPT_RESPONSE14 Q1)
                if modifiable_files or readonly_files:
                    prompt_parts.append("\n# File Modification Rules")
                    prompt_parts.append(
                        "You are only allowed to modify files that are fully shown below."
                    )
                    prompt_parts.append(
                        "Any file marked as READ-ONLY CONTEXT must NOT appear in the `files` list in your JSON output."
                    )
                    prompt_parts.append(
                        "For each file you modify, return the COMPLETE new file content in `new_content`."
                    )
                    prompt_parts.append(
                        "Do NOT use ellipses (...) or omit any code that should remain."
                    )

                # Show modifiable files with full content (Bucket A: ≤500 lines)
                if modifiable_files:
                    prompt_parts.append("\n# Files You May Modify (COMPLETE CONTENT):")
                    for file_path, content, line_count, meta in modifiable_files:
                        missing_note = (
                            " — file does not exist yet, create it." if meta.get("missing") else ""
                        )
                        prompt_parts.append(f"\n## {file_path} ({line_count} lines){missing_note}")
                        if meta.get("missing"):
                            prompt_parts.append(
                                "This file is currently missing. Provide the complete new content below."
                            )
                        prompt_parts.append(f"```\n{content}\n```")

                # Show read-only files with truncated content (Bucket B+C: >500 lines)
                readonly_combined = readonly_files + [
                    (path, content, line_count, {})
                    for path, content, line_count in fallback_readonly
                ]
                if readonly_combined:
                    prompt_parts.append("\n# Read-Only Context Files (DO NOT MODIFY):")
                    for file_path, content, line_count, meta in readonly_combined:
                        prompt_parts.append(f"\n## {file_path} (READ-ONLY CONTEXT — DO NOT MODIFY)")
                        prompt_parts.append(
                            f"This file has {line_count} lines (too large for full-file replacement)."
                        )
                        prompt_parts.append(
                            "You may read this snippet as context, but you must NOT include it in your JSON output."
                        )

                        # Show first 200 + last 50 lines for context
                        lines = content.split("\n")
                        first_part = "\n".join(lines[:200])
                        last_part = "\n".join(lines[-50:])
                        prompt_parts.append(
                            f"```\n{first_part}\n\n... [{line_count - 250} lines omitted] ...\n\n{last_part}\n```"
                        )
            else:
                # Legacy diff mode: show truncated content
                prompt_parts.append("\n# Repository Context:")
                for file_path, content in list(files.items())[:5]:
                    prompt_parts.append(f"\n## {file_path}")
                    # Show first 500 chars without literal "..." to avoid teaching model bad habits
                    if isinstance(content, str):
                        prompt_parts.append(f"```\n{content[:500]}\n```")
                    else:
                        prompt_parts.append(f"```\n{str(content)[:500]}\n```")

        return "\n".join(prompt_parts)


class AnthropicAuditorClient:
    """Auditor implementation using Anthropic Claude API

    Used for:
    - Primary auditing in progressive strategies (claude-sonnet-4-5)
    - High-risk auditing in best_first strategies (claude-opus-4-5)
    - Dual auditing partner with OpenAI
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Anthropic client

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
        """
        if Anthropic is None:
            raise ImportError(
                "anthropic package not installed. " "Install with: pip install anthropic"
            )

        self.client = Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))

    def review_patch(
        self,
        patch_content: str,
        phase_spec: Dict,
        file_context: Optional[Dict] = None,
        max_tokens: Optional[int] = None,
        model: str = "claude-sonnet-4-5",
        project_rules: Optional[List] = None,
        run_hints: Optional[List] = None,
    ) -> AuditorResult:
        """Review patch using Claude

        Args:
            patch_content: Git diff format patch
            phase_spec: Phase specification
            file_context: Repository context
            max_tokens: Token budget
            model: Claude model
            project_rules: Learned rules
            run_hints: Within-run hints from earlier phases

        Returns:
            AuditorResult with issues found
        """
        try:
            # Build system prompt
            system_prompt = self._build_system_prompt()

            # Build user prompt
            user_prompt = self._build_user_prompt(
                patch_content, phase_spec, file_context, project_rules, run_hints
            )

            # Call Anthropic API
            # Use higher token limit to avoid truncation on complex reviews
            # Actual usage is typically ~500 tokens for JSON response
            response = self.client.messages.create(
                model=model,
                max_tokens=min(max_tokens or 8192, 8192),
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=0.1,  # Low temperature for consistent auditing
            )

            # Extract content
            content = response.content[0].text

            # Parse JSON response
            try:
                result_json = json.loads(content)
            except json.JSONDecodeError:
                # Fallback: treat as text review
                result_json = {
                    "approved": False,
                    "issues": [{"severity": "major", "description": content}],
                    "summary": "Review completed",
                }

            return AuditorResult(
                approved=result_json.get("approved", False),
                issues_found=result_json.get("issues", []),
                auditor_messages=[result_json.get("summary", "")],
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                model_used=model,
            )

        except Exception as e:
            # Return error result
            return AuditorResult(
                approved=False,
                issues_found=[
                    {
                        "severity": "critical",
                        "category": "auditor_error",
                        "description": f"Auditor error: {str(e)}",
                    }
                ],
                auditor_messages=[f"Auditor failed: {str(e)}"],
                tokens_used=0,
                model_used=model,
                error=str(e),
            )

    def _build_system_prompt(self) -> str:
        """Build system prompt for Claude Auditor"""
        base_prompt = """You are an expert code reviewer for an autonomous build system.

Your task is to review code patches for:
- Security vulnerabilities (OWASP Top 10)
- Type safety issues
- Edge cases and error handling
- Performance problems
- Best practice violations

Output Format (JSON):
{
  "approved": true/false,
  "issues": [
    {
      "severity": "minor|major|critical",
      "category": "security|types|logic|performance|style",
      "description": "Detailed issue description",
      "file_path": "path/to/file.py",
      "line_number": 42
    }
  ],
  "summary": "Brief review summary"
}

Approval Criteria:
- REJECT if any critical or major issues
- APPROVE if only minor issues or no issues"""

        # Inject prevention rules from debug journal
        try:
            prevention_rules = get_prevention_prompt_injection()
            if prevention_rules:
                base_prompt += "\n\n" + prevention_rules
        except Exception:
            # Gracefully continue if prevention rules can't be loaded
            pass

        return base_prompt

    def _build_user_prompt(
        self,
        patch_content: str,
        phase_spec: Dict,
        file_context: Optional[Dict],
        project_rules: Optional[List],
        run_hints: Optional[List] = None,
    ) -> str:
        """Build user prompt with patch to review"""
        prompt_parts = [
            "# Patch to Review",
            f"```diff\n{patch_content}\n```",
            "\n# Phase Context",
            f"Category: {phase_spec.get('task_category', 'general')}",
            f"Description: {phase_spec.get('description', '')}",
        ]

        if project_rules:
            prompt_parts.append("\n# Project Rules (check compliance):")
            for rule in project_rules[:10]:
                prompt_parts.append(f"- {rule.get('rule_text', '')}")

        if run_hints:
            prompt_parts.append("\n# Recent Run Hints:")
            for hint in run_hints[:5]:
                prompt_parts.append(f"- {hint}")

        # Milestone 2: Inject intention anchor (for validation context)
        if run_id := phase_spec.get("run_id"):
            from .intention_anchor import load_and_render_for_auditor

            anchor_section = load_and_render_for_auditor(
                run_id=run_id,
                base_dir=".",  # Use current directory (.autonomous_runs/<run_id>/)
            )
            if anchor_section:
                prompt_parts.append("\n")
                prompt_parts.append(anchor_section)

        prompt_parts.append("\nProvide your review as a JSON response.")

        return "\n".join(prompt_parts)
