"""Tests for provider adapters."""

import pytest

from src.autopack.generative.adapters import (
    AdapterRegistry,
    ProviderAdapter,
    RunPodAdapter,
    SelfHostedAdapter,
    TogetherAIAdapter,
    VertexAIAdapter,
)
from src.autopack.generative.adapters.base import ProviderFeatures
from src.autopack.generative.exceptions import InvalidConfigurationError


class TestProviderFeatures:
    """Test ProviderFeatures dataclass."""

    def test_features_default_initialization(self):
        """Test default initialization of features."""
        features = ProviderFeatures()
        assert not features.supports_image_generation
        assert not features.supports_video_generation
        assert not features.supports_voice_tts
        assert not features.supports_background_removal
        assert features.supports_async
        assert features.requires_authentication
        assert features.supported_image_formats == ["png", "jpg", "webp"]
        assert features.supported_video_formats == ["mp4", "webm"]
        assert features.supported_audio_formats == ["mp3", "wav", "m4a"]

    def test_features_custom_initialization(self):
        """Test custom initialization of features."""
        features = ProviderFeatures(
            supports_image_generation=True,
            supports_voice_tts=True,
            rate_limit_per_minute=100,
            supported_image_formats=["jpg", "png"],
        )
        assert features.supports_image_generation
        assert features.supports_voice_tts
        assert features.rate_limit_per_minute == 100
        assert features.supported_image_formats == ["jpg", "png"]


class TestTogetherAIAdapter:
    """Test Together AI adapter."""

    def test_initialization(self):
        """Test adapter initialization."""
        adapter = TogetherAIAdapter(api_key="test-key")
        assert adapter.name == "together_ai"
        assert adapter.api_key == "test-key"

    def test_features(self):
        """Test adapter features."""
        adapter = TogetherAIAdapter(api_key="test-key")
        features = adapter.features
        assert features.supports_image_generation
        assert features.supports_voice_tts
        assert not features.supports_video_generation
        assert not features.supports_background_removal
        assert features.rate_limit_per_minute == 300

    @pytest.mark.asyncio
    async def test_generate_image(self):
        """Test image generation."""
        adapter = TogetherAIAdapter(api_key="test-key")
        result = await adapter.generate_image(
            prompt="a cat",
            model_id="flux-schnell",
            width=1024,
            height=1024,
        )
        assert "image_url" in result
        assert result["metadata"]["provider"] == "together_ai"
        assert result["metadata"]["model"] == "flux-schnell"

    @pytest.mark.asyncio
    async def test_generate_voice(self):
        """Test voice generation."""
        adapter = TogetherAIAdapter(api_key="test-key")
        result = await adapter.generate_voice(
            text="hello world",
            model_id="elevenlabs",
            voice_profile="male",
            language="en",
        )
        assert "audio_url" in result
        assert result["voice_profile"] == "male"
        assert result["metadata"]["provider"] == "together_ai"

    @pytest.mark.asyncio
    async def test_video_generation_not_supported(self):
        """Test that video generation raises NotImplementedError."""
        adapter = TogetherAIAdapter(api_key="test-key")
        with pytest.raises(NotImplementedError):
            await adapter.generate_video(
                prompt="a video",
                model_id="test-model",
            )

    @pytest.mark.asyncio
    async def test_background_removal_not_supported(self):
        """Test that background removal raises NotImplementedError."""
        adapter = TogetherAIAdapter(api_key="test-key")
        with pytest.raises(NotImplementedError):
            await adapter.remove_background(
                image_url="http://example.com/image.png",
                model_id="test-model",
            )

    @pytest.mark.asyncio
    async def test_validate_credentials(self):
        """Test credential validation."""
        adapter = TogetherAIAdapter(api_key="test-key")
        result = await adapter.validate_credentials()
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_credentials_missing_key(self):
        """Test credential validation with missing key."""
        adapter = TogetherAIAdapter()
        result = await adapter.validate_credentials()
        assert result is False

    @pytest.mark.asyncio
    async def test_get_available_models(self):
        """Test getting available models."""
        adapter = TogetherAIAdapter(api_key="test-key")
        models = await adapter.get_available_models()
        assert "image_generation" in models
        assert "voice_tts" in models
        assert len(models["image_generation"]) > 0


