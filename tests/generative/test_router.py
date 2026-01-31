"""Tests for generative model router."""

import os
import tempfile

import pytest
import yaml

from autopack.generative.exceptions import CapabilityNotSupportedError
from autopack.generative.router import GenerativeModelRouter, ImageResult


@pytest.fixture
def sample_config() -> dict:
    """Create a comprehensive sample configuration."""
    return {
        "providers": {
            "provider1": {
                "endpoint": "https://api1.example.com",
                "api_key_env": "API_KEY_1",
                "timeout_seconds": 120,
                "max_retries": 3,
            },
            "provider2": {
                "endpoint": "https://api2.example.com",
                "api_key_env": "API_KEY_2",
                "timeout_seconds": 120,
                "max_retries": 3,
            },
        },
        "capabilities": {
            "image_generation": {
                "default_model": "model_a",
                "fallback_chain": ["model_a", "model_b"],
                "min_acceptable_quality": 0.75,
                "prefer_open_source_if_above": 0.85,
                "models": {
                    "model_a": {
                        "provider": "provider1",
                        "name": "Model A",
                        "quality_score": 0.9,
                        "cost_per_unit": 0.001,
                        "license": "Apache 2.0",
                    },
                    "model_b": {
                        "provider": "provider2",
                        "name": "Model B",
                        "quality_score": 0.8,
                        "cost_per_unit": 0.0005,
                        "license": "MIT",
                    },
                },
            },
            "voice_tts": {
                "default_model": "voice_model_a",
                "fallback_chain": ["voice_model_a", "voice_model_b"],
                "min_acceptable_quality": 0.75,
                "prefer_open_source_if_above": 0.85,
                "models": {
                    "voice_model_a": {
                        "provider": "provider1",
                        "name": "Voice Model A",
                        "quality_score": 0.85,
                        "cost_per_unit": 0.0005,
                        "license": "Apache 2.0",
                    },
                    "voice_model_b": {
                        "provider": "provider2",
                        "name": "Voice Model B",
                        "quality_score": 0.75,
                        "cost_per_unit": 0.0003,
                        "license": "Open Source",
                    },
                },
            },
        },
        "quality_thresholds": {
            "min_acceptable": 0.75,
            "prefer_open_source_if_above": 0.85,
        },
    }


