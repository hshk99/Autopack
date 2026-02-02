"""Tests for LLM model registry.

Part of IMP-LLM-001: LLM Model Validation & Routing System.
"""

import pytest

from autopack.llm.model_registry import (
    ModelCapabilities,
    ModelCost,
    ModelHealth,
    ModelInfo,
    ModelLimits,
    ModelRegistry,
    ModelStatus,
    ModelTier,
)


class TestModelCapabilities:
    """Tests for ModelCapabilities class."""

    def test_has_capability(self):
        """Test capability checking."""
        caps = ModelCapabilities(
            capabilities=("reasoning", "coding", "analysis"),
            benchmark_scores={"reasoning": 0.9, "coding": 0.85},
        )
        assert caps.has_capability("reasoning")
        assert caps.has_capability("coding")
        assert not caps.has_capability("multimodal")

    def test_has_all_capabilities(self):
        """Test checking for all required capabilities."""
        caps = ModelCapabilities(
            capabilities=("reasoning", "coding", "analysis"),
            benchmark_scores={},
        )
        assert caps.has_all_capabilities(["reasoning", "coding"])
        assert caps.has_all_capabilities(["reasoning"])
        assert not caps.has_all_capabilities(["reasoning", "multimodal"])

    def test_get_benchmark_score(self):
        """Test getting benchmark scores."""
        caps = ModelCapabilities(
            capabilities=(),
            benchmark_scores={"reasoning": 0.9, "coding": 0.85},
        )
        assert caps.get_benchmark_score("reasoning") == 0.9
        assert caps.get_benchmark_score("coding") == 0.85
        assert caps.get_benchmark_score("unknown") == 0.0

    def test_weighted_score_default(self):
        """Test weighted score with default weights."""
        caps = ModelCapabilities(
            capabilities=(),
            benchmark_scores={"reasoning": 0.8, "coding": 0.6},
        )
        # Default: equal weighting = (0.8 + 0.6) / 2 = 0.7
        assert caps.weighted_score() == 0.7

    def test_weighted_score_custom_weights(self):
        """Test weighted score with custom weights."""
        caps = ModelCapabilities(
            capabilities=(),
            benchmark_scores={"reasoning": 0.8, "coding": 0.6},
        )
        weights = {"reasoning": 0.7, "coding": 0.3}
        # (0.8 * 0.7 + 0.6 * 0.3) / 1.0 = 0.74
        assert caps.weighted_score(weights) == pytest.approx(0.74)

    def test_weighted_score_empty(self):
        """Test weighted score with empty scores."""
        caps = ModelCapabilities(capabilities=(), benchmark_scores={})
        assert caps.weighted_score() == 0.0


class TestModelCost:
    """Tests for ModelCost class."""

    def test_estimate_cost(self):
        """Test cost estimation."""
        cost = ModelCost(
            cost_per_1k_input_tokens=0.003,
            cost_per_1k_output_tokens=0.015,
        )
        # 1000 input, 500 output
        # (1000/1000) * 0.003 + (500/1000) * 0.015 = 0.003 + 0.0075 = 0.0105
        assert cost.estimate_cost(1000, 500) == pytest.approx(0.0105)

    def test_estimate_cost_zero(self):
        """Test cost estimation with zero tokens."""
        cost = ModelCost(
            cost_per_1k_input_tokens=0.003,
            cost_per_1k_output_tokens=0.015,
        )
        assert cost.estimate_cost(0, 0) == 0.0


class TestModelLimits:
    """Tests for ModelLimits class."""

    def test_can_handle_context(self):
        """Test context size checking."""
        limits = ModelLimits(max_tokens=100000, max_output_tokens=4096)
        assert limits.can_handle_context(50000)
        assert limits.can_handle_context(100000)
        assert not limits.can_handle_context(100001)

    def test_get_available_output_tokens(self):
        """Test available output token calculation."""
        limits = ModelLimits(max_tokens=100000, max_output_tokens=4096)
        # With 50000 input, remaining is 50000, but limited by max_output_tokens
        assert limits.get_available_output_tokens(50000) == 4096
        # With 99000 input, remaining is 1000
        assert limits.get_available_output_tokens(99000) == 1000