class TestRunPodAdapter:
    """Test RunPod adapter."""

    def test_initialization(self):
        """Test adapter initialization."""
        adapter = RunPodAdapter(api_key="test-key")
        assert adapter.name == "runpod"
        assert adapter.api_key == "test-key"

    def test_features(self):
        """Test adapter features."""
        adapter = RunPodAdapter(api_key="test-key")
        features = adapter.features
        assert not features.supports_image_generation
        assert features.supports_video_generation
        assert features.supports_voice_tts
        assert features.supports_background_removal
        assert features.rate_limit_per_minute == 60

    @pytest.mark.asyncio
    async def test_generate_video(self):
        """Test video generation."""
        adapter = RunPodAdapter(api_key="test-key")
        result = await adapter.generate_video(
            prompt="a video",
            model_id="hunyuan-video",
            duration=5,
            num_frames=240,
        )
        assert "video_url" in result
        assert result["duration_seconds"] == 5
        assert result["metadata"]["provider"] == "runpod"

    @pytest.mark.asyncio
    async def test_generate_voice(self):
        """Test voice generation."""
        adapter = RunPodAdapter(api_key="test-key")
        result = await adapter.generate_voice(
            text="hello",
            model_id="chatterbox-turbo",
        )
        assert "audio_url" in result
        assert result["metadata"]["provider"] == "runpod"

    @pytest.mark.asyncio
    async def test_remove_background(self):
        """Test background removal."""
        adapter = RunPodAdapter(api_key="test-key")
        result = await adapter.remove_background(
            image_url="http://example.com/image.jpg",
            model_id="bria-rmbg-2",
            output_format="png",
        )
        assert "image_url" in result
        assert result["metadata"]["output_format"] == "png"

    @pytest.mark.asyncio
    async def test_image_generation_not_supported(self):
        """Test that image generation raises NotImplementedError."""
        adapter = RunPodAdapter(api_key="test-key")
        with pytest.raises(NotImplementedError):
            await adapter.generate_image(
                prompt="a cat",
                model_id="test-model",
            )


class TestVertexAIAdapter:
    """Test Vertex AI adapter."""

    def test_initialization(self):
        """Test adapter initialization."""
        adapter = VertexAIAdapter(api_key="test-key")
        assert adapter.name == "vertex_ai"
        assert adapter.api_key == "test-key"

    def test_features(self):
        """Test adapter features."""
        adapter = VertexAIAdapter(api_key="test-key")
        features = adapter.features
        assert features.supports_image_generation
        assert features.supports_video_generation
        assert not features.supports_voice_tts
        assert not features.supports_background_removal

    @pytest.mark.asyncio
    async def test_generate_image(self):
        """Test image generation."""
        adapter = VertexAIAdapter(api_key="test-key")
        result = await adapter.generate_image(
            prompt="a cat",
            model_id="imagegeneration@006",
        )
        assert "image_url" in result
        assert result["metadata"]["provider"] == "vertex_ai"

    @pytest.mark.asyncio
    async def test_generate_video(self):
        """Test video generation."""
        adapter = VertexAIAdapter(api_key="test-key")
        result = await adapter.generate_video(
            prompt="a video",
            model_id="veo-3.1",
        )
        assert "video_url" in result
        assert result["metadata"]["provider"] == "vertex_ai"

    @pytest.mark.asyncio
    async def test_voice_generation_not_supported(self):
        """Test that voice generation raises NotImplementedError."""
        adapter = VertexAIAdapter(api_key="test-key")
        with pytest.raises(NotImplementedError):
            await adapter.generate_voice(
                text="hello",
                model_id="test-model",
            )