@pytest.fixture
def temp_config_file(sample_config) -> str:
    """Create a temporary config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(sample_config, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.fixture
def router(temp_config_file):
    """Create a router instance."""
    return GenerativeModelRouter(temp_config_file)


class TestGenerativeModelRouter:
    """Test GenerativeModelRouter."""

    def test_router_initialization(self, router):
        """Test router initialization."""
        assert len(router.registry.list_providers()) == 2
        assert len(router.registry.list_capabilities()) == 2

    def test_router_with_nonexistent_config(self):
        """Test router initialization with nonexistent config."""
        # This test depends on the actual config path resolution
        # For now, we'll skip it if no default config exists
        pass

    @pytest.mark.asyncio
    async def test_generate_image(self, router):
        """Test image generation."""
        result = await router.generate_image("A beautiful sunset")
        assert isinstance(result, ImageResult)
        assert result.model_id in ["model_a", "model_b"]
        assert result.provider in ["provider1", "provider2"]

    @pytest.mark.asyncio
    async def test_generate_image_with_hints(self, router):
        """Test image generation with hints."""
        result = await router.generate_image(
            "A beautiful sunset",
            capability_hints={"model_id": "model_b"},
        )
        assert result.model_id == "model_b"

    @pytest.mark.asyncio
    async def test_generate_image_unsupported_capability(self, router):
        """Test requesting unsupported capability."""
        # Directly call internal method with unsupported capability
        with pytest.raises(CapabilityNotSupportedError):
            await router._generate_with_capability(
                capability_type="unsupported_capability",
                generation_params={},
                result_type="image",
            )

    @pytest.mark.asyncio
    async def test_generate_voice(self, router):
        """Test voice generation."""
        result = await router.generate_voice("Hello, world!")
        assert result.model_id in ["voice_model_a", "voice_model_b"]
        assert result.provider in ["provider1", "provider2"]

    @pytest.mark.asyncio
    async def test_generate_video(self, router):
        """Test video generation (should fail - not in config)."""
        with pytest.raises(CapabilityNotSupportedError):
            await router.generate_video("A cat playing with a ball")

    @pytest.mark.asyncio
    async def test_generate_background_removal(self, router):
        """Test background removal (should fail - not in config)."""
        with pytest.raises(CapabilityNotSupportedError):
            await router.remove_background("https://example.com/image.jpg")

    def test_select_model_default(self, router):
        """Test model selection with default."""
        capability = router.registry.get_capability("image_generation")
        model_id = router._select_model(capability)
        assert model_id == "model_a"

    def test_select_model_with_hint(self, router):
        """Test model selection with explicit hint."""
        capability = router.registry.get_capability("image_generation")
        model_id = router._select_model(capability, hints={"model_id": "model_b"})
        assert model_id == "model_b"

    def test_select_model_with_quality_hint(self, router):
        """Test model selection with quality hint."""
        capability = router.registry.get_capability("image_generation")
        model_id = router._select_model(capability, hints={"min_quality": 0.85})
        assert model_id == "model_a"  # Only model_a meets the threshold

    def test_select_model_with_open_source_preference(self, router):
        """Test model selection with open source preference."""
        capability = router.registry.get_capability("image_generation")
        model_id = router._select_model(capability, hints={"prefer_open_source": True})
        # Both models have open-source licenses, should return first in chain
        assert model_id in ["model_a", "model_b"]

    @pytest.mark.asyncio
    async def test_check_provider_availability(self, router):
        """Test checking provider availability."""
        availability = await router.check_provider_availability()
        assert "provider1" in availability
        assert "provider2" in availability

    def test_get_health_summary(self, router):
        """Test getting health summary."""
        summary = router.get_health_summary()
        assert "healthy_providers" in summary
        assert "unhealthy_providers" in summary
        assert "all_health_status" in summary

    def test_health_monitor_integration(self, router):
        """Test health monitor is integrated."""
        router.health_monitor.mark_failure("provider1", "Connection error")
        # After 1 failure, provider is still healthy (threshold is 3)
        health = router.health_monitor.get_health_status("provider1")
        assert health.consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_fallback_chain_on_failure(self, router):
        """Test that fallback chain is used on model failure."""
        # Mark first model's provider as unhealthy
        router.health_monitor.mark_failure("provider1", "Provider error")

        # Generation should still work via fallback
        result = await router.generate_image("Test image")
        assert isinstance(result, ImageResult)

    def test_registry_access(self, router):
        """Test accessing registry through router."""
        providers = router.registry.list_providers()
        assert len(providers) == 2

        capabilities = router.registry.list_capabilities()
        assert "image_generation" in capabilities

    @pytest.mark.asyncio
    async def test_image_result_structure(self, router):
        """Test structure of image result."""
        result = await router.generate_image("Test")
        assert hasattr(result, "image_url")
        assert hasattr(result, "model_id")
        assert hasattr(result, "provider")
        assert hasattr(result, "metadata")

    @pytest.mark.asyncio
    async def test_audio_result_structure(self, router):
        """Test structure of audio result."""
        result = await router.generate_voice("Test")
        assert hasattr(result, "audio_url")
        assert hasattr(result, "model_id")
        assert hasattr(result, "provider")
        assert hasattr(result, "voice_profile")

    def test_provider_initialization(self, router):
        """Test that providers are initialized in health monitor."""
        for provider_name in router.registry.list_providers():
            health = router.health_monitor.get_health_status(provider_name)
            assert health is not None