class TestModelHealth:
    """Tests for ModelHealth class."""

    def test_initial_state(self):
        """Test initial health state."""
        health = ModelHealth()
        assert health.status == ModelStatus.UNKNOWN
        assert health.consecutive_failures == 0
        assert health.success_rate == 1.0
        assert health.is_available()

    def test_record_success(self):
        """Test recording successful requests."""
        health = ModelHealth()
        health.record_success(100.0)
        assert health.status == ModelStatus.HEALTHY
        assert health.consecutive_failures == 0
        assert health.average_latency_ms == 100.0

    def test_record_failure(self):
        """Test recording failed requests."""
        health = ModelHealth()
        health.record_failure("Rate limit")
        assert health.status == ModelStatus.DEGRADED
        assert health.consecutive_failures == 1
        assert health.last_error == "Rate limit"

    def test_unhealthy_after_failures(self):
        """Test model becomes unhealthy after multiple failures."""
        health = ModelHealth()
        health.record_failure("Error 1")
        health.record_failure("Error 2")
        health.record_failure("Error 3")
        assert health.status == ModelStatus.UNHEALTHY
        assert not health.is_available()

    def test_recovery_after_success(self):
        """Test recovery after success."""
        health = ModelHealth()
        health.record_failure("Error")
        health.record_failure("Error")
        assert health.status == ModelStatus.DEGRADED
        health.record_success(50.0)
        assert health.status == ModelStatus.HEALTHY
        assert health.consecutive_failures == 0


class TestModelInfo:
    """Tests for ModelInfo class."""

    def test_is_available(self):
        """Test availability checking."""
        model = ModelInfo(
            model_id="test-model",
            provider="test",
            display_name="Test Model",
            tier=ModelTier.STANDARD,
            capabilities=ModelCapabilities(capabilities=("coding",), benchmark_scores={}),
            cost=ModelCost(0.001, 0.002),
            limits=ModelLimits(100000, 4096),
        )
        assert model.is_available()
        model.health.record_failure("Error")
        model.health.record_failure("Error")
        model.health.record_failure("Error")
        assert not model.is_available()

    def test_can_handle_task(self):
        """Test task capability checking."""
        model = ModelInfo(
            model_id="test-model",
            provider="test",
            display_name="Test Model",
            tier=ModelTier.STANDARD,
            capabilities=ModelCapabilities(capabilities=("coding", "reasoning"), benchmark_scores={}),
            cost=ModelCost(0.001, 0.002),
            limits=ModelLimits(100000, 4096),
        )
        assert model.can_handle_task(["coding"], 50000)
        assert model.can_handle_task(["coding", "reasoning"], 50000)
        assert not model.can_handle_task(["multimodal"], 50000)
        assert not model.can_handle_task(["coding"], 150000)


