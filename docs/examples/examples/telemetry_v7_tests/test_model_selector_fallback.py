"""Unit tests for ModelSelector fallback logic.

Tests cover:
- Tier escalation (tier-1 → tier-2 → tier-3)
- Model unavailable scenarios
- Fallback to cheaper models
- Budget constraints forcing fallback
- Exhausted fallback chains
"""

import pytest
from typing import Optional


class ModelTier:
    """Model tier enumeration."""
    TIER_1 = "tier-1"  # Premium models (GPT-4, Claude-3-Opus)
    TIER_2 = "tier-2"  # Standard models (GPT-3.5-Turbo, Claude-3-Sonnet)
    TIER_3 = "tier-3"  # Budget models (GPT-3.5, Claude-3-Haiku)


class ModelConfig:
    """Model configuration."""
    
    def __init__(self, name: str, tier: str, cost_per_1k: float, available: bool = True):
        self.name = name
        self.tier = tier
        self.cost_per_1k = cost_per_1k
        self.available = available


class ModelSelector:
    """Simplified ModelSelector for testing.
    
    Selects appropriate models based on:
    - Phase complexity and token budget
    - Model availability
    - Cost constraints
    - Fallback tiers
    """
    
    # Model registry with tier and cost information
    MODELS = {
        "gpt-4": ModelConfig("gpt-4", ModelTier.TIER_1, 0.03),
        "claude-3-opus": ModelConfig("claude-3-opus", ModelTier.TIER_1, 0.015),
        "gpt-3.5-turbo": ModelConfig("gpt-3.5-turbo", ModelTier.TIER_2, 0.002),
        "claude-3-sonnet": ModelConfig("claude-3-sonnet", ModelTier.TIER_2, 0.003),
        "gpt-3.5": ModelConfig("gpt-3.5", ModelTier.TIER_3, 0.0015),
        "claude-3-haiku": ModelConfig("claude-3-haiku", ModelTier.TIER_3, 0.00025),
    }
    
    # Tier escalation order
    TIER_ORDER = [ModelTier.TIER_1, ModelTier.TIER_2, ModelTier.TIER_3]
    
    def __init__(self, model_availability: Optional[dict] = None):
        """Initialize ModelSelector.
        
        Args:
            model_availability: Optional dict mapping model names to availability status
        """
        self.model_availability = model_availability or {}
    
    def select_model(
        self,
        complexity: str,
        token_budget: int,
        max_cost_per_1k: Optional[float] = None,
        preferred_tier: Optional[str] = None,
    ) -> Optional[str]:
        """Select appropriate model with fallback logic.
        
        Args:
            complexity: Phase complexity (low/medium/high)
            token_budget: Available token budget
            max_cost_per_1k: Maximum cost per 1K tokens (budget constraint)
            preferred_tier: Preferred tier to start from
            
        Returns:
            Selected model name, or None if no suitable model found
        """
        # Determine starting tier based on complexity
        if preferred_tier:
            start_tier = preferred_tier
        elif complexity == "high":
            start_tier = ModelTier.TIER_1
        elif complexity == "medium":
            start_tier = ModelTier.TIER_2
        else:
            start_tier = ModelTier.TIER_3
        
        # Try tiers in escalation order starting from start_tier
        start_idx = self.TIER_ORDER.index(start_tier)
        
        for tier in self.TIER_ORDER[start_idx:]:
            model = self._select_from_tier(
                tier=tier,
                token_budget=token_budget,
                max_cost_per_1k=max_cost_per_1k,
            )
            if model:
                return model
        
        # No suitable model found
        return None
    
    def _select_from_tier(
        self,
        tier: str,
        token_budget: int,
        max_cost_per_1k: Optional[float] = None,
    ) -> Optional[str]:
        """Select best available model from a specific tier.
        
        Args:
            tier: Model tier to select from
            token_budget: Available token budget
            max_cost_per_1k: Maximum cost per 1K tokens
            
        Returns:
            Selected model name, or None if no suitable model in tier
        """
        # Get models in this tier
        tier_models = [
            (name, config)
            for name, config in self.MODELS.items()
            if config.tier == tier
        ]
        
        # Filter by availability
        available_models = [
            (name, config)
            for name, config in tier_models
            if self._is_available(name)
        ]
        
        if not available_models:
            return None
        
        # Filter by cost constraint if specified
        if max_cost_per_1k is not None:
            available_models = [
                (name, config)
                for name, config in available_models
                if config.cost_per_1k <= max_cost_per_1k
            ]
        
        if not available_models:
            return None
        
        # Select cheapest model in tier
        available_models.sort(key=lambda x: x[1].cost_per_1k)
        return available_models[0][0]
    
    def _is_available(self, model_name: str) -> bool:
        """Check if a model is available.
        
        Args:
            model_name: Name of the model to check
            
        Returns:
            True if model is available, False otherwise
        """
        # Check override availability first
        if model_name in self.model_availability:
            return self.model_availability[model_name]
        
        # Default to model config availability
        return self.MODELS[model_name].available


