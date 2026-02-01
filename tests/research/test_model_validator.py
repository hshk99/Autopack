"""Tests for model discovery and validation system."""

import pytest
from datetime import datetime

from src.autopack.research.model_validator import (
    BenchmarkScore,
    HardwareCompatibility,
    HardwareRequirement,
    InferenceMetrics,
    ModelDiscoverySystem,
    ModelMetadata,
    ModelRegistry,
    ModelType,
    ModelValidator,
    create_example_model,
)


class TestBenchmarkScore:
    """Tests for BenchmarkScore dataclass."""

    def test_benchmark_creation(self):
        """Test creating a benchmark score."""
        score = BenchmarkScore("mmlu", 85.0, max_score=100.0, source="test")
        assert score.name == "mmlu"
        assert score.score == 85.0
        assert score.max_score == 100.0
        assert score.source == "test"

    def test_normalized_score(self):
        """Test normalized score calculation."""
        score = BenchmarkScore("mtbench", 8.5, max_score=10.0)
        assert score.normalized_score() == 85.0

    def test_normalized_score_full(self):
        """Test normalized score when already at 100."""
        score = BenchmarkScore("test", 100.0, max_score=100.0)
        assert score.normalized_score() == 100.0


class TestInferenceMetrics:
    """Tests for InferenceMetrics dataclass."""

    def test_inference_metrics_creation(self):
        """Test creating inference metrics."""
        metrics = InferenceMetrics(
            time_to_first_token_ms=200,
            tokens_per_second=150,
            memory_bf16_gb=55,
        )
        assert metrics.time_to_first_token_ms == 200
        assert metrics.tokens_per_second == 150
        assert metrics.memory_bf16_gb == 55
        assert metrics.quantization_friendly is True


class TestHardwareCompatibility:
    """Tests for HardwareCompatibility dataclass."""

    def test_hardware_creation(self):
        """Test creating hardware compatibility info."""
        compat = HardwareCompatibility(
            hardware_type=HardwareRequirement.CONSUMER_GPU,
            min_vram_gb=16,
            recommended_vram_gb=24,
            max_batch_size=4,
            framework="vLLM",
        )
        assert compat.hardware_type == HardwareRequirement.CONSUMER_GPU
        assert compat.min_vram_gb == 16
        assert compat.recommended_vram_gb == 24
        assert compat.max_batch_size == 4

    def test_invalid_vram_requirements(self):
        """Test that min should be <= recommended."""
        # This is tested in validation, not in the dataclass
        compat = HardwareCompatibility(
            hardware_type=HardwareRequirement.CONSUMER_GPU,
            min_vram_gb=24,
            recommended_vram_gb=16,  # Invalid but allowed in dataclass
        )
        assert compat.min_vram_gb == 24


class TestModelMetadata:
    """Tests for ModelMetadata dataclass."""

    def test_model_creation(self):
        """Test creating model metadata."""
        model = ModelMetadata(
            name="Test Model",
            provider="Test Provider",
            model_type=ModelType.REASONING,
            release_date="2024-01",
            context_window=8000,
        )
        assert model.name == "Test Model"
        assert model.provider == "Test Provider"
        assert model.model_type == ModelType.REASONING
        assert model.context_window == 8000

    def test_calculate_overall_score(self):
        """Test overall score calculation."""
        model = ModelMetadata(
            name="Test",
            provider="Test",
            model_type=ModelType.GENERAL,
            release_date="2024-01",
            context_window=4000,
            benchmarks={
                "bench1": BenchmarkScore("bench1", 80.0),
                "bench2": BenchmarkScore("bench2", 90.0),
            },
        )
        score = model.calculate_overall_score()
        assert score == 85.0  # Average of 80 and 90

    def test_calculate_overall_score_empty(self):
        """Test overall score with no benchmarks."""
        model = ModelMetadata(
            name="Test",
            provider="Test",
            model_type=ModelType.GENERAL,
            release_date="2024-01",
            context_window=4000,
        )
        score = model.calculate_overall_score()
        assert score == 0.0

    def test_model_to_dict(self):
        """Test converting model to dictionary."""
        model = create_example_model()
        model.overall_score = model.calculate_overall_score()

        model_dict = model.to_dict()
        assert model_dict["name"] == "Claude 3.5 Sonnet"
        assert model_dict["provider"] == "Anthropic"
        assert model_dict["context_window"] == 200000
        assert "benchmarks" in model_dict
        assert "overall_score" in model_dict


