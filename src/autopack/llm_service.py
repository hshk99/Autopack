"""LLM Service with integrated ModelRouter and UsageRecorder

This service wraps the OpenAI clients and provides:
- Automatic model selection via ModelRouter
- Usage tracking via UsageRecorder
- Centralized error handling and logging
- Quality gate enforcement for high-risk categories
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def estimate_tokens(text: str, *, chars_per_token: float = 4.0) -> int:
    """
    Rough token estimation for soft cap warnings.

    Per GPT_RESPONSE20 C2 and GPT_RESPONSE21 Q2: Single factor 4.0 for all models in Phase 1.
    ±20-30% error is acceptable for advisory soft caps.
    Actual usage from provider is authoritative for cost tracking.

    Args:
        text: Text to estimate tokens for
        chars_per_token: Average characters per token (default 4.0 for all models)

    Returns:
        Estimated token count (minimum 1)
    """
    return max(1, int(len(text) / chars_per_token))


from .llm_client import AuditorResult, BuilderResult
from .model_router import ModelRouter
from .quality_gate import QualityGate, integrate_with_auditor
from .usage_recorder import LlmUsageEvent
from .error_recovery import (
    DoctorRequest,
    DoctorResponse,
    DoctorContextSummary,
    choose_doctor_model,
    should_escalate_doctor_model,
)
from .dual_auditor import DualAuditor
from .llm.client_resolution import resolve_client_and_model
from .llm.usage import (
    record_usage as record_usage_impl,
    record_usage_total_only as record_usage_total_only_impl,
    model_to_provider,
)
from .llm import doctor

# Import OpenAI clients with graceful fallback
try:
    from .openai_clients import OpenAIAuditorClient, OpenAIBuilderClient

    OPENAI_AVAILABLE = True
except (ImportError, Exception):
    # Catch both ImportError and OpenAIError (API key missing during init)
    OPENAI_AVAILABLE = False
    OpenAIAuditorClient = None  # type: ignore[assignment]
    OpenAIBuilderClient = None  # type: ignore[assignment]

# Import Anthropic clients with graceful fallback
try:
    from .anthropic_clients import AnthropicAuditorClient, AnthropicBuilderClient

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

"""
NOTE: GLM support is currently disabled.

