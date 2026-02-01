"""Tests for model registry."""

import pytest

from autopack.generative.exceptions import InvalidConfigurationError
from autopack.generative.registry import (CapabilityGroup, ModelCapability,
                                          ModelRegistry, Provider)


class TestProvider:
    """Test Provider dataclass."""

    def test_provider_creation(self):
        """Test creating a provider."""
        provider = Provider(
            name="test_provider",
            endpoint="https://api.example.com",
            api_key_env="TEST_API_KEY",
            timeout_seconds=60,
            max_retries=3,
        )
        assert provider.name == "test_provider"
        assert provider.endpoint == "https://api.example.com"
        assert provider.api_key_env == "TEST_API_KEY"
        assert provider.timeout_seconds == 60
        assert provider.max_retries == 3

    def test_provider_with_metadata(self):
        """Test creating a provider with metadata."""
        metadata = {"region": "us-west-2", "type": "cloud"}
        provider = Provider(
            name="aws",
            endpoint="https://aws.amazon.com",
            metadata=metadata,
        )
        assert provider.metadata == metadata


class TestModelCapability:
    """Test ModelCapability dataclass."""

    def test_model_capability_creation(self):
        """Test creating a model capability."""
        model = ModelCapability(
            model_id="test_model",
            provider="test_provider",
            name="Test Model",
            quality_score=0.85,
            cost_per_unit=0.001,
            license="MIT",
        )
        assert model.model_id == "test_model"
        assert model.quality_score == 0.85

    def test_model_capability_invalid_quality_score_too_high(self):
        """Test validation of quality score > 1.0."""
        with pytest.raises(InvalidConfigurationError):
            ModelCapability(
                model_id="bad_model",
                provider="test_provider",
                name="Bad Model",
                quality_score=1.5,
                cost_per_unit=0.001,
                license="MIT",
            )

    def test_model_capability_invalid_quality_score_too_low(self):
        """Test validation of quality score < 0.0."""
        with pytest.raises(InvalidConfigurationError):
            ModelCapability(
                model_id="bad_model",
                provider="test_provider",
                name="Bad Model",
                quality_score=-0.1,
                cost_per_unit=0.001,
                license="MIT",
            )

    def test_model_capability_invalid_cost(self):
        """Test validation of negative cost."""
        with pytest.raises(InvalidConfigurationError):
            ModelCapability(
                model_id="bad_model",
                provider="test_provider",
                name="Bad Model",
                quality_score=0.8,
                cost_per_unit=-0.001,
                license="MIT",
            )


class TestCapabilityGroup:
    """Test CapabilityGroup dataclass."""

    def test_capability_group_creation(self):
        """Test creating a capability group."""
        model1 = ModelCapability(
            model_id="model1",
            provider="provider1",
            name="Model 1",
            quality_score=0.9,
            cost_per_unit=0.001,
            license="MIT",
        )
        model2 = ModelCapability(
            model_id="model2",
            provider="provider2",
            name="Model 2",
            quality_score=0.8,
            cost_per_unit=0.002,
            license="Apache 2.0",
        )

        capability = CapabilityGroup(
            capability_type="image_generation",
            default_model="model1",
            fallback_chain=["model1", "model2"],
            models={"model1": model1, "model2": model2},
        )
        assert capability.capability_type == "image_generation"
        assert capability.default_model == "model1"
        assert len(capability.models) == 2

    def test_capability_group_invalid_default_model(self):
        """Test validation of default model in fallback chain."""
        model = ModelCapability(
            model_id="model1",
            provider="provider1",
            name="Model 1",
            quality_score=0.9,
            cost_per_unit=0.001,
            license="MIT",
        )

        with pytest.raises(InvalidConfigurationError):
            CapabilityGroup(
                capability_type="image_generation",
                default_model="nonexistent_model",  # Not in fallback chain
                fallback_chain=["model1"],
                models={"model1": model},
            )

    def test_capability_group_get_best_available_model(self):
        """Test getting the best available model."""
        model1 = ModelCapability(
            model_id="model1",
            provider="provider1",
            name="Model 1",
            quality_score=0.9,
            cost_per_unit=0.001,
            license="MIT",
        )
        model2 = ModelCapability(
            model_id="model2",
            provider="provider2",
            name="Model 2",
            quality_score=0.8,
            cost_per_unit=0.002,
            license="Apache 2.0",
        )

        capability = CapabilityGroup(
            capability_type="image_generation",
            default_model="model1",
            fallback_chain=["model1", "model2"],
            models={"model1": model1, "model2": model2},
        )

        best_model = capability.get_best_available_model()
        assert best_model == "model1"

    def test_capability_group_get_model_by_quality(self):
        """Test getting a model by quality threshold."""
        model1 = ModelCapability(
            model_id="model1",
            provider="provider1",
            name="Model 1",
            quality_score=0.9,
            cost_per_unit=0.001,
            license="MIT",
        )
        model2 = ModelCapability(
            model_id="model2",
            provider="provider2",
            name="Model 2",
            quality_score=0.75,
            cost_per_unit=0.002,
            license="Apache 2.0",
        )

        capability = CapabilityGroup(
            capability_type="image_generation",
            default_model="model1",
            fallback_chain=["model1", "model2"],
            models={"model1": model1, "model2": model2},
        )

        # Should find model1 (quality 0.9)
        model = capability.get_model_by_quality(0.85)
        assert model == "model1"

        # Should not find any model below 0.7 quality
        model = capability.get_model_by_quality(0.95)
        assert model is None


