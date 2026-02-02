"""Tests for LLM routing engine.

Part of IMP-LLM-001: LLM Model Validation & Routing System.
"""

import pytest

from autopack.llm.model_registry import (
    ModelCapabilities,
    ModelCost,
    ModelInfo,
    ModelLimits,
    ModelRegistry,
    ModelTier,
)
from autopack.llm.routing_engine import (
    ComplexityEstimate,
    FallbackChain,
    FallbackTrigger,
    RoutingDecision,
    RoutingEngine,
    RoutingRule,
    RoutingStrategy,
)


class TestRoutingRule:
    """Tests for RoutingRule class."""

    def test_from_dict(self):
        """Test creating rule from dictionary."""
        data = {
            "task_type": "code_generation",
            "description": "Generate code",
            "preferred_model": "claude-sonnet-4-5",
            "complexity_threshold": 0.7,
            "required_capabilities": ["coding", "reasoning"],
            "fallback_chain": ["claude-sonnet-4-5", "gpt-4o"],
            "strategy": "progressive",
        }
        rule = RoutingRule.from_dict(data)
        assert rule.task_type == "code_generation"
        assert rule.preferred_model == "claude-sonnet-4-5"
        assert rule.complexity_threshold == 0.7
        assert rule.required_capabilities == ["coding", "reasoning"]
        assert rule.strategy == RoutingStrategy.PROGRESSIVE

    def test_from_dict_defaults(self):
        """Test creating rule with default values."""
        data = {"task_type": "test"}
        rule = RoutingRule.from_dict(data)
        assert rule.complexity_threshold == 0.5
        assert rule.required_capabilities == []
        assert rule.strategy == RoutingStrategy.PROGRESSIVE


class TestFallbackChain:
    """Tests for FallbackChain class."""

    def test_get_current_model(self):
        """Test getting current model."""
        chain = FallbackChain(models=["model-1", "model-2", "model-3"])
        assert chain.get_current_model() == "model-1"

    def test_advance(self):
        """Test advancing through the chain."""
        chain = FallbackChain(models=["model-1", "model-2", "model-3"])
        assert chain.advance() == "model-2"
        assert chain.advance() == "model-3"
        assert chain.advance() is None

    def test_should_retry(self):
        """Test retry checking."""
        chain = FallbackChain(models=["model-1"], max_retries_per_model=2)
        assert chain.should_retry("model-1")
        chain.record_attempt("model-1")
        assert chain.should_retry("model-1")
        chain.record_attempt("model-1")
        assert not chain.should_retry("model-1")

    def test_has_more_fallbacks(self):
        """Test checking for more fallbacks."""
        chain = FallbackChain(models=["model-1", "model-2"])
        assert chain.has_more_fallbacks()
        chain.advance()
        assert not chain.has_more_fallbacks()

    def test_reset(self):
        """Test resetting the chain."""
        chain = FallbackChain(models=["model-1", "model-2"])
        chain.advance()
        chain.record_attempt("model-1")
        chain.reset()
        assert chain.current_index == 0
        assert chain.retry_counts == {}


class TestRoutingDecision:
    """Tests for RoutingDecision class."""

    def test_is_fallback(self):
        """Test fallback detection."""
        decision1 = RoutingDecision(
            model_id="model-1",
            task_type="test",
            complexity_score=0.5,
            strategy_used=RoutingStrategy.PROGRESSIVE,
            fallback_position=0,
            reasoning="Primary selection",
            alternatives=[],
        )
        assert not decision1.is_fallback

        decision2 = RoutingDecision(
            model_id="model-2",
            task_type="test",
            complexity_score=0.5,
            strategy_used=RoutingStrategy.PROGRESSIVE,
            fallback_position=1,
            reasoning="Fallback selection",
            alternatives=[],
        )
        assert decision2.is_fallback


