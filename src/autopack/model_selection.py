"""Model selection with intra-tier and cross-tier escalation.

This module implements the dynamic model selection strategy:
1. Intra-tier escalation: cheap -> mid -> expensive models within a tier
2. Cross-tier escalation: Low -> Medium -> High complexity after repeated failures
3. High-risk category protection: Never downgrade for security/auth/schema tasks
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional

import yaml

logger = logging.getLogger(__name__)

# High-risk categories that bypass escalation chains and use fixed overrides
HIGH_RISK_CATEGORIES = {
    "security_auth_change",
    "external_feature_reuse_remote",
    "schema_contract_change_destructive",
}


@dataclass
class PhaseHistory:
    """Track attempt history for a phase."""

    phase_id: str
    initial_complexity: str
    current_complexity: str
    attempts: List[Dict] = field(default_factory=list)
    escalated_at_attempt: Optional[int] = None

    def add_attempt(
        self,
        model: str,
        outcome: Literal[
            "success",
            "auditor_reject",
            "ci_fail",
            "patch_apply_error",
            "infra_error",
            "builder_churn_limit_exceeded",
        ],
        details: Optional[str] = None
    ):
        """Record an attempt outcome."""
        self.attempts.append({
            "attempt_index": len(self.attempts),
            "model": model,
            "outcome": outcome,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "complexity": self.current_complexity,
        })

    def count_recent_failures(self) -> int:
        """Count failures that should trigger escalation."""
        failure_types = {"auditor_reject", "ci_fail", "patch_apply_error"}
        return sum(1 for a in self.attempts if a["outcome"] in failure_types)

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)


class ModelSelector:
    """
    Centralized model selection with escalation logic.

    Handles:
    - Intra-tier escalation (cheap -> mid -> expensive within a tier)
    - Cross-tier escalation (Low -> Medium -> High after failures)
    - High-risk category protection
    """

    def __init__(self, config_path: str = "config/models.yaml"):
        """
        Initialize ModelSelector.

        Args:
            config_path: Path to models.yaml config
        """
        with open(Path(config_path)) as f:
            self.config = yaml.safe_load(f)

        self.escalation_chains = self.config.get("escalation_chains", {})
        self.complexity_escalation = self.config.get("complexity_escalation", {})
        self.category_models = self.config.get("category_models", {})
        self.llm_routing_policies = self.config.get("llm_routing_policies", {})

        # Phase history tracking
        self._phase_histories: Dict[str, PhaseHistory] = {}

    def get_or_create_phase_history(
        self,
        phase_id: str,
        initial_complexity: str
    ) -> PhaseHistory:
        """Get or create phase history for tracking."""
        if phase_id not in self._phase_histories:
            self._phase_histories[phase_id] = PhaseHistory(
                phase_id=phase_id,
                initial_complexity=initial_complexity,
                current_complexity=initial_complexity,
            )
        return self._phase_histories[phase_id]

    def select_model_for_attempt(
        self,
        role: Literal["builder", "auditor"],
        complexity: str,
        phase_id: str,
        task_category: Optional[str] = None,
        attempt_index: int = 0,
        phase_history: Optional[PhaseHistory] = None,
    ) -> tuple[str, str, Dict]:
        """
        Select model based on role, complexity, category, and attempt history.

        Escalation strategy:
        1. First, exhaust all models in current complexity tier (intra-tier escalation)
        2. Then, escalate to next complexity tier and start with cheapest model

        Example for LOW complexity with chain [gpt-4o-mini, gpt-4o, claude-sonnet]:
        - Attempt 0: gpt-4o-mini (low tier, model 0)
        - Attempt 1: gpt-4o (low tier, model 1) - intra-tier escalation
        - Attempt 2: gpt-4o (medium tier, model 0) - complexity escalation
        - Attempt 3: claude-sonnet (medium tier, model 1)
        - Attempt 4: claude-sonnet (high tier, model 0) - complexity escalation

        Args:
            role: 'builder' or 'auditor'
            complexity: 'low', 'medium', or 'high'
            phase_id: Phase identifier
            task_category: Task category (e.g., 'security_auth_change')
            attempt_index: 0-based index of current attempt
            phase_history: Optional phase history for escalation tracking

        Returns:
            Tuple of (model_name, effective_complexity, escalation_info)
        """
        escalation_info = {
            "original_complexity": complexity,
            "effective_complexity": complexity,
            "model_escalation_reason": None,
            "complexity_escalation_reason": None,
        }

        # 1. High-risk categories use fixed overrides and bypass escalation
        if task_category in HIGH_RISK_CATEGORIES:
            model = self._get_high_risk_model(role, task_category)
            escalation_info["model_escalation_reason"] = f"high_risk_category:{task_category}"
            logger.info(f"[ModelSelector] High-risk category {task_category}: using {model}")
            return model, "high", escalation_info

        # 2. Check llm_routing_policies for category-specific strategies
        if task_category and task_category in self.llm_routing_policies:
            policy = self.llm_routing_policies[task_category]
            model = self._apply_routing_policy(role, policy, attempt_index)
            if model:
                escalation_info["model_escalation_reason"] = f"routing_policy:{task_category}"
                return model, complexity, escalation_info

        # 3. Calculate effective complexity and intra-tier attempt
        # Strategy: exhaust models in current tier before escalating complexity
        effective_complexity, intra_tier_attempt = self._calculate_escalation(
            role, complexity, attempt_index, escalation_info
        )

        # 4. Select model from escalation chain based on intra-tier attempt
        model = self._select_from_chain(role, effective_complexity, attempt_index, intra_tier_attempt)

        # Log escalation decision
        if effective_complexity != complexity:
            logger.info(
                f"[ModelSelector] Complexity escalated: {complexity} -> {effective_complexity} "
                f"for phase {phase_id}"
            )

        logger.info(
            f"[ModelSelector] Selected {model} for {role} "
            f"(complexity={effective_complexity}, attempt={attempt_index}, intra_tier={intra_tier_attempt})"
        )

        return model, effective_complexity, escalation_info

    def _get_high_risk_model(self, role: str, task_category: str) -> str:
        """Get model for high-risk category from category_models or llm_routing_policies."""
        # Check llm_routing_policies first
        if task_category in self.llm_routing_policies:
            policy = self.llm_routing_policies[task_category]
            if role == "builder":
                return policy.get("builder_primary", "gpt-5")
            else:
                return policy.get("auditor_primary", "claude-opus-4-5")

        # Fall back to category_models
        if task_category in self.category_models:
            cat_config = self.category_models[task_category]
            if role == "builder":
                return cat_config.get("builder_model_override", "gpt-5")
            else:
                return cat_config.get("auditor_model_override", "claude-opus-4-5")

        # Default high-risk models
        return "gpt-5" if role == "builder" else "claude-opus-4-5"

    def _apply_routing_policy(
        self,
        role: str,
        policy: Dict,
        attempt_index: int
    ) -> Optional[str]:
        """Apply llm_routing_policy to select model."""
        strategy = policy.get("strategy", "progressive")

        if strategy == "best_first":
            # Always use primary model
            if role == "builder":
                return policy.get("builder_primary")
            else:
                return policy.get("auditor_primary")

        elif strategy == "progressive":
            # Check if we should escalate
            escalate_config = policy.get("escalate_to", {})
            escalate_after = escalate_config.get("after_attempts", 2)

            if attempt_index >= escalate_after:
                if role == "builder":
                    return escalate_config.get("builder", policy.get("builder_primary"))
                else:
                    return escalate_config.get("auditor", policy.get("auditor_primary"))
            else:
                if role == "builder":
                    return policy.get("builder_primary")
                else:
                    return policy.get("auditor_primary")

        elif strategy == "cheap_first":
            # Start cheap, escalate after failures
            escalate_config = policy.get("escalate_to", {})
            escalate_after = escalate_config.get("after_attempts", 3)

            if attempt_index >= escalate_after:
                if role == "builder":
                    return escalate_config.get("builder")
                # auditor usually doesn't have escalation in cheap_first

            if role == "builder":
                return policy.get("builder_primary")
            else:
                return policy.get("auditor_primary")

        return None

    def _calculate_escalation(
        self,
        role: str,
        complexity: str,
        attempt_index: int,
        escalation_info: Dict
    ) -> tuple[str, int]:
        """
        Calculate effective complexity and intra-tier attempt index.

        Strategy: Exhaust all models in current tier before escalating complexity.

        For LOW complexity builder with chain [gpt-4o-mini, gpt-4o, claude-sonnet] (3 models):
        - Attempt 0: low tier, intra_tier=0 -> gpt-4o-mini
        - Attempt 1: low tier, intra_tier=1 -> gpt-4o (intra-tier escalation)
        - Attempt 2: medium tier, intra_tier=0 -> medium's first model (complexity escalation)
        - etc.

        Returns:
            Tuple of (effective_complexity, intra_tier_attempt)
        """
        if not self.complexity_escalation.get("enabled", False):
            # No escalation - just use attempt_index as intra-tier
            return complexity, attempt_index

        # Get the number of attempts per tier for this role
        # Low tier: 2 attempts (cheap model, then mid model)
        # Medium tier: 3 attempts (more tries before expensive escalation)
        # High tier: unlimited (strongest models, no further escalation)
        def get_tier_size(tier: str) -> int:
            chain = self.escalation_chains.get(role, {}).get(tier, {}).get("models", [])
            if not chain:
                return 1
            if tier == "low":
                return min(len(chain), 2)  # 2 attempts in low tier
            elif tier == "medium":
                return min(len(chain), 3)  # 3 attempts in medium tier
            else:
                return len(chain)  # All models in high tier

        # Calculate which tier we should be in based on attempt_index
        low_size = get_tier_size("low")
        medium_size = get_tier_size("medium")

        if complexity == "low":
            if attempt_index < low_size:
                # Still in low tier
                escalation_info["effective_complexity"] = "low"
                return "low", attempt_index
            elif attempt_index < low_size + medium_size:
                # Escalated to medium tier
                intra_tier = attempt_index - low_size
                escalation_info["effective_complexity"] = "medium"
                escalation_info["complexity_escalation_reason"] = (
                    f"low_to_medium after {low_size} attempts (exhausted low tier models)"
                )
                return "medium", intra_tier
            else:
                # Escalated to high tier
                intra_tier = attempt_index - low_size - medium_size
                escalation_info["effective_complexity"] = "high"
                escalation_info["complexity_escalation_reason"] = (
                    f"low_to_high after {low_size + medium_size} attempts"
                )
                return "high", intra_tier

        elif complexity == "medium":
            if attempt_index < medium_size:
                # Still in medium tier
                escalation_info["effective_complexity"] = "medium"
                return "medium", attempt_index
            else:
                # Escalated to high tier
                intra_tier = attempt_index - medium_size
                escalation_info["effective_complexity"] = "high"
                escalation_info["complexity_escalation_reason"] = (
                    f"medium_to_high after {medium_size} attempts"
                )
                return "high", intra_tier

        else:
            # Already high complexity - no escalation possible
            escalation_info["effective_complexity"] = "high"
            return "high", attempt_index

    def _maybe_escalate_complexity(
        self,
        current_complexity: str,
        phase_history: Optional[PhaseHistory],
        escalation_info: Dict
    ) -> str:
        """
        DEPRECATED: Use _calculate_escalation instead.
        Kept for backwards compatibility.
        """
        if not self.complexity_escalation.get("enabled", False):
            return current_complexity

        if phase_history is None:
            return current_complexity

        failures = phase_history.count_recent_failures()
        thresholds = self.complexity_escalation.get("thresholds", {})

        effective = current_complexity

        if current_complexity == "low":
            low_to_medium = thresholds.get("low_to_medium", 2)
            if failures >= low_to_medium:
                effective = "medium"
                escalation_info["complexity_escalation_reason"] = (
                    f"low_to_medium after {failures} failures"
                )
                # Check if we need to escalate further
                medium_to_high = thresholds.get("medium_to_high", 2)
                if failures >= low_to_medium + medium_to_high:
                    effective = "high"
                    escalation_info["complexity_escalation_reason"] = (
                        f"low_to_high after {failures} failures"
                    )

        elif current_complexity == "medium":
            medium_to_high = thresholds.get("medium_to_high", 2)
            if failures >= medium_to_high:
                effective = "high"
                escalation_info["complexity_escalation_reason"] = (
                    f"medium_to_high after {failures} failures"
                )

        # Update phase history if escalated
        if effective != current_complexity and phase_history:
            if phase_history.escalated_at_attempt is None:
                phase_history.escalated_at_attempt = phase_history.attempt_count
            phase_history.current_complexity = effective

        escalation_info["effective_complexity"] = effective
        return effective

    def _select_from_chain(
        self,
        role: str,
        complexity: str,
        attempt_index: int,
        intra_tier_attempt: int = 0
    ) -> str:
        """
        Select model from escalation chain based on intra-tier attempt index.

        Intra-tier escalation (within same complexity tier):
        - intra_tier_attempt 0: index 0 (cheapest model in tier)
        - intra_tier_attempt 1: index 1 (middle model in tier)
        - intra_tier_attempt 2+: last index (strongest model in tier)

        Args:
            role: 'builder' or 'auditor'
            complexity: 'low', 'medium', or 'high'
            attempt_index: Overall attempt number (for logging)
            intra_tier_attempt: Attempt within current complexity tier
        """
        chain = self.escalation_chains.get(role, {}).get(complexity, {}).get("models", [])

        if not chain:
            # Fall back to defaults
            logger.warning(
                f"[ModelSelector] No escalation chain for {role}/{complexity}, using default"
            )
            if role == "builder":
                return "glm-4.6"
            else:
                return "glm-4.6"

        # Map intra-tier attempt to chain index
        # Each model in chain gets one attempt before moving to next
        idx = min(intra_tier_attempt, len(chain) - 1)

        return chain[idx]

    def get_max_attempts(self) -> int:
        """Get maximum attempts per phase from config."""
        return self.complexity_escalation.get("max_attempts_per_phase", 5)

    def log_model_selection(
        self,
        phase_id: str,
        role: str,
        model: str,
        complexity: str,
        effective_complexity: str,
        attempt_index: int,
        escalation_info: Dict,
        log_dir: str = "logs/autopack"
    ):
        """
        Log model selection to JSONL file for analysis.

        Args:
            phase_id: Phase identifier
            role: builder or auditor
            model: Selected model
            complexity: Original complexity
            effective_complexity: Complexity after escalation
            attempt_index: Attempt number
            escalation_info: Escalation details
            log_dir: Directory for log files
        """
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        log_file = log_path / f"model_selections_{today}.jsonl"

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase_id": phase_id,
            "role": role,
            "model": model,
            "original_complexity": complexity,
            "effective_complexity": effective_complexity,
            "attempt_index": attempt_index,
            "escalation_info": escalation_info,
        }

        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning(f"[ModelSelector] Failed to log selection: {e}")


# Singleton instance for convenience
_selector: Optional[ModelSelector] = None


def get_model_selector(config_path: str = "config/models.yaml") -> ModelSelector:
    """Get or create the singleton ModelSelector instance."""
    global _selector
    if _selector is None:
        _selector = ModelSelector(config_path)
    return _selector


def select_model_for_attempt(
    role: Literal["builder", "auditor"],
    complexity: str,
    phase_id: str,
    task_category: Optional[str] = None,
    attempt_index: int = 0,
    phase_history: Optional[PhaseHistory] = None,
) -> tuple[str, str, Dict]:
    """
    Convenience function to select model using default selector.

    See ModelSelector.select_model_for_attempt for details.
    """
    selector = get_model_selector()
    return selector.select_model_for_attempt(
        role=role,
        complexity=complexity,
        phase_id=phase_id,
        task_category=task_category,
        attempt_index=attempt_index,
        phase_history=phase_history,
    )
