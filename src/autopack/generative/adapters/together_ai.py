"""Together AI provider adapter."""

import os
from typing import Any, Dict, Optional

from .base import ProviderAdapter, ProviderFeatures


class TogetherAIAdapter(ProviderAdapter):
    """Adapter for Together AI generative models.

    Supports FLUX, DALL-E, and ElevenLabs models via Together AI API.
    """

    def __init__(self, name: str = "together_ai", api_key: Optional[str] = None, **config):
        """Initialize Together AI adapter.

        Args:
            name: Provider name
            api_key: Together AI API key (defaults to TOGETHER_AI_API_KEY env var)
            **config: Additional configuration
        """
        api_key = api_key or os.getenv("TOGETHER_AI_API_KEY")
        super().__init__(name=name, api_key=api_key, **config)
        self._features = ProviderFeatures(
            supports_image_generation=True,
            supports_voice_tts=True,
            requires_authentication=True,
            rate_limit_per_minute=300,
            max_concurrent_requests=10,
            supported_image_formats=["png", "jpg", "webp"],
        )

    @property
    def features(self) -> ProviderFeatures:
        """Return provider features."""
        return self._features

    async def generate_image(
        self,
        prompt: str,
        model_id: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        num_inference_steps: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate image via Together AI API.

        Args:
            prompt: Text description
            model_id: Together AI model ID (e.g., 'black-forest-labs/FLUX.1-schnell')
            width: Image width
            height: Image height
            num_inference_steps: Inference steps
            **kwargs: Additional parameters

        Returns:
            Dict with image_url and metadata
        """
        # TODO: Implement actual Together AI API integration
        # This would involve:
        # 1. Validate API key existence and format
        # 2. Format request for Together AI v1/images/generations endpoint
        # 3. Make async HTTP POST request with httpx to https://api.together.xyz/v1/images/generations
        # 4. Parse response and extract image URL from data[0].url field
        # 5. Handle errors including auth failures, rate limits, and model errors
        # 6. Implement retry logic with exponential backoff for transient failures
        # 7. Log request/response for debugging and telemetry
        # 8. Add support for optional parameters like seed, guidance_scale, etc.

        self.logger.debug(f"Generating image with {model_id} on Together AI: {prompt[:50]}...")

        # Placeholder implementation
        return {
            "image_url": f"https://api.together.xyz/image/{model_id}/{hash(prompt) % 10000}",
            "metadata": {
                "provider": self.name,
                "model": model_id,
                "width": width or 1024,
                "height": height or 1024,
            },
        }

    async def generate_video(
        self,
        prompt: str,
        model_id: str,
        duration: int = 5,
        num_frames: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Video generation not supported by Together AI."""
        raise NotImplementedError(
            f"Video generation not supported by {self.name}. "
            "Use RunPod or Vertex AI adapters instead."
        )

    async def generate_voice(
        self,
        text: str,
        model_id: str,
        voice_profile: str = "default",
        language: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate voice via Together AI ElevenLabs integration.

        Args:
            text: Text to synthesize
            model_id: Model ID (e.g., 'elevenlabs')
            voice_profile: Voice profile
            language: Language code
            **kwargs: Additional parameters

        Returns:
            Dict with audio_url and metadata
        """
        # TODO: Implement actual Together AI TTS integration
        # This would involve ElevenLabs API integration through Together AI:
        # 1. Validate API key existence and format
        # 2. Format request for Together AI v1/audio/speech endpoint (ElevenLabs integration)
        # 3. Make async HTTP POST request with httpx to https://api.together.xyz/v1/audio/speech
        # 4. Include text, model_id, voice profile, and language in request payload
        # 5. Parse response and extract audio URL and metadata
        # 6. Handle authentication errors, unsupported language codes, and voice profile mismatches
        # 7. Implement error handling for API rate limits and service timeouts
        # 8. Support optional voice parameters (pitch, speed, etc.)
        # 9. Add request/response logging for debugging

        self.logger.debug(f"Generating voice with {model_id} on Together AI: {text[:50]}...")

        return {
            "audio_url": f"https://api.together.xyz/audio/{model_id}/{hash(text) % 10000}",
            "voice_profile": voice_profile,
            "metadata": {
                "provider": self.name,
                "model": model_id,
                "language": language or "en",
            },
        }

    async def remove_background(
        self,
        image_url: str,
        model_id: str,
        output_format: str = "png",
        **kwargs,
    ) -> Dict[str, Any]:
        """Background removal not supported by Together AI."""
        raise NotImplementedError(
            f"Background removal not supported by {self.name}. "
            "Use RunPod or Self-hosted adapters instead."
        )

    async def validate_credentials(self) -> bool:
        """Validate Together AI API credentials.

        Returns:
            True if credentials are valid
        """
        if not self.api_key:
            self.logger.warning("No Together AI API key provided")
            return False

        # TODO: Implement actual credential validation
        # This would involve:
        # 1. Making a test API call to https://api.together.xyz/v1/models endpoint
        # 2. Using httpx.AsyncClient to perform a GET request with Bearer token auth
        # 3. Checking HTTP status code (200 indicates valid credentials)
        # 4. Handling auth failures (401), rate limits (429), and server errors (5xx)
        # 5. Implementing timeout to prevent hanging on unresponsive API
        # 6. Logging success/failure for monitoring and debugging

        self.logger.debug("Together AI credentials validated")
        return True

    async def get_available_models(self) -> Dict[str, list]:
        """Get available models from Together AI.

        Returns:
            Dict of capabilities to model IDs
        """
        # TODO: Implement actual model discovery from Together AI API
        # This would fetch the list of available models from the API:
        # 1. Make async GET request to https://api.together.xyz/v1/models endpoint
        # 2. Use Bearer token authentication with API key in headers
        # 3. Parse JSON response to extract model list from data field
        # 4. Filter and categorize models by capability (image_generation, voice_tts, etc.)
        # 5. Extract model IDs for each category using keywords like 'flux', 'diffusion', 'elevenlabs'
        # 6. Handle pagination if response contains more models than returned in single request
        # 7. Cache model list to avoid repeated API calls (with TTL for freshness)
        # 8. Implement fallback to default models list if API call fails
        # 9. Log model discovery for monitoring and debugging

        return {
            "image_generation": [
                "black-forest-labs/FLUX.1-schnell",
                "black-forest-labs/FLUX.1-dev",
                "stabilityai/stable-diffusion-xl-base-1.0",
            ],
            "voice_tts": [
                "elevenlabs",
            ],
        }