The GLM client imports and routing were kept for historical reference but
the active configuration no longer selects glm-* models. We keep the
stubs here to avoid breaking older logs/configs, but they are never used
in current routing (Doctor and core flows stay on Claude Sonnet/Opus).
"""
GLM_AVAILABLE = False
GLMBuilderClient = None  # type: ignore[assignment]
GLMAuditorClient = None  # type: ignore[assignment]

# Import Gemini clients with graceful fallback
try:
    from .gemini_clients import GeminiBuilderClient, GeminiAuditorClient

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    GeminiBuilderClient = None  # type: ignore[assignment]
    GeminiAuditorClient = None  # type: ignore[assignment]


class LlmService:
    """
    Centralized LLM service with model routing and usage tracking.

    This service:
    1. Uses ModelRouter to select appropriate models based on task/quota
    2. Delegates to OpenAI or Anthropic clients based on model selection
    3. Records usage in database via LlmUsageEvent
    """

    def __init__(
        self,
        db: Session,
        config_path: str = "config/models.yaml",
        repo_root: Optional[Path] = None,
    ):
        """
        Initialize LLM service.

        Args:
            db: Database session for usage recording
            config_path: Path to models.yaml config
            repo_root: Repository root for quality gate (defaults to current dir)
        """
        self.db = db
        self.model_router = ModelRouter(db, config_path)

        # GLM support disabled: keep explicit None clients to avoid accidental use
        self.glm_builder = None
        self.glm_auditor = None

        # Initialize OpenAI clients if available (fallback for non-GLM OpenAI models)
        openai_key = os.getenv("OPENAI_API_KEY")
        if OPENAI_AVAILABLE and openai_key:
            try:
                self.openai_builder = OpenAIBuilderClient()
                self.openai_auditor = OpenAIAuditorClient()
            except Exception as e:
                print(f"Warning: Failed to initialize OpenAI clients: {e}")
                self.openai_builder = None
                self.openai_auditor = None
        else:
            if OPENAI_AVAILABLE and not openai_key:
                msg = "OpenAI package available but OPENAI_API_KEY not set. Skipping OpenAI initialization."
                print(f"Warning: {msg}")
            self.openai_builder = None
            self.openai_auditor = None

        # Initialize Anthropic clients if available and key is present
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if ANTHROPIC_AVAILABLE and anthropic_key:
            try:
                self.anthropic_builder = AnthropicBuilderClient()
                self.anthropic_auditor = AnthropicAuditorClient()
            except Exception as e:
                print(f"Warning: Failed to initialize Anthropic clients: {e}")
                self.anthropic_builder = None
                self.anthropic_auditor = None
                self.model_router.disable_provider("anthropic", reason=str(e))
        else:
            if ANTHROPIC_AVAILABLE and not anthropic_key:
                msg = "Anthropic package available but ANTHROPIC_API_KEY not set. Skipping Anthropic initialization."
                print(f"Warning: {msg}")
                self.model_router.disable_provider("anthropic", reason=msg)
            self.anthropic_builder = None
            self.anthropic_auditor = None

        # Initialize Gemini clients if available and key is present
        google_key = os.getenv("GOOGLE_API_KEY")
        if GEMINI_AVAILABLE and google_key:
            try:
                self.gemini_builder = GeminiBuilderClient()
                self.gemini_auditor = GeminiAuditorClient()
            except Exception as e:
                print(f"Warning: Failed to initialize Gemini clients: {e}")
                self.gemini_builder = None
                self.gemini_auditor = None
                # Mark Gemini provider as disabled for this process
                self.model_router.disable_provider("google_gemini", reason=str(e))
        else:
            if GEMINI_AVAILABLE and not google_key:
                msg = "Gemini package available but GOOGLE_API_KEY not set. Skipping Gemini initialization."
                print(f"Warning: {msg}")
                self.model_router.disable_provider("google_gemini", reason=msg)
            self.gemini_builder = None
            self.gemini_auditor = None

        # Initialize quality gate with project config
        self.repo_root = repo_root or Path.cwd()
        # Use default config for quality gate (config_loader was removed)
        self.quality_gate = QualityGate(repo_root=self.repo_root, config={})

    def _resolve_client_and_model(self, role: str, requested_model: str):
        """Resolve client and fallback model if needed.

        This method delegates to client_resolution.resolve_client_and_model.

        Routing priority (current stack):
        1. Gemini models (gemini-*) -> Gemini client (uses GOOGLE_API_KEY)
        2. Claude models (claude-*) -> Anthropic client
        3. OpenAI models (gpt-*, o1-*) -> OpenAI client
        4. Fallback chain: Gemini -> Anthropic -> OpenAI

        GLM models (glm-*) are treated as legacy; current configs never
        select them, and GLM clients are disabled.
        """
        if role == "builder":
            glm_client = self.glm_builder
            openai_client = self.openai_builder
            anthropic_client = self.anthropic_builder
            gemini_client = self.gemini_builder
        else:
            glm_client = self.glm_auditor
            openai_client = self.openai_auditor
            anthropic_client = self.anthropic_auditor
            gemini_client = self.gemini_auditor

        return resolve_client_and_model(
            role,
            requested_model,
            gemini_client=gemini_client,
            anthropic_client=anthropic_client,
            openai_client=openai_client,
            glm_client=glm_client,
        )

    def generate_deliverables_manifest(
        self,
        *,
        expected_paths: List[str],
        allowed_roots: List[str],
        run_id: Optional[str] = None,
        phase_id: Optional[str] = None,
        attempt_index: int = 0,
    ) -> Tuple[bool, List[str], Optional[str], Optional[str]]:
        """
        Deliverables manifest gate (executor-side).

        The executor uses this to produce a deterministic manifest of file paths that Builder is allowed
        to touch for the current phase/batch. This is used for:
        - injecting `deliverables_manifest` into Builder prompts (when supported)
        - validating patches do not introduce files outside the approved manifest

        NOTE:
        - Earlier iterations implemented this as an LLM "plan first" call; in this codebase we use a
          deterministic gate to avoid extra token spend and to keep convergence stable.
        """
        try:
            exp = [p for p in (expected_paths or []) if isinstance(p, str) and p.strip()]
            manifest = sorted(set(exp))

            roots = [r for r in (allowed_roots or []) if isinstance(r, str) and r.strip()]
            if roots:
                not_covered = [p for p in manifest if not any(p.startswith(r) for r in roots)]
                if not_covered:
                    err = (
                        f"Expected paths include entries outside allowed_roots. "
                        f"outside_count={len(not_covered)} sample={not_covered[:5]} roots={roots} "
                        f"(run_id={run_id}, phase_id={phase_id}, attempt={attempt_index})"
                    )
                    return False, [], err, None

            raw = json.dumps(manifest, indent=2, sort_keys=False)
            return True, manifest, None, raw
        except Exception as e:
            return False, [], f"deliverables manifest gate exception: {e}", None

    def execute_builder_phase(
        self,
        phase_spec: Dict,
        file_context: Optional[Dict] = None,
        max_tokens: Optional[int] = None,
        project_rules: Optional[List] = None,
        run_hints: Optional[List] = None,
        run_id: Optional[str] = None,
        phase_id: Optional[str] = None,
        run_context: Optional[Dict] = None,
        attempt_index: int = 0,
        use_full_file_mode: bool = True,  # NEW: Pass mode from pre-flight check
        config=None,  # NEW: Pass BuilderOutputConfig for consistency
        retrieved_context: Optional[str] = None,  # NEW: Vector memory context
    ) -> BuilderResult:
        """
        Execute builder phase with automatic model selection and usage tracking.

        Args:
            phase_spec: Phase specification with task_category, complexity, etc.
            file_context: Repository file context
            max_tokens: Token budget limit
            project_rules: Persistent learned rules
            run_hints: Within-run hints
            run_id: Run identifier for usage tracking
            phase_id: Phase identifier for usage tracking
            run_context: Run context with potential model_overrides
            attempt_index: 0-based attempt number for escalation (default 0)
            use_full_file_mode: Use full-file mode (True) or diff mode (False)
            config: BuilderOutputConfig instance
            retrieved_context: Retrieved context from vector memory (formatted string)

        Returns:
            BuilderResult with patch and metadata
        """
        # Select model using ModelRouter with escalation support
        task_category = phase_spec.get("task_category", "general")
        complexity = phase_spec.get("complexity", "medium")

        # Use escalation-aware model selection
        model, effective_complexity, escalation_info = (
            self.model_router.select_model_with_escalation(
                role="builder",
                task_category=task_category,
                complexity=complexity,
                phase_id=phase_id or "unknown",
                attempt_index=attempt_index,
                run_context=run_context,
            )
        )

        # Log model selection (always, for observability per GPT recommendation)
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            f"[MODEL-SELECT] Builder: model={model}, complexity={complexity}->{effective_complexity}, "
            f"attempt={attempt_index}, category={task_category}"
        )
        if escalation_info.get("complexity_escalation_reason"):
            logger.info(
                f"[ESCALATION] Builder complexity escalated: {escalation_info['complexity_escalation_reason']}"
            )
        if escalation_info.get("model_escalation_reason"):
            logger.info(
                f"[MODEL] Builder using {model} due to: {escalation_info['model_escalation_reason']}"
            )
        if escalation_info.get("budget_warning"):
            budget_warning = escalation_info["budget_warning"]
            logger.warning(f"[{budget_warning['level'].upper()}] {budget_warning['message']}")

        # Resolve client and model (handling fallbacks)
        builder_client, resolved_model = self._resolve_client_and_model("builder", model)

        # Execute builder with selected model
        result = builder_client.execute_phase(
            phase_spec=phase_spec,
            file_context=file_context,
            max_tokens=max_tokens,
            model=resolved_model,
            project_rules=project_rules,
            run_hints=run_hints,
            use_full_file_mode=use_full_file_mode,  # NEW: Pass mode from pre-flight
            config=config,  # NEW: Pass BuilderOutputConfig
            retrieved_context=retrieved_context,  # NEW: Vector memory context
        )

        # Classify outcome for escalation tracking / provider health
        if phase_id:
            if result.success:
                self.record_attempt_outcome(
                    phase_id=phase_id,
                    model=resolved_model,
                    outcome="success",
                    details=None,
                )
            else:
                error_text = (result.error or "").lower()
                if "churn_limit_exceeded" in error_text:
                    # Builder guardrail: churn limit exceeded (not an auditor rejection).
                    outcome = "builder_churn_limit_exceeded"
                elif "connection error" in error_text or "timeout" in error_text:
                    outcome = "infra_error"
                else:
                    # Default builder failure classification
                    outcome = "auditor_reject"
                self.record_attempt_outcome(
                    phase_id=phase_id,
                    model=resolved_model,
                    outcome=outcome,
                    details=result.error,
                )

        # Record usage in database
        if result.success and result.tokens_used > 0:
            # BUILD-144 P0: No heuristic token splits - require exact counts or record total-only
            if result.prompt_tokens is not None and result.completion_tokens is not None:
                # Exact counts available - use them
                self._record_usage(
                    provider=self._model_to_provider(resolved_model),
                    model=resolved_model,
                    role="builder",
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    run_id=run_id,
                    phase_id=phase_id,
                )
            else:
                # No exact splits available - record total-only with warning
                logger.warning(
                    f"[TOKEN-ACCOUNTING] Builder result missing exact token counts (model={resolved_model}). "
                    f"Recording total_tokens={result.tokens_used} without split. "
                    f"Provider SDK should be updated to return exact counts."
                )
                # Record with None for splits to indicate "total-only" accounting
                self._record_usage_total_only(
                    provider=self._model_to_provider(resolved_model),
                    model=resolved_model,
                    role="builder",
                    total_tokens=result.tokens_used,
                    run_id=run_id,
                    phase_id=phase_id,
                )

        return result

    def execute_auditor_review(
        self,
        patch_content: str,
        phase_spec: Dict,
        max_tokens: Optional[int] = None,
        project_rules: Optional[List] = None,
        run_hints: Optional[List] = None,
        run_id: Optional[str] = None,
        phase_id: Optional[str] = None,
        run_context: Optional[Dict] = None,
        ci_result: Optional[Dict] = None,
        coverage_delta: Optional[float] = None,
        attempt_index: int = 0,
    ) -> AuditorResult:
        """
        Execute auditor review with automatic model selection, usage tracking,
        and quality gate enforcement.

        Args:
            patch_content: Git diff/patch to review
            phase_spec: Phase specification for context
            max_tokens: Token budget limit
            project_rules: Persistent learned rules
            run_hints: Within-run hints
            run_id: Run identifier for usage tracking
            phase_id: Phase identifier for usage tracking
            run_context: Run context with potential model_overrides
            ci_result: CI test result (passed, failed, skipped) for quality gate
            coverage_delta: Coverage change (+5%, -2%, etc.) for quality gate
            attempt_index: 0-based attempt number for escalation (default 0)

        Returns:
            AuditorResult with review, issues, and quality gate assessment
        """
        # Select model using ModelRouter with escalation support
        task_category = phase_spec.get("task_category", "general")
        complexity = phase_spec.get("complexity", "medium")

        # Use escalation-aware model selection
        model, effective_complexity, escalation_info = (
            self.model_router.select_model_with_escalation(
                role="auditor",
                task_category=task_category,
                complexity=complexity,
                phase_id=phase_id or "unknown",
                attempt_index=attempt_index,
                run_context=run_context,
            )
        )

        # Log model selection (always, for observability per GPT recommendation)
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            f"[MODEL-SELECT] Auditor: model={model}, complexity={complexity}->{effective_complexity}, "
            f"attempt={attempt_index}, category={task_category}"
        )
        if escalation_info.get("complexity_escalation_reason"):
            logger.info(
                f"[ESCALATION] Auditor complexity escalated: {escalation_info['complexity_escalation_reason']}"
            )
        if escalation_info.get("model_escalation_reason"):
            logger.info(
                f"[MODEL] Auditor using {model} due to: {escalation_info['model_escalation_reason']}"
            )
        if escalation_info.get("budget_warning"):
            budget_warning = escalation_info["budget_warning"]
            logger.warning(f"[{budget_warning['level'].upper()}] {budget_warning['message']}")

        # Check for dual audit configuration
        if self._should_use_dual_audit(task_category):
            secondary_model = self._get_secondary_auditor_model(task_category)
            logger.info(
                f"[DUAL-AUDIT] Dual audit enabled for category={task_category}, "
                f"primary={model}, secondary={secondary_model}"
            )

            # Run dual audit
            primary_result, secondary_result = self._run_dual_audit(
                patch_content=patch_content,
                phase_spec=phase_spec,
                primary_model=model,
                secondary_model=secondary_model,
                max_tokens=max_tokens,
                project_rules=project_rules,
                run_hints=run_hints,
                run_id=run_id,
                phase_id=phase_id,
            )

            # Detect disagreement
            disagreement = self._detect_dual_audit_disagreement(primary_result, secondary_result)

            # Escalate to judge if disagreement detected
            judge_result = None
            if disagreement["has_disagreement"]:
                judge_result = self._run_judge_audit(
                    patch_content=patch_content,
                    phase_spec=phase_spec,
                    primary_result=primary_result,
                    secondary_result=secondary_result,
                    disagreement=disagreement,
                    max_tokens=max_tokens,
                    project_rules=project_rules,
                    run_hints=run_hints,
                    run_id=run_id,
                    phase_id=phase_id,
                )

            # Merge results
            result = self._merge_dual_audit_results(primary_result, secondary_result, judge_result)
            resolved_model = result.model_used

            # Log telemetry
            self._log_dual_audit_telemetry(
                phase_id=phase_id or "unknown",
                task_category=task_category,
                primary_model=model,
                secondary_model=secondary_model,
                primary_result=primary_result,
                secondary_result=secondary_result,
                disagreement=disagreement,
                judge_result=judge_result,
                final_result=result,
            )
        else:
            # Standard single-auditor path
            # Resolve client and model (handling fallbacks)
            auditor_client, resolved_model = self._resolve_client_and_model("auditor", model)

            # Execute auditor with selected model
            result = auditor_client.review_patch(
                patch_content=patch_content,
                phase_spec=phase_spec,
                max_tokens=max_tokens,
                model=resolved_model,
                project_rules=project_rules,
                run_hints=run_hints,
            )

        # Classify outcome for escalation tracking
        if phase_id:
            if result.approved:
                self.record_attempt_outcome(
                    phase_id=phase_id,
                    model=resolved_model,
                    outcome="success",
                    details=None,
                )
            else:
                self.record_attempt_outcome(
                    phase_id=phase_id,
                    model=resolved_model,
                    outcome="auditor_reject",
                    details="Auditor did not approve patch",
                )

        # Record usage in database (skip if dual audit - usage already recorded)
        if not self._should_use_dual_audit(task_category) and result.tokens_used > 0:
            # BUILD-144 P0: No heuristic token splits - require exact counts or record total-only
            if result.prompt_tokens is not None and result.completion_tokens is not None:
                # Exact counts available - use them
                self._record_usage(
                    provider=self._model_to_provider(resolved_model),
                    model=resolved_model,
                    role="auditor",
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    run_id=run_id,
                    phase_id=phase_id,
                )
            else:
                # No exact splits available - record total-only with warning
                logger.warning(
                    f"[TOKEN-ACCOUNTING] Auditor result missing exact token counts (model={resolved_model}). "
                    f"Recording total_tokens={result.tokens_used} without split. "
                    f"Provider SDK should be updated to return exact counts."
                )
                # Record with None for splits to indicate "total-only" accounting
                self._record_usage_total_only(
                    provider=self._model_to_provider(resolved_model),
                    model=resolved_model,
                    role="auditor",
                    total_tokens=result.tokens_used,
                    run_id=run_id,
                    phase_id=phase_id,
                )

        # Run quality gate assessment (Phase 2: Thin quality gate)
        if phase_id:
            quality_report = self.quality_gate.assess_phase(
                phase_id=phase_id,
                phase_spec=phase_spec,
                auditor_result=result.metadata if hasattr(result, "metadata") else {},
                ci_result=ci_result,
                coverage_delta=coverage_delta,
            )

            # Log quality assessment
            print(self.quality_gate.format_report(quality_report))

            # Integrate quality gate results with auditor result
            if hasattr(result, "metadata"):
                result.metadata = integrate_with_auditor(result.metadata, quality_report)

        return result

    def _record_usage(
        self,
        provider: str,
        model: str,
        role: str,
        prompt_tokens: int,
        completion_tokens: int,
        run_id: Optional[str] = None,
        phase_id: Optional[str] = None,
    ):
        """
        Record LLM usage in database with exact token splits.

        BUILD-144 P0.4: Always records total_tokens = prompt_tokens + completion_tokens.

        Args:
            provider: Provider name (openai, anthropic, etc.)
            model: Model name
            role: builder, auditor, or agent:name
            prompt_tokens: Input tokens (exact from provider)
            completion_tokens: Output tokens (exact from provider)
            run_id: Optional run identifier
            phase_id: Optional phase identifier
        """
        try:
            usage_event = LlmUsageEvent(
                provider=provider,
                model=model,
                role=role,
                total_tokens=prompt_tokens + completion_tokens,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                run_id=run_id,
                phase_id=phase_id,
                created_at=datetime.now(timezone.utc),
            )
            self.db.add(usage_event)
            self.db.commit()
        except Exception as e:
            # Don't fail the LLM call if usage recording fails
            print(f"Warning: Failed to record usage: {e}")
            self.db.rollback()

    def _record_usage_total_only(
        self,
        provider: str,
        model: str,
        role: str,
        total_tokens: int,
        run_id: Optional[str] = None,
        phase_id: Optional[str] = None,
    ):
        """
        Record LLM usage when provider doesn't return exact token splits.

        BUILD-144 P0.4: Records total_tokens explicitly with prompt_tokens=None and
        completion_tokens=None to indicate "total-only" accounting. Dashboard totals
        now use total_tokens field to avoid under-reporting.

        Args:
            provider: Provider name (openai, anthropic, etc.)
            model: Model name
            role: builder, auditor, or agent:name
            total_tokens: Total tokens used (sum of prompt + completion)
            run_id: Optional run identifier
            phase_id: Optional phase identifier
        """
        try:
            # Record with total_tokens populated and prompt/completion as None
            usage_event = LlmUsageEvent(
                provider=provider,
                model=model,
                role=role,
                total_tokens=total_tokens,
                prompt_tokens=None,  # Explicit None: no guessing
                completion_tokens=None,  # Explicit None: no guessing
                run_id=run_id,
                phase_id=phase_id,
                created_at=datetime.now(timezone.utc),
            )
            self.db.add(usage_event)
            self.db.commit()
            logger.info(
                f"[TOKEN-ACCOUNTING] Recorded total-only usage: provider={provider}, model={model}, "
                f"role={role}, total={total_tokens} (no split available)"
            )
        except Exception as e:
            # Don't fail the LLM call if usage recording fails
            print(f"Warning: Failed to record total-only usage: {e}")
            self.db.rollback()

    def _model_to_provider(self, model: str) -> str:
        """
        Map model name to provider.

        Args:
            model: Model name

        Returns:
            Provider name
        """
        if model.startswith("gemini-"):
            return "google"
        elif model.startswith("gpt-") or model.startswith("o1-"):
            return "openai"
        elif model.startswith("claude-") or model.startswith("opus-"):
            return "anthropic"
        else:
            return "openai"  # Safe default

    def record_attempt_outcome(
        self, phase_id: str, model: str, outcome: str, details: Optional[str] = None
    ):
        """
        Record the outcome of an attempt for escalation tracking.

        This should be called after each Builder/Auditor attempt to
        track success/failure for model escalation decisions.

        Args:
            phase_id: Phase identifier
            model: Model used for this attempt
            outcome: One of: success, auditor_reject, ci_fail, patch_apply_error, infra_error
            details: Optional details about the outcome
        """
        self.model_router.record_attempt_outcome(
            phase_id=phase_id,
            model=model,
            outcome=outcome,
            details=details,
        )

        # If we see infra_error outcomes for a provider, allow callers to
        # disable that provider for the remainder of the run.
        if outcome == "infra_error" and model and model != "unknown":
            provider = self._model_to_provider(model)
            # Conservatively disable only non-OpenAI providers, since OpenAI
            # acts as the global fallback in most configs.
            if provider in {"zhipu_glm", "google_gemini", "anthropic"}:
                reason = f"infra_error for model {model} in phase {phase_id} ({details})"
                self.model_router.disable_provider(provider, reason=reason)

    def get_max_attempts(self) -> int:
        """Get maximum attempts per phase from config."""
        return self.model_router.get_max_attempts()

    # =========================================================================
    # DOCTOR INVOCATION (per GPT_RESPONSE8 Section 3.2)
    # =========================================================================

    def execute_doctor(
        self,
        request: DoctorRequest,
        ctx_summary: Optional[DoctorContextSummary] = None,
        run_id: Optional[str] = None,
        phase_id: Optional[str] = None,
        allow_escalation: bool = True,
    ) -> DoctorResponse:
        """
        Invoke the Autopack Doctor to diagnose a phase failure.

        This method delegates to the doctor module for the actual implementation.
        The doctor module was extracted from llm_service.py as part of Item 1.1
        god file refactoring (PR-SVC-3).

        Args:
            request: Doctor diagnostic request with failure context
            ctx_summary: Optional summary of phase-level error context
            run_id: Run identifier for usage tracking
            phase_id: Phase identifier for logging
            allow_escalation: Whether to escalate to strong model if needed

        Returns:
            DoctorResponse with action, confidence, rationale, and optional hints
        """
        # Resolve client for the doctor module
        # Doctor uses builder role for client resolution (historical behavior)
        model, _ = choose_doctor_model(request, ctx_summary)
        client, _ = self._resolve_client_and_model("builder", model)

        # Delegate to doctor module with usage recording callbacks
        return doctor.execute_doctor(
            client=client,
            request=request,
            ctx_summary=ctx_summary,
            run_id=run_id,
            phase_id=phase_id,
            allow_escalation=allow_escalation,
            model_to_provider_fn=self._model_to_provider,
            record_usage_fn=self._record_usage,
            record_usage_total_only_fn=self._record_usage_total_only,
        )

    # =========================================================================
    # DUAL AUDIT WIRING (per GPT recommendation: dual_audit: true enforcement)
    # =========================================================================

    def _should_use_dual_audit(self, task_category: str) -> bool:
        """Check if dual_audit: true is configured for this task category.

        Args:
            task_category: The task category from phase_spec

        Returns:
            True if dual_audit is enabled for this category
        """
        routing_policies = self.model_router.config.get("llm_routing_policies", {})
        policy = routing_policies.get(task_category, {})
        # Explicitly check for True to avoid MagicMock truthiness issues in tests
        return policy.get("dual_audit", False) is True

    def _get_secondary_auditor_model(self, task_category: str) -> str:
        """Get the secondary auditor model from config.

        Args:
            task_category: The task category from phase_spec

        Returns:
            Secondary auditor model name (defaults to claude-sonnet-4-5)
        """
        routing_policies = self.model_router.config.get("llm_routing_policies", {})
        policy = routing_policies.get(task_category, {})
        return policy.get("secondary_auditor", "claude-sonnet-4-5")

    def _run_dual_audit(
        self,
        patch_content: str,
        phase_spec: Dict,
        primary_model: str,
        secondary_model: str,
        max_tokens: Optional[int],
        project_rules: Optional[List],
        run_hints: Optional[List],
        run_id: Optional[str],
        phase_id: Optional[str],
    ) -> Tuple[AuditorResult, AuditorResult]:
        """Run both primary and secondary auditors.

        Args:
            patch_content: Git diff/patch to review
            phase_spec: Phase specification
            primary_model: Primary auditor model
            secondary_model: Secondary auditor model
            max_tokens: Token budget
            project_rules: Learned rules
            run_hints: Run hints
            run_id: Run identifier
            phase_id: Phase identifier

        Returns:
            Tuple of (primary_result, secondary_result)
        """
        logger.info(
            f"[DUAL-AUDIT] Running dual audit: primary={primary_model}, secondary={secondary_model}"
        )

        # Run primary auditor
        primary_client, resolved_primary = self._resolve_client_and_model("auditor", primary_model)
        primary_result = primary_client.review_patch(
            patch_content=patch_content,
            phase_spec=phase_spec,
            max_tokens=max_tokens,
            model=resolved_primary,
            project_rules=project_rules,
            run_hints=run_hints,
        )

        # Run secondary auditor
        secondary_client, resolved_secondary = self._resolve_client_and_model(
            "auditor", secondary_model
        )
        secondary_result = secondary_client.review_patch(
            patch_content=patch_content,
            phase_spec=phase_spec,
            max_tokens=max_tokens // 2 if max_tokens else None,
            model=resolved_secondary,
            project_rules=project_rules,
            run_hints=run_hints,
        )

        # Record usage for both
        for result, model, role_suffix in [
            (primary_result, resolved_primary, "primary"),
            (secondary_result, resolved_secondary, "secondary"),
        ]:
            if result.tokens_used > 0:
                if result.prompt_tokens is not None and result.completion_tokens is not None:
                    self._record_usage(
                        provider=self._model_to_provider(model),
                        model=model,
                        role=f"auditor:{role_suffix}",
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens,
                        run_id=run_id,
                        phase_id=phase_id,
                    )
                else:
                    self._record_usage_total_only(
                        provider=self._model_to_provider(model),
                        model=model,
                        role=f"auditor:{role_suffix}",
                        total_tokens=result.tokens_used,
                        run_id=run_id,
                        phase_id=phase_id,
                    )

        return primary_result, secondary_result

    def _detect_dual_audit_disagreement(
        self, primary: AuditorResult, secondary: AuditorResult
    ) -> Dict:
        """Detect disagreement between two auditor results.

        Disagreement types:
        - approval_mismatch: One approves, one rejects
        - severity_mismatch: Both reject but different severity levels
        - category_miss: One auditor finds issues the other completely missed

        Args:
            primary: Primary auditor result
            secondary: Secondary auditor result

        Returns:
            Dict with disagreement info: {has_disagreement, type, details}
        """
        disagreement = {"has_disagreement": False, "type": None, "details": {}}

        # Check approval mismatch
        if primary.approved != secondary.approved:
            disagreement["has_disagreement"] = True
            disagreement["type"] = "approval_mismatch"
            disagreement["details"] = {
                "primary_approved": primary.approved,
                "secondary_approved": secondary.approved,
            }
            return disagreement

        # Both rejected - check for severity mismatch
        if not primary.approved and not secondary.approved:
            primary_major = sum(1 for i in primary.issues_found if i.get("severity") == "major")
            secondary_major = sum(1 for i in secondary.issues_found if i.get("severity") == "major")

            # Significant severity difference (one found >2x major issues)
            if primary_major > 0 or secondary_major > 0:
                ratio = max(primary_major, secondary_major) / max(
                    min(primary_major, secondary_major), 1
                )
                if ratio > 2:
                    disagreement["has_disagreement"] = True
                    disagreement["type"] = "severity_mismatch"
                    disagreement["details"] = {
                        "primary_major_issues": primary_major,
                        "secondary_major_issues": secondary_major,
                    }
                    return disagreement

        # Check for category misses (one found issues the other completely missed)
        primary_categories = {i.get("category") for i in primary.issues_found}
        secondary_categories = {i.get("category") for i in secondary.issues_found}

        missed_by_primary = secondary_categories - primary_categories
        missed_by_secondary = primary_categories - secondary_categories

        # If one auditor found a category the other completely missed
        if missed_by_primary or missed_by_secondary:
            # Only flag as disagreement if major issues were missed
            primary_major_cats = {
                i.get("category") for i in primary.issues_found if i.get("severity") == "major"
            }
            secondary_major_cats = {
                i.get("category") for i in secondary.issues_found if i.get("severity") == "major"
            }

            major_missed = (secondary_major_cats - primary_major_cats) | (
                primary_major_cats - secondary_major_cats
            )
            if major_missed:
                disagreement["has_disagreement"] = True
                disagreement["type"] = "category_miss"
                disagreement["details"] = {
                    "missed_by_primary": list(missed_by_primary),
                    "missed_by_secondary": list(missed_by_secondary),
                    "major_categories_missed": list(major_missed),
                }

        return disagreement

    def _run_judge_audit(
        self,
        patch_content: str,
        phase_spec: Dict,
        primary_result: AuditorResult,
        secondary_result: AuditorResult,
        disagreement: Dict,
        max_tokens: Optional[int],
        project_rules: Optional[List],
        run_hints: Optional[List],
        run_id: Optional[str],
        phase_id: Optional[str],
    ) -> AuditorResult:
        """Run top-tier model as judge when auditors disagree.

        Args:
            patch_content: Git diff/patch to review
            phase_spec: Phase specification
            primary_result: Primary auditor result
            secondary_result: Secondary auditor result
            disagreement: Disagreement info from _detect_dual_audit_disagreement
            max_tokens: Token budget
            project_rules: Learned rules
            run_hints: Run hints
            run_id: Run identifier
            phase_id: Phase identifier

        Returns:
            Judge's AuditorResult
        """
        # Get judge model from config (default to claude-opus-4-5 as top-tier)
        judge_model = self.model_router.config.get("dual_audit_judge", {}).get(
            "model", "claude-opus-4-5"
        )

        logger.info(
            f"[DUAL-AUDIT] Disagreement detected ({disagreement['type']}), "
            f"escalating to judge: {judge_model}"
        )

        # Build enhanced phase_spec with disagreement context
        judge_phase_spec = phase_spec.copy()
        judge_phase_spec["dual_audit_context"] = {
            "disagreement_type": disagreement["type"],
            "disagreement_details": disagreement["details"],
            "primary_approved": primary_result.approved,
            "primary_issues_count": len(primary_result.issues_found),
            "secondary_approved": secondary_result.approved,
            "secondary_issues_count": len(secondary_result.issues_found),
        }

        # Resolve judge client
        judge_client, resolved_judge = self._resolve_client_and_model("auditor", judge_model)

        judge_result = judge_client.review_patch(
            patch_content=patch_content,
            phase_spec=judge_phase_spec,
            max_tokens=max_tokens,
            model=resolved_judge,
            project_rules=project_rules,
            run_hints=run_hints,
        )

        # Record judge usage
        if judge_result.tokens_used > 0:
            if (
                judge_result.prompt_tokens is not None
                and judge_result.completion_tokens is not None
            ):
                self._record_usage(
                    provider=self._model_to_provider(resolved_judge),
                    model=resolved_judge,
                    role="auditor:judge",
                    prompt_tokens=judge_result.prompt_tokens,
                    completion_tokens=judge_result.completion_tokens,
                    run_id=run_id,
                    phase_id=phase_id,
                )
            else:
                self._record_usage_total_only(
                    provider=self._model_to_provider(resolved_judge),
                    model=resolved_judge,
                    role="auditor:judge",
                    total_tokens=judge_result.tokens_used,
                    run_id=run_id,
                    phase_id=phase_id,
                )

        return judge_result

    def _merge_dual_audit_results(
        self,
        primary: AuditorResult,
        secondary: AuditorResult,
        judge: Optional[AuditorResult] = None,
    ) -> AuditorResult:
        """Merge dual audit results using issue-based conflict resolution.

        Per GPT recommendation:
        1. Union of issue sets
        2. Escalate severity: any "major" → effective_severity="major"
        3. If judge was invoked, use judge's approval decision
        4. Gate decision based on merged profile (any major → fail)

        Args:
            primary: Primary auditor result
            secondary: Secondary auditor result
            judge: Optional judge result (if disagreement was escalated)

        Returns:
            Merged AuditorResult
        """
        # Build merged issue set using DualAuditor's merge logic
        dual_auditor = DualAuditor(None, None)  # Stateless merge
        merged_issues = dual_auditor._build_merged_issue_set(
            primary.issues_found, secondary.issues_found
        )

        # Determine approval
        if judge is not None:
            # Judge's decision is authoritative
            approved = judge.approved
            logger.info(f"[DUAL-AUDIT] Using judge decision: approved={approved}")
        else:
            # No judge - use merged issue profile
            has_major_issues = any(issue.effective_severity == "major" for issue in merged_issues)
            approved = not has_major_issues

        # Convert MergedIssue to dict
        merged_issues_dict = [
            {
                "severity": issue.effective_severity,
                "category": issue.category,
                "description": issue.description,
                "location": issue.location,
                "sources": issue.sources,
                "suggestion": "; ".join(issue.suggestions) if issue.suggestions else None,
            }
            for issue in merged_issues
        ]

        # Combine auditor messages
        combined_messages = []
        combined_messages.extend(primary.auditor_messages or [])
        combined_messages.append("--- Secondary Auditor ---")
        combined_messages.extend(secondary.auditor_messages or [])
        if judge:
            combined_messages.append("--- Judge Auditor ---")
            combined_messages.extend(judge.auditor_messages or [])

        # Calculate total tokens
        total_tokens = primary.tokens_used + secondary.tokens_used
        if judge:
            total_tokens += judge.tokens_used

        # Build model string
        model_used = f"{primary.model_used}+{secondary.model_used}"
        if judge:
            model_used += f"+{judge.model_used}"

        return AuditorResult(
            approved=approved,
            issues_found=merged_issues_dict,
            auditor_messages=combined_messages,
            tokens_used=total_tokens,
            model_used=model_used,
        )

    def _log_dual_audit_telemetry(
        self,
        phase_id: str,
        task_category: str,
        primary_model: str,
        secondary_model: str,
        primary_result: AuditorResult,
        secondary_result: AuditorResult,
        disagreement: Dict,
        judge_result: Optional[AuditorResult],
        final_result: AuditorResult,
    ):
        """Log dual audit telemetry to JSONL file for analysis.

        Args:
            phase_id: Phase identifier
            task_category: Task category
            primary_model: Primary auditor model
            secondary_model: Secondary auditor model
            primary_result: Primary auditor result
            secondary_result: Secondary auditor result
            disagreement: Disagreement info
            judge_result: Optional judge result
            final_result: Final merged result
        """
        telemetry_dir = Path("logs/telemetry")
        telemetry_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        telemetry_file = telemetry_dir / f"dual_audit_telemetry_{today}.jsonl"

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase_id": phase_id,
            "task_category": task_category,
            "primary_model": primary_model,
            "secondary_model": secondary_model,
            "primary_approved": primary_result.approved,
            "primary_issues_count": len(primary_result.issues_found),
            "secondary_approved": secondary_result.approved,
            "secondary_issues_count": len(secondary_result.issues_found),
            "has_disagreement": disagreement["has_disagreement"],
            "disagreement_type": disagreement.get("type"),
            "judge_invoked": judge_result is not None,
            "judge_approved": judge_result.approved if judge_result else None,
            "final_approved": final_result.approved,
            "final_issues_count": len(final_result.issues_found),
            "total_tokens": final_result.tokens_used,
        }

        try:
            with open(telemetry_file, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.warning(f"[DUAL-AUDIT] Failed to write telemetry: {e}")

    # =========================================================================
    # SCOPE REDUCTION PROPOSAL (GAP-8.2.1)
    # =========================================================================

    def generate_scope_reduction_proposal(
        self,
        prompt: str,
        run_id: Optional[str] = None,
        phase_id: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Call LLM to generate scope reduction proposal.

        Per GAP-8.2.1: Wire scope reduction proposal generation to LlmService
        for intention-grounded scope reductions when phases are stuck.

        Args:
            prompt: Scope reduction prompt (from scope_reduction.generate_scope_reduction_prompt)
            run_id: Run identifier for usage tracking
            phase_id: Phase identifier for logging

        Returns:
            Parsed JSON dict matching ScopeReductionProposal schema, or None on failure
        """
        # Use a fast/cheap model for scope reduction (not mission-critical)
        model = "claude-sonnet-4-5"

        logger.info(f"[SCOPE-REDUCTION] Generating proposal: phase={phase_id}, run={run_id}")

        # Resolve client
        client, resolved_model = self._resolve_client_and_model("builder", model)

        # Build messages
        system_prompt = """You are helping reduce scope for a stuck phase.

Your task is to propose which deliverables to keep and which to drop,
based on the Intention Anchor's success criteria and constraints.

CRITICAL: Respond with ONLY a JSON object matching ScopeReductionProposal schema.
No markdown, no explanation text. Start with { and end with }.

Required JSON structure:
{
  "run_id": "<run identifier>",
  "phase_id": "<phase identifier>",
  "anchor_id": "<anchor identifier>",
  "diff": {
    "original_deliverables": ["<list of original deliverables>"],
    "kept_deliverables": ["<list of deliverables to keep>"],
    "dropped_deliverables": ["<list of deliverables to drop>"],
    "rationale": {
      "success_criteria_preserved": ["<which success criteria remain satisfied>"],
      "success_criteria_deferred": ["<which success criteria are deferred>"],
      "constraints_still_met": ["<which constraints are still satisfied>"],
      "reason": "<why scope reduction is necessary>"
    }
  },
  "estimated_budget_savings": <float 0.0-1.0>
}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        try:
            # Use the client's underlying API call
            if hasattr(client, "client") and hasattr(client.client, "chat"):
                # OpenAI client
                completion = client.client.chat.completions.create(
                    model=resolved_model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=2000,
                    response_format={"type": "json_object"},
                )
                content = completion.choices[0].message.content
                if completion.usage:
                    prompt_tokens = completion.usage.prompt_tokens
                    completion_tokens = completion.usage.completion_tokens
                    tokens_used = completion.usage.total_tokens
                else:
                    prompt_tokens = None
                    completion_tokens = None
                    tokens_used = 0
            elif hasattr(client, "client") and hasattr(client.client, "messages"):
                # Anthropic client
                completion = client.client.messages.create(
                    model=resolved_model,
                    max_tokens=2000,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                )
                content = completion.content[0].text
                if completion.usage:
                    prompt_tokens = completion.usage.input_tokens
                    completion_tokens = completion.usage.output_tokens
                    tokens_used = prompt_tokens + completion_tokens
                else:
                    prompt_tokens = None
                    completion_tokens = None
                    tokens_used = 0
            else:
                raise RuntimeError(f"Unknown client type for model {resolved_model}")

            # Record usage
            if tokens_used > 0:
                if prompt_tokens is not None and completion_tokens is not None:
                    self._record_usage(
                        provider=self._model_to_provider(resolved_model),
                        model=resolved_model,
                        role="scope_reduction",
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        run_id=run_id,
                        phase_id=phase_id,
                    )
                else:
                    self._record_usage_total_only(
                        provider=self._model_to_provider(resolved_model),
                        model=resolved_model,
                        role="scope_reduction",
                        total_tokens=tokens_used,
                        run_id=run_id,
                        phase_id=phase_id,
                    )

            # Parse JSON response
            proposal_data = json.loads(content)
            logger.info(
                f"[SCOPE-REDUCTION] Proposal generated successfully: "
                f"kept={len(proposal_data.get('diff', {}).get('kept_deliverables', []))}, "
                f"dropped={len(proposal_data.get('diff', {}).get('dropped_deliverables', []))}"
            )
            return proposal_data

        except json.JSONDecodeError as e:
            logger.error(f"[SCOPE-REDUCTION] Failed to parse JSON response: {e}")
            return None
        except Exception as e:
            logger.error(f"[SCOPE-REDUCTION] LLM call failed: {e}")
            return None