class TestSelfHostedAdapter:
    """Test Self-hosted adapter."""

    def test_initialization(self):
        """Test adapter initialization."""
        adapter = SelfHostedAdapter()
        assert adapter.name == "self_hosted"

    def test_initialization_with_config(self):
        """Test adapter initialization with custom config."""
        adapter = SelfHostedAdapter(
            base_url="http://custom-host",
            port=9000,
        )
        assert adapter.base_url == "http://custom-host"
        assert adapter.port == 9000

    def test_features(self):
        """Test adapter features."""
        adapter = SelfHostedAdapter()
        features = adapter.features
        assert not features.supports_image_generation
        assert not features.supports_video_generation
        assert features.supports_voice_tts
        assert features.supports_background_removal
        assert not features.requires_authentication

    @pytest.mark.asyncio
    async def test_generate_voice(self):
        """Test voice generation."""
        adapter = SelfHostedAdapter(base_url="http://localhost", port=8000)
        result = await adapter.generate_voice(
            text="hello",
            model_id="kokoro-82m",
        )
        assert "audio_url" in result
        assert result["metadata"]["provider"] == "self_hosted"

    @pytest.mark.asyncio
    async def test_remove_background(self):
        """Test background removal."""
        adapter = SelfHostedAdapter()
        result = await adapter.remove_background(
            image_url="http://example.com/image.jpg",
            model_id="birefnet",
        )
        assert "image_url" in result
        assert result["metadata"]["provider"] == "self_hosted"


class TestAdapterRegistry:
    """Test adapter registry."""

    def test_initialization(self):
        """Test registry initialization."""
        registry = AdapterRegistry()
        assert len(registry.list_providers()) == 0

    def test_register_adapter_class(self):
        """Test registering adapter class."""
        registry = AdapterRegistry()
        registry.register_adapter_class("test_provider", TogetherAIAdapter)
        assert registry.has_adapter("test_provider")
        assert "test_provider" in registry.list_providers()

    def test_register_invalid_adapter_class(self):
        """Test registering invalid adapter class."""
        registry = AdapterRegistry()
        with pytest.raises(InvalidConfigurationError):
            registry.register_adapter_class("invalid", str)

    def test_register_adapter_instance(self):
        """Test registering adapter instance."""
        registry = AdapterRegistry()
        adapter = TogetherAIAdapter(api_key="test-key")
        registry.register_adapter_instance("test_provider", adapter)
        assert registry.has_adapter("test_provider")

    def test_get_adapter_from_instance(self):
        """Test getting adapter from registered instance."""
        registry = AdapterRegistry()
        adapter = TogetherAIAdapter(api_key="test-key")
        registry.register_adapter_instance("test_provider", adapter)
        retrieved = registry.get_adapter("test_provider")
        assert retrieved is adapter

    def test_get_adapter_from_class(self):
        """Test getting adapter from registered class."""
        registry = AdapterRegistry()
        registry.register_adapter_class("test_provider", TogetherAIAdapter)
        adapter = registry.get_adapter("test_provider", api_key="test-key")
        assert isinstance(adapter, TogetherAIAdapter)

    def test_get_adapter_unknown_provider(self):
        """Test getting unknown adapter."""
        registry = AdapterRegistry()
        with pytest.raises(InvalidConfigurationError):
            registry.get_adapter("unknown_provider")

    def test_get_features(self):
        """Test getting provider features."""
        registry = AdapterRegistry()
        registry.register_adapter_class("test_provider", TogetherAIAdapter)
        features = registry.get_features("test_provider")
        assert features.supports_image_generation
        assert features.supports_voice_tts

    def test_list_providers(self):
        """Test listing providers."""
        registry = AdapterRegistry()
        registry.register_adapter_class("provider1", TogetherAIAdapter)
        registry.register_adapter_class("provider2", RunPodAdapter)
        providers = registry.list_providers()
        assert "provider1" in providers
        assert "provider2" in providers


class TestProviderAdapter:
    """Test abstract base class."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that abstract class cannot be instantiated."""
        with pytest.raises(TypeError):
            ProviderAdapter(name="test")

    def test_abstract_methods_required(self):
        """Test that subclasses must implement abstract methods."""

        class IncompleteAdapter(ProviderAdapter):
            @property
            def features(self):
                return ProviderFeatures()

        # This should fail because other abstract methods are not implemented
        with pytest.raises(TypeError):
            IncompleteAdapter(name="test")