class TestModelRegistry:
    """Test ModelRegistry."""

    def test_registry_creation(self):
        """Test creating a registry."""
        registry = ModelRegistry()
        assert len(registry.list_providers()) == 0
        assert len(registry.list_capabilities()) == 0

    def test_register_provider(self):
        """Test registering a provider."""
        registry = ModelRegistry()
        provider = Provider(
            name="test_provider",
            endpoint="https://api.example.com",
        )
        registry.register_provider(provider)
        assert "test_provider" in registry.list_providers()

    def test_register_duplicate_provider(self):
        """Test that registering duplicate provider raises error."""
        registry = ModelRegistry()
        provider = Provider(
            name="test_provider",
            endpoint="https://api.example.com",
        )
        registry.register_provider(provider)

        with pytest.raises(InvalidConfigurationError):
            registry.register_provider(provider)

    def test_register_capability(self):
        """Test registering a capability."""
        registry = ModelRegistry()
        model = ModelCapability(
            model_id="model1",
            provider="provider1",
            name="Model 1",
            quality_score=0.9,
            cost_per_unit=0.001,
            license="MIT",
        )
        capability = CapabilityGroup(
            capability_type="image_generation",
            default_model="model1",
            fallback_chain=["model1"],
            models={"model1": model},
        )
        registry.register_capability(capability)
        assert "image_generation" in registry.list_capabilities()

    def test_get_provider(self):
        """Test getting a provider."""
        registry = ModelRegistry()
        provider = Provider(
            name="test_provider",
            endpoint="https://api.example.com",
        )
        registry.register_provider(provider)

        retrieved = registry.get_provider("test_provider")
        assert retrieved.name == "test_provider"

    def test_get_nonexistent_provider(self):
        """Test getting a nonexistent provider raises error."""
        registry = ModelRegistry()
        with pytest.raises(InvalidConfigurationError):
            registry.get_provider("nonexistent")

    def test_get_capability(self):
        """Test getting a capability."""
        registry = ModelRegistry()
        model = ModelCapability(
            model_id="model1",
            provider="provider1",
            name="Model 1",
            quality_score=0.9,
            cost_per_unit=0.001,
            license="MIT",
        )
        capability = CapabilityGroup(
            capability_type="image_generation",
            default_model="model1",
            fallback_chain=["model1"],
            models={"model1": model},
        )
        registry.register_capability(capability)

        retrieved = registry.get_capability("image_generation")
        assert retrieved.capability_type == "image_generation"

    def test_get_nonexistent_capability(self):
        """Test getting a nonexistent capability raises error."""
        registry = ModelRegistry()
        with pytest.raises(InvalidConfigurationError):
            registry.get_capability("nonexistent")
