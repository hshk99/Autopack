"""Generative Model Router - main entry point for all AI capabilities."""

import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional

from .adapters import (
    AdapterRegistry,
    RunPodAdapter,
    SelfHostedAdapter,
    TogetherAIAdapter,
    VertexAIAdapter,
)
from .config_loader import ConfigLoader
from .exceptions import (
    CapabilityNotSupportedError,
    InvalidConfigurationError,
    ModelNotAvailableError,
)
from .health_monitor import HealthMonitor
from .registry import ModelRegistry

logger = logging.getLogger(__name__)


@dataclass
class ImageResult:
    """Result of image generation."""

    image_url: str
    model_id: str
    provider: str
    metadata: Dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class VideoResult:
    """Result of video generation."""

    video_url: str
    model_id: str
    provider: str
    duration_seconds: int
    metadata: Dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class AudioResult:
    """Result of voice/TTS generation."""

    audio_url: str
    model_id: str
    provider: str
    voice_profile: str
    metadata: Dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class GenerativeModelRouter:
    """Main entry point for generative AI capabilities.

    Provides a unified interface for image, video, voice, and background removal
    with hot-swappable model configuration and automatic fallback chains.
    """

    def __init__(self, config_path: Optional[str] = None):
        """Initialize the router with configuration.

        Args:
            config_path: Path to generative_models.yaml config file
        """
        self.config_loader = ConfigLoader(config_path)
        self.registry: ModelRegistry = self.config_loader.get_registry()
        self.health_monitor = HealthMonitor()

        # Initialize adapter registry and register all provider adapters
        self.adapter_registry = AdapterRegistry()
        self._initialize_adapters()

        # Initialize provider health tracking
        for provider_name in self.registry.list_providers():
            self.health_monitor.initialize_provider(provider_name)

        logger.info(
            f"GenerativeModelRouter initialized with "
            f"{len(self.registry.list_providers())} providers, "
            f"{len(self.registry.list_capabilities())} capabilities, and "
            f"{len(self.adapter_registry.list_providers())} adapters"
        )

    def _initialize_adapters(self) -> None:
        """Initialize and register all provider adapters.

        Adapters are registered both as classes (for lazy instantiation) and
        can be instantiated with environment-specific configuration.
        """
        # Register adapter classes
        self.adapter_registry.register_adapter_class("together_ai", TogetherAIAdapter)
        self.adapter_registry.register_adapter_class("runpod", RunPodAdapter)
        self.adapter_registry.register_adapter_class("vertex_ai", VertexAIAdapter)
        self.adapter_registry.register_adapter_class("self_hosted", SelfHostedAdapter)

        logger.debug("Registered all provider adapters")

    async def generate_image(
        self,
        prompt: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        num_inference_steps: Optional[int] = None,
        capability_hints: Optional[Dict] = None,
    ) -> ImageResult:
        """Generate an image from a text prompt.

        Args:
            prompt: Text description of the image to generate
            width: Image width in pixels
            height: Image height in pixels
            num_inference_steps: Number of inference steps (quality vs speed tradeoff)
            capability_hints: Optional hints for model selection

        Returns:
            ImageResult with generated image URL and metadata

        Raises:
            CapabilityNotSupportedError: If image generation is not configured
            ModelNotAvailableError: If no suitable model is available
        """
        return await self._generate_with_capability(
            capability_type="image_generation",
            generation_params={
                "prompt": prompt,
                "width": width,
                "height": height,
                "num_inference_steps": num_inference_steps,
            },
            hints=capability_hints,
            result_type="image",
        )

    async def generate_video(
        self,
        prompt: str,
        duration: int = 5,
        num_frames: Optional[int] = None,
        capability_hints: Optional[Dict] = None,
    ) -> VideoResult:
        """Generate a video from a text prompt.

        Args:
            prompt: Text description of the video to generate
            duration: Video duration in seconds
            num_frames: Number of frames to generate
            capability_hints: Optional hints for model selection

        Returns:
            VideoResult with generated video URL and metadata

        Raises:
            CapabilityNotSupportedError: If video generation is not configured
            ModelNotAvailableError: If no suitable model is available
        """
        return await self._generate_with_capability(
            capability_type="video_generation",
            generation_params={
                "prompt": prompt,
                "duration": duration,
                "num_frames": num_frames,
            },
            hints=capability_hints,
            result_type="video",
        )

    async def generate_voice(
        self,
        text: str,
        voice_profile: str = "default",
        language: Optional[str] = None,
        capability_hints: Optional[Dict] = None,
    ) -> AudioResult:
        """Generate voice/speech from text (TTS).

        Args:
            text: Text to convert to speech
            voice_profile: Voice profile/character to use
            language: Language code (e.g., 'en', 'es', 'fr')
            capability_hints: Optional hints for model selection

        Returns:
            AudioResult with generated audio URL and metadata

        Raises:
            CapabilityNotSupportedError: If voice generation is not configured
            ModelNotAvailableError: If no suitable model is available
        """
        return await self._generate_with_capability(
            capability_type="voice_tts",
            generation_params={
                "text": text,
                "voice_profile": voice_profile,
                "language": language,
            },
            hints=capability_hints,
            result_type="audio",
        )

    async def remove_background(
        self,
        image_url: str,
        output_format: str = "png",
        capability_hints: Optional[Dict] = None,
    ) -> ImageResult:
        """Remove background from an image.

        Args:
            image_url: URL of the image to process
            output_format: Output format (png, jpg, webp, etc.)
            capability_hints: Optional hints for model selection

        Returns:
            ImageResult with background-removed image URL

        Raises:
            CapabilityNotSupportedError: If background removal is not configured
            ModelNotAvailableError: If no suitable model is available
        """
        return await self._generate_with_capability(
            capability_type="background_removal",
            generation_params={
                "image_url": image_url,
                "output_format": output_format,
            },
            hints=capability_hints,
            result_type="image",
        )

    async def _generate_with_capability(
        self,
        capability_type: str,
        generation_params: Dict,
        hints: Optional[Dict] = None,
        result_type: str = "image",
    ):
        """Internal method to generate content using a capability.

        Handles model selection, fallback chains, and error recovery.
        """
        # Get capability configuration
        try:
            capability = self.registry.get_capability(capability_type)
        except InvalidConfigurationError:
            raise CapabilityNotSupportedError(f"Capability '{capability_type}' is not configured")

        # Select model based on hints and quality thresholds
        model_id = self._select_model(capability, hints)

        if not model_id:
            raise ModelNotAvailableError(f"No suitable model available for {capability_type}")

        model = capability.models[model_id]
        provider = self.registry.get_provider(model.provider)

        # Log model selection
        logger.info(
            f"Selected model '{model_id}' (quality: {model.quality_score}) "
            f"from provider '{model.provider}' for {capability_type}"
        )

        # Execute generation with this model
        try:
            result = await self._execute_generation(
                capability_type=capability_type,
                model=model,
                provider=provider,
                generation_params=generation_params,
                result_type=result_type,
            )
            self.health_monitor.mark_success(model.provider)
            return result
        except Exception as e:
            logger.error(f"Generation failed with {model_id}: {e}")
            self.health_monitor.mark_failure(model.provider, str(e))

            # Try fallback models
            return await self._try_fallback_chain(
                capability=capability,
                generation_params=generation_params,
                result_type=result_type,
                tried_model=model_id,
            )

    def _select_model(self, capability, hints: Optional[Dict] = None) -> Optional[str]:
        """Select the best model for a capability.

        Considers quality thresholds, hints, and open source preferences.

        Args:
            capability: CapabilityGroup to select from
            hints: Optional hints for model selection

        Returns:
            Model ID or None if no suitable model found
        """
        # Check for explicit model hint
        if hints and "model_id" in hints:
            requested_model = hints["model_id"]
            if requested_model in capability.models:
                return requested_model

        # Check for quality hint
        if hints and "min_quality" in hints:
            model = capability.get_model_by_quality(hints["min_quality"])
            if model:
                return model

        # Check for open source preference
        if hints and hints.get("prefer_open_source"):
            for model_id in capability.fallback_chain:
                if model_id in capability.models:
                    model = capability.models[model_id]
                    # Simple heuristic: assume models with 'open' in license name
                    if "open" in model.license.lower():
                        return model_id

        # Default: use first available model from fallback chain
        return capability.get_best_available_model()

    async def _execute_generation(
        self,
        capability_type: str,
        model,
        provider,
        generation_params: Dict,
        result_type: str,
    ):
        """Execute actual generation call using provider adapters.

        Routes requests to the appropriate provider adapter based on capability and model.

        Args:
            capability_type: Type of capability (image_generation, video_generation, etc.)
            model: ModelCapability object with model metadata
            provider: Provider object with provider metadata
            generation_params: Generation parameters (prompt, duration, etc.)
            result_type: Expected result type (image, video, audio)

        Returns:
            ImageResult, VideoResult, or AudioResult depending on result_type

        Raises:
            Exception: If generation fails in the adapter
        """
        logger.debug(
            f"Executing {capability_type} with {model.model_id} on {provider.name} (adapter-backed)"
        )

        # Get the adapter for this provider
        adapter_config = {
            "api_key": os.getenv(provider.api_key_env) if provider.api_key_env else None,
            "timeout": provider.timeout_seconds,
            "max_retries": provider.max_retries,
        }
        # Add provider-specific configuration if available
        if provider.metadata:
            adapter_config.update(provider.metadata)

        adapter = self.adapter_registry.get_adapter(provider.name, **adapter_config)

        # Validate adapter credentials
        if not await adapter.validate_credentials():
            raise ModelNotAvailableError(f"Provider {provider.name} credentials are invalid")

        # Call appropriate adapter method based on capability
        try:
            if capability_type == "image_generation":
                adapter_result = await adapter.generate_image(
                    prompt=generation_params.get("prompt"),
                    model_id=model.model_id,
                    width=generation_params.get("width"),
                    height=generation_params.get("height"),
                    num_inference_steps=generation_params.get("num_inference_steps"),
                )
                return ImageResult(
                    image_url=adapter_result["image_url"],
                    model_id=model.model_id,
                    provider=provider.name,
                    metadata=adapter_result.get("metadata", {}),
                )
            elif capability_type == "video_generation":
                adapter_result = await adapter.generate_video(
                    prompt=generation_params.get("prompt"),
                    model_id=model.model_id,
                    duration=generation_params.get("duration", 5),
                    num_frames=generation_params.get("num_frames"),
                )
                return VideoResult(
                    video_url=adapter_result["video_url"],
                    model_id=model.model_id,
                    provider=provider.name,
                    duration_seconds=adapter_result.get("duration_seconds", 5),
                    metadata=adapter_result.get("metadata", {}),
                )
            elif capability_type == "voice_tts":
                adapter_result = await adapter.generate_voice(
                    text=generation_params.get("text"),
                    model_id=model.model_id,
                    voice_profile=generation_params.get("voice_profile", "default"),
                    language=generation_params.get("language"),
                )
                return AudioResult(
                    audio_url=adapter_result["audio_url"],
                    model_id=model.model_id,
                    provider=provider.name,
                    voice_profile=adapter_result.get("voice_profile", "default"),
                    metadata=adapter_result.get("metadata", {}),
                )
            elif capability_type == "background_removal":
                adapter_result = await adapter.remove_background(
                    image_url=generation_params.get("image_url"),
                    model_id=model.model_id,
                    output_format=generation_params.get("output_format", "png"),
                )
                return ImageResult(
                    image_url=adapter_result["image_url"],
                    model_id=model.model_id,
                    provider=provider.name,
                    metadata=adapter_result.get("metadata", {}),
                )
            else:
                raise ValueError(f"Unknown capability type: {capability_type}")
        except NotImplementedError as e:
            logger.error(
                f"Capability {capability_type} not supported by adapter {provider.name}: {e}"
            )
            raise
        except Exception as e:
            logger.error(f"Adapter {provider.name} failed for {capability_type}: {e}")
            raise

    async def _try_fallback_chain(
        self,
        capability,
        generation_params: Dict,
        result_type: str,
        tried_model: str,
    ):
        """Try remaining models in fallback chain.

        Args:
            capability: CapabilityGroup with fallback chain
            generation_params: Parameters for generation
            result_type: Type of result expected
            tried_model: Model ID that already failed

        Returns:
            Generation result or raises exception if all models fail
        """
        logger.info(f"Attempting fallback models for {capability.capability_type}")

        for model_id in capability.fallback_chain:
            if model_id == tried_model:
                continue  # Skip already-tried model

            if model_id not in capability.models:
                logger.warning(f"Model {model_id} in fallback chain not found, skipping")
                continue

            model = capability.models[model_id]
            provider = self.registry.get_provider(model.provider)

            try:
                result = await self._execute_generation(
                    capability_type=capability.capability_type,
                    model=model,
                    provider=provider,
                    generation_params=generation_params,
                    result_type=result_type,
                )
                self.health_monitor.mark_success(model.provider)
                logger.info(f"Fallback model {model_id} succeeded")
                return result
            except Exception as e:
                logger.warning(f"Fallback model {model_id} failed: {e}")
                self.health_monitor.mark_failure(model.provider, str(e))
                continue

        # All models failed
        raise ModelNotAvailableError(
            f"All models in fallback chain failed for {capability.capability_type}"
        )

    async def check_provider_availability(self) -> Dict[str, bool]:
        """Check availability of all providers.

        Returns:
            Dict mapping provider names to availability status
        """
        results = {}
        for provider_name in self.registry.list_providers():
            results[provider_name] = self.health_monitor.is_healthy(provider_name)
        return results

    def get_provider_features(self, provider_name: str) -> Dict:
        """Get feature capabilities for a specific provider.

        Args:
            provider_name: Name of the provider

        Returns:
            Dict with feature information for the provider

        Raises:
            InvalidConfigurationError: If provider not found
        """
        features = self.adapter_registry.get_features(provider_name)
        return {
            "provider": provider_name,
            "supports_image_generation": features.supports_image_generation,
            "supports_video_generation": features.supports_video_generation,
            "supports_voice_tts": features.supports_voice_tts,
            "supports_background_removal": features.supports_background_removal,
            "supports_async": features.supports_async,
            "requires_authentication": features.requires_authentication,
            "rate_limit_per_minute": features.rate_limit_per_minute,
            "max_concurrent_requests": features.max_concurrent_requests,
            "supported_formats": {
                "image": features.supported_image_formats,
                "video": features.supported_video_formats,
                "audio": features.supported_audio_formats,
            },
        }

    def get_all_provider_features(self) -> Dict[str, Dict]:
        """Get feature capabilities for all providers.

        Returns:
            Dict mapping provider names to their feature information
        """
        features = {}
        for provider_name in self.adapter_registry.list_providers():
            try:
                features[provider_name] = self.get_provider_features(provider_name)
            except Exception as e:
                logger.warning(f"Could not get features for {provider_name}: {e}")
        return features

    def get_health_summary(self) -> Dict:
        """Get overall health summary of all providers and capabilities.

        Returns:
            Dict with health status information
        """
        return {
            "healthy_providers": self.health_monitor.get_healthy_providers(),
            "unhealthy_providers": self.health_monitor.get_unhealthy_providers(),
            "all_health_status": {
                name: {
                    "is_healthy": health.is_healthy,
                    "consecutive_failures": health.consecutive_failures,
                    "last_error": health.last_error,
                    "last_check": health.last_check.isoformat() if health.last_check else None,
                }
                for name, health in self.health_monitor.get_all_health_status().items()
            },
        }
