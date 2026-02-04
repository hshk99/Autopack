"""LLM Routing Engine for intelligent model selection.

This module provides intelligent routing of LLM requests to appropriate models
based on task complexity, required capabilities, and model availability.

Part of IMP-LLM-001: LLM Model Validation & Routing System.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

from .model_registry import (
    ModelInfo,
    ModelRegistry,
    ModelTier,
    get_model_registry,
)
from .model_validator import ModelValidator, get_model_validator

logger = logging.getLogger(__name__)


class RoutingStrategy(Enum):
    """Model routing strategies."""

    BEST_FIRST = "best_first"  # Always use the best model for the task
    PROGRESSIVE = "progressive"  # Start simple, escalate on failure
    CHEAP_FIRST = "cheap_first"  # Start with cheapest, escalate if needed
    ROUND_ROBIN = "round_robin"  # Distribute across available models
    CAPABILITY_MATCH = "capability_match"  # Strict capability matching


class FallbackTrigger(Enum):
    """Triggers that cause model fallback."""

    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    CAPABILITY_MISMATCH = "capability_mismatch"
    VALIDATION_FAILURE = "validation_failure"
    EXPLICIT = "explicit"  # User-requested fallback


@dataclass
class RoutingRule:
    """Rule for routing tasks to models."""

    task_type: str
    description: str
    preferred_model: str
    complexity_threshold: float
    required_capabilities: List[str]
    fallback_chain: List[str]
    strategy: RoutingStrategy = RoutingStrategy.PROGRESSIVE

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoutingRule":
        """Create RoutingRule from dictionary."""
        strategy_str = data.get("strategy", "progressive")
        strategy = (
            RoutingStrategy(strategy_str)
            if strategy_str in [s.value for s in RoutingStrategy]
            else RoutingStrategy.PROGRESSIVE
        )

        return cls(
            task_type=data.get("task_type", ""),
            description=data.get("description", ""),
            preferred_model=data.get("preferred_model", ""),
            complexity_threshold=data.get("complexity_threshold", 0.5),
            required_capabilities=data.get("required_capabilities", []),
            fallback_chain=data.get("fallback_chain", []),
            strategy=strategy,
        )


@dataclass
class RoutingDecision:
    """Result of a routing decision."""

    model_id: str
    task_type: str
    complexity_score: float
    strategy_used: RoutingStrategy
    fallback_position: int  # 0 = primary, 1+ = fallback
    reasoning: str
    alternatives: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_fallback(self) -> bool:
        """Check if this is a fallback decision."""
        return self.fallback_position > 0


@dataclass
class FallbackChain:
    """Manages fallback chain for model failures."""

    models: List[str]
    current_index: int = 0
    max_retries_per_model: int = 3
    retry_counts: Dict[str, int] = field(default_factory=dict)

    def get_current_model(self) -> Optional[str]:
        """Get current model in the chain."""
        if self.current_index < len(self.models):
            return self.models[self.current_index]
        return None

    def advance(self) -> Optional[str]:
        """Advance to next model in chain."""
        self.current_index += 1
        return self.get_current_model()

    def should_retry(self, model_id: str) -> bool:
        """Check if we should retry the current model."""
        count = self.retry_counts.get(model_id, 0)
        return count < self.max_retries_per_model

    def record_attempt(self, model_id: str) -> None:
        """Record an attempt for a model."""
        self.retry_counts[model_id] = self.retry_counts.get(model_id, 0) + 1

    def has_more_fallbacks(self) -> bool:
        """Check if there are more fallback options."""
        return self.current_index < len(self.models) - 1

    def reset(self) -> None:
        """Reset the chain to the beginning."""
        self.current_index = 0
        self.retry_counts.clear()


@dataclass
class ComplexityEstimate:
    """Estimated complexity of a task."""

    score: float  # 0.0 to 1.0
    factors: Dict[str, float]
    recommended_tier: ModelTier
    reasoning: str


class RoutingEngine:
    """Routes LLM requests to appropriate models.

    Provides:
    - Task-to-model routing based on complexity and capabilities
    - Fallback chain management
    - Request execution with automatic retries
    - Performance-based model selection
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        validator: Optional[ModelValidator] = None,
        config_path: str = "config/llm_validation.yaml",
    ):
        """Initialize the routing engine.

        Args:
            registry: Model registry instance.
            validator: Model validator instance.
            config_path: Path to configuration file.
        """
        self.registry = registry or get_model_registry(config_path)
        self.validator = validator or get_model_validator(config_path)
        self._config = self._load_config(config_path)
        self._routing_rules = self._load_routing_rules()
        self._active_chains: Dict[str, FallbackChain] = {}

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from file."""
        config_file = Path(config_path)
        if not config_file.is_absolute():
            repo_root = Path(__file__).resolve().parents[3]
            config_file = repo_root / config_path

        if config_file.exists():
            try:
                return yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
            except Exception as e:
                logger.warning(f"[RoutingEngine] Failed to load config: {e}")
        return {}

    def _load_routing_rules(self) -> Dict[str, RoutingRule]:
        """Load routing rules from configuration."""
        rules = {}
        rules_config = self._config.get("routing_rules", [])

        for rule_data in rules_config:
            rule = RoutingRule.from_dict(rule_data)
            rules[rule.task_type] = rule
            logger.debug(f"[RoutingEngine] Loaded routing rule: {rule.task_type}")

        return rules

    def estimate_complexity(
        self,
        task_type: str,
        token_count: int = 0,
        file_count: int = 0,
        context: Optional[Dict[str, Any]] = None,
    ) -> ComplexityEstimate:
        """Estimate task complexity.

        Args:
            task_type: Type of task.
            token_count: Estimated token count.
            file_count: Number of files involved.
            context: Additional context for estimation.

        Returns:
            ComplexityEstimate with score and recommendations.
        """
        context = context or {}
        complexity_config = self._config.get("complexity_estimation", {})

        # Token-based score
        token_thresholds = complexity_config.get(
            "token_thresholds",
            {
                "simple": 1000,
                "moderate": 5000,
                "complex": 20000,
            },
        )
        if token_count <= token_thresholds.get("simple", 1000):
            token_score = 0.2
        elif token_count <= token_thresholds.get("moderate", 5000):
            token_score = 0.5
        elif token_count <= token_thresholds.get("complex", 20000):
            token_score = 0.8
        else:
            token_score = 1.0

        # Task type multiplier
        task_multipliers = complexity_config.get("task_multipliers", {})
        task_multiplier = task_multipliers.get(task_type, 1.0)

        # Context factors
        context_factors = complexity_config.get("context_factors", {})
        file_weight = context_factors.get("file_count_weight", 0.1)
        file_score = min(1.0, file_count * file_weight)

        # Calculate final score
        base_score = token_score * task_multiplier
        adjusted_score = min(1.0, base_score + file_score)

        # Determine recommended tier
        if adjusted_score <= 0.3:
            tier = ModelTier.ECONOMY
        elif adjusted_score <= 0.7:
            tier = ModelTier.STANDARD
        else:
            tier = ModelTier.PREMIUM

        factors = {
            "token_score": token_score,
            "task_multiplier": task_multiplier,
            "file_score": file_score,
            "base_score": base_score,
        }

        reasoning = (
            f"Token complexity: {token_score:.2f}, "
            f"Task multiplier: {task_multiplier:.2f}, "
            f"File factor: {file_score:.2f}"
        )

        return ComplexityEstimate(
            score=adjusted_score,
            factors=factors,
            recommended_tier=tier,
            reasoning=reasoning,
        )

    def select_model(
        self,
        task_type: str,
        complexity_score: Optional[float] = None,
        required_capabilities: Optional[List[str]] = None,
        preferred_model: Optional[str] = None,
        exclude_models: Optional[List[str]] = None,
        strategy: Optional[RoutingStrategy] = None,
    ) -> RoutingDecision:
        """Select the best model for a task.

        Args:
            task_type: Type of task.
            complexity_score: Pre-calculated complexity score.
            required_capabilities: Required model capabilities.
            preferred_model: Preferred model ID.
            exclude_models: Models to exclude from selection.
            strategy: Routing strategy to use.

        Returns:
            RoutingDecision with selected model and alternatives.
        """
        exclude_models = exclude_models or []

        # Get routing rule for task type
        rule = self._routing_rules.get(task_type)

        # Use rule settings or provided values
        if rule:
            if required_capabilities is None:
                required_capabilities = rule.required_capabilities
            if preferred_model is None:
                preferred_model = rule.preferred_model
            if strategy is None:
                strategy = rule.strategy
            if complexity_score is None:
                complexity_score = rule.complexity_threshold
        else:
            required_capabilities = required_capabilities or []
            strategy = strategy or RoutingStrategy.PROGRESSIVE
            complexity_score = complexity_score or 0.5

        # Find suitable models
        candidates = self.registry.find_models_for_task(
            required_capabilities=required_capabilities,
            exclude_models=set(exclude_models),
        )

        if not candidates:
            # Fall back to any available model
            candidates = self.registry.get_available_models()
            if not candidates:
                logger.error("[RoutingEngine] No available models found")
                return RoutingDecision(
                    model_id="",
                    task_type=task_type,
                    complexity_score=complexity_score,
                    strategy_used=strategy,
                    fallback_position=0,
                    reasoning="No available models found",
                    alternatives=[],
                )

        # Apply routing strategy
        if strategy == RoutingStrategy.BEST_FIRST:
            selected = self._select_best_model(candidates, required_capabilities)
        elif strategy == RoutingStrategy.CHEAP_FIRST:
            selected = self._select_cheapest_model(candidates)
        elif strategy == RoutingStrategy.CAPABILITY_MATCH:
            selected = self._select_by_capability(candidates, required_capabilities)
        else:  # PROGRESSIVE or default
            selected = self._select_progressive(candidates, complexity_score)

        # Check if preferred model is in candidates
        if preferred_model and preferred_model not in exclude_models:
            preferred = self.registry.get_model(preferred_model)
            if preferred and preferred.is_available():
                selected = preferred

        # Get alternatives
        alternatives = [m.model_id for m in candidates if m.model_id != selected.model_id][:5]

        reasoning = (
            f"Selected {selected.model_id} using {strategy.value} strategy. "
            f"Complexity: {complexity_score:.2f}, "
            f"Required capabilities: {required_capabilities}"
        )

        return RoutingDecision(
            model_id=selected.model_id,
            task_type=task_type,
            complexity_score=complexity_score,
            strategy_used=strategy,
            fallback_position=0,
            reasoning=reasoning,
            alternatives=alternatives,
        )

    def _select_best_model(
        self, candidates: List[ModelInfo], required_capabilities: List[str]
    ) -> ModelInfo:
        """Select the best model based on benchmark scores."""
        if not candidates:
            raise ValueError("No candidates provided")

        # Sort by weighted benchmark score
        def score_key(m: ModelInfo) -> float:
            return m.capabilities.weighted_score()

        return max(candidates, key=score_key)

    def _select_cheapest_model(self, candidates: List[ModelInfo]) -> ModelInfo:
        """Select the cheapest suitable model."""
        if not candidates:
            raise ValueError("No candidates provided")

        # Sort by cost (input + output tokens)
        def cost_key(m: ModelInfo) -> float:
            return m.cost.cost_per_1k_input_tokens + m.cost.cost_per_1k_output_tokens

        return min(candidates, key=cost_key)

    def _select_by_capability(
        self, candidates: List[ModelInfo], required_capabilities: List[str]
    ) -> ModelInfo:
        """Select model with best capability match."""
        if not candidates:
            raise ValueError("No candidates provided")

        def capability_score(m: ModelInfo) -> int:
            return sum(1 for cap in required_capabilities if m.capabilities.has_capability(cap))

        return max(candidates, key=capability_score)

    def _select_progressive(
        self, candidates: List[ModelInfo], complexity_score: float
    ) -> ModelInfo:
        """Select model based on complexity-matched progression."""
        if not candidates:
            raise ValueError("No candidates provided")

        # Map complexity to tier preference
        if complexity_score <= 0.3:
            preferred_tier = ModelTier.ECONOMY
        elif complexity_score <= 0.7:
            preferred_tier = ModelTier.STANDARD
        else:
            preferred_tier = ModelTier.PREMIUM

        # Find best match for preferred tier
        tier_candidates = [m for m in candidates if m.tier == preferred_tier]
        if tier_candidates:
            return max(tier_candidates, key=lambda m: m.capabilities.weighted_score())

        # Fall back to any available
        return max(candidates, key=lambda m: m.capabilities.weighted_score())

    def create_fallback_chain(
        self,
        primary_model: str,
        task_type: str,
        chain_id: Optional[str] = None,
    ) -> FallbackChain:
        """Create a fallback chain for a task.

        Args:
            primary_model: Primary model ID.
            task_type: Task type for fallback configuration.
            chain_id: Optional chain identifier for tracking.

        Returns:
            FallbackChain with models ordered by preference.
        """
        # Get fallback chain from routing rule
        rule = self._routing_rules.get(task_type)
        if rule and rule.fallback_chain:
            chain_models = [primary_model] if primary_model not in rule.fallback_chain else []
            chain_models.extend(rule.fallback_chain)
        else:
            # Build chain from registry fallbacks
            chain_models = self.registry.get_fallback_chain(primary_model)

        fallback_config = self._config.get("fallback", {})
        max_retries = fallback_config.get("max_retries", 3)

        chain = FallbackChain(
            models=chain_models,
            max_retries_per_model=max_retries,
        )

        if chain_id:
            self._active_chains[chain_id] = chain

        return chain

    def get_fallback_chain(self, chain_id: str) -> Optional[FallbackChain]:
        """Get an active fallback chain by ID.

        Args:
            chain_id: Chain identifier.

        Returns:
            FallbackChain or None if not found.
        """
        return self._active_chains.get(chain_id)

    def handle_failure(
        self,
        chain_id: str,
        trigger: FallbackTrigger,
        error_message: str,
    ) -> Optional[str]:
        """Handle a model failure and get next fallback.

        Args:
            chain_id: Chain identifier.
            trigger: Failure trigger type.
            error_message: Error message.

        Returns:
            Next model ID or None if no more fallbacks.
        """
        chain = self._active_chains.get(chain_id)
        if chain is None:
            logger.warning(f"[RoutingEngine] Chain not found: {chain_id}")
            return None

        current_model = chain.get_current_model()
        if current_model:
            chain.record_attempt(current_model)
            self.registry.record_failure(current_model, error_message)

            # Check if we should retry or fallback
            if trigger in [FallbackTrigger.RATE_LIMIT, FallbackTrigger.SERVER_ERROR]:
                if chain.should_retry(current_model):
                    logger.info(f"[RoutingEngine] Retrying {current_model} after {trigger.value}")
                    return current_model

        # Advance to next fallback
        next_model = chain.advance()
        if next_model:
            logger.info(
                f"[RoutingEngine] Falling back from {current_model} to {next_model} "
                f"(trigger: {trigger.value})"
            )
        else:
            logger.warning(f"[RoutingEngine] No more fallbacks for chain {chain_id}")

        return next_model

    async def execute_with_fallback(
        self,
        task_type: str,
        model_call: Callable[..., Any],
        chain_id: Optional[str] = None,
        max_attempts: int = 5,
        **call_kwargs: Any,
    ) -> Tuple[Any, RoutingDecision]:
        """Execute a model call with automatic fallback.

        Args:
            task_type: Task type for routing.
            model_call: Async callable to invoke model.
            chain_id: Optional chain identifier.
            max_attempts: Maximum total attempts.
            **call_kwargs: Arguments to pass to model_call.

        Returns:
            Tuple of (result, routing_decision).

        Raises:
            Exception: If all attempts fail.
        """
        import asyncio

        # Get initial routing decision
        decision = self.select_model(task_type)
        if not decision.model_id:
            raise ValueError(f"No suitable model found for task type: {task_type}")

        # Create fallback chain
        chain_id = chain_id or f"chain_{int(time.time() * 1000)}"
        chain = self.create_fallback_chain(decision.model_id, task_type, chain_id)

        attempts = 0
        last_error = None

        while attempts < max_attempts:
            current_model = chain.get_current_model()
            if current_model is None:
                break

            attempts += 1
            start_time = time.time()

            try:
                # Execute the call
                result = await model_call(model_id=current_model, **call_kwargs)

                # Record success
                latency_ms = (time.time() - start_time) * 1000
                self.registry.record_success(current_model, latency_ms)

                # Update decision with actual model used
                decision = RoutingDecision(
                    model_id=current_model,
                    task_type=task_type,
                    complexity_score=decision.complexity_score,
                    strategy_used=decision.strategy_used,
                    fallback_position=chain.current_index,
                    reasoning=f"Succeeded on attempt {attempts}",
                    alternatives=decision.alternatives,
                    metadata={"attempts": attempts, "latency_ms": latency_ms},
                )

                return result, decision

            except asyncio.TimeoutError as e:
                last_error = e
                next_model = self.handle_failure(chain_id, FallbackTrigger.TIMEOUT, str(e))
                if next_model is None:
                    break

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                if "rate limit" in error_str:
                    trigger = FallbackTrigger.RATE_LIMIT
                elif "server" in error_str or "500" in error_str:
                    trigger = FallbackTrigger.SERVER_ERROR
                else:
                    trigger = FallbackTrigger.EXPLICIT

                next_model = self.handle_failure(chain_id, trigger, str(e))
                if next_model is None:
                    break

        # All attempts failed
        raise Exception(f"All attempts failed for task type {task_type}. Last error: {last_error}")

    def get_routing_stats(self) -> Dict[str, Any]:
        """Get routing statistics.

        Returns:
            Dictionary with routing metrics.
        """
        return {
            "registered_models": self.registry.model_count,
            "available_models": len(self.registry.get_available_models()),
            "routing_rules": len(self._routing_rules),
            "active_chains": len(self._active_chains),
            "model_health": self.registry.get_health_summary(),
        }

    def cleanup_chains(self, max_age_seconds: int = 3600) -> int:
        """Clean up old fallback chains.

        Args:
            max_age_seconds: Maximum age for chains to keep.

        Returns:
            Number of chains removed.
        """
        # For simplicity, just clear all chains
        # In production, you'd track creation time
        count = len(self._active_chains)
        self._active_chains.clear()
        return count


# Singleton instance
_engine: Optional[RoutingEngine] = None


def get_routing_engine(config_path: str = "config/llm_validation.yaml") -> RoutingEngine:
    """Get or create the singleton RoutingEngine instance.

    Args:
        config_path: Path to configuration file.

    Returns:
        RoutingEngine singleton instance.
    """
    global _engine
    if _engine is None:
        _engine = RoutingEngine(config_path=config_path)
    return _engine
