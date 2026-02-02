"""LLM Model Registry with capability metadata and health tracking.

This module provides a central registry for all available LLM models,
including their capabilities, costs, and fallback configurations.

Part of IMP-LLM-001: LLM Model Validation & Routing System.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

logger = logging.getLogger(__name__)


class ModelTier(Enum):
    """Model pricing/capability tiers."""

    PREMIUM = "premium"
    STANDARD = "standard"
    ECONOMY = "economy"


class ModelStatus(Enum):
    """Model health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ModelCapabilities:
    """Model capability metadata."""

    capabilities: tuple[str, ...]
    benchmark_scores: Dict[str, float]

    def has_capability(self, capability: str) -> bool:
        """Check if model has a specific capability."""
        return capability in self.capabilities

    def has_all_capabilities(self, required: List[str]) -> bool:
        """Check if model has all required capabilities."""
        return all(cap in self.capabilities for cap in required)

    def get_benchmark_score(self, benchmark: str) -> float:
        """Get benchmark score for a specific test."""
        return self.benchmark_scores.get(benchmark, 0.0)

    def weighted_score(self, weights: Optional[Dict[str, float]] = None) -> float:
        """Calculate weighted average of benchmark scores."""
        if not self.benchmark_scores:
            return 0.0

        if weights is None:
            # Default equal weighting
            return sum(self.benchmark_scores.values()) / len(self.benchmark_scores)

        total_weight = sum(weights.get(k, 0.0) for k in self.benchmark_scores)
        if total_weight == 0:
            return 0.0

        weighted_sum = sum(
            score * weights.get(name, 0.0) for name, score in self.benchmark_scores.items()
        )
        return weighted_sum / total_weight


