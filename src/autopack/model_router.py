"""Model router for quota-aware model selection"""

from typing import Dict, Literal, Optional

import yaml
from pathlib import Path
from sqlalchemy.orm import Session

from .usage_service import UsageService


class ModelRouter:
    """
    Centralized model selection with quota-awareness.

    Handles:
    - Baseline model mapping from config
    - Per-run model overrides
    - Quota-aware fallback logic
    - Fail-fast for critical categories
    """

    def __init__(self, db: Session, config_path: str = "config/models.yaml"):
        """
        Initialize ModelRouter.

        Args:
            db: Database session for usage queries
            config_path: Path to models.yaml config
        """
        self.db = db
        self.usage_service = UsageService(db)

        # Load configuration
        with open(Path(config_path)) as f:
            self.config = yaml.safe_load(f)

        self.complexity_models = self.config.get("complexity_models", {})
        self.category_models = self.config.get("category_models", {})
        self.provider_quotas = self.config.get("provider_quotas", {})
        self.fallback_strategy = self.config.get("fallback_strategy", {})
        self.quota_routing = self.config.get("quota_routing", {})

    def select_model(
        self,
        role: Literal["builder", "auditor"] | str,  # or "agent:<name>"
        task_category: Optional[str],
        complexity: str,
        run_context: Optional[Dict] = None,
        phase_id: Optional[str] = None,
    ) -> tuple[str, Optional[Dict]]:
        """
        Select appropriate model based on task and quota state.

        Args:
            role: Role requesting model (builder/auditor/agent:name)
            task_category: Task category (e.g., security_auth_change)
            complexity: Complexity level (low/medium/high)
            run_context: Optional run context with model_overrides
            phase_id: Optional phase ID for budget tracking

        Returns:
            Tuple of (model_name, budget_warning)
            budget_warning is None or dict with {"level": "info|warning|critical", "message": str}
        """
        run_context = run_context or {}
        budget_warning = None

        # 1. Check per-run overrides first
        if "model_overrides" in run_context:
            overrides = run_context["model_overrides"].get(role, {})
            key = f"{task_category}:{complexity}"
            if key in overrides:
                return overrides[key], budget_warning

        # 2. Get baseline model from config
        baseline_model = self._get_baseline_model(role, task_category, complexity)

        # 3. Check quota state and apply fallback if needed
        if self.quota_routing.get("enabled", False):
            if self._is_provider_over_soft_limit(baseline_model):
                provider = self._model_to_provider(baseline_model)

                if self._is_fail_fast_category(task_category):
                    # For critical categories, warn but don't downgrade
                    budget_warning = {
                        "level": "warning",
                        "message": f"Provider {provider} over soft limit, but category {task_category} requires baseline model"
                    }
                else:
                    # Try fallback
                    fallback = self._get_fallback_model(task_category, complexity)
                    if fallback:
                        budget_warning = {
                            "level": "info",
                            "message": f"Provider {provider} over soft limit, using fallback model {fallback}"
                        }
                        return fallback, budget_warning

        return baseline_model, budget_warning

    def _get_baseline_model(
        self, role: str, task_category: Optional[str], complexity: str
    ) -> str:
        """
        Get baseline model from config.

        Priority:
        1. Category-specific override
        2. Complexity-based default
        3. Global default
        """
        # Check category overrides first
        if task_category and task_category in self.category_models:
            category_config = self.category_models[task_category]
            override_key = f"{role}_model_override"
            if override_key in category_config:
                return category_config[override_key]

        # Fall back to complexity-based selection
        if complexity in self.complexity_models:
            complexity_config = self.complexity_models[complexity]
            if role in complexity_config:
                return complexity_config[role]

        # Default fallback
        if role == "builder":
            return self.config.get("defaults", {}).get("high_risk_builder", "gpt-4o")
        elif role == "auditor":
            return self.config.get("defaults", {}).get("high_risk_auditor", "gpt-4o")
        else:
            return "gpt-4o"  # Safe default

    def _is_provider_over_soft_limit(self, model: str) -> bool:
        """
        Check if provider has exceeded soft limit (80% by default).

        Args:
            model: Model name to check provider for

        Returns:
            True if over soft limit
        """
        provider = self._model_to_provider(model)
        usage = self.usage_service.get_provider_usage_summary("week")

        if provider not in usage:
            return False  # No usage yet

        quota_config = self.provider_quotas.get(provider, {})
        cap = quota_config.get("weekly_token_cap", 0)
        soft_limit_ratio = quota_config.get("soft_limit_ratio", 0.8)

        if cap == 0:
            return False  # No cap configured

        provider_usage = usage[provider]["total_tokens"]
        soft_limit = cap * soft_limit_ratio

        return provider_usage > soft_limit

    def _is_fail_fast_category(self, task_category: Optional[str]) -> bool:
        """
        Check if category should fail fast instead of falling back.

        Args:
            task_category: Category to check

        Returns:
            True if should never fallback
        """
        never_fallback = self.quota_routing.get("never_fallback_categories", [])
        return task_category in never_fallback

    def _get_fallback_model(self, task_category: Optional[str], complexity: str) -> Optional[str]:
        """
        Get fallback model based on category and complexity.

        Args:
            task_category: Task category
            complexity: Complexity level

        Returns:
            Fallback model name or None
        """
        fallback_config = self.fallback_strategy.get("by_category", {})

        # Try category-specific fallback
        if task_category and task_category in fallback_config:
            fallbacks = fallback_config[task_category].get("fallbacks", [])
            if fallbacks:
                return fallbacks[0]  # Return first available fallback

        # Try complexity-based fallback
        if f"{complexity}_complexity_general" in fallback_config:
            fallbacks = fallback_config[f"{complexity}_complexity_general"].get("fallbacks", [])
            if fallbacks:
                return fallbacks[0]

        # Default fallback chain
        default_fallbacks = self.fallback_strategy.get("default_fallbacks", [])
        if default_fallbacks:
            return default_fallbacks[0]

        return None

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
            # Try to infer from config
            for provider_name in self.provider_quotas.keys():
                if provider_name in model.lower():
                    return provider_name
            return "openai"  # Safe default

    def get_current_mappings(self) -> Dict:
        """
        Get all current model mappings for dashboard display.

        Returns:
            Dict with mappings by role, category, and complexity
        """
        mappings = {
            "builder": {},
            "auditor": {},
        }

        # Generate mappings for all combinations
        complexities = ["low", "medium", "high"]
        categories = list(self.category_models.keys()) + ["general"]

        for role in ["builder", "auditor"]:
            for category in categories:
                for complexity in complexities:
                    key = f"{category}:{complexity}"
                    model = self._get_baseline_model(
                        role,
                        category if category != "general" else None,
                        complexity,
                    )
                    mappings[role][key] = model

        return mappings
