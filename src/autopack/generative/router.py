"""Generative Model Router - main entry point for all AI capabilities."""

import logging
from dataclasses import dataclass
from typing import Dict, Optional

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

        # Initialize provider health tracking
        for provider_name in self.registry.list_providers():
            self.health_monitor.initialize_provider(provider_name)

        logger.info(
            f"GenerativeModelRouter initialized with "
            f"{len(self.registry.list_providers())} providers and "
            f"{len(self.registry.list_capabilities())} capabilities"
        )

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
        """Execute actual generation call (stub for implementation).

        This is where actual API calls to providers would be made.
        For now, returns mock results.
        """
        # TODO: Implement actual API calls to providers
        # This is a placeholder that should be extended to call real provider APIs

        logger.debug(f"Executing {capability_type} with {model.model_id} " f"on {provider.name}")

        # Mock implementation - replace with actual provider calls
        if result_type == "image":
            return ImageResult(
                image_url=f"mock://image/{model.model_id}",
                model_id=model.model_id,
                provider=model.provider,
                metadata={"capability": capability_type},
            )
        elif result_type == "video":
            return VideoResult(
                video_url=f"mock://video/{model.model_id}",
                model_id=model.model_id,
                provider=model.provider,
                duration_seconds=generation_params.get("duration", 5),
                metadata={"capability": capability_type},
            )
        elif result_type == "audio":
            return AudioResult(
                audio_url=f"mock://audio/{model.model_id}",
                model_id=model.model_id,
                provider=model.provider,
                voice_profile=generation_params.get("voice_profile", "default"),
                metadata={"capability": capability_type},
            )

        raise ValueError(f"Unknown result type: {result_type}")

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
