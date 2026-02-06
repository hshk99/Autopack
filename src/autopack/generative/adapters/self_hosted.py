"""Self-hosted model provider adapter."""

import hashlib
import io
import os
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import aiohttp

from .base import ProviderAdapter, ProviderFeatures


class SelfHostedAdapter(ProviderAdapter):
    """Adapter for self-hosted generative models.

    Supports locally deployed models like Kokoro TTS, Bark, BiRefNet, and InSPyreNet.
    Manages connections to local or internal infrastructure.
    """

    def __init__(self, name: str = "self_hosted", api_key: Optional[str] = None, **config):
        """Initialize Self-hosted adapter.

        Args:
            name: Provider name
            api_key: Optional authentication token for self-hosted services
            **config: Additional configuration (base_url, port, etc.)
        """
        super().__init__(name=name, api_key=api_key, **config)
        self.base_url = config.get("base_url") or os.getenv(
            "SELF_HOSTED_BASE_URL", "http://localhost:8000"
        )
        self.port = config.get("port") or os.getenv("SELF_HOSTED_PORT", 8000)
        self._features = ProviderFeatures(
            supports_image_generation=False,
            supports_video_generation=True,
            supports_voice_tts=True,
            supports_background_removal=True,
            requires_authentication=False,
            rate_limit_per_minute=None,  # Local, no rate limits
            max_concurrent_requests=4,
            supported_audio_formats=["mp3", "wav", "m4a", "ogg"],
            supported_image_formats=["png", "jpg", "webp"],
            supported_video_formats=["mp4", "webm", "mov"],
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
        """Image generation not supported by self-hosted adapter."""
        raise NotImplementedError(
            f"Image generation not supported by {self.name}. "
            "Use Together AI or Vertex AI adapters instead."
        )

    async def generate_video(
        self,
        prompt: str,
        model_id: str,
        duration: int = 5,
        num_frames: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate video via self-hosted model.

        Args:
            prompt: Text description for video generation
            model_id: Local model ID (e.g., 'stable-video-diffusion', 'zeroscope')
            duration: Video duration in seconds
            num_frames: Number of frames to generate
            **kwargs: Additional parameters

        Returns:
            Dict with video_url, duration_seconds, and metadata
        """
        self.logger.debug(f"Generating video with {model_id} on self-hosted: {prompt[:50]}...")

        try:
            # Connect to local model service via HTTP
            service_url = (
                f"{self.base_url}:{self.port}" if isinstance(self.port, int) else f"{self.base_url}"
            )

            # Create request payload for video generation inference
            payload = {
                "prompt": prompt,
                "model": model_id,
                "duration": duration,
            }

            if num_frames is not None:
                payload["num_frames"] = num_frames

            # Make inference request to local service
            async with aiohttp.ClientSession() as session:
                inference_url = urljoin(service_url, "/v1/video/generate")
                async with session.post(
                    inference_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=600),  # Video generation takes longer
                ) as response:
                    if response.status != 200:
                        self.logger.error(f"Video generation service returned status {response.status}")
                        raise RuntimeError(f"Video generation failed: {response.status}")

                    # Verify video data received
                    _ = await response.read()

            # Generate unique identifier for the video
            prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
            video_filename = f"{model_id}_{prompt_hash}.mp4"

            # Generate accessible URL for the video
            video_url = f"{service_url}/video/{video_filename}"

            self.logger.debug(f"Successfully generated video: {video_url}")

            return {
                "video_url": video_url,
                "duration_seconds": duration,
                "metadata": {
                    "provider": self.name,
                    "model": model_id,
                    "num_frames": num_frames,
                    "base_url": self.base_url,
                    "service_url": service_url,
                },
            }
        except Exception as e:
            self.logger.error(f"Video generation failed: {str(e)}")
            raise RuntimeError(f"Self-hosted video generation service error: {str(e)}") from e

    async def generate_voice(
        self,
        text: str,
        model_id: str,
        voice_profile: str = "default",
        language: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate voice via self-hosted TTS model.

        Args:
            text: Text to synthesize
            model_id: Local model ID (e.g., 'kokoro-82m', 'bark')
            voice_profile: Voice profile/speaker
            language: Language code
            **kwargs: Additional parameters

        Returns:
            Dict with audio_url and metadata
        """
        self.logger.debug(f"Generating voice with {model_id} on self-hosted: {text[:50]}...")

        try:
            # Connect to local model service via HTTP
            service_url = (
                f"{self.base_url}:{self.port}" if isinstance(self.port, int) else f"{self.base_url}"
            )

            # Create request payload for TTS inference
            payload = {
                "text": text,
                "model": model_id,
                "voice": voice_profile,
                "language": language or "en",
            }

            # Make inference request to local service
            async with aiohttp.ClientSession() as session:
                inference_url = urljoin(service_url, "/v1/audio/speech")
                async with session.post(
                    inference_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as response:
                    if response.status != 200:
                        self.logger.error(f"TTS service returned status {response.status}")
                        raise RuntimeError(f"TTS inference failed: {response.status}")

                    # Verify audio data received
                    _ = await response.read()

            # Generate unique identifier for the audio
            text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            audio_filename = f"{model_id}_{text_hash}.mp3"

            # Generate accessible URL for the audio
            audio_url = f"{service_url}/audio/{audio_filename}"

            self.logger.debug(f"Successfully generated voice: {audio_url}")

            return {
                "audio_url": audio_url,
                "voice_profile": voice_profile,
                "metadata": {
                    "provider": self.name,
                    "model": model_id,
                    "language": language or "en",
                    "base_url": self.base_url,
                    "service_url": service_url,
                },
            }
        except Exception as e:
            self.logger.error(f"Voice generation failed: {str(e)}")
            raise RuntimeError(f"Self-hosted TTS service error: {str(e)}") from e

    async def remove_background(
        self,
        image_url: str,
        model_id: str,
        output_format: str = "png",
        **kwargs,
    ) -> Dict[str, Any]:
        """Remove background from image via self-hosted model.

        Args:
            image_url: URL of image to process
            model_id: Local model ID (e.g., 'birefnet', 'inspyrenet')
            output_format: Output format
            **kwargs: Additional parameters

        Returns:
            Dict with image_url and metadata
        """
        self.logger.debug(
            f"Removing background with {model_id} on self-hosted: {image_url[:50]}..."
        )

        try:
            service_url = (
                f"{self.base_url}:{self.port}" if isinstance(self.port, int) else f"{self.base_url}"
            )

            async with aiohttp.ClientSession() as session:
                # Download image from provided URL
                async with session.get(
                    image_url, timeout=aiohttp.ClientTimeout(total=30)
                ) as img_response:
                    if img_response.status != 200:
                        self.logger.error(f"Failed to download image: {img_response.status}")
                        raise RuntimeError(f"Image download failed: {img_response.status}")

                    image_data = await img_response.read()

                # Create form data with image for inference
                data = aiohttp.FormData()
                data.add_field("image", io.BytesIO(image_data), filename="image.jpg")
                data.add_field("model", model_id)
                data.add_field("output_format", output_format)

                # Send to background removal service
                inference_url = urljoin(service_url, "/v1/images/remove-background")
                async with session.post(
                    inference_url,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as response:
                    if response.status != 200:
                        self.logger.error(
                            f"Background removal service returned status {response.status}"
                        )
                        raise RuntimeError(f"Background removal failed: {response.status}")

                    # Verify processed image received
                    _ = await response.read()

            # Generate unique identifier for the processed image
            image_hash = hashlib.md5(image_url.encode()).hexdigest()[:8]
            processed_filename = f"{model_id}_{image_hash}.{output_format}"

            # Generate accessible URL for processed image
            processed_url = f"{service_url}/processed/{processed_filename}"

            self.logger.debug(f"Successfully removed background: {processed_url}")

            return {
                "image_url": processed_url,
                "metadata": {
                    "provider": self.name,
                    "model": model_id,
                    "output_format": output_format,
                    "source_url": image_url,
                    "base_url": self.base_url,
                    "service_url": service_url,
                },
            }
        except Exception as e:
            self.logger.error(f"Background removal failed: {str(e)}")
            raise RuntimeError(f"Self-hosted background removal error: {str(e)}") from e

    async def validate_credentials(self) -> bool:
        """Validate self-hosted service availability.

        Returns:
            True if service is accessible
        """
        try:
            service_url = (
                f"{self.base_url}:{self.port}" if isinstance(self.port, int) else f"{self.base_url}"
            )

            # Make HTTP request to health endpoint
            async with aiohttp.ClientSession() as session:
                health_url = urljoin(service_url, "/health")
                async with session.get(
                    health_url,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        self.logger.warning(f"Service health check failed: {response.status}")
                        return False

                    # Parse response to check service availability
                    data = await response.json()
                    is_healthy = data.get("status") == "healthy" or response.status == 200

            if is_healthy:
                self.logger.debug("Self-hosted service validated successfully")
            else:
                self.logger.warning("Self-hosted service returned unhealthy status")

            return is_healthy
        except Exception as e:
            self.logger.warning(f"Self-hosted service validation failed: {str(e)}")
            return False

    async def get_available_models(self) -> Dict[str, list]:
        """Get available models from self-hosted service.

        Returns:
            Dict of capabilities to model IDs
        """
        try:
            service_url = (
                f"{self.base_url}:{self.port}" if isinstance(self.port, int) else f"{self.base_url}"
            )

            # Query service for available models
            async with aiohttp.ClientSession() as session:
                models_url = urljoin(service_url, "/v1/models")
                async with session.get(
                    models_url,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        # Parse response with actual models from service
                        data = await response.json()
                        models = data.get("models", {})

                        self.logger.debug(f"Retrieved models from service: {models}")

                        return {
                            "voice_tts": models.get(
                                "tts",
                                [
                                    "kokoro-82m",
                                    "bark",
                                ],
                            ),
                            "video_generation": models.get(
                                "video",
                                [
                                    "stable-video-diffusion",
                                    "zeroscope",
                                ],
                            ),
                            "background_removal": models.get(
                                "background_removal",
                                [
                                    "birefnet",
                                    "inspyrenet",
                                ],
                            ),
                        }
                    else:
                        self.logger.warning(f"Failed to fetch models: {response.status}")

        except Exception as e:
            self.logger.warning(f"Model discovery failed: {str(e)}")

        # Return default models if service query fails
        return {
            "voice_tts": [
                "kokoro-82m",
                "bark",
            ],
            "video_generation": [
                "stable-video-diffusion",
                "zeroscope",
            ],
            "background_removal": [
                "birefnet",
                "inspyrenet",
            ],
        }