class TestModelRegistry:
    """Tests for ModelRegistry class."""

    @pytest.fixture
    def registry(self):
        """Create a test registry without loading config."""
        reg = ModelRegistry.__new__(ModelRegistry)
        reg._models = {}
        reg._providers = set()
        reg._config = {}
        reg._config_path = "test"
        return reg

    def test_register_model(self, registry):
        """Test model registration."""
        model = ModelInfo(
            model_id="test-model",
            provider="test",
            display_name="Test Model",
            tier=ModelTier.STANDARD,
            capabilities=ModelCapabilities(capabilities=("coding",), benchmark_scores={}),
            cost=ModelCost(0.001, 0.002),
            limits=ModelLimits(100000, 4096),
        )
        registry.register_model(model)
        assert registry.get_model("test-model") == model
        assert "test" in registry.providers
        assert registry.model_count == 1

    def test_get_models_by_provider(self, registry):
        """Test filtering models by provider."""
        for i, provider in enumerate(["anthropic", "anthropic", "openai"]):
            model = ModelInfo(
                model_id=f"model-{i}",
                provider=provider,
                display_name=f"Model {i}",
                tier=ModelTier.STANDARD,
                capabilities=ModelCapabilities(capabilities=(), benchmark_scores={}),
                cost=ModelCost(0.001, 0.002),
                limits=ModelLimits(100000, 4096),
            )
            registry.register_model(model)

        anthropic_models = registry.get_models_by_provider("anthropic")
        assert len(anthropic_models) == 2

        openai_models = registry.get_models_by_provider("openai")
        assert len(openai_models) == 1

    def test_get_models_by_tier(self, registry):
        """Test filtering models by tier."""
        for tier in [ModelTier.ECONOMY, ModelTier.STANDARD, ModelTier.PREMIUM]:
            model = ModelInfo(
                model_id=f"model-{tier.value}",
                provider="test",
                display_name=f"Model {tier.value}",
                tier=tier,
                capabilities=ModelCapabilities(capabilities=(), benchmark_scores={}),
                cost=ModelCost(0.001, 0.002),
                limits=ModelLimits(100000, 4096),
            )
            registry.register_model(model)

        standard_models = registry.get_models_by_tier(ModelTier.STANDARD)
        assert len(standard_models) == 1

    def test_get_models_with_capability(self, registry):
        """Test filtering models by capability."""
        model1 = ModelInfo(
            model_id="model-1",
            provider="test",
            display_name="Model 1",
            tier=ModelTier.STANDARD,
            capabilities=ModelCapabilities(capabilities=("coding", "reasoning"), benchmark_scores={}),
            cost=ModelCost(0.001, 0.002),
            limits=ModelLimits(100000, 4096),
        )
        model2 = ModelInfo(
            model_id="model-2",
            provider="test",
            display_name="Model 2",
            tier=ModelTier.STANDARD,
            capabilities=ModelCapabilities(capabilities=("fast_response",), benchmark_scores={}),
            cost=ModelCost(0.001, 0.002),
            limits=ModelLimits(100000, 4096),
        )
        registry.register_model(model1)
        registry.register_model(model2)

        coding_models = registry.get_models_with_capability("coding")
        assert len(coding_models) == 1
        assert coding_models[0].model_id == "model-1"

    def test_get_fallback_chain(self, registry):
        """Test fallback chain retrieval."""
        model1 = ModelInfo(
            model_id="model-1",
            provider="test",
            display_name="Model 1",
            tier=ModelTier.PREMIUM,
            capabilities=ModelCapabilities(capabilities=(), benchmark_scores={}),
            cost=ModelCost(0.01, 0.02),
            limits=ModelLimits(100000, 4096),
            fallback_model_id="model-2",
        )
        model2 = ModelInfo(
            model_id="model-2",
            provider="test",
            display_name="Model 2",
            tier=ModelTier.STANDARD,
            capabilities=ModelCapabilities(capabilities=(), benchmark_scores={}),
            cost=ModelCost(0.001, 0.002),
            limits=ModelLimits(100000, 4096),
            fallback_model_id="model-3",
        )
        model3 = ModelInfo(
            model_id="model-3",
            provider="test",
            display_name="Model 3",
            tier=ModelTier.ECONOMY,
            capabilities=ModelCapabilities(capabilities=(), benchmark_scores={}),
            cost=ModelCost(0.0001, 0.0002),
            limits=ModelLimits(100000, 4096),
        )
        registry.register_model(model1)
        registry.register_model(model2)
        registry.register_model(model3)

        chain = registry.get_fallback_chain("model-1")
        assert chain == ["model-1", "model-2", "model-3"]

    def test_record_success_and_failure(self, registry):
        """Test recording success and failure."""
        model = ModelInfo(
            model_id="test-model",
            provider="test",
            display_name="Test Model",
            tier=ModelTier.STANDARD,
            capabilities=ModelCapabilities(capabilities=(), benchmark_scores={}),
            cost=ModelCost(0.001, 0.002),
            limits=ModelLimits(100000, 4096),
        )
        registry.register_model(model)

        registry.record_success("test-model", 100.0)
        assert model.health.status == ModelStatus.HEALTHY

        registry.record_failure("test-model", "Error")
        assert model.health.consecutive_failures == 1

    def test_estimate_cost(self, registry):
        """Test cost estimation."""
        model = ModelInfo(
            model_id="test-model",
            provider="test",
            display_name="Test Model",
            tier=ModelTier.STANDARD,
            capabilities=ModelCapabilities(capabilities=(), benchmark_scores={}),
            cost=ModelCost(0.003, 0.015),
            limits=ModelLimits(100000, 4096),
        )
        registry.register_model(model)

        cost = registry.estimate_cost("test-model", 1000, 500)
        assert cost == pytest.approx(0.0105)

    def test_get_health_summary(self, registry):
        """Test health summary generation."""
        model = ModelInfo(
            model_id="test-model",
            provider="test",
            display_name="Test Model",
            tier=ModelTier.STANDARD,
            capabilities=ModelCapabilities(capabilities=(), benchmark_scores={}),
            cost=ModelCost(0.001, 0.002),
            limits=ModelLimits(100000, 4096),
        )
        registry.register_model(model)
        registry.record_success("test-model", 100.0)

        summary = registry.get_health_summary()
        assert "test-model" in summary
        assert summary["test-model"]["status"] == "healthy"