@dataclass
class ModelCost:
    """Model cost information."""

    cost_per_1k_input_tokens: float
    cost_per_1k_output_tokens: float

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate total cost for a request."""
        input_cost = (input_tokens / 1000) * self.cost_per_1k_input_tokens
        output_cost = (output_tokens / 1000) * self.cost_per_1k_output_tokens
        return input_cost + output_cost


@dataclass
class ModelLimits:
    """Model token limits."""

    max_tokens: int
    max_output_tokens: int

    def can_handle_context(self, token_count: int) -> bool:
        """Check if model can handle the given context size."""
        return token_count <= self.max_tokens

    def get_available_output_tokens(self, input_tokens: int) -> int:
        """Get available output tokens given input size."""
        remaining = self.max_tokens - input_tokens
        return min(remaining, self.max_output_tokens)


@dataclass
class ModelHealth:
    """Model health tracking."""

    status: ModelStatus = ModelStatus.UNKNOWN
    last_check: Optional[datetime] = None
    consecutive_failures: int = 0
    success_rate: float = 1.0
    average_latency_ms: float = 0.0
    last_error: Optional[str] = None

    def record_success(self, latency_ms: float) -> None:
        """Record a successful request."""
        self.consecutive_failures = 0
        self.status = ModelStatus.HEALTHY
        self.last_check = datetime.now(timezone.utc)
        # Exponential moving average for latency
        alpha = 0.2
        if self.average_latency_ms == 0:
            self.average_latency_ms = latency_ms
        else:
            self.average_latency_ms = alpha * latency_ms + (1 - alpha) * self.average_latency_ms
        # Update success rate
        self.success_rate = min(1.0, self.success_rate * 0.99 + 0.01)

    def record_failure(self, error: str) -> None:
        """Record a failed request."""
        self.consecutive_failures += 1
        self.last_check = datetime.now(timezone.utc)
        self.last_error = error
        # Update success rate
        self.success_rate = max(0.0, self.success_rate * 0.99)
        # Update status based on consecutive failures
        if self.consecutive_failures >= 3:
            self.status = ModelStatus.UNHEALTHY
        elif self.consecutive_failures >= 1:
            self.status = ModelStatus.DEGRADED

    def is_available(self) -> bool:
        """Check if model is available for use."""
        return self.status != ModelStatus.UNHEALTHY


@dataclass
class ModelInfo:
    """Complete model information."""

    model_id: str
    provider: str
    display_name: str
    tier: ModelTier
    capabilities: ModelCapabilities
    cost: ModelCost
    limits: ModelLimits
    fallback_model_id: Optional[str] = None
    health: ModelHealth = field(default_factory=ModelHealth)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_available(self) -> bool:
        """Check if model is available for use."""
        return self.health.is_available()

    def can_handle_task(self, required_capabilities: List[str], token_count: int = 0) -> bool:
        """Check if model can handle a specific task."""
        if not self.is_available():
            return False
        if not self.capabilities.has_all_capabilities(required_capabilities):
            return False
        if token_count > 0 and not self.limits.can_handle_context(token_count):
            return False
        return True


class ModelRegistry:
    """Central registry for LLM models.

    Provides:
    - Model registration and lookup
    - Capability-based model discovery
    - Health tracking and fallback management
    - Cost estimation
    """

    def __init__(self, config_path: str = "config/llm_validation.yaml"):
        """Initialize the model registry.

        Args:
            config_path: Path to LLM validation configuration file.
        """
        self._models: Dict[str, ModelInfo] = {}
        self._providers: Set[str] = set()
        self._config: Dict[str, Any] = {}
        self._config_path = config_path

        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        config_file = Path(self._config_path)
        if not config_file.is_absolute():
            # Resolve relative to repo root
            repo_root = Path(__file__).resolve().parents[3]
            config_file = repo_root / self._config_path

        if not config_file.exists():
            logger.warning(f"[ModelRegistry] Config file not found: {config_file}")
            return

        try:
            self._config = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
            self._register_models_from_config()
            logger.info(f"[ModelRegistry] Loaded {len(self._models)} models from config")
        except Exception as e:
            logger.error(f"[ModelRegistry] Failed to load config: {e}")

    def _register_models_from_config(self) -> None:
        """Register models from configuration."""
        models_config = self._config.get("models", {})

        for model_id, model_data in models_config.items():
            try:
                self._register_model_from_dict(model_id, model_data)
            except Exception as e:
                logger.warning(f"[ModelRegistry] Failed to register model {model_id}: {e}")

    def _register_model_from_dict(self, model_id: str, data: Dict[str, Any]) -> None:
        """Register a model from dictionary configuration."""
        tier_str = data.get("tier", "standard").lower()
        tier = (
            ModelTier(tier_str) if tier_str in [t.value for t in ModelTier] else ModelTier.STANDARD
        )

        capabilities = ModelCapabilities(
            capabilities=tuple(data.get("capabilities", [])),
            benchmark_scores=dict(data.get("benchmark_scores", {})),
        )

        cost = ModelCost(
            cost_per_1k_input_tokens=data.get("cost_per_1k_input_tokens", 0.0),
            cost_per_1k_output_tokens=data.get("cost_per_1k_output_tokens", 0.0),
        )

        limits = ModelLimits(
            max_tokens=data.get("max_tokens", 100000),
            max_output_tokens=data.get("max_output_tokens", 4096),
        )

        model_info = ModelInfo(
            model_id=model_id,
            provider=data.get("provider", "unknown"),
            display_name=data.get("display_name", model_id),
            tier=tier,
            capabilities=capabilities,
            cost=cost,
            limits=limits,
            fallback_model_id=data.get("fallback"),
            metadata=data.get("metadata", {}),
        )

        self.register_model(model_info)

    def register_model(self, model: ModelInfo) -> None:
        """Register a model in the registry.

        Args:
            model: Model information to register.
        """
        self._models[model.model_id] = model
        self._providers.add(model.provider)
        logger.debug(f"[ModelRegistry] Registered model: {model.model_id}")

    def get_model(self, model_id: str) -> Optional[ModelInfo]:
        """Get model information by ID.

        Args:
            model_id: Model identifier.

        Returns:
            ModelInfo or None if not found.
        """
        return self._models.get(model_id)

    def get_all_models(self) -> List[ModelInfo]:
        """Get all registered models.

        Returns:
            List of all registered models.
        """
        return list(self._models.values())

    def get_models_by_provider(self, provider: str) -> List[ModelInfo]:
        """Get all models from a specific provider.

        Args:
            provider: Provider name (e.g., 'anthropic', 'openai').

        Returns:
            List of models from the provider.
        """
        return [m for m in self._models.values() if m.provider == provider]

    def get_models_by_tier(self, tier: ModelTier) -> List[ModelInfo]:
        """Get all models in a specific tier.

        Args:
            tier: Model tier to filter by.

        Returns:
            List of models in the tier.
        """
        return [m for m in self._models.values() if m.tier == tier]

    def get_models_with_capability(self, capability: str) -> List[ModelInfo]:
        """Get all models with a specific capability.

        Args:
            capability: Required capability.

        Returns:
            List of models with the capability.
        """
        return [m for m in self._models.values() if m.capabilities.has_capability(capability)]

    def get_available_models(self) -> List[ModelInfo]:
        """Get all healthy/available models.

        Returns:
            List of available models.
        """
        return [m for m in self._models.values() if m.is_available()]

    def find_models_for_task(
        self,
        required_capabilities: List[str],
        token_count: int = 0,
        preferred_tier: Optional[ModelTier] = None,
        exclude_models: Optional[Set[str]] = None,
    ) -> List[ModelInfo]:
        """Find models suitable for a specific task.

        Args:
            required_capabilities: List of required capabilities.
            token_count: Estimated token count for the task.
            preferred_tier: Preferred model tier.
            exclude_models: Models to exclude from results.

        Returns:
            List of suitable models, sorted by relevance.
        """
        exclude_models = exclude_models or set()
        candidates = []

        for model in self._models.values():
            if model.model_id in exclude_models:
                continue
            if not model.can_handle_task(required_capabilities, token_count):
                continue
            candidates.append(model)

        # Sort by tier preference and benchmark scores
        def sort_key(m: ModelInfo) -> tuple:
            tier_score = 0
            if preferred_tier:
                if m.tier == preferred_tier:
                    tier_score = 2
                elif m.tier == ModelTier.STANDARD:
                    tier_score = 1
            else:
                # Default: prefer standard tier
                tier_scores = {ModelTier.STANDARD: 2, ModelTier.PREMIUM: 1, ModelTier.ECONOMY: 0}
                tier_score = tier_scores.get(m.tier, 0)

            benchmark_score = m.capabilities.weighted_score()
            return (tier_score, benchmark_score)

        candidates.sort(key=sort_key, reverse=True)
        return candidates

    def get_fallback_chain(self, model_id: str, max_depth: int = 5) -> List[str]:
        """Get the fallback chain for a model.

        Args:
            model_id: Starting model ID.
            max_depth: Maximum chain depth to prevent cycles.

        Returns:
            List of model IDs in the fallback chain.
        """
        chain = []
        current_id = model_id
        visited = set()

        while current_id and len(chain) < max_depth:
            if current_id in visited:
                break  # Prevent cycles
            visited.add(current_id)

            model = self.get_model(current_id)
            if model is None:
                break

            chain.append(current_id)
            current_id = model.fallback_model_id

        return chain

    def get_next_fallback(self, model_id: str) -> Optional[str]:
        """Get the next fallback model for a given model.

        Args:
            model_id: Current model ID.

        Returns:
            Fallback model ID or None if no fallback.
        """
        model = self.get_model(model_id)
        if model and model.fallback_model_id:
            return model.fallback_model_id
        return None

    def record_success(self, model_id: str, latency_ms: float) -> None:
        """Record a successful model request.

        Args:
            model_id: Model that was used.
            latency_ms: Request latency in milliseconds.
        """
        model = self.get_model(model_id)
        if model:
            model.health.record_success(latency_ms)

    def record_failure(self, model_id: str, error: str) -> None:
        """Record a failed model request.

        Args:
            model_id: Model that failed.
            error: Error description.
        """
        model = self.get_model(model_id)
        if model:
            model.health.record_failure(error)
            logger.warning(
                f"[ModelRegistry] Model {model_id} failure recorded: {error} "
                f"(consecutive failures: {model.health.consecutive_failures})"
            )

    def estimate_cost(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate the cost for a request.

        Args:
            model_id: Model to use.
            input_tokens: Estimated input token count.
            output_tokens: Estimated output token count.

        Returns:
            Estimated cost in USD.
        """
        model = self.get_model(model_id)
        if model:
            return model.cost.estimate_cost(input_tokens, output_tokens)
        return 0.0

    def get_health_summary(self) -> Dict[str, Any]:
        """Get health summary for all models.

        Returns:
            Dictionary with health information for each model.
        """
        summary = {}
        for model_id, model in self._models.items():
            summary[model_id] = {
                "status": model.health.status.value,
                "success_rate": model.health.success_rate,
                "average_latency_ms": model.health.average_latency_ms,
                "consecutive_failures": model.health.consecutive_failures,
                "last_check": (
                    model.health.last_check.isoformat() if model.health.last_check else None
                ),
            }
        return summary

    def reset_health(self, model_id: Optional[str] = None) -> None:
        """Reset health tracking for model(s).

        Args:
            model_id: Specific model to reset, or None for all models.
        """
        if model_id:
            model = self.get_model(model_id)
            if model:
                model.health = ModelHealth()
        else:
            for model in self._models.values():
                model.health = ModelHealth()

    @property
    def providers(self) -> Set[str]:
        """Get set of all registered providers."""
        return self._providers.copy()

    @property
    def model_count(self) -> int:
        """Get total number of registered models."""
        return len(self._models)


# Singleton instance
_registry: Optional[ModelRegistry] = None


def get_model_registry(config_path: str = "config/llm_validation.yaml") -> ModelRegistry:
    """Get or create the singleton ModelRegistry instance.

    Args:
        config_path: Path to configuration file.

    Returns:
        ModelRegistry singleton instance.
    """
    global _registry
    if _registry is None:
        _registry = ModelRegistry(config_path)
    return _registry