class TestModelRegistry:
    """Tests for ModelRegistry."""

    def test_registry_creation(self):
        """Test creating a registry."""
        registry = ModelRegistry()
        assert len(registry.models) == 0

    def test_register_model(self):
        """Test registering a model."""
        registry = ModelRegistry()
        model = create_example_model()

        registry.register_model(model)
        assert len(registry.models) == 1
        assert registry.get_model("Claude 3.5 Sonnet") == model

    def test_get_model(self):
        """Test retrieving a model."""
        registry = ModelRegistry()
        model = create_example_model()
        registry.register_model(model)

        retrieved = registry.get_model("Claude 3.5 Sonnet")
        assert retrieved is not None
        assert retrieved.name == "Claude 3.5 Sonnet"

    def test_get_nonexistent_model(self):
        """Test retrieving nonexistent model."""
        registry = ModelRegistry()
        result = registry.get_model("Nonexistent")
        assert result is None

    def test_list_models_empty(self):
        """Test listing models from empty registry."""
        registry = ModelRegistry()
        models = registry.list_models()
        assert len(models) == 0

    def test_list_models_filtered_by_type(self):
        """Test filtering models by type."""
        registry = ModelRegistry()

        model1 = ModelMetadata(
            name="Model1",
            provider="Test",
            model_type=ModelType.REASONING,
            release_date="2024-01",
            context_window=4000,
        )
        model2 = ModelMetadata(
            name="Model2",
            provider="Test",
            model_type=ModelType.CODE,
            release_date="2024-01",
            context_window=4000,
        )

        registry.register_model(model1)
        registry.register_model(model2)

        reasoning = registry.list_models(model_type=ModelType.REASONING)
        assert len(reasoning) == 1
        assert reasoning[0].name == "Model1"

    def test_list_models_filtered_by_score(self):
        """Test filtering models by score."""
        registry = ModelRegistry()

        model1 = ModelMetadata(
            name="Model1",
            provider="Test",
            model_type=ModelType.REASONING,
            release_date="2024-01",
            context_window=4000,
            overall_score=80.0,
        )
        model2 = ModelMetadata(
            name="Model2",
            provider="Test",
            model_type=ModelType.CODE,
            release_date="2024-01",
            context_window=4000,
            overall_score=60.0,
        )

        registry.register_model(model1)
        registry.register_model(model2)

        high_score = registry.list_models(min_score=70.0)
        assert len(high_score) == 1
        assert high_score[0].name == "Model1"

    def test_find_best_for_hardware(self):
        """Test finding models for specific hardware."""
        registry = ModelRegistry()

        model = ModelMetadata(
            name="Test",
            provider="Test",
            model_type=ModelType.GENERAL,
            release_date="2024-01",
            context_window=4000,
            overall_score=85.0,
            hardware_options=[
                HardwareCompatibility(
                    hardware_type=HardwareRequirement.CONSUMER_GPU,
                    min_vram_gb=16,
                    recommended_vram_gb=24,
                )
            ],
        )

        registry.register_model(model)

        compatible = registry.find_best_for_hardware(HardwareRequirement.CONSUMER_GPU)
        assert len(compatible) == 1
        assert compatible[0].name == "Test"

    def test_registry_to_dict(self):
        """Test converting registry to dictionary."""
        registry = ModelRegistry()
        model = create_example_model()
        model.overall_score = model.calculate_overall_score()
        registry.register_model(model)

        reg_dict = registry.to_dict()
        assert "models" in reg_dict
        assert "total_models" in reg_dict
        assert reg_dict["total_models"] == 1


