"""LLM Service with integrated ModelRouter and UsageRecorder

This service wraps the OpenAI clients and provides:
- Automatic model selection via ModelRouter
- Usage tracking via UsageRecorder
- Centralized error handling and logging
- Quality gate enforcement for high-risk categories
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from .config_loader import get_config
from .llm_client import AuditorResult, BuilderResult
from .model_router import ModelRouter
from .openai_clients import OpenAIAuditorClient, OpenAIBuilderClient
from .quality_gate import QualityGate, integrate_with_auditor
from .usage_recorder import LlmUsageEvent

# Import Anthropic clients with graceful fallback
try:
    from .anthropic_clients import AnthropicAuditorClient, AnthropicBuilderClient
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


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

        # Initialize OpenAI clients (always available)
        self.openai_builder = OpenAIBuilderClient()
        self.openai_auditor = OpenAIAuditorClient()

        # Initialize Anthropic clients if available
        if ANTHROPIC_AVAILABLE:
            self.anthropic_builder = AnthropicBuilderClient()
            self.anthropic_auditor = AnthropicAuditorClient()
        else:
            self.anthropic_builder = None
            self.anthropic_auditor = None

        # Initialize quality gate with project config
        self.repo_root = repo_root or Path.cwd()
        config = get_config(self.repo_root / ".autopack" / "config.yaml")
        self.quality_gate = QualityGate(
            repo_root=self.repo_root, config=config._config
        )

    def _get_builder_client(self, model: str):
        """Select appropriate builder client based on model name"""
        if "claude" in model.lower():
            if self.anthropic_builder is None:
                print(f"Warning: Claude model {model} selected but Anthropic not available. Falling back to OpenAI.")
                return self.openai_builder
            return self.anthropic_builder
        return self.openai_builder

    def _get_auditor_client(self, model: str):
        """Select appropriate auditor client based on model name"""
        if "claude" in model.lower():
            if self.anthropic_auditor is None:
                print(f"Warning: Claude model {model} selected but Anthropic not available. Falling back to OpenAI.")
                return self.openai_auditor
            return self.anthropic_auditor
        return self.openai_auditor

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

        Returns:
            BuilderResult with patch and metadata
        """
        # Select model using ModelRouter
        task_category = phase_spec.get("task_category", "general")
        complexity = phase_spec.get("complexity", "medium")

        model, budget_warning = self.model_router.select_model(
            role="builder",
            task_category=task_category,
            complexity=complexity,
            run_context=run_context,
            phase_id=phase_id,
        )

        # Log budget warning if present (alerts, not hard stops)
        if budget_warning:
            print(f"[{budget_warning['level'].upper()}] {budget_warning['message']}")

        # Select appropriate client based on model
        builder_client = self._get_builder_client(model)

        # Execute builder with selected model
        result = builder_client.execute_phase(
            phase_spec=phase_spec,
            file_context=file_context,
            max_tokens=max_tokens,
            model=model,
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
                provider=self._model_to_provider(model),
                model=model,
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

        Returns:
            AuditorResult with review, issues, and quality gate assessment
        """
        # Select model using ModelRouter
        task_category = phase_spec.get("task_category", "general")
        complexity = phase_spec.get("complexity", "medium")

        model, budget_warning = self.model_router.select_model(
            role="auditor",
            task_category=task_category,
            complexity=complexity,
            run_context=run_context,
            phase_id=phase_id,
        )

        # Log budget warning if present (alerts, not hard stops)
        if budget_warning:
            print(f"[{budget_warning['level'].upper()}] {budget_warning['message']}")

        # Select appropriate client based on model
        auditor_client = self._get_auditor_client(model)

        # Execute auditor with selected model
        result = auditor_client.review_patch(
            patch_content=patch_content,
            phase_spec=phase_spec,
            max_tokens=max_tokens,
            model=model,
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
                provider=self._model_to_provider(model),
                model=model,
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
        if model.startswith("gpt-") or model.startswith("o1-"):
            return "openai"
        elif model.startswith("claude-") or model.startswith("opus-"):
            return "anthropic"
        elif model.startswith("gemini-"):
            return "google_gemini"
        elif model.startswith("glm-"):
            return "zhipu_glm"
        else:
            return "openai"  # Safe default
