"""Builder orchestration for phase execution.

Extracted from autonomous_executor.py as part of PR-EXE-11.
Handles Builder LLM invocation, context loading, validation, and retry logic.
"""

import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from autopack.llm_client import BuilderResult

if TYPE_CHECKING:
    from autopack.autonomous_executor import AutonomousExecutor
from autopack.deliverables_validator import (
    validate_deliverables,
    format_validation_feedback_for_builder,
)
from autopack.governed_apply import GovernedApplyPath

logger = logging.getLogger(__name__)


class BuilderOrchestrator:
    """Orchestrates Builder execution with validation and retry logic.

    Responsibilities:
    1. Load context (file, learning, memory, intention)
    2. Pre-flight file size validation
    3. Deliverables contract and manifest gate
    4. Builder LLM invocation with fallback modes
    5. Auto-fallback to structured edits on parse/truncation failure
    6. Empty patch validation
    7. Empty files array retry logic
    8. Infra error backoff and provider health gating
    9. Token budget escalation (P10)
    10. Builder guardrail failure handling
    11. Deliverables validation (patch and JSON)
    12. Post builder result to API
    """

    def __init__(self, executor: "AutonomousExecutor"):
        """Initialize with reference to parent executor.

        Args:
            executor: Parent AutonomousExecutor instance for accessing:
                - llm_service: LLM service for Builder invocation
                - api_client: API client for posting results
                - memory_service: Vector memory service for context retrieval
                - context_preflight: File size validation module
                - file_size_telemetry: File size tracking
                - builder_output_config: Builder output configuration
                - run_id: Run identifier
                - run_type: Run type for governed apply
                - workspace: Workspace path
                - _run_tokens_used: Token usage tracking
                - _last_file_context: Last loaded file context
                - _last_builder_result: Last builder result for Doctor
                - _last_files_changed: Patch statistics
                - _last_lines_added: Patch statistics
                - _last_lines_removed: Patch statistics
                - _provider_infra_errors: Provider health tracking
        """
        self.executor = executor
        self.llm_service = executor.llm_service
        self.api_client = executor.api_client
        self.memory_service = getattr(executor, "memory_service", None)
        self.context_preflight = executor.context_preflight
        self.file_size_telemetry = executor.file_size_telemetry
        self.builder_output_config = executor.builder_output_config
        self.run_id = executor.run_id
        self.run_type = executor.run_type
        self.workspace = executor.workspace

    def execute_builder_with_validation(
        self,
        phase_id: str,
        phase: Dict,
        attempt_index: int,
        allowed_paths: Optional[List[str]] = None,
        memory_context: Optional[str] = None,
    ) -> Tuple[BuilderResult, Dict[str, Any]]:
        """Execute Builder with full validation pipeline.

        Main entry point for Builder orchestration. Loads context, invokes Builder,
        validates output, and handles all retry scenarios.

        Args:
            phase_id: Unique phase identifier
            phase: Phase specification dict
            attempt_index: Current attempt number for model escalation
            allowed_paths: Optional list of allowed file paths
            memory_context: Optional memory context to inject (IMP-ARCH-002)

        Returns:
            Tuple of (BuilderResult, context_info dict with file_context, learning_context, etc.)

        Raises:
            Exception: If context loading fails critically
        """
        logger.info(f"[{phase_id}] Step 1/4: Generating code with Builder (via LlmService)...")

        # 1A-1E: Load all context types
        context_info = self._load_context(phase_id, phase, memory_context=memory_context)

        # 1F-1G: Prepare phase spec with deliverables and protected paths
        phase_with_constraints, use_full_file_mode = self._prepare_phase_spec(
            phase_id, phase, context_info, attempt_index
        )

        # 1H-1J: Invoke Builder with auto-fallback to structured edits
        builder_result = self._invoke_builder(
            phase_id,
            phase,
            phase_with_constraints,
            context_info,
            use_full_file_mode,
            attempt_index,
        )

        # Store result for Doctor diagnostics and telemetry
        self.executor._last_builder_result = builder_result

        # Accumulate token usage
        self.executor._run_tokens_used += getattr(builder_result, "tokens_used", 0) or 0

        # Extract and store patch statistics
        self._extract_patch_stats(builder_result)

        # Sync metadata from phase_with_constraints back to phase
        if "metadata" in phase_with_constraints:
            phase.setdefault("metadata", {}).update(phase_with_constraints["metadata"])

        # 1K: Validate output (empty patch check)
        builder_result = self._validate_output(phase_id, builder_result)

        # 1K+: Validate deliverables against intention anchor constraints
        builder_result = self._validate_deliverable_against_intentions(
            phase_id, builder_result, context_info
        )

        # Return builder result and context for caller to handle posting/validation
        return builder_result, context_info

    def _load_context(
        self, phase_id: str, phase: Dict, memory_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Load all context types for Builder.

        Loads:
        - 1A: File context from repository
        - 1B: Scope validation
        - 1C: Learning context (rules and hints)
        - 1D: Vector memory retrieval (or use injected memory_context from IMP-ARCH-002)
        - 1E: Intention context injection

        Args:
            phase_id: Phase identifier for logging
            phase: Phase specification
            memory_context: Optional memory context from autonomous loop (IMP-ARCH-002)

        Returns:
            Dict with file_context, learning_context, retrieved_context, intention_context
        """
        # 1A: Load repository context
        file_context = self._load_file_context(phase_id, phase)

        # 1B: Validate scope configuration if present
        scope_config = phase.get("scope")
        if scope_config and scope_config.get("paths"):
            self.executor._validate_scope_context(phase, file_context, scope_config)

        # 1C: Load learning context (Stage 0A hints + Stage 0B rules)
        learning_context = self.executor._get_learning_context_for_phase(phase)
        project_rules = learning_context.get("project_rules", [])
        run_hints = learning_context.get("run_hints", [])

        if project_rules or run_hints:
            logger.info(
                f"[{phase_id}] Learning context: {len(project_rules)} rules, {len(run_hints)} hints"
            )

        # 1D: Retrieve supplemental context from vector memory or use injected memory_context
        if memory_context:
            # IMP-ARCH-002: Use memory context injected from autonomous loop
            retrieved_context = memory_context
            logger.info(f"[{phase_id}] Using injected memory context from autonomous loop")
        else:
            # Standard path: retrieve from vector memory
            retrieved_context = self._retrieve_memory_context(phase_id, phase)

        # 1E: Intention context injection
        intention_context = self._inject_intention_context(phase_id, retrieved_context)

        # Combine intention context with retrieved context
        if intention_context:
            if retrieved_context:
                retrieved_context = f"{intention_context}\n\n{retrieved_context}"
            else:
                retrieved_context = intention_context

        return {
            "file_context": file_context,
            "project_rules": project_rules,
            "run_hints": run_hints,
            "retrieved_context": retrieved_context,
        }

    def _load_file_context(self, phase_id: str, phase: Dict) -> Dict[str, Any]:
        """Load repository context for Builder.

        Args:
            phase_id: Phase identifier for logging
            phase: Phase specification

        Returns:
            File context dict with existing_files

        Raises:
            TypeError: If path/list error occurs (caught and handled)
        """
        try:
            file_context = self.executor._load_repository_context(phase)
            # BUILD-145 P1.1: Store context for telemetry
            self.executor._last_file_context = file_context
            logger.info(
                f"[{phase_id}] Loaded {len(file_context.get('existing_files', {}))} files for context"
            )
            return file_context

        except TypeError as e:
            if "unsupported operand type(s) for /" in str(e) and "list" in str(e):
                logger.error(f"[{phase_id}] Path/list error in context loading: {e}")
                import traceback

                logger.error(f"Traceback: {traceback.format_exc()}")
                # Return empty context to allow execution to continue
                file_context = {"existing_files": {}}
                self.executor._last_file_context = file_context
                return file_context
            else:
                raise

    def _retrieve_memory_context(self, phase_id: str, phase: Dict) -> str:
        """Retrieve supplemental context from vector memory.

        Args:
            phase_id: Phase identifier for logging
            phase: Phase specification

        Returns:
            Formatted retrieved context string
        """
        retrieved_context = ""

        if not self.memory_service or not self.memory_service.enabled:
            return retrieved_context

        try:
            # Build query from phase description for retrieval
            phase_description = phase.get("description", "")
            query = f"{phase_description[:500]}"
            project_id = self.executor._get_project_slug() or self.run_id

            # BUILD-154: Make SOT budget gating + telemetry explicit and non-silent
            from autopack.config import settings

            max_context_chars = max(4000, settings.autopack_sot_retrieval_max_chars + 2000)
            include_sot = self.executor._should_include_sot_retrieval(
                max_context_chars, phase_id=phase_id
            )

            retrieved = self.memory_service.retrieve_context(
                query=query,
                project_id=project_id,
                run_id=self.run_id,
                include_code=True,
                include_summaries=True,
                include_errors=True,
                include_hints=True,
                include_planning=True,
                include_plan_changes=True,
                include_decisions=True,
                include_sot=include_sot,
            )
            retrieved_context = self.memory_service.format_retrieved_context(
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

        return retrieved_context

    def _inject_intention_context(self, phase_id: str, retrieved_context: str) -> str:
        """Inject intention context if enabled.

        Args:
            phase_id: Phase identifier for logging
            retrieved_context: Current retrieved context (for telemetry)

        Returns:
            Intention context string (empty if disabled or failed)
        """
        # [BUILD-146 P6.2] Intention Context Injection (compact semantic anchor)
        intention_context = ""
        if os.getenv("AUTOPACK_ENABLE_INTENTION_CONTEXT", "false").lower() != "true":
            return intention_context

        try:
            from autopack.intention_wiring import IntentionContextInjector

            # Create injector (cached on first call per run)
            if not hasattr(self.executor, "_intention_injector"):
                project_id = self.executor._get_project_slug() or self.run_id
                self.executor._intention_injector = IntentionContextInjector(
                    run_id=self.run_id,
                    project_id=project_id,
                    memory_service=(
                        self.memory_service if hasattr(self.executor, "memory_service") else None
                    ),
                )

            # Get bounded intention context (≤2KB)
            intention_context = self.executor._intention_injector.get_intention_context(
                max_chars=2048
            )

            if intention_context:
                logger.info(
                    f"[{phase_id}] Injected {len(intention_context)} chars of intention context"
                )

                # [BUILD-146 P2] Record Phase 6 telemetry for intention context
                self._record_intention_telemetry(phase_id, intention_context)

        except Exception as e:
            logger.warning(f"[{phase_id}] Intention context injection failed: {e}")

        return intention_context

    def _record_intention_telemetry(self, phase_id: str, intention_context: str) -> None:
        """Record intention context telemetry to database.

        Args:
            phase_id: Phase identifier
            intention_context: Intention context string
        """
        if os.getenv("TELEMETRY_DB_ENABLED", "false").lower() != "true":
            return

        try:
            from autopack.usage_recorder import record_phase6_metrics
            from autopack.database import SessionLocal

            db = SessionLocal()
            try:
                # Determine source: memory or fallback
                source = (
                    "memory"
                    if hasattr(self.executor, "memory_service") and self.executor.memory_service
                    else "fallback"
                )

                record_phase6_metrics(
                    db=db,
                    run_id=self.run_id,
                    phase_id=phase_id,
                    intention_context_injected=True,
                    intention_context_chars=len(intention_context),
                    intention_context_source=source,
                )
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[{phase_id}] Failed to record Phase 6 telemetry: {e}")

    def _prepare_phase_spec(
        self, phase_id: str, phase: Dict, context_info: Dict, attempt_index: int = 0
    ) -> Tuple[Dict, bool]:
        """Prepare phase spec with deliverables contract and constraints.

        Performs:
        - 1F: Pre-flight file size validation and mode selection
        - 1G: Deliverables contract and manifest gate

        Args:
            phase_id: Phase identifier
            phase: Phase specification
            context_info: Context info with file_context
            attempt_index: Current attempt number for telemetry tracking

        Returns:
            Tuple of (phase_with_constraints, use_full_file_mode)
        """
        file_context = context_info["file_context"]

        # Pre-flight file size validation
        use_full_file_mode = self._validate_file_sizes(phase_id, phase, file_context)

        # Build deliverables contract
        deliverables_contract = self.executor._build_deliverables_contract(phase, phase_id)

        # Protected paths
        protected_paths = [".autonomous_runs/", ".git/", "autopack.db"]

        # Build phase with constraints
        phase_with_constraints = {
            **phase,
            "protected_paths": protected_paths,
            "deliverables_contract": deliverables_contract,
        }

        # Deliverables manifest gate
        self._run_deliverables_manifest_gate(phase_id, phase, phase_with_constraints, attempt_index)

        return phase_with_constraints, use_full_file_mode

    def _validate_file_sizes(self, phase_id: str, phase: Dict, file_context: Dict) -> bool:
        """Pre-flight file size validation.

        Checks if files exceed max line limits and decides on full-file vs structured mode.

        Args:
            phase_id: Phase identifier
            phase: Phase specification
            file_context: File context with existing_files

        Returns:
            True if full-file mode should be used, False for structured edits
        """
        use_full_file_mode = True  # Default mode

        # Override to structured edits if phase explicitly requests it
        if phase.get("builder_mode") == "structured_edit":
            use_full_file_mode = False

        if not file_context:
            return use_full_file_mode

        config = self.builder_output_config
        files = file_context.get("existing_files", {})

        # PR-EXE-5: Delegated to ContextPreflight module
        # Per GPT_RESPONSE15: Simplified 2-bucket policy
        # Bucket A: ≤1000 lines → full-file mode
        # Bucket B: >1000 lines → read-only context
        decision = self.context_preflight.decide_read_only(files)

        if decision.read_only:
            logger.warning(
                f"[{phase_id}] Large files in context (read-only, >{config.max_lines_hard_limit} lines): "
                f"{', '.join(p for p, _ in decision.oversized_files)}"
            )
            # Record telemetry for each large file
            for file_path, line_count in decision.oversized_files:
                self.file_size_telemetry.record_preflight_reject(
                    run_id=self.run_id,
                    phase_id=phase_id,
                    file_path=file_path,
                    line_count=line_count,
                    limit=config.max_lines_hard_limit,
                    bucket="B",  # Now just "too large" bucket
                )
            # Don't fail - these files can be read-only context
            # Parser will enforce that LLM doesn't try to modify them

        # For large scoped contexts, prefer structured edits to avoid truncation
        if len(files) >= 30:
            use_full_file_mode = False

        # Defensive check: If diff mode is somehow enabled, log loudly
        if config.legacy_diff_fallback_enabled and use_full_file_mode:
            logger.error(
                f"[{phase_id}] WARNING: legacy_diff_fallback_enabled is True but should be False! "
                f"All files ≤{config.max_lines_for_full_file} lines will use full-file mode."
            )

        return use_full_file_mode

    def _run_deliverables_manifest_gate(
        self, phase_id: str, phase: Dict, phase_with_constraints: Dict, attempt_index: int = 0
    ) -> None:
        """Run deliverables manifest gate (BUILD-065).

        Asks LLM for explicit manifest of file paths it will create,
        validates against expected deliverables.

        Args:
            phase_id: Phase identifier
            phase: Phase specification
            phase_with_constraints: Phase spec with constraints to update
            attempt_index: Current attempt number for telemetry tracking

        Raises:
            None - failures are logged but don't crash executor
        """
        try:
            from autopack.deliverables_validator import extract_deliverables_from_scope

            scope_cfg = phase.get("scope") or {}
            expected_paths = extract_deliverables_from_scope(scope_cfg)
            deliverables_contract = phase_with_constraints.get("deliverables_contract")

            if not expected_paths or not self.llm_service or not deliverables_contract:
                return

            # Derive allowed roots (tight allowlist)
            expected_set = {p for p in expected_paths if isinstance(p, str)}

            # Don't allow broad bucket prefixes to dilute the manifest
            bucket_roots = {"docs", "tests", "code", "polish"}
            expected_set = {
                p for p in expected_set if p.rstrip("/").replace("\\", "/") not in bucket_roots
            }
            expected_list = sorted(expected_set)

            allowed_roots: List[str] = []
            preferred_roots = (
                "src/autopack/research/",
                "src/autopack/cli/",
                "tests/research/",
                "docs/research/",
                "examples/",
            )
            for r in preferred_roots:
                if any(p.startswith(r) for p in expected_list):
                    allowed_roots.append(r)

            def _covered(path: str) -> bool:
                return any(path.startswith(r) for r in allowed_roots)

            if not allowed_roots or not all(_covered(p) for p in expected_list):
                expanded: List[str] = []
                for p in expected_list:
                    # Normalize trailing-slash directory prefixes
                    p_norm = p.rstrip("/")
                    parts = p_norm.split("/") if p_norm else []
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

            # Generate manifest with attempt_index for accurate telemetry
            ok_manifest, manifest_paths, manifest_error, _raw = (
                self.llm_service.generate_deliverables_manifest(
                    expected_paths=list(expected_set),
                    allowed_roots=allowed_roots,
                    run_id=self.run_id,
                    phase_id=phase_id,
                    attempt_index=attempt_index,
                )
            )

            if not ok_manifest:
                err_details = manifest_error or "deliverables manifest gate failed"
                logger.error(f"[{phase_id}] Deliverables manifest gate FAILED: {err_details}")
                self.executor._record_phase_error(
                    phase, "deliverables_manifest_failed", err_details, attempt_index
                )
                self.executor._record_learning_hint(
                    phase, "deliverables_manifest_failed", err_details
                )
                # Note: We don't return False here because this method doesn't control flow
                # The caller will handle the failure
            else:
                logger.info(
                    f"[{phase_id}] Deliverables manifest gate PASSED ({len(manifest_paths or [])} paths)"
                )
                # Attach manifest to phase spec so Builder prompt can be constrained
                phase_with_constraints["deliverables_manifest"] = manifest_paths or []

        except Exception as e:
            # Manifest gate should not crash the executor; fall back to normal builder
            logger.warning(f"[{phase_id}] Deliverables manifest gate error (skipping gate): {e}")

    def _invoke_builder(
        self,
        phase_id: str,
        phase: Dict,
        phase_with_constraints: Dict,
        context_info: Dict,
        use_full_file_mode: bool,
        attempt_index: int,
    ) -> BuilderResult:
        """Invoke Builder LLM with auto-fallback to structured edits.

        Performs:
        - 1H: Primary Builder invocation
        - 1I: Auto-fallback to structured edits on parse/truncation failure
        - 1J: Metadata sync back to phase

        Args:
            phase_id: Phase identifier
            phase: Phase specification
            phase_with_constraints: Phase spec with constraints
            context_info: Context info with file_context, rules, hints, retrieved_context
            use_full_file_mode: Whether to use full-file mode
            attempt_index: Current attempt number

        Returns:
            BuilderResult from LLM service
        """
        # Extract context components
        file_context = context_info["file_context"]
        project_rules = context_info["project_rules"]
        run_hints = context_info["run_hints"]
        retrieved_context = context_info["retrieved_context"]

        # Primary Builder invocation
        builder_result = self.llm_service.execute_builder_phase(
            phase_spec=phase_with_constraints,
            file_context=file_context,
            max_tokens=phase.get("_escalated_tokens"),
            project_rules=project_rules,
            run_hints=run_hints,
            run_id=self.run_id,
            phase_id=phase_id,
            run_context=self.executor._build_run_context(),
            attempt_index=attempt_index,
            use_full_file_mode=use_full_file_mode,
            config=self.builder_output_config,
            retrieved_context=retrieved_context,
        )

        # Sync metadata back to phase
        if "metadata" in phase_with_constraints:
            phase.setdefault("metadata", {}).update(phase_with_constraints["metadata"])

        # Auto-fallback to structured edits on parse/truncation failure
        retry_parse_markers = [
            "full_file_parse_failed",
            "expected json with 'files' array",
            "full-file json parse failed",
            "output was truncated",
            "stop_reason=max_tokens",
            "no git diff markers found",
            "output must start with 'diff --git'",
        ]
        error_text_lower = (builder_result.error or "").lower() if builder_result.error else ""
        should_retry_structured = not builder_result.success and any(
            m in error_text_lower for m in retry_parse_markers
        )

        if should_retry_structured:
            logger.warning(
                f"[{phase_id}] Falling back to structured_edit after full-file parse/truncation failure"
            )

            phase_structured = {
                **phase,
                "builder_mode": "structured_edit",
                "protected_paths": phase_with_constraints.get("protected_paths"),
                "deliverables_contract": phase_with_constraints.get("deliverables_contract"),
            }

            builder_result = self.llm_service.execute_builder_phase(
                phase_spec=phase_structured,
                file_context=file_context,
                max_tokens=phase.get("_escalated_tokens"),
                project_rules=project_rules,
                run_hints=run_hints,
                run_id=self.run_id,
                phase_id=phase_id,
                run_context=self.executor._build_run_context(),
                attempt_index=attempt_index,
                use_full_file_mode=False,
                config=self.builder_output_config,
                retrieved_context=retrieved_context,
            )

            # Sync metadata from fallback attempt
            if "metadata" in phase_structured:
                phase.setdefault("metadata", {}).update(phase_structured["metadata"])

            # Accumulate token usage for fallback
            self.executor._run_tokens_used += getattr(builder_result, "tokens_used", 0) or 0

            # Extract patch stats for fallback
            self._extract_patch_stats(builder_result)

        return builder_result

    def _extract_patch_stats(self, builder_result: BuilderResult) -> None:
        """Extract and store patch statistics.

        Args:
            builder_result: Builder result with patch content
        """
        is_maintenance_run = self.run_type in [
            "autopack_maintenance",
            "autopack_upgrade",
            "self_repair",
        ]
        governed_apply = GovernedApplyPath(
            workspace=Path(self.workspace),
            run_type=self.run_type,
            autopack_internal_mode=is_maintenance_run,
        )
        (
            self.executor._last_files_changed,
            self.executor._last_lines_added,
            self.executor._last_lines_removed,
        ) = governed_apply.parse_patch_stats(builder_result.patch_content or "")

    def _validate_output(self, phase_id: str, builder_result: BuilderResult) -> BuilderResult:
        """Validate Builder output for empty patches.

        Checks if patch content or edit_plan is present, handles no-op cases.

        Args:
            phase_id: Phase identifier
            builder_result: Builder result to validate

        Returns:
            BuilderResult (possibly modified with error if validation fails)
        """
        # Allow explicit structured-edit no-op (builder already warned) to pass through
        # BUILD-141 Part 8: Allow explicit full-file no-op (idempotent phase) to pass through
        # Allow edit_plan as valid alternative to patch_content (structured edits)
        has_patch = builder_result.patch_content and builder_result.patch_content.strip()
        has_edit_plan = (
            hasattr(builder_result, "edit_plan") and builder_result.edit_plan is not None
        )

        if builder_result.success and not has_patch and not has_edit_plan:
            messages = builder_result.builder_messages or []
            no_op_structured = any("Structured edit produced no operations" in m for m in messages)
            no_op_fullfile = any("Full-file produced no diffs" in m for m in messages)

            if not no_op_structured and not no_op_fullfile:
                builder_result = BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=["empty_patch: builder produced no changes"],
                    tokens_used=builder_result.tokens_used,
                    model_used=getattr(builder_result, "model_used", None),
                    error="empty_patch: builder produced no changes",
                )

        return builder_result

    def handle_retry_scenarios(
        self, phase_id: str, phase: Dict, builder_result: BuilderResult, attempt_index: int
    ) -> Tuple[bool, str]:
        """Handle Builder retry scenarios.

        Checks for:
        - 1L: Empty files array retry
        - 1M: Infra error backoff
        - 1N: Token budget escalation (P10)
        - 1O: Builder guardrail failures

        Args:
            phase_id: Phase identifier
            phase: Phase specification
            builder_result: Builder result to check
            attempt_index: Current attempt number

        Returns:
            Tuple of (should_retry, retry_reason)
            - should_retry: False if phase should fail, True to retry
            - retry_reason: Reason code for retry (or "FAILED")
        """
        if builder_result.success:
            return True, "SUCCESS"  # No retry needed

        # 1L: Empty files array retry
        retry_result = self._handle_empty_files_retry(
            phase_id, phase, builder_result, attempt_index
        )
        if retry_result:
            return retry_result

        # 1M: Infra error backoff
        retry_result = self._handle_infra_errors(phase_id, phase, builder_result, attempt_index)
        if retry_result:
            return retry_result

        # 1N: Token budget escalation (P10)
        retry_result = self._handle_token_escalation(phase_id, phase, builder_result, attempt_index)
        if retry_result:
            return retry_result

        # 1O: Builder guardrail failures - no retry, just record
        return False, "FAILED"

    def _handle_empty_files_retry(
        self, phase_id: str, phase: Dict, builder_result: BuilderResult, attempt_index: int
    ) -> Optional[Tuple[bool, str]]:
        """Handle empty files array retry logic.

        Args:
            phase_id: Phase identifier
            phase: Phase specification
            builder_result: Builder result
            attempt_index: Current attempt number

        Returns:
            None if not applicable, (False, "EMPTY_FILES_RETRY") if should retry
        """
        # BUILD-141 Telemetry Unblock: Targeted retry for "empty files array" errors
        empty_files_markers = ["empty files array", "llm returned empty files array"]
        error_text_lower = (builder_result.error or "").lower() if builder_result.error else ""
        is_empty_files_error = any(m in error_text_lower for m in empty_files_markers)

        if not is_empty_files_error:
            return None

        # Check if we've already retried for empty files array (limit to 1 retry)
        empty_files_retry_count = phase.get("_empty_files_retry_count", 0)
        max_builder_attempts = phase.get("max_builder_attempts") or 5

        if empty_files_retry_count == 0 and attempt_index < (max_builder_attempts - 1):
            logger.warning(
                f"[{phase_id}] Empty files array detected - retrying ONCE with stronger deliverables emphasis "
                f"(attempt {attempt_index + 1}/{max_builder_attempts})"
            )
            phase["_empty_files_retry_count"] = 1
            return False, "EMPTY_FILES_RETRY"
        else:
            logger.error(
                f"[{phase_id}] Empty files array persists after targeted retry - failing fast to avoid token waste"
            )
            # Fall through to normal error handling
            return None

    def _handle_infra_errors(
        self, phase_id: str, phase: Dict, builder_result: BuilderResult, attempt_index: int
    ) -> Optional[Tuple[bool, str]]:
        """Handle infrastructure error backoff and provider health gating.

        Args:
            phase_id: Phase identifier
            phase: Phase specification (unused but kept for API consistency)
            builder_result: Builder result
            attempt_index: Current attempt number

        Returns:
            None if not applicable, (False, "INFRA_RETRY") if should retry
        """
        # Retryable infra errors: backoff and retry without burning through non-infra budgets
        infra_markers = [
            "connection error",
            "timeout",
            "timed out",
            "api failure",
            "server error",
            "http 500",
        ]
        error_text_lower = (builder_result.error or "").lower() if builder_result.error else ""
        is_infra_error = any(m in error_text_lower for m in infra_markers)

        if not is_infra_error:
            return None

        backoff = min(5 * (attempt_index + 1), 20)
        logger.warning(
            f"[{phase_id}] Infra error detected (retryable): {builder_result.error}. "
            f"Backing off {backoff}s before retry."
        )

        # Provider health gating: disable provider after repeated infra errors
        model_used = getattr(builder_result, "model_used", "") or ""
        provider = self.executor._model_to_provider(model_used)
        if provider:
            self.executor._provider_infra_errors[provider] = (
                self.executor._provider_infra_errors.get(provider, 0) + 1
            )
            if self.executor._provider_infra_errors[provider] >= 2:
                try:
                    self.llm_service.model_router.disable_provider(provider, reason="infra_error")
                    logger.warning(
                        f"[{phase_id}] Disabled provider {provider} for this run after repeated infra errors."
                    )
                except Exception as e:
                    logger.warning(f"[{phase_id}] Failed to disable provider {provider}: {e}")

        # NOTE: time.sleep() intentional - orchestrator runs in sync context
        time.sleep(backoff)
        return False, "INFRA_RETRY"

    def _handle_token_escalation(
        self, phase_id: str, phase: Dict, builder_result: BuilderResult, attempt_index: int
    ) -> Optional[Tuple[bool, str]]:
        """Handle token budget escalation (P10).

        Escalates token budget once if output was truncated or high utilization.

        Args:
            phase_id: Phase identifier
            phase: Phase specification
            builder_result: Builder result
            attempt_index: Current attempt number

        Returns:
            None if not applicable, (False, "TOKEN_ESCALATION") if should retry with more tokens
        """
        # BUILD-129 Phase 3 P10: Escalate-once for high utilization or truncation
        max_builder_attempts = phase.get("max_builder_attempts") or 5
        metadata = phase.get("metadata", {})
        token_budget = metadata.get("token_budget", {})
        token_prediction = metadata.get("token_prediction", {})

        # Check if we should escalate
        was_truncated = getattr(builder_result, "was_truncated", False)
        output_utilization = token_budget.get("output_utilization", 0)
        should_escalate = was_truncated or output_utilization >= 95.0

        # Check if we've already escalated once
        already_escalated = phase.get("_escalated_once", False)

        if not should_escalate or already_escalated or attempt_index >= (max_builder_attempts - 1):
            return None

        # Escalate from highest evidence-based bound
        selected_budget = token_prediction.get("selected_budget", 0)
        actual_max_tokens = token_prediction.get("actual_max_tokens", 0)
        tokens_used = token_budget.get("actual_output_tokens", 0)

        base_candidates = {
            "selected_budget": selected_budget,
            "actual_max_tokens": actual_max_tokens,
            "tokens_used": tokens_used,
        }

        current_max_tokens = max(base_candidates.values())
        base_source = max(base_candidates, key=base_candidates.get)

        if current_max_tokens == 0:
            # Fallback to complexity-based defaults (BUILD-042)
            complexity = phase.get("complexity", "medium")
            if complexity == "low":
                current_max_tokens = 8192
            elif complexity == "medium":
                current_max_tokens = 12288
            elif complexity == "high":
                current_max_tokens = 16384
            else:
                current_max_tokens = 8192
            base_source = "complexity_default"

        # Escalate by 25% (conservative to save tokens)
        escalation_factor = 1.25
        escalated_tokens = min(int(current_max_tokens * escalation_factor), 64000)
        phase["_escalated_tokens"] = escalated_tokens
        phase["_escalated_once"] = True  # Prevent multiple escalations

        # Record P10 escalation details in metadata
        p10_metadata = {
            "retry_budget_escalation_factor": escalation_factor,
            "p10_base_value": current_max_tokens,
            "p10_base_source": base_source,
            "p10_retry_max_tokens": escalated_tokens,
            "p10_selected_budget": selected_budget,
            "p10_actual_max_tokens": actual_max_tokens,
            "p10_tokens_used": tokens_used,
        }
        phase.setdefault("metadata", {}).setdefault("token_budget", {}).update(p10_metadata)

        reason = "truncation" if was_truncated else f"{output_utilization:.1f}% utilization"
        logger.info(
            f"[BUILD-129:P10] ESCALATE-ONCE: phase={phase_id} attempt={attempt_index + 1} "
            f"base={current_max_tokens} (from {base_source}) → retry={escalated_tokens} (1.25x, {reason})"
        )

        # Persist P10 decision to DB
        if os.environ.get("TELEMETRY_DB_ENABLED", "").lower() in ["1", "true", "yes"]:
            from autopack.executor.db_events import try_record_token_budget_escalation_event

            try_record_token_budget_escalation_event(
                run_id=self.run_id,
                phase_id=phase_id,
                attempt_index=attempt_index + 1,
                reason="truncation" if was_truncated else "utilization",
                was_truncated=bool(was_truncated),
                output_utilization=(
                    float(output_utilization) if output_utilization is not None else None
                ),
                escalation_factor=float(escalation_factor),
                base_value=int(current_max_tokens),
                base_source=str(base_source),
                retry_max_tokens=int(escalated_tokens),
                selected_budget=(int(selected_budget) if selected_budget else None),
                actual_max_tokens=(int(actual_max_tokens) if actual_max_tokens else None),
                tokens_used=int(tokens_used) if tokens_used else None,
            )

        return False, "TOKEN_ESCALATION"

    def handle_builder_failure(
        self, phase_id: str, phase: Dict, builder_result: BuilderResult, attempt_index: int
    ) -> Tuple[str, bool]:
        """Handle Builder guardrail failures with Doctor invocation.

        Records learning hints, invokes Doctor for diagnosis, and creates structured issues.

        Args:
            phase_id: Phase identifier
            phase: Phase specification
            builder_result: Failed builder result
            attempt_index: Current attempt number

        Returns:
            Tuple of (action_taken, should_continue)
        """
        logger.error(f"[{phase_id}] Builder failed: {builder_result.error}")

        # Record guardrail-type failures explicitly for learning / Doctor
        error_text = (builder_result.error or "").lower()
        if "churn_limit_exceeded" in error_text:
            error_category = "builder_churn_limit_exceeded"
        elif any(
            g in error_text
            for g in [
                "suspicious_growth",
                "suspicious_shrinkage",
                "truncation",
                "pack_fullfile",
            ]
        ):
            error_category = "builder_guardrail"
        else:
            error_category = "auditor_reject"

        # Learning + replan telemetry
        self.executor._record_learning_hint(
            phase=phase,
            hint_type=error_category,
            details=builder_result.error or "Builder failed without error message",
        )
        self.executor._record_phase_error(
            phase=phase,
            error_type=error_category,
            error_details=builder_result.error or "Builder failed without error message",
            attempt_index=attempt_index,
        )

        # Optionally invoke Doctor for diagnosable builder failures
        doctor_response = self.executor._invoke_doctor(
            phase=phase,
            error_category=error_category,
            builder_attempts=attempt_index + 1,
            last_patch=None,
            patch_errors=[],
            logs_excerpt=builder_result.error or "",
        )

        action_taken = "no_action"
        should_continue = True

        if doctor_response:
            action_taken, should_continue = self.executor._handle_doctor_action(
                phase=phase,
                response=doctor_response,
                attempt_index=attempt_index,
            )

        # Record a structured issue for builder guardrail failures
        self._record_builder_issue(phase_id, phase, error_category, builder_result)

        return action_taken, should_continue

    def _record_builder_issue(
        self, phase_id: str, phase: Dict, error_category: str, builder_result: BuilderResult
    ) -> None:
        """Record structured issue for Builder guardrail failure.

        Args:
            phase_id: Phase identifier
            phase: Phase specification
            error_category: Error category
            builder_result: Failed builder result
        """
        try:
            from autopack.issue_tracker import IssueTracker

            tracker = IssueTracker(run_id=self.run_id)
            tier_id = phase.get("tier_id", "unknown")

            if error_category == "builder_churn_limit_exceeded":
                issue_key = "builder_churn_limit_exceeded"
                category = "builder_guardrail"
            elif error_category == "builder_guardrail":
                issue_key = "builder_guardrail_failure"
                category = "builder_guardrail"
            else:
                issue_key = "builder_failure"
                category = "builder_failure"

            tracker.record_issue(
                phase_index=phase.get("phase_index", 0),
                phase_id=phase_id,
                tier_id=tier_id,
                issue_key=issue_key,
                severity="major",
                source="builder",
                category=category,
                task_category=phase.get("task_category"),
                complexity=phase.get("complexity"),
                evidence_refs=[builder_result.error] if builder_result.error else None,
            )
        except Exception as e:
            logger.warning(f"[IssueTracker] Failed to record builder guardrail issue: {e}")

    def validate_deliverables(
        self,
        phase_id: str,
        phase: Dict,
        builder_result: BuilderResult,
        attempt_index: int,
    ) -> Tuple[bool, str]:
        """Validate deliverables in patch content.

        Performs:
        - 1Q: Patch deliverables validation
        - 1R: JSON deliverables validation with auto-repair

        Args:
            phase_id: Phase identifier
            phase: Phase specification
            builder_result: Builder result with patch
            attempt_index: Current attempt number

        Returns:
            Tuple of (is_valid, failure_reason)
            - is_valid: True if all validations passed
            - failure_reason: Reason code if validation failed (or empty string)
        """
        # First check if we need to escalate due to truncation (before deliverables validation)
        escalation_result = self._check_deliverables_truncation_escalation(
            phase_id, phase, builder_result, attempt_index
        )
        if escalation_result:
            return escalation_result

        # 1Q: Validate patch deliverables
        validation_result = self._validate_patch_deliverables(
            phase_id, phase, builder_result, attempt_index
        )
        if not validation_result[0]:
            return validation_result

        # 1R: Validate JSON deliverables
        validation_result = self._validate_json_deliverables(
            phase_id, phase, builder_result, attempt_index
        )
        if not validation_result[0]:
            return validation_result

        return True, ""

    def _check_deliverables_truncation_escalation(
        self,
        phase_id: str,
        phase: Dict,
        builder_result: BuilderResult,
        attempt_index: int,
    ) -> Optional[Tuple[bool, str]]:
        """Check if deliverables validation failure is due to truncation and escalate.

        Args:
            phase_id: Phase identifier
            phase: Phase specification
            builder_result: Builder result
            attempt_index: Current attempt number

        Returns:
            None if no escalation needed, (False, "TOKEN_ESCALATION") if should escalate
        """
        # BUILD-129 Phase 3 P10 (expanded): If builder output was truncated/near-ceiling,
        # deliverables validation failures are often just "incomplete output"
        try:
            max_builder_attempts = phase.get("max_builder_attempts") or 5
            metadata = phase.get("metadata", {})
            token_budget = metadata.get("token_budget", {})
            token_prediction = metadata.get("token_prediction", {})

            was_truncated = getattr(builder_result, "was_truncated", False)
            output_utilization = token_budget.get("output_utilization", 0) or 0
            should_escalate = was_truncated or output_utilization >= 95.0
            already_escalated = phase.get("_escalated_once", False)

            if (
                should_escalate
                and not already_escalated
                and attempt_index < (max_builder_attempts - 1)
            ):
                # Same escalation logic as in _handle_token_escalation
                selected_budget = token_prediction.get("selected_budget", 0)
                actual_max_tokens = token_prediction.get("actual_max_tokens", 0)
                tokens_used = token_budget.get("actual_output_tokens", 0)

                base_candidates = {
                    "selected_budget": selected_budget,
                    "actual_max_tokens": actual_max_tokens,
                    "tokens_used": tokens_used,
                }

                current_max_tokens = max(base_candidates.values())
                base_source = max(base_candidates, key=base_candidates.get)

                if current_max_tokens == 0:
                    complexity = phase.get("complexity", "medium")
                    if complexity == "low":
                        current_max_tokens = 8192
                    elif complexity == "medium":
                        current_max_tokens = 12288
                    elif complexity == "high":
                        current_max_tokens = 16384
                    else:
                        current_max_tokens = 8192
                    base_source = "complexity_default"

                escalation_factor = 1.25
                escalated_tokens = min(int(current_max_tokens * escalation_factor), 64000)
                phase["_escalated_tokens"] = escalated_tokens
                phase["_escalated_once"] = True

                p10_metadata = {
                    "retry_budget_escalation_factor": escalation_factor,
                    "p10_base_value": current_max_tokens,
                    "p10_base_source": base_source,
                    "p10_retry_max_tokens": escalated_tokens,
                    "p10_selected_budget": selected_budget,
                    "p10_actual_max_tokens": actual_max_tokens,
                    "p10_tokens_used": tokens_used,
                }
                phase.setdefault("metadata", {}).setdefault("token_budget", {}).update(p10_metadata)

                reason = "truncation" if was_truncated else f"{output_utilization:.1f}% utilization"
                logger.info(
                    f"[BUILD-129:P10] ESCALATE-ONCE: phase={phase_id} attempt={attempt_index + 1} "
                    f"base={current_max_tokens} (from {base_source}) → retry={escalated_tokens} (1.25x, {reason})"
                )

                # Persist P10 decision to DB
                if os.environ.get("TELEMETRY_DB_ENABLED", "").lower() in ["1", "true", "yes"]:
                    from autopack.executor.db_events import try_record_token_budget_escalation_event

                    try_record_token_budget_escalation_event(
                        run_id=self.run_id,
                        phase_id=phase_id,
                        attempt_index=attempt_index + 1,
                        reason="truncation" if was_truncated else "utilization",
                        was_truncated=bool(was_truncated),
                        output_utilization=(
                            float(output_utilization) if output_utilization is not None else None
                        ),
                        escalation_factor=float(escalation_factor),
                        base_value=int(current_max_tokens),
                        base_source=str(base_source),
                        retry_max_tokens=int(escalated_tokens),
                        selected_budget=(int(selected_budget) if selected_budget else None),
                        actual_max_tokens=(int(actual_max_tokens) if actual_max_tokens else None),
                        tokens_used=int(tokens_used) if tokens_used else None,
                    )

                return False, "TOKEN_ESCALATION"
        except Exception as e:
            logger.warning(f"[BUILD-129:P10] Deliverables-failure escalation check failed: {e}")

        return None

    def _validate_patch_deliverables(
        self,
        phase_id: str,
        phase: Dict,
        builder_result: BuilderResult,
        attempt_index: int,
    ) -> Tuple[bool, str]:
        """Validate patch deliverables.

        Args:
            phase_id: Phase identifier
            phase: Phase specification
            builder_result: Builder result
            attempt_index: Current attempt number (unused but kept for consistency)

        Returns:
            Tuple of (is_valid, failure_reason)
        """
        scope_config = phase.get("scope", {})

        # If we have a deliverables manifest, include it in validation
        deliverables_manifest = phase.get("deliverables_manifest")
        if isinstance(deliverables_manifest, list) and deliverables_manifest:
            try:
                scope_config = {
                    **(scope_config or {}),
                    "deliverables_manifest": deliverables_manifest,
                }
            except Exception:
                pass

        # Structured-edit deliverables: extract touched paths from edit_plan
        touched_paths = None
        try:
            plan = getattr(builder_result, "edit_plan", None)
            ops = getattr(plan, "operations", None) if plan is not None else None
            if ops:
                extracted = []
                for op in ops:
                    p = getattr(op, "file_path", None)
                    if isinstance(p, str) and p.strip():
                        extracted.append(p.strip())
                if extracted:
                    touched_paths = extracted
        except Exception:
            touched_paths = None

        is_valid, validation_errors, validation_details = validate_deliverables(
            patch_content=builder_result.patch_content or "",
            phase_scope=scope_config,
            phase_id=phase_id,
            workspace=Path(self.workspace),
            touched_paths=touched_paths,
        )

        if not is_valid:
            # Generate detailed feedback for Builder
            feedback = format_validation_feedback_for_builder(
                errors=validation_errors,
                details=validation_details,
                phase_description=phase.get("description", ""),
            )

            logger.error(f"[{phase_id}] Deliverables validation failed")
            logger.error(f"[{phase_id}] {feedback}")

            # Record learning hint with path structure emphasis
            self._record_deliverables_hint(phase_id, phase, validation_details)

            return False, "DELIVERABLES_VALIDATION_FAILED"

        return True, ""

    def _record_deliverables_hint(
        self, phase_id: str, phase: Dict, validation_details: Dict
    ) -> None:
        """Record learning hint for deliverables validation failure.

        Args:
            phase_id: Phase identifier
            phase: Phase specification
            validation_details: Validation details dict
        """
        missing_paths = validation_details.get("missing_paths", [])
        misplaced = validation_details.get("misplaced_paths", {})

        hint_details = []

        # If there are misplaced files, emphasize the path correction
        if misplaced:
            expected_paths = validation_details.get("expected_paths", [])
            if expected_paths:
                # Get common directory prefix
                from os.path import commonpath

                try:
                    common_prefix = commonpath(expected_paths)
                    hint_details.append(f"All files must be under: {common_prefix}/")
                except (ValueError, TypeError):
                    pass

            # Show examples of wrong → correct
            for expected, actual in list(misplaced.items())[:2]:
                hint_details.append(f"Wrong: {actual} → Correct: {expected}")

        # Strong heuristic: forbid top-level tracer_bullet/ package
        actual_paths = validation_details.get("actual_paths", []) or []
        if any(p.startswith("tracer_bullet/") for p in actual_paths):
            hint_details.insert(
                0,
                "DO NOT create a top-level 'tracer_bullet/' package. "
                "All tracer bullet code MUST live under 'src/autopack/research/tracer_bullet/'. "
                "Tests MUST live under 'tests/research/tracer_bullet/'. "
                "Docs MUST live under 'docs/research/'.",
            )

        # Add missing files if space
        if len(hint_details) < 3 and missing_paths:
            hint_details.append(
                f"Missing {len(missing_paths)} files including: {', '.join(missing_paths[:3])}"
            )

        hint_text = (
            "; ".join(hint_details) if hint_details else f"Missing: {', '.join(missing_paths[:3])}"
        )

        self.executor._record_learning_hint(
            phase=phase, hint_type="deliverables_validation_failed", details=hint_text
        )

    def _validate_json_deliverables(
        self,
        phase_id: str,
        phase: Dict,
        builder_result: BuilderResult,
        attempt_index: int,
    ) -> Tuple[bool, str]:
        """Validate JSON deliverables with auto-repair.

        Args:
            phase_id: Phase identifier
            phase: Phase specification
            builder_result: Builder result (modified in-place if repaired)
            attempt_index: Current attempt number (unused but kept for consistency)

        Returns:
            Tuple of (is_valid, failure_reason)
        """
        # BUILD-070: Pre-apply validation for new JSON deliverables
        try:
            from autopack.deliverables_validator import (
                extract_deliverables_from_scope,
                validate_new_json_deliverables_in_patch,
            )

            scope_config = phase.get("scope", {})
            expected_paths = extract_deliverables_from_scope(scope_config or {})

            ok_json, json_errors, json_details = validate_new_json_deliverables_in_patch(
                patch_content=builder_result.patch_content or "",
                expected_paths=expected_paths,
                workspace=Path(self.workspace),
            )

            if not ok_json:
                # BUILD-075: Auto-repair empty/invalid required JSON deliverables
                ok_json, json_errors, json_details = self._auto_repair_json_deliverables(
                    phase_id, phase, builder_result, expected_paths, json_details
                )

            if not ok_json:
                logger.error(f"[{phase_id}] Pre-apply JSON deliverables validation failed")
                for e in json_errors[:5]:
                    logger.error(f"[{phase_id}]    {e}")

                # Record learning hint
                self.executor._record_learning_hint(
                    phase=phase,
                    hint_type="deliverables_validation_failed",
                    details="JSON deliverable invalid/empty (must be valid non-empty JSON; e.g. gold_set.json)",
                )

                return False, "DELIVERABLES_VALIDATION_FAILED"

        except Exception as e:
            logger.warning(f"[{phase_id}] Pre-apply JSON validation skipped due to error: {e}")

        return True, ""

    def _auto_repair_json_deliverables(
        self,
        phase_id: str,
        phase: Dict,
        builder_result: BuilderResult,
        expected_paths: List[str],
        json_details: Dict,
    ) -> Tuple[bool, List[str], Dict]:
        """Auto-repair empty/invalid required JSON deliverables.

        Args:
            phase_id: Phase identifier
            phase: Phase specification
            builder_result: Builder result (modified in-place if repaired)
            expected_paths: Expected deliverable paths
            json_details: JSON validation details

        Returns:
            Tuple of (ok_json, json_errors, json_details) after repair attempt
        """
        try:
            from autopack.deliverables_validator import (
                repair_empty_required_json_deliverables_in_patch,
                validate_new_json_deliverables_in_patch,
            )

            repaired, repaired_patch, repairs = repair_empty_required_json_deliverables_in_patch(
                patch_content=builder_result.patch_content or "",
                expected_paths=expected_paths,
                workspace=Path(self.workspace),
                minimal_json="[]\n",
            )

            if repaired:
                logger.warning(
                    f"[{phase_id}] Auto-repaired {len(repairs)} required JSON deliverable(s) to minimal valid JSON"
                )
                for r in repairs[:5]:
                    logger.warning(
                        f"[{phase_id}]    repaired {r.get('path')}: {r.get('reason')} -> {r.get('applied')}"
                    )

                builder_result.patch_content = repaired_patch

                # Re-validate after repair
                ok_json2, json_errors2, json_details2 = validate_new_json_deliverables_in_patch(
                    patch_content=builder_result.patch_content or "",
                    expected_paths=expected_paths,
                    workspace=Path(self.workspace),
                )

                if ok_json2:
                    self.executor._record_learning_hint(
                        phase=phase,
                        hint_type="success_after_retry",
                        details="Auto-repaired required JSON deliverable to minimal valid JSON placeholder ([]).",
                    )
                    return True, [], json_details2
                else:
                    return False, json_errors2, json_details2

        except Exception as e:
            logger.warning(
                f"[{phase_id}] Auto-repair for JSON deliverables skipped due to error: {e}"
            )

        # Return original validation state if repair failed or was skipped
        return False, [], json_details

    def _validate_deliverable_against_intentions(
        self, phase_id: str, builder_result: BuilderResult, context_info: Dict[str, Any]
    ) -> BuilderResult:
        """Validate builder deliverables against intention anchor constraints.

        Performs post-hoc validation that builder output respects intention
        constraints (must_not, hard_blocks, success_criteria).

        Args:
            phase_id: Phase identifier for logging
            builder_result: Builder result with deliverable content
            context_info: Context info containing intention context

        Returns:
            BuilderResult (possibly modified with warnings if validation fails)
        """
        # Skip if builder already failed
        if not builder_result.success:
            return builder_result

        # Skip if no patch content to validate
        if not builder_result.patch_content or not builder_result.patch_content.strip():
            return builder_result

        try:
            # Try to load intention anchor from executor if available
            intention_anchor = getattr(self.executor, "_intention_anchor", None)

            if not intention_anchor:
                # Try to load from storage
                try:
                    from autopack.intention_anchor.storage import IntentionAnchorStorage

                    intention_anchor = IntentionAnchorStorage.load_anchor(self.run_id)
                except Exception:
                    intention_anchor = None

            # If no anchor available, skip validation with no warning
            if not intention_anchor:
                return builder_result

            # Validate deliverable against intention anchor
            from autopack.builder import DeliverableValidator

            validator = DeliverableValidator(anchor=intention_anchor)
            result = validator.validate(
                builder_result.patch_content,
                metadata={"phase": phase_id},
            )

            # Log validation results
            if result.violations:
                logger.error(
                    f"[{phase_id}] Deliverable validation FAILED: {len(result.violations)} violations"
                )
                for violation in result.violations:
                    logger.error(f"  - {violation}")

                # Add violations to builder messages
                messages = builder_result.builder_messages or []
                messages.extend([f"Validation violation: {v}" for v in result.violations])
                builder_result = BuilderResult(
                    success=False,
                    patch_content=builder_result.patch_content,
                    builder_messages=messages,
                    tokens_used=builder_result.tokens_used,
                    model_used=getattr(builder_result, "model_used", None),
                    error="deliverable_validation_failed: constraint violations detected",
                )

            if result.warnings:
                logger.warning(
                    f"[{phase_id}] Deliverable validation WARNINGS: {len(result.warnings)} issues"
                )
                for warning in result.warnings:
                    logger.warning(f"  - {warning}")

                # Add warnings to builder messages
                messages = builder_result.builder_messages or []
                messages.extend([f"Validation warning: {w}" for w in result.warnings])
                builder_result.builder_messages = messages

        except Exception as e:
            logger.warning(f"[{phase_id}] Intention validation error (continuing): {e}")
            # Don't fail the phase on validation errors - log and continue

        return builder_result

    def post_builder_result(
        self, phase_id: str, builder_result: BuilderResult, allowed_paths: Optional[List[str]]
    ) -> None:
        """Post builder result to API.

        Args:
            phase_id: Phase identifier
            builder_result: Builder result to post
            allowed_paths: Optional list of allowed file paths
        """
        self.executor._post_builder_result(phase_id, builder_result, allowed_paths)
