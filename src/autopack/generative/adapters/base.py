"""Base adapter class for all model providers."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProviderFeatures:
    """Feature capabilities of a provider."""

    supports_image_generation: bool = False
    supports_video_generation: bool = False
    supports_voice_tts: bool = False
    supports_background_removal: bool = False
    supports_async: bool = True
    requires_authentication: bool = True
    rate_limit_per_minute: Optional[int] = None
    max_concurrent_requests: Optional[int] = None
    supported_image_formats: list = None
    supported_video_formats: list = None
    supported_audio_formats: list = None

    def __post_init__(self):
        """Initialize defaults."""
        if self.supported_image_formats is None:
            self.supported_image_formats = ["png", "jpg", "webp"]
        if self.supported_video_formats is None:
            self.supported_video_formats = ["mp4", "webm"]
        if self.supported_audio_formats is None:
            self.supported_audio_formats = ["mp3", "wav", "m4a"]


class ProviderAdapter(ABC):
    """Abstract base class for provider adapters.

    Each provider implementation must subclass this and implement all abstract methods.
    The adapter acts as an interface between the generative router and the actual provider API.
    """

    def __init__(self, name: str, api_key: Optional[str] = None, **config):
        """Initialize the adapter.

        Args:
            name: Provider name (e.g., 'together_ai', 'runpod')
            api_key: API key for authentication
            **config: Additional provider-specific configuration
        """
        self.name = name
        self.api_key = api_key
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @property
    @abstractmethod
    def features(self) -> ProviderFeatures:
        """Return the feature capabilities of this provider."""
        pass

    @abstractmethod
    async def generate_image(
        self,
        prompt: str,
        model_id: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        num_inference_steps: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate an image from a text prompt.

        Args:
            prompt: Text description of the image
            model_id: Model identifier for this provider
            width: Image width in pixels
            height: Image height in pixels
            num_inference_steps: Number of inference steps
            **kwargs: Additional provider-specific parameters

        Returns:
            Dict with keys: 'image_url', 'metadata' at minimum

        Raises:
            Exception: If generation fails
        """
        pass

    @abstractmethod
    async def generate_video(
        self,
        prompt: str,
        model_id: str,
        duration: int = 5,
        num_frames: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate a video from a text prompt.

        Args:
            prompt: Text description of the video
            model_id: Model identifier for this provider
            duration: Video duration in seconds
            num_frames: Number of frames to generate
            **kwargs: Additional provider-specific parameters

        Returns:
            Dict with keys: 'video_url', 'duration_seconds', 'metadata' at minimum

        Raises:
            Exception: If generation fails
        """
        pass

    @abstractmethod
    async def generate_voice(
        self,
        text: str,
        model_id: str,
        voice_profile: str = "default",
        language: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate voice/TTS from text.

        Args:
            text: Text to convert to speech
            model_id: Model identifier for this provider
            voice_profile: Voice profile/character to use
            language: Language code (e.g., 'en', 'es')
            **kwargs: Additional provider-specific parameters

        Returns:
            Dict with keys: 'audio_url', 'voice_profile', 'metadata' at minimum

        Raises:
            Exception: If generation fails
        """
        pass

    @abstractmethod
    async def remove_background(
        self,
        image_url: str,
        model_id: str,
        output_format: str = "png",
        **kwargs,
    ) -> Dict[str, Any]:
        """Remove background from an image.

        Args:
            image_url: URL of the image to process
            model_id: Model identifier for this provider
            output_format: Output format (png, jpg, webp, etc.)
            **kwargs: Additional provider-specific parameters

        Returns:
            Dict with keys: 'image_url', 'metadata' at minimum

        Raises:
            Exception: If processing fails
        """
        pass

    @abstractmethod
    async def validate_credentials(self) -> bool:
        """Validate that provider credentials are valid.

        Returns:
            True if credentials are valid, False otherwise
        """
        pass

    @abstractmethod
    async def get_available_models(self) -> Dict[str, list]:
        """Get list of available models by capability.

        Returns:
            Dict mapping capability types to lists of model IDs
            Example:
            {
                'image_generation': ['flux-schnell', 'sdxl-turbo'],
                'video_generation': ['hunyuan-video', 'ltx-video'],
                ...
            }
        """
        pass