class TestModelValidator:
    """Tests for ModelValidator."""

    def test_validator_creation(self):
        """Test creating a validator."""
        validator = ModelValidator()
        assert isinstance(validator.registry, ModelRegistry)

    def test_validate_benchmarks_valid(self):
        """Test valid benchmark validation."""
        validator = ModelValidator()
        model = ModelMetadata(
            name="Test",
            provider="Test",
            model_type=ModelType.GENERAL,
            release_date="2024-01",
            context_window=4000,
            benchmarks={"bench1": BenchmarkScore("bench1", 85.0, max_score=100.0)},
        )
        assert validator.validate_benchmarks(model) is True

    def test_validate_benchmarks_invalid_score(self):
        """Test invalid benchmark score."""
        validator = ModelValidator()
        model = ModelMetadata(
            name="Test",
            provider="Test",
            model_type=ModelType.GENERAL,
            release_date="2024-01",
            context_window=4000,
            benchmarks={"bench1": BenchmarkScore("bench1", 150.0, max_score=100.0)},
        )
        assert validator.validate_benchmarks(model) is False

    def test_validate_benchmarks_empty(self):
        """Test empty benchmarks."""
        validator = ModelValidator()
        model = ModelMetadata(
            name="Test",
            provider="Test",
            model_type=ModelType.GENERAL,
            release_date="2024-01",
            context_window=4000,
        )
        assert validator.validate_benchmarks(model) is False

    def test_validate_hardware_compatibility(self):
        """Test hardware compatibility validation."""
        validator = ModelValidator()
        model = ModelMetadata(
            name="Test",
            provider="Test",
            model_type=ModelType.GENERAL,
            release_date="2024-01",
            context_window=4000,
            hardware_options=[
                HardwareCompatibility(
                    hardware_type=HardwareRequirement.CONSUMER_GPU,
                    min_vram_gb=16,
                    recommended_vram_gb=24,
                    max_batch_size=4,
                )
            ],
        )
        assert validator.validate_hardware_compatibility(model) is True

    def test_validate_reasoning_assessment(self):
        """Test reasoning assessment validation."""
        validator = ModelValidator()

        # Valid reasoning score
        model = ModelMetadata(
            name="Test",
            provider="Test",
            model_type=ModelType.REASONING,
            release_date="2024-01",
            context_window=4000,
            reasoning_score=85.0,
        )
        assert validator.validate_reasoning_assessment(model) is True

        # Invalid reasoning score
        model.reasoning_score = 150.0
        assert validator.validate_reasoning_assessment(model) is False

    def test_validate_community_feedback(self):
        """Test community feedback validation."""
        validator = ModelValidator()

        model = ModelMetadata(
            name="Test",
            provider="Test",
            model_type=ModelType.GENERAL,
            release_date="2024-01",
            context_window=4000,
            community_stars=4.5,
            community_feedback_count=100,
        )
        assert validator.validate_community_feedback(model) is True

        # Invalid stars
        model.community_stars = 6.0
        assert validator.validate_community_feedback(model) is False

    def test_validate_model_success(self):
        """Test complete model validation - success case."""
        validator = ModelValidator()
        model = create_example_model()
        model.overall_score = model.calculate_overall_score()

        is_valid, errors = validator.validate_model(model)
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_model_missing_fields(self):
        """Test validation with missing fields."""
        validator = ModelValidator()
        model = ModelMetadata(
            name="",
            provider="",
            model_type=ModelType.GENERAL,
            release_date="2024-01",
            context_window=4000,
        )

        is_valid, errors = validator.validate_model(model)
        assert is_valid is False
        assert any("required" in error.lower() for error in errors)

    def test_register_and_validate(self):
        """Test registering and validating a model."""
        validator = ModelValidator()
        model = create_example_model()
        model.overall_score = model.calculate_overall_score()

        is_valid, errors = validator.register_and_validate(model)
        assert is_valid is True
        assert len(errors) == 0
        assert validator.registry.get_model(model.name) is not None


class TestModelDiscoverySystem:
    """Tests for ModelDiscoverySystem."""

    def test_discovery_creation(self):
        """Test creating discovery system."""
        discovery = ModelDiscoverySystem()
        assert len(discovery.discovered_models) == 0
        assert discovery.discovery_metadata["total_models_found"] == 0

    def test_scan_registries(self):
        """Test registry scanning."""
        discovery = ModelDiscoverySystem()
        discovery.scan_registries()

        assert "registries_scanned" in discovery.discovery_metadata
        # Should have attempted all registries even if empty
        assert len(discovery.discovery_metadata["registries_scanned"]) > 0

    def test_get_discovered_models(self):
        """Test getting discovered models."""
        discovery = ModelDiscoverySystem()
        models = discovery.get_discovered_models()
        assert isinstance(models, list)


class TestExampleModel:
    """Tests for example model creation."""

    def test_create_example_model(self):
        """Test creating example model."""
        model = create_example_model()
        assert model.name == "Claude 3.5 Sonnet"
        assert model.provider == "Anthropic"
        assert model.context_window == 200000
        assert model.reasoning_score == 98.0

    def test_example_model_validation(self):
        """Test example model validates correctly."""
        validator = ModelValidator()
        model = create_example_model()
        model.overall_score = model.calculate_overall_score()

        is_valid, errors = validator.validate_model(model)
        assert is_valid is True
        assert len(errors) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
