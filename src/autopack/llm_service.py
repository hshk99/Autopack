"""LLM Service with integrated ModelRouter and UsageRecorder

This service wraps the OpenAI clients and provides:
- Automatic model selection via ModelRouter
- Usage tracking via UsageRecorder
- Centralized error handling and logging
- Quality gate enforcement for high-risk categories
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from .config_loader import get_config
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
    DOCTOR_MIN_BUILDER_ATTEMPTS,
)

# Import OpenAI clients with graceful fallback
try:
    from .openai_clients import OpenAIAuditorClient, OpenAIBuilderClient
    OPENAI_AVAILABLE = True
except (ImportError, Exception) as e:
    # Catch both ImportError and OpenAIError (API key missing during init)
    OPENAI_AVAILABLE = False
    OpenAIAuditorClient = None
    OpenAIBuilderClient = None

# Import Anthropic clients with graceful fallback
try:
    from .anthropic_clients import AnthropicAuditorClient, AnthropicBuilderClient
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

# Import GLM clients with graceful fallback
try:
    from .glm_clients import GLMBuilderClient, GLMAuditorClient
    GLM_AVAILABLE = True
except ImportError:
    GLM_AVAILABLE = False
    GLMBuilderClient = None
    GLMAuditorClient = None

# Import Gemini clients with graceful fallback
try:
    from .gemini_clients import GeminiBuilderClient, GeminiAuditorClient
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    GeminiBuilderClient = None
    GeminiAuditorClient = None


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

        # Initialize GLM clients if available and key is present (check first - primary provider)
        glm_key = os.getenv("GLM_API_KEY")
        if GLM_AVAILABLE and glm_key:
            try:
                self.glm_builder = GLMBuilderClient()
                self.glm_auditor = GLMAuditorClient()
            except Exception as e:
                print(f"Warning: Failed to initialize GLM clients: {e}")
                self.glm_builder = None
                self.glm_auditor = None
        else:
            if GLM_AVAILABLE and not glm_key:
                print("Warning: GLM package available but GLM_API_KEY not set. Skipping GLM initialization.")
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
                print("Warning: OpenAI package available but OPENAI_API_KEY not set. Skipping OpenAI initialization.")
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
        else:
            if ANTHROPIC_AVAILABLE and not anthropic_key:
                print("Warning: Anthropic package available but ANTHROPIC_API_KEY not set. Skipping Anthropic initialization.")
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
        else:
            if GEMINI_AVAILABLE and not google_key:
                print("Warning: Gemini package available but GOOGLE_API_KEY not set. Skipping Gemini initialization.")
            self.gemini_builder = None
            self.gemini_auditor = None

        # Initialize quality gate with project config
        self.repo_root = repo_root or Path.cwd()
        config = get_config(self.repo_root / ".autopack" / "config.yaml")
        self.quality_gate = QualityGate(
            repo_root=self.repo_root, config=config._config
        )

    def _resolve_client_and_model(self, role: str, requested_model: str):
        """Resolve client and fallback model if needed.

        Routing priority:
        1. Gemini models (gemini-*) -> Gemini client (uses GOOGLE_API_KEY)
        2. GLM models (glm-*) -> GLM client (uses GLM_API_KEY)
        3. Claude models (claude-*) -> Anthropic client
        4. OpenAI models (gpt-*, o1-*) -> OpenAI client
        5. Fallback chain: Gemini -> GLM -> Anthropic -> OpenAI
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

        # Route Gemini models to Gemini client
        if requested_model.lower().startswith("gemini-"):
            if gemini_client is not None:
                return gemini_client, requested_model
            # Gemini not available, try fallbacks
            if anthropic_client is not None:
                print(f"Warning: Gemini model {requested_model} selected but GOOGLE_API_KEY not set. Falling back to Anthropic (claude-sonnet-4-5).")
                return anthropic_client, "claude-sonnet-4-5"
            if openai_client is not None:
                print(f"Warning: Gemini model {requested_model} selected but GOOGLE_API_KEY not set. Falling back to OpenAI (gpt-4o).")
                return openai_client, "gpt-4o"
            if glm_client is not None:
                print(f"Warning: Gemini model {requested_model} selected but GOOGLE_API_KEY not set. Falling back to GLM (glm-4.5-20250101).")
                return glm_client, "glm-4.5-20250101"
            raise RuntimeError(f"Gemini model {requested_model} selected but no LLM clients are available. Set GOOGLE_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY, or GLM_API_KEY.")

        # Route GLM models to GLM client
        if requested_model.lower().startswith("glm-"):
            if glm_client is not None:
                return glm_client, requested_model
            # GLM not available, try fallbacks
            if gemini_client is not None:
                print(f"Warning: GLM model {requested_model} selected but GLM_API_KEY not set. Falling back to Gemini (gemini-2.5-pro).")
                return gemini_client, "gemini-2.5-pro"
            if anthropic_client is not None:
                print(f"Warning: GLM model {requested_model} selected but GLM_API_KEY not set. Falling back to Anthropic (claude-sonnet-4-5).")
                return anthropic_client, "claude-sonnet-4-5"
            if openai_client is not None:
                print(f"Warning: GLM model {requested_model} selected but GLM_API_KEY not set. Falling back to OpenAI (gpt-4o).")
                return openai_client, "gpt-4o"
            raise RuntimeError(f"GLM model {requested_model} selected but no LLM clients are available. Set GLM_API_KEY, GOOGLE_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY.")

        # Route Claude models to Anthropic client
        if "claude" in requested_model.lower():
            if anthropic_client is not None:
                return anthropic_client, requested_model
            # Anthropic not available, try fallbacks
            if gemini_client is not None:
                print(f"Warning: Claude model {requested_model} selected but Anthropic not available. Falling back to Gemini (gemini-2.5-pro).")
                return gemini_client, "gemini-2.5-pro"
            if glm_client is not None:
                print(f"Warning: Claude model {requested_model} selected but Anthropic not available. Falling back to GLM (glm-4.5-20250101).")
                return glm_client, "glm-4.5-20250101"
            if openai_client is not None:
                print(f"Warning: Claude model {requested_model} selected but Anthropic not available. Falling back to OpenAI (gpt-4o).")
                return openai_client, "gpt-4o"
            raise RuntimeError(f"Claude model {requested_model} selected but no LLM clients are available")

        # Route OpenAI models (gpt-*, o1-*, etc.) to OpenAI client
        if openai_client is not None:
            return openai_client, requested_model
        # OpenAI not available, try fallbacks
        if gemini_client is not None:
            print(f"Warning: OpenAI model {requested_model} selected but OpenAI not available. Falling back to Gemini (gemini-2.5-pro).")
            return gemini_client, "gemini-2.5-pro"
        if glm_client is not None:
            print(f"Warning: OpenAI model {requested_model} selected but OpenAI not available. Falling back to GLM (glm-4.5-20250101).")
            return glm_client, "glm-4.5-20250101"
        if anthropic_client is not None:
            print(f"Warning: OpenAI model {requested_model} selected but OpenAI not available. Falling back to Anthropic (claude-sonnet-4-5).")
            return anthropic_client, "claude-sonnet-4-5"
        raise RuntimeError(f"OpenAI model {requested_model} selected but no LLM clients are available")

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

        Returns:
            BuilderResult with patch and metadata
        """
        # Select model using ModelRouter with escalation support
        task_category = phase_spec.get("task_category", "general")
        complexity = phase_spec.get("complexity", "medium")

        # Use escalation-aware model selection
        model, effective_complexity, escalation_info = self.model_router.select_model_with_escalation(
            role="builder",
            task_category=task_category,
            complexity=complexity,
            phase_id=phase_id or "unknown",
            attempt_index=attempt_index,
            run_context=run_context,
        )

        # Log model selection (always, for observability per GPT recommendation)
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            f"[MODEL-SELECT] Builder: model={model}, complexity={complexity}->{effective_complexity}, "
            f"attempt={attempt_index}, category={task_category}"
        )
        if escalation_info.get("complexity_escalation_reason"):
            logger.info(f"[ESCALATION] Builder complexity escalated: {escalation_info['complexity_escalation_reason']}")
        if escalation_info.get("model_escalation_reason"):
            logger.info(f"[MODEL] Builder using {model} due to: {escalation_info['model_escalation_reason']}")
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
        )

        # Record usage in database
        if result.success and result.tokens_used > 0:
            # For now, use rough 40/60 split (prompt/completion typical for builder)
            # TODO: Update OpenAI clients to return separate prompt/completion counts
            prompt_tokens = int(result.tokens_used * 0.4)
            completion_tokens = result.tokens_used - prompt_tokens

            self._record_usage(
                provider=self._model_to_provider(resolved_model),
                model=resolved_model,
                role="builder",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
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
        model, effective_complexity, escalation_info = self.model_router.select_model_with_escalation(
            role="auditor",
            task_category=task_category,
            complexity=complexity,
            phase_id=phase_id or "unknown",
            attempt_index=attempt_index,
            run_context=run_context,
        )

        # Log model selection (always, for observability per GPT recommendation)
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            f"[MODEL-SELECT] Auditor: model={model}, complexity={complexity}->{effective_complexity}, "
            f"attempt={attempt_index}, category={task_category}"
        )
        if escalation_info.get("complexity_escalation_reason"):
            logger.info(f"[ESCALATION] Auditor complexity escalated: {escalation_info['complexity_escalation_reason']}")
        if escalation_info.get("model_escalation_reason"):
            logger.info(f"[MODEL] Auditor using {model} due to: {escalation_info['model_escalation_reason']}")
        if escalation_info.get("budget_warning"):
            budget_warning = escalation_info["budget_warning"]
            logger.warning(f"[{budget_warning['level'].upper()}] {budget_warning['message']}")

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

        # Record usage in database
        if result.tokens_used > 0:
            # For auditor, use rough 60/40 split (prompt/completion - auditor reads more, writes less)
            # TODO: Update OpenAI clients to return separate prompt/completion counts
            prompt_tokens = int(result.tokens_used * 0.6)
            completion_tokens = result.tokens_used - prompt_tokens

            self._record_usage(
                provider=self._model_to_provider(resolved_model),
                model=resolved_model,
                role="auditor",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
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
                result.metadata = integrate_with_auditor(
                    result.metadata, quality_report
                )

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
        Record LLM usage in database.

        Args:
            provider: Provider name (openai, anthropic, etc.)
            model: Model name
            role: builder, auditor, or agent:name
            prompt_tokens: Input tokens
            completion_tokens: Output tokens
            run_id: Optional run identifier
            phase_id: Optional phase identifier
        """
        try:
            usage_event = LlmUsageEvent(
                provider=provider,
                model=model,
                role=role,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                run_id=run_id,
                phase_id=phase_id,
                created_at=datetime.utcnow(),
            )
            self.db.add(usage_event)
            self.db.commit()
        except Exception as e:
            # Don't fail the LLM call if usage recording fails
            print(f"Warning: Failed to record usage: {e}")
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
        elif model.startswith("glm-"):
            return "zhipu"
        else:
            return "openai"  # Safe default

    def record_attempt_outcome(
        self,
        phase_id: str,
        model: str,
        outcome: str,
        details: Optional[str] = None
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
            details=details
        )

    def get_max_attempts(self) -> int:
        """Get maximum attempts per phase from config."""
        return self.model_router.get_max_attempts()

    # =========================================================================
    # DOCTOR INVOCATION (per GPT_RESPONSE8 Section 3.2)
    # =========================================================================

    # Doctor system prompt (per GPT_RESPONSE8 + Phase 3 execute_fix)
    DOCTOR_SYSTEM_PROMPT = """You are the Autopack Doctor, an expert at diagnosing build failures.

Your role is to analyze phase failures and recommend the best action to recover. You receive:
- Phase context (phase_id, error_category, builder_attempts)
- Health budget status (how many failures the run has left)
- Recent patch content (if any)
- Patch validation errors (if any)
- Log excerpts

Based on this context, you MUST return a JSON response with exactly these fields:
{
  "action": "<one of: retry_with_fix, replan, rollback_run, skip_phase, mark_fatal, execute_fix>",
  "confidence": <float 0.0-1.0>,
  "rationale": "<brief explanation of your diagnosis>",
  "builder_hint": "<optional: specific instruction for the next Builder attempt>",
  "suggested_patch": "<optional: small fix if obvious, in git diff format>",
  "fix_commands": ["<optional: list of shell commands for execute_fix action>"],
  "fix_type": "<optional: git|file|python - required if using execute_fix>",
  "verify_command": "<optional: command to verify the fix worked>"
}

Action Guide:
- "retry_with_fix": The issue is local and you have a specific hint for Builder. Best for mechanical errors.
- "replan": The phase approach is flawed. Need architectural reconsideration. Builder's strategy is wrong.
- "rollback_run": The run has accumulated too many failures or the codebase is in a broken state. Revert all changes.
- "skip_phase": The phase is optional and blocking progress. Mark as skipped and continue.
- "mark_fatal": The issue is unrecoverable. Human intervention required.
- "execute_fix": INFRASTRUCTURE ISSUES ONLY. Use for git conflicts, missing files, dependency issues.

execute_fix Guidelines (ONLY for infrastructure issues, NOT code logic):
- Use "execute_fix" ONLY when the failure is caused by infrastructure, not code logic
- Good candidates: merge conflicts, missing directories, pip install failures, git state issues
- BAD candidates: logic bugs, wrong function calls, incorrect imports (use retry_with_fix instead)
- fix_type must be one of: "git", "file", "python"
- Allowed commands by type:
  * git: checkout, reset --hard HEAD, stash, stash pop, clean -fd, merge --abort, rebase --abort
  * file: rm -f, mkdir -p, mv, cp
  * python: pip install, pip uninstall -y, python -m pip install
- NEVER use shell metacharacters (;, &&, ||, |, >, <, etc.)
- ALWAYS provide a verify_command to confirm the fix worked

Example execute_fix for merge conflict:
{
  "action": "execute_fix",
  "confidence": 0.9,
  "rationale": "Git merge conflict detected in auth/login.py. The file has uncommitted changes conflicting with the patch.",
  "fix_commands": ["git checkout -- auth/login.py"],
  "fix_type": "git",
  "verify_command": "git status --porcelain auth/login.py"
}

Example execute_fix for missing directory:
{
  "action": "execute_fix",
  "confidence": 0.85,
  "rationale": "Target directory tests/integration/ does not exist.",
  "fix_commands": ["mkdir -p tests/integration"],
  "fix_type": "file",
  "verify_command": "ls -la tests/integration/"
}

Guidelines:
1. High confidence (>0.8): Only when the issue and fix are clear
2. Medium confidence (0.5-0.8): Reasonable diagnosis but uncertain fix
3. Low confidence (<0.5): Uncertain diagnosis, may need escalation to stronger model

Example response for a simple patch error:
{
  "action": "retry_with_fix",
  "confidence": 0.85,
  "rationale": "Patch context mismatch on line 42. The target file was modified by a previous phase.",
  "builder_hint": "Re-read the current version of auth/login.py before generating the patch. The function signature changed.",
  "suggested_patch": null
}

Example response for repeated failures:
{
  "action": "replan",
  "confidence": 0.7,
  "rationale": "3 consecutive failures with different error types suggests the phase specification is ambiguous or incomplete.",
  "builder_hint": null,
  "suggested_patch": null
}

IMPORTANT: Never apply patches directly. All code changes go through: Builder -> Auditor -> QualityGate -> governed_apply.
IMPORTANT: execute_fix is for INFRASTRUCTURE fixes only. Code logic issues should use retry_with_fix or replan."""

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

        Per GPT_RESPONSE8 Section 3.2: Doctor wrapper in llm_service.py that:
        1. Resolves client/model via choose_doctor_model()
        2. Builds system + user messages using Doctor prompt template
        3. Parses JSON into DoctorResponse.from_dict()
        4. Records usage via _record_usage(role="doctor", ...)
        5. Optionally escalates to strong model if confidence is low

        Args:
            request: Doctor diagnostic request with failure context
            ctx_summary: Optional summary of phase-level error context
            run_id: Run identifier for usage tracking
            phase_id: Phase identifier for logging
            allow_escalation: Whether to escalate to strong model if needed

        Returns:
            DoctorResponse with action, confidence, rationale, and optional hints
        """
        import json
        import logging
        logger = logging.getLogger(__name__)

        # 1. Choose Doctor model based on failure complexity
        model = choose_doctor_model(request, ctx_summary)
        logger.info(
            f"[Doctor] Invoking Doctor for phase={phase_id or request.phase_id}, "
            f"model={model}, builder_attempts={request.builder_attempts}, "
            f"error_category={request.error_category}"
        )

        # 2. Build messages
        user_message = self._build_doctor_user_message(request)

        # 3. Invoke LLM
        response = self._call_doctor_llm(model, user_message, run_id, phase_id)

        # 4. Check for escalation (per GPT_RESPONSE7 recommendations)
        if allow_escalation and should_escalate_doctor_model(
            response, model, request.builder_attempts
        ):
            logger.info(
                f"[Doctor] Escalating from {model} to strong model due to low confidence"
            )
            from .error_recovery import DOCTOR_STRONG_MODEL
            strong_response = self._call_doctor_llm(
                DOCTOR_STRONG_MODEL, user_message, run_id, phase_id
            )
            # Prefer strong response if its confidence is higher
            if strong_response.confidence >= response.confidence:
                response = strong_response

        # 5. Log structured Doctor decision (per GPT_RESPONSE8 Section 5.1)
        health_ratio = request.health_budget.get("total_failures", 0) / max(
            request.health_budget.get("total_cap", 25), 1
        )
        logger.info(
            f"[Doctor] Decision: phase_id={phase_id or request.phase_id}, "
            f"builder_attempts={request.builder_attempts}, health_ratio={health_ratio:.2f}, "
            f"error_category={request.error_category}, model_chosen={model}, "
            f"is_complex={choose_doctor_model(request, ctx_summary) != 'gpt-4o-mini'}, "
            f"doctor_action={response.action}, confidence={response.confidence:.2f}, "
            f"escalated={model != choose_doctor_model(request, ctx_summary)}"
        )

        return response

    def _build_doctor_user_message(self, request: DoctorRequest) -> str:
        """Build user message for Doctor LLM call."""
        message_parts = [
            f"## Phase Failure Diagnosis Request",
            f"",
            f"**Phase ID**: {request.phase_id}",
            f"**Error Category**: {request.error_category}",
            f"**Builder Attempts**: {request.builder_attempts}",
            f"**Run ID**: {request.run_id or 'unknown'}",
            f"",
            f"### Health Budget",
            f"- HTTP 500 errors: {request.health_budget.get('http_500', 0)}",
            f"- Patch failures: {request.health_budget.get('patch_failures', 0)}",
            f"- Total failures: {request.health_budget.get('total_failures', 0)}",
            f"- Total cap: {request.health_budget.get('total_cap', 25)}",
        ]

        if request.patch_errors:
            message_parts.append("")
            message_parts.append("### Patch Validation Errors")
            for i, err in enumerate(request.patch_errors[:5], 1):
                message_parts.append(f"{i}. {err.get('error_type', 'unknown')}: {err.get('message', 'No message')}")

        if request.last_patch:
            message_parts.append("")
            message_parts.append("### Last Patch (truncated)")
            message_parts.append("```diff")
            message_parts.append(request.last_patch[:1500])
            message_parts.append("```")

        if request.logs_excerpt:
            message_parts.append("")
            message_parts.append("### Relevant Logs")
            message_parts.append("```")
            message_parts.append(request.logs_excerpt[:800])
            message_parts.append("```")

        message_parts.append("")
        message_parts.append("Please diagnose this failure and recommend an action.")

        return "\n".join(message_parts)

    def _call_doctor_llm(
        self,
        model: str,
        user_message: str,
        run_id: Optional[str],
        phase_id: Optional[str],
    ) -> DoctorResponse:
        """
        Call LLM for Doctor diagnosis and parse response.

        Args:
            model: Model to use (cheap or strong)
            user_message: Formatted user message
            run_id: Run identifier for usage tracking
            phase_id: Phase identifier for logging

        Returns:
            DoctorResponse parsed from LLM output
        """
        import json
        import logging
        logger = logging.getLogger(__name__)

        # Resolve client
        client, resolved_model = self._resolve_client_and_model("builder", model)

        # Build messages
        messages = [
            {"role": "system", "content": self.DOCTOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        try:
            # Use the client's underlying API call
            if hasattr(client, 'client') and hasattr(client.client, 'chat'):
                # OpenAI client
                completion = client.client.chat.completions.create(
                    model=resolved_model,
                    messages=messages,
                    temperature=0.3,  # Lower temperature for more consistent diagnosis
                    max_tokens=1000,
                    response_format={"type": "json_object"},
                )
                content = completion.choices[0].message.content
                tokens_used = completion.usage.total_tokens if completion.usage else 0
            elif hasattr(client, 'client') and hasattr(client.client, 'messages'):
                # Anthropic client
                completion = client.client.messages.create(
                    model=resolved_model,
                    max_tokens=1000,
                    system=self.DOCTOR_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_message}],
                )
                content = completion.content[0].text
                tokens_used = completion.usage.input_tokens + completion.usage.output_tokens if completion.usage else 0
            else:
                raise RuntimeError(f"Unknown client type for model {resolved_model}")

            # Parse JSON response
            try:
                data = json.loads(content)
                response = DoctorResponse.from_dict(data)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"[Doctor] Failed to parse JSON response: {e}")
                # Return conservative default
                response = DoctorResponse(
                    action="replan",
                    confidence=0.3,
                    rationale=f"Failed to parse Doctor response: {str(e)[:100]}",
                    builder_hint=None,
                    suggested_patch=None,
                )

            # Record usage
            if tokens_used > 0:
                prompt_tokens = int(tokens_used * 0.7)  # Doctor reads more than writes
                completion_tokens = tokens_used - prompt_tokens
                self._record_usage(
                    provider=self._model_to_provider(resolved_model),
                    model=resolved_model,
                    role="doctor",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    run_id=run_id,
                    phase_id=phase_id,
                )

            return response

        except Exception as e:
            logger.error(f"[Doctor] LLM call failed: {e}")
            # Return conservative default on failure
            return DoctorResponse(
                action="replan",
                confidence=0.2,
                rationale=f"Doctor LLM call failed: {str(e)[:100]}",
                builder_hint=None,
                suggested_patch=None,
            )
