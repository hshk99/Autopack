"""Phase execution orchestration for Anthropic Claude Builder.

Extracted from anthropic_clients.py as part of PR-CLIENT-1.
Handles the orchestration of Builder phase execution: input preparation,
context assembly, LLM invocation, response parsing, and result assembly.

This is a MECHANICAL EXTRACTION of the 1,015-line execute_phase() method
with minimal changes. The method calls back to the parent client for helper
methods like prompt building and parsing, which will be extracted in PR-CLIENT-2.
"""

import copy
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from ...continuation_recovery import ContinuationRecovery
from ...llm_client import BuilderResult
from ...llm_service import estimate_tokens
from ...token_estimator import TokenEstimator
from ..providers.anthropic_transport import AnthropicTransport

logger = logging.getLogger(__name__)


# Import the normalize_complexity function (module-level in anthropic_clients.py)
def normalize_complexity(value: str | None) -> str:
    """Normalize complexity value to canonical form.

    Per GPT_RESPONSE24 C1: Handle case variations, common suffixes, and aliases.
    Per GPT_RESPONSE25 C1: Log DATA_INTEGRITY for unknown values and fallback to "medium".

    Args:
        value: Raw complexity value from phase_spec

    Returns:
        Normalized complexity value (always one of ALLOWED_COMPLEXITIES)
    """
    if value is None:
        return "medium"  # Default

    # Normalize to lowercase and strip whitespace
    normalized = str(value).lower().strip()

    # Handle common aliases and variations
    if normalized in ["low", "simple", "trivial", "easy"]:
        return "low"
    elif normalized in ["medium", "moderate", "normal", "average"]:
        return "medium"
    elif normalized in ["high", "complex", "difficult", "hard"]:
        return "high"
    else:
        # Unknown value - log for data integrity tracking and fall back to medium
        logger.warning(
            f"[DATA_INTEGRITY] Unknown complexity value: {value!r} (normalized: {normalized!r}); "
            f"falling back to 'medium'"
        )
        return "medium"


# NOTE: _write_token_estimation_v2_telemetry will be imported at runtime
# to avoid circular imports. It remains in anthropic_clients.py for now.