@pytest.fixture
def selector():
    """Provide a ModelSelector instance with all models available."""
    return ModelSelector()


@pytest.fixture
def selector_with_unavailable_tier1():
    """Provide a ModelSelector with tier-1 models unavailable."""
    return ModelSelector(
        model_availability={
            "gpt-4": False,
            "claude-3-opus": False,
        }
    )


class TestModelSelectorFallback:
    """Test suite for ModelSelector fallback logic."""
    
    def test_tier_escalation_high_complexity(self, selector_with_unavailable_tier1):
        """Test tier escalation from tier-1 to tier-2 when tier-1 unavailable.
        
        High complexity phase should prefer tier-1, but fall back to tier-2
        when tier-1 models are unavailable.
        """
        # High complexity should try tier-1 first, then fall back to tier-2
        model = selector_with_unavailable_tier1.select_model(
            complexity="high",
            token_budget=50000,
        )
        
        # Should select cheapest tier-2 model (gpt-3.5-turbo at 0.002)
        assert model == "gpt-3.5-turbo"
        assert ModelSelector.MODELS[model].tier == ModelTier.TIER_2
    
    def test_tier_escalation_to_tier3(self, selector):
        """Test full tier escalation from tier-1 → tier-2 → tier-3.
        
        When tier-1 and tier-2 are unavailable, should fall back to tier-3.
        """
        # Make tier-1 and tier-2 unavailable
        selector_limited = ModelSelector(
            model_availability={
                "gpt-4": False,
                "claude-3-opus": False,
                "gpt-3.5-turbo": False,
                "claude-3-sonnet": False,
            }
        )
        
        model = selector_limited.select_model(
            complexity="high",
            token_budget=50000,
        )
        
        # Should select cheapest tier-3 model (claude-3-haiku at 0.00025)
        assert model == "claude-3-haiku"
        assert ModelSelector.MODELS[model].tier == ModelTier.TIER_3
    
    def test_model_unavailable_within_tier(self, selector):
        """Test fallback to alternative model within same tier.
        
        When preferred model in tier is unavailable, should select
        alternative model in same tier.
        """
        # Make gpt-4 unavailable but keep claude-3-opus available
        selector_partial = ModelSelector(
            model_availability={
                "gpt-4": False,
            }
        )
        
        model = selector_partial.select_model(
            complexity="high",
            token_budget=50000,
        )
        
        # Should select claude-3-opus (other tier-1 model)
        assert model == "claude-3-opus"
        assert ModelSelector.MODELS[model].tier == ModelTier.TIER_1
    
    def test_fallback_to_cheaper_model_budget_constraint(self, selector):
        """Test fallback to cheaper model when budget constraint applied.
        
        When max_cost_per_1k is specified, should skip expensive models
        and select cheaper alternatives.
        """
        # Set max cost that excludes tier-1 models
        model = selector.select_model(
            complexity="high",
            token_budget=50000,
            max_cost_per_1k=0.005,  # Excludes gpt-4 (0.03) and claude-3-opus (0.015)
        )
        
        # Should fall back to tier-2 (gpt-3.5-turbo at 0.002)
        assert model == "gpt-3.5-turbo"
        assert ModelSelector.MODELS[model].cost_per_1k <= 0.005
    
    def test_fallback_to_cheapest_model_strict_budget(self, selector):
        """Test fallback to cheapest model with very strict budget.
        
        With extremely low max_cost_per_1k, should select the absolute
        cheapest model available.
        """
        # Set very low max cost
        model = selector.select_model(
            complexity="high",
            token_budget=50000,
            max_cost_per_1k=0.001,  # Only claude-3-haiku qualifies (0.00025)
        )
        
        # Should select claude-3-haiku (cheapest at 0.00025)
        assert model == "claude-3-haiku"
        assert ModelSelector.MODELS[model].cost_per_1k == 0.00025
    
    def test_no_suitable_model_all_unavailable(self, selector):
        """Test that None is returned when all models unavailable.
        
        When no models meet availability criteria, should return None.
        """
        # Make all models unavailable
        selector_none = ModelSelector(
            model_availability={
                "gpt-4": False,
                "claude-3-opus": False,
                "gpt-3.5-turbo": False,
                "claude-3-sonnet": False,
                "gpt-3.5": False,
                "claude-3-haiku": False,
            }
        )
        
        model = selector_none.select_model(
            complexity="high",
            token_budget=50000,
        )
        
        # Should return None
        assert model is None
    
    def test_no_suitable_model_budget_too_strict(self, selector):
        """Test that None is returned when budget constraint too strict.
        
        When max_cost_per_1k is lower than all available models,
        should return None.
        """
        # Set max cost lower than cheapest model
        model = selector.select_model(
            complexity="high",
            token_budget=50000,
            max_cost_per_1k=0.0001,  # Lower than claude-3-haiku (0.00025)
        )
        
        # Should return None
        assert model is None
