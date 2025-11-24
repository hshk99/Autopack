"""LLM Client Abstractions for Autopack

Per v7 GPT architect recommendation:
- BuilderClient: Generates code patches from phase specs
- AuditorClient: Reviews patches and finds issues
- ModelSelector: Chooses appropriate model based on complexity/risk

Architecture:
- Abstract interfaces (Protocol)
- OpenAI implementation for Builder and Auditor
- Extensible for future Cursor/Claude implementations
"""

from typing import Dict, List, Optional, Protocol
from dataclasses import dataclass


@dataclass
class BuilderResult:
    """Result from Builder execution"""
    success: bool
    patch_content: str
    builder_messages: List[str]
    tokens_used: int
    model_used: str
    error: Optional[str] = None


@dataclass
class AuditorResult:
    """Result from Auditor review"""
    approved: bool
    issues_found: List[Dict]  # List of IssueCreate dicts
    auditor_messages: List[str]
    tokens_used: int
    model_used: str
    error: Optional[str] = None


@dataclass
class ModelSelection:
    """Model selection result"""
    builder_model: str
    auditor_model: str
    rationale: str  # Why these models were selected


class BuilderClient(Protocol):
    """Protocol for Builder implementations

    Builder generates code patches from phase specifications.
    Implementations:
    - OpenAIBuilderClient (using GPT-4.1/Codex)
    - CursorCloudBuilderClient (future)
    """

    def execute_phase(
        self,
        phase_spec: Dict,
        file_context: Optional[Dict] = None,
        max_tokens: Optional[int] = None
    ) -> BuilderResult:
        """Execute a phase and generate code patch

        Args:
            phase_spec: Phase specification with task_category, complexity, description
            file_context: Current repo files and structure
            max_tokens: Token budget limit for this call

        Returns:
            BuilderResult with patch_content and metadata
        """
        ...


class AuditorClient(Protocol):
    """Protocol for Auditor implementations

    Auditor reviews code patches and finds issues.
    Implementations:
    - OpenAIAuditorClient (using GPT-4.1)
    - ClaudeAuditorClient (future)
    """

    def review_patch(
        self,
        patch_content: str,
        phase_spec: Dict,
        max_tokens: Optional[int] = None
    ) -> AuditorResult:
        """Review a patch and find issues

        Args:
            patch_content: Git diff/patch to review
            phase_spec: Phase specification for context
            max_tokens: Token budget limit for this call

        Returns:
            AuditorResult with issues_found and metadata
        """
        ...


class ModelSelector:
    """Selects appropriate LLM models based on task complexity and risk

    Per v7 GPT architect recommendation:
    - Low complexity → cheap/fast models (gpt-4.1-mini)
    - Medium complexity → balanced models (gpt-4.1)
    - High complexity/HIGH_RISK → best models (gpt-4.1, o4-mini)

    Configuration loaded from config/models.yaml
    """

    def __init__(self, models_config: Dict):
        """Initialize with models configuration

        Args:
            models_config: Loaded from config/models.yaml
        """
        self.models_config = models_config

    def select_models(
        self,
        task_category: str,
        complexity: str,
        is_high_risk: bool = False
    ) -> ModelSelection:
        """Select appropriate models for Builder and Auditor

        Args:
            task_category: From phase spec (e.g., "feature_scaffolding")
            complexity: "low", "medium", or "high"
            is_high_risk: True if task_category in HIGH_RISK_DEFAULTS

        Returns:
            ModelSelection with builder_model and auditor_model names
        """
        # Get category-specific config or fallback to defaults
        category_config = self.models_config.get(
            "category_models", {}
        ).get(task_category, {})

        # For HIGH_RISK categories, always use best models
        if is_high_risk:
            builder_model = category_config.get(
                "builder_model_override",
                self.models_config["defaults"]["high_risk_builder"]
            )
            auditor_model = category_config.get(
                "auditor_model_override",
                self.models_config["defaults"]["high_risk_auditor"]
            )
            rationale = f"HIGH_RISK category: {task_category}"
        else:
            # Use complexity-based selection
            complexity_models = self.models_config["complexity_models"]
            builder_model = complexity_models[complexity]["builder"]
            auditor_model = complexity_models[complexity]["auditor"]
            rationale = f"Complexity: {complexity}, Category: {task_category}"

        return ModelSelection(
            builder_model=builder_model,
            auditor_model=auditor_model,
            rationale=rationale
        )