class TestRoutingEngine:
    """Tests for RoutingEngine class."""

    @pytest.fixture
    def registry(self):
        """Create a test registry with models."""
        reg = ModelRegistry.__new__(ModelRegistry)
        reg._models = {}
        reg._providers = set()
        reg._config = {}
        reg._config_path = "test"

        # Add test models
        models = [
            ModelInfo(
                model_id="claude-opus-4-5",
                provider="anthropic",
                display_name="Claude Opus 4.5",
                tier=ModelTier.PREMIUM,
                capabilities=ModelCapabilities(
                    capabilities=("reasoning", "coding", "analysis"),
                    benchmark_scores={"reasoning": 0.95, "coding": 0.92},
                ),
                cost=ModelCost(0.015, 0.075),
                limits=ModelLimits(200000, 32000),
                fallback_model_id="claude-sonnet-4-5",
            ),
            ModelInfo(
                model_id="claude-sonnet-4-5",
                provider="anthropic",
                display_name="Claude Sonnet 4.5",
                tier=ModelTier.STANDARD,
                capabilities=ModelCapabilities(
                    capabilities=("reasoning", "coding", "fast_response"),
                    benchmark_scores={"reasoning": 0.88, "coding": 0.90},
                ),
                cost=ModelCost(0.003, 0.015),
                limits=ModelLimits(200000, 16000),
                fallback_model_id="claude-3-haiku-20240307",
            ),
            ModelInfo(
                model_id="claude-3-haiku-20240307",
                provider="anthropic",
                display_name="Claude 3 Haiku",
                tier=ModelTier.ECONOMY,
                capabilities=ModelCapabilities(
                    capabilities=("fast_response", "simple_tasks"),
                    benchmark_scores={"reasoning": 0.72, "speed": 0.98},
                ),
                cost=ModelCost(0.00025, 0.00125),
                limits=ModelLimits(200000, 4096),
            ),
        ]
        for model in models:
            reg.register_model(model)

        return reg

    @pytest.fixture
    def engine(self, registry):
        """Create a test routing engine."""
        eng = RoutingEngine.__new__(RoutingEngine)
        eng.registry = registry
        eng.validator = None
        eng._config = {
            "routing_rules": [
                {
                    "task_type": "code_generation",
                    "description": "Code generation",
                    "preferred_model": "claude-sonnet-4-5",
                    "complexity_threshold": 0.7,
                    "required_capabilities": ["coding"],
                    "fallback_chain": ["claude-sonnet-4-5", "claude-opus-4-5"],
                },
                {
                    "task_type": "quick_response",
                    "description": "Quick responses",
                    "preferred_model": "claude-3-haiku-20240307",
                    "complexity_threshold": 0.3,
                    "required_capabilities": ["fast_response"],
                    "fallback_chain": ["claude-3-haiku-20240307", "claude-sonnet-4-5"],
                },
            ],
            "complexity_estimation": {
                "token_thresholds": {"simple": 1000, "moderate": 5000, "complex": 20000},
                "task_multipliers": {"code_generation": 1.5, "quick_response": 0.5},
            },
            "fallback": {"max_retries": 3},
        }
        eng._routing_rules = eng._load_routing_rules()
        eng._active_chains = {}
        return eng

    def test_estimate_complexity_simple(self, engine):
        """Test simple complexity estimation."""
        estimate = engine.estimate_complexity("quick_response", token_count=500)
        assert estimate.score < 0.3
        assert estimate.recommended_tier == ModelTier.ECONOMY

    def test_estimate_complexity_moderate(self, engine):
        """Test moderate complexity estimation."""
        estimate = engine.estimate_complexity("code_generation", token_count=3000)
        # With task_multiplier 1.5 for code_generation: 0.5 * 1.5 = 0.75
        assert 0.3 <= estimate.score <= 0.85
        assert estimate.recommended_tier in [ModelTier.STANDARD, ModelTier.PREMIUM]

    def test_estimate_complexity_complex(self, engine):
        """Test complex task estimation."""
        estimate = engine.estimate_complexity("code_generation", token_count=15000)
        assert estimate.score > 0.7
        assert estimate.recommended_tier in [ModelTier.STANDARD, ModelTier.PREMIUM]

    def test_select_model_with_rule(self, engine):
        """Test model selection with routing rule."""
        decision = engine.select_model("code_generation")
        assert decision.model_id in ["claude-sonnet-4-5", "claude-opus-4-5"]
        assert decision.task_type == "code_generation"
        assert decision.strategy_used == RoutingStrategy.PROGRESSIVE

    def test_select_model_cheap_first(self, engine):
        """Test cheap-first model selection."""
        decision = engine.select_model(
            "unknown_task",
            strategy=RoutingStrategy.CHEAP_FIRST,
        )
        # Should select cheapest model
        assert decision.model_id == "claude-3-haiku-20240307"

    def test_select_model_best_first(self, engine):
        """Test best-first model selection."""
        decision = engine.select_model(
            "unknown_task",
            strategy=RoutingStrategy.BEST_FIRST,
            required_capabilities=["coding"],
        )
        # Should select best model with coding capability
        assert decision.model_id in ["claude-opus-4-5", "claude-sonnet-4-5"]

    def test_select_model_with_exclusions(self, engine):
        """Test model selection with exclusions."""
        decision = engine.select_model(
            "code_generation",
            exclude_models=["claude-sonnet-4-5"],
        )
        assert decision.model_id != "claude-sonnet-4-5"

    def test_create_fallback_chain(self, engine):
        """Test fallback chain creation."""
        chain = engine.create_fallback_chain(
            "claude-sonnet-4-5",
            "code_generation",
            chain_id="test-chain",
        )
        assert chain.models[0] == "claude-sonnet-4-5"
        assert len(chain.models) >= 1
        assert engine.get_fallback_chain("test-chain") == chain

    def test_handle_failure_retry(self, engine):
        """Test handling failure with retry."""
        engine.create_fallback_chain(
            "claude-sonnet-4-5",
            "code_generation",
            chain_id="retry-chain",
        )
        next_model = engine.handle_failure(
            "retry-chain",
            FallbackTrigger.RATE_LIMIT,
            "Rate limit exceeded",
        )
        # Should retry same model first
        assert next_model == "claude-sonnet-4-5"

    def test_handle_failure_fallback(self, engine):
        """Test handling failure with fallback."""
        chain = engine.create_fallback_chain(
            "claude-sonnet-4-5",
            "code_generation",
            chain_id="fallback-chain",
        )
        # Exhaust retries
        for _ in range(4):
            engine.handle_failure(
                "fallback-chain",
                FallbackTrigger.RATE_LIMIT,
                "Rate limit exceeded",
            )
        # Should fall back to next model
        next_model = chain.get_current_model()
        assert next_model != "claude-sonnet-4-5" or next_model is None

    def test_get_routing_stats(self, engine):
        """Test getting routing statistics."""
        stats = engine.get_routing_stats()
        assert "registered_models" in stats
        assert "available_models" in stats
        assert "routing_rules" in stats
        assert stats["registered_models"] == 3
        assert stats["routing_rules"] == 2

    def test_cleanup_chains(self, engine):
        """Test cleaning up old chains."""
        engine.create_fallback_chain("model-1", "test", "chain-1")
        engine.create_fallback_chain("model-2", "test", "chain-2")
        assert len(engine._active_chains) == 2

        removed = engine.cleanup_chains()
        assert removed == 2
        assert len(engine._active_chains) == 0


class TestComplexityEstimate:
    """Tests for ComplexityEstimate class."""

    def test_attributes(self):
        """Test complexity estimate attributes."""
        estimate = ComplexityEstimate(
            score=0.75,
            factors={"token_score": 0.8, "task_multiplier": 1.0},
            recommended_tier=ModelTier.PREMIUM,
            reasoning="High complexity task",
        )
        assert estimate.score == 0.75
        assert estimate.recommended_tier == ModelTier.PREMIUM
        assert "token_score" in estimate.factors