class AnthropicPhaseExecutor:
    """Orchestrates Builder phase execution for Anthropic Claude.

    This class contains the extracted execute_phase() method from AnthropicBuilderClient.
    It orchestrates the entire phase execution flow but delegates to the parent client
    for helper methods (prompt building, parsing) which will be extracted in PR-CLIENT-2.

    Responsibilities:
    1. Input preparation (token budgets, format config, scope paths)
    2. Context assembly (system/user prompts with vector memory)
    3. LLM invocation via transport layer
    4. Response parsing coordination with continuation recovery
    5. Result assembly with telemetry and validation

    This orchestrator delegates to:
    - AnthropicTransport for API calls
    - Parent client for prompt building (_build_system_prompt, _build_user_prompt)
    - Parent client for parsing methods (_parse_ndjson_output, etc.)
    """

    def __init__(self, transport: AnthropicTransport, client):
        """Initialize with Anthropic transport layer and parent client.

        Args:
            transport: AnthropicTransport instance for API calls
            client: Parent AnthropicBuilderClient instance for calling helper methods
        """
        self.transport = transport
        self.client = client  # For calling helper methods during transition

    def execute_phase(
        self,
        phase_spec: Dict,
        file_context: Optional[Dict] = None,
        max_tokens: Optional[int] = None,
        model: str = "claude-sonnet-4-5",
        project_rules: Optional[List] = None,
        run_hints: Optional[List] = None,
        use_full_file_mode: bool = True,
        config=None,
        retrieved_context: Optional[str] = None,
    ) -> BuilderResult:
        """Execute a phase using Claude.

        This is the EXTRACTED execute_phase method from AnthropicBuilderClient.
        The code is preserved verbatim from lines 314-1310 of anthropic_clients.py.

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
            # Delegate to client helper method
            system_prompt = self.client._build_system_prompt(
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

            # Delegate to client helper method
            user_prompt = self.client._build_user_prompt(
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
                config_path = Path(__file__).parent.parent.parent.parent / "config" / "models.yaml"
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
                user_prompt = self.client._build_user_prompt(
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

            # PR-LLM-1: Call Anthropic API via transport wrapper with streaming for long operations
            # Use Claude's max output capacity (64K) to avoid truncation of large patches
            # Enable streaming to avoid 10-minute timeout for complex generations
            response = self.transport.send_request(
                messages=[{"role": "user", "content": user_prompt}],
                model=model,
                max_tokens=min(max_tokens or 64000, 64000),
                system=system_prompt,
                temperature=0.2,
                stream=True,
            )

            # Extract content and metadata from transport response
            content = response.content

            # BUILD-043: Comprehensive token budget logging
            actual_input_tokens = response.usage.input_tokens
            actual_output_tokens = response.usage.output_tokens
            total_tokens_used = response.usage.total_tokens
            output_utilization = (actual_output_tokens / max_tokens * 100) if max_tokens else 0

            logger.info(
                f"[TOKEN_BUDGET] phase={phase_id} complexity={complexity} "
                f"input={actual_input_tokens} output={actual_output_tokens}/{max_tokens} "
                f"total={total_tokens_used} utilization={output_utilization:.1f}% "
                f"model={response.model}"
            )

            # Track truncation (stop_reason from Anthropic API)
            stop_reason = response.stop_reason
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

            # Define parsing dispatcher (delegates to client parsing methods)
            def _parse_once(text: str):
                if use_ndjson_format:
                    return self.client._parse_ndjson_output(
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
                    return self.client._parse_structured_edit_output(
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
                    # Full-file mode is the default; legacy diff mode has been removed
                    return self.client._parse_full_file_output(
                        text,
                        file_context,
                        response,
                        model,
                        phase_spec,
                        config=config,
                        stop_reason=stop_reason,
                        was_truncated=was_truncated,
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
                        # PR-LLM-1: Call continuation via transport wrapper
                        continuation_response = self.transport.send_request(
                            messages=[{"role": "user", "content": continuation_prompt}],
                            model=model,
                            max_tokens=min(max_tokens or 64000, 64000),
                            system=system_prompt,
                            temperature=0.2,
                            stream=True,
                        )

                        continuation_content = continuation_response.content

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
                            return self.client._parse_full_file_output(
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
                    # Import telemetry function to avoid circular import
                    from ...anthropic_clients import _write_token_estimation_v2_telemetry

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
                    # Import telemetry function to avoid circular import
                    from ...anthropic_clients import _write_token_estimation_v2_telemetry

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
                    user_prompt_retry = self.client._build_user_prompt(
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

                    # IMP-003: Use transport wrapper for consistent circuit breaker,
                    # typed error handling, and telemetry during retries
                    retry_response = self.transport.send_request(
                        messages=[{"role": "user", "content": user_prompt_retry}],
                        model=model,
                        max_tokens=min(max_tokens or 64000, 64000),
                        system=system_prompt,
                        temperature=0.2,
                        stream=True,
                    )
                    retry_content = retry_response.content
                    retry_stop_reason = retry_response.stop_reason
                    retry_was_truncated = retry_stop_reason == "max_tokens"

                    if use_ndjson_format:
                        return self.client._parse_ndjson_output(
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
                        return self.client._parse_structured_edit_output(
                            retry_content,
                            file_context,
                            retry_response,
                            model,
                            phase_spec,
                            config=config,
                            stop_reason=retry_stop_reason,
                            was_truncated=retry_was_truncated,
                        )
                    # Full-file mode is the default; legacy diff mode has been removed
                    return self.client._parse_full_file_output(
                        retry_content,
                        file_context,
                        retry_response,
                        model,
                        phase_spec,
                        config=config,
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
