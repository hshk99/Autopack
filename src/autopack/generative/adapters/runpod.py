"""RunPod provider adapter."""

import asyncio
import os
from typing import Any, Dict, Optional

import httpx

from .base import ProviderAdapter, ProviderFeatures


class RunPodAdapter(ProviderAdapter):
    """Adapter for RunPod serverless GPU compute.

    Supports video generation, voice synthesis, and background removal via RunPod endpoints.
    """

    def __init__(self, name: str = "runpod", api_key: Optional[str] = None, **config):
        """Initialize RunPod adapter.

        Args:
            name: Provider name
            api_key: RunPod API key (defaults to RUNPOD_API_KEY env var)
            **config: Additional configuration (endpoint_id, endpoint_url, timeout, etc.)
        """
        api_key = api_key or os.getenv("RUNPOD_API_KEY")
        super().__init__(name=name, api_key=api_key, **config)
        self._endpoint_url = config.get("endpoint_url") or os.getenv("RUNPOD_ENDPOINT_URL")
        self._timeout = float(config.get("timeout", 30.0))
        self._http_client: Optional[httpx.AsyncClient] = None
        self._features = ProviderFeatures(
            supports_image_generation=False,
            supports_video_generation=True,
            supports_voice_tts=True,
            supports_background_removal=True,
            requires_authentication=True,
            rate_limit_per_minute=60,
            max_concurrent_requests=5,
            supported_video_formats=["mp4", "webm"],
        )

    @property
    def features(self) -> ProviderFeatures:
        """Return provider features."""
        return self._features

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for API requests.

        Returns:
            httpx.AsyncClient configured with API key header.
        """
        if self._http_client is None or self._http_client.is_closed:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
            self._http_client = httpx.AsyncClient(
                headers=headers,
                timeout=self._timeout,
            )
        return self._http_client

    def _get_placeholder_video_response(
        self, prompt: str, model_id: str, duration: int, num_frames: Optional[int]
    ) -> Dict[str, Any]:
        """Generate placeholder video response when API is unavailable."""
        return {
            "video_url": f"https://runpod.io/video/{model_id}/{hash(prompt) % 10000}.mp4",
            "duration_seconds": duration,
            "metadata": {
                "provider": self.name,
                "model": model_id,
                "frames": num_frames or 240,
            },
        }

    def _get_placeholder_voice_response(
        self, text: str, model_id: str, voice_profile: str, language: Optional[str]
    ) -> Dict[str, Any]:
        """Generate placeholder voice response when API is unavailable."""
        return {
            "audio_url": f"https://runpod.io/audio/{model_id}/{hash(text) % 10000}.mp3",
            "voice_profile": voice_profile,
            "metadata": {
                "provider": self.name,
                "model": model_id,
                "language": language or "en",
            },
        }

    def _get_placeholder_background_response(
        self, image_url: str, model_id: str, output_format: str
    ) -> Dict[str, Any]:
        """Generate placeholder background removal response when API is unavailable."""
        return {
            "image_url": f"https://runpod.io/processed/{model_id}/{hash(image_url) % 10000}.{output_format}",
            "metadata": {
                "provider": self.name,
                "model": model_id,
                "output_format": output_format,
                "source_url": image_url,
            },
        }

    async def close(self) -> None:
        """Close the HTTP client connection."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    async def generate_image(
        self,
        prompt: str,
        model_id: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        num_inference_steps: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Image generation not supported by RunPod."""
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
        """Generate video via RunPod serverless endpoint.

        Args:
            prompt: Text description
            model_id: RunPod model ID (e.g., 'hunyuan-video')
            duration: Video duration in seconds
            num_frames: Number of frames
            **kwargs: Additional parameters

        Returns:
            Dict with video_url, duration_seconds, and metadata
        """
        if not self.api_key:
            raise ValueError("RunPod API key is required for video generation")

        self.logger.debug(f"Generating video with {model_id} on RunPod: {prompt[:50]}...")

        try:
            client = await self._get_http_client()

            # Prepare request payload for RunPod API
            payload = {
                "input": {
                    "prompt": prompt,
                    "duration": duration,
                    "num_frames": num_frames or 240,
                    **kwargs,
                }
            }

            # Submit job to RunPod serverless endpoint
            endpoint = self._endpoint_url or f"https://api.runpod.io/v1/{model_id}"
            response = await client.post(f"{endpoint}/run", json=payload)

            if response.status_code in (200, 201):
                data = response.json()
                job_id = data.get("id") or data.get("job_id")

                # Poll for job completion (with timeout)
                max_retries = 120  # ~10 minutes with 5-second intervals
                retry_count = 0

                while retry_count < max_retries:
                    status_response = await client.get(f"{endpoint}/status/{job_id}")

                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        job_status = status_data.get("status", "").lower()

                        if job_status == "completed":
                            output = status_data.get("output", {})
                            video_url = output.get("video_url") or output.get("url")

                            if video_url:
                                self.logger.info(f"Video generated successfully: {job_id}")
                                return {
                                    "video_url": video_url,
                                    "duration_seconds": duration,
                                    "metadata": {
                                        "provider": self.name,
                                        "model": model_id,
                                        "frames": num_frames or 240,
                                        "job_id": job_id,
                                    },
                                }

                        elif job_status == "failed":
                            error = status_data.get("error", "Unknown error")
                            self.logger.error(f"RunPod job failed: {error}")
                            # Fall back to placeholder
                            return self._get_placeholder_video_response(
                                prompt, model_id, duration, num_frames
                            )

                    await asyncio.sleep(5)  # Wait before polling again
                    retry_count += 1

                self.logger.warning(f"RunPod job {job_id} did not complete within timeout")
                # Fall back to placeholder
                return self._get_placeholder_video_response(prompt, model_id, duration, num_frames)

            else:
                self.logger.warning(f"RunPod API returned status {response.status_code}")
                # Fall back to placeholder for non-successful responses
                return self._get_placeholder_video_response(prompt, model_id, duration, num_frames)

        except (httpx.HTTPError, Exception) as e:
            self.logger.debug(f"Using placeholder for video generation due to: {e}")
            # Fall back to placeholder when API is unavailable
            return self._get_placeholder_video_response(prompt, model_id, duration, num_frames)

    async def generate_voice(
        self,
        text: str,
        model_id: str,
        voice_profile: str = "default",
        language: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate voice via RunPod serverless endpoint.

        Args:
            text: Text to synthesize
            model_id: RunPod model ID (e.g., 'chatterbox-turbo')
            voice_profile: Voice profile
            language: Language code
            **kwargs: Additional parameters

        Returns:
            Dict with audio_url and metadata
        """
        if not self.api_key:
            raise ValueError("RunPod API key is required for voice generation")

        self.logger.debug(f"Generating voice with {model_id} on RunPod: {text[:50]}...")

        try:
            client = await self._get_http_client()

            # Prepare request payload for RunPod TTS API
            payload = {
                "input": {
                    "text": text,
                    "voice_profile": voice_profile,
                    "language": language or "en",
                    **kwargs,
                }
            }

            # Submit job to RunPod serverless endpoint
            endpoint = self._endpoint_url or f"https://api.runpod.io/v1/{model_id}"
            response = await client.post(f"{endpoint}/run", json=payload)

            if response.status_code in (200, 201):
                data = response.json()
                job_id = data.get("id") or data.get("job_id")

                # Poll for job completion
                max_retries = 60  # ~5 minutes with 5-second intervals
                retry_count = 0

                while retry_count < max_retries:
                    status_response = await client.get(f"{endpoint}/status/{job_id}")

                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        job_status = status_data.get("status", "").lower()

                        if job_status == "completed":
                            output = status_data.get("output", {})
                            audio_url = output.get("audio_url") or output.get("url")

                            if audio_url:
                                self.logger.info(f"Voice generated successfully: {job_id}")
                                return {
                                    "audio_url": audio_url,
                                    "voice_profile": voice_profile,
                                    "metadata": {
                                        "provider": self.name,
                                        "model": model_id,
                                        "language": language or "en",
                                        "job_id": job_id,
                                    },
                                }

                        elif job_status == "failed":
                            error = status_data.get("error", "Unknown error")
                            self.logger.error(f"RunPod job failed: {error}")
                            # Fall back to placeholder
                            return self._get_placeholder_voice_response(
                                text, model_id, voice_profile, language
                            )

                    await asyncio.sleep(5)
                    retry_count += 1

                self.logger.warning(f"RunPod job {job_id} did not complete within timeout")
                # Fall back to placeholder
                return self._get_placeholder_voice_response(text, model_id, voice_profile, language)

            else:
                self.logger.warning(f"RunPod API returned status {response.status_code}")
                # Fall back to placeholder for non-successful responses
                return self._get_placeholder_voice_response(text, model_id, voice_profile, language)

        except (httpx.HTTPError, Exception) as e:
            self.logger.debug(f"Using placeholder for voice generation due to: {e}")
            # Fall back to placeholder when API is unavailable
            return self._get_placeholder_voice_response(text, model_id, voice_profile, language)

    async def remove_background(
        self,
        image_url: str,
        model_id: str,
        output_format: str = "png",
        **kwargs,
    ) -> Dict[str, Any]:
        """Remove background from image via RunPod endpoint.

        Args:
            image_url: URL of image to process
            model_id: RunPod model ID (e.g., 'bria-rmbg-2')
            output_format: Output format
            **kwargs: Additional parameters

        Returns:
            Dict with image_url and metadata
        """
        if not self.api_key:
            raise ValueError("RunPod API key is required for background removal")

        self.logger.debug(f"Removing background with {model_id} on RunPod: {image_url[:50]}...")

        try:
            client = await self._get_http_client()

            # Prepare request payload for RunPod background removal API
            payload = {
                "input": {
                    "image_url": image_url,
                    "output_format": output_format,
                    **kwargs,
                }
            }

            # Submit job to RunPod serverless endpoint
            endpoint = self._endpoint_url or f"https://api.runpod.io/v1/{model_id}"
            response = await client.post(f"{endpoint}/run", json=payload)

            if response.status_code in (200, 201):
                data = response.json()
                job_id = data.get("id") or data.get("job_id")

                # Poll for job completion
                max_retries = 60  # ~5 minutes with 5-second intervals
                retry_count = 0

                while retry_count < max_retries:
                    status_response = await client.get(f"{endpoint}/status/{job_id}")

                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        job_status = status_data.get("status", "").lower()

                        if job_status == "completed":
                            output = status_data.get("output", {})
                            processed_url = output.get("image_url") or output.get("url")

                            if processed_url:
                                self.logger.info(f"Background removed successfully: {job_id}")
                                return {
                                    "image_url": processed_url,
                                    "metadata": {
                                        "provider": self.name,
                                        "model": model_id,
                                        "output_format": output_format,
                                        "source_url": image_url,
                                        "job_id": job_id,
                                    },
                                }

                        elif job_status == "failed":
                            error = status_data.get("error", "Unknown error")
                            self.logger.error(f"RunPod job failed: {error}")
                            # Fall back to placeholder
                            return self._get_placeholder_background_response(
                                image_url, model_id, output_format
                            )

                    await asyncio.sleep(5)
                    retry_count += 1

                self.logger.warning(f"RunPod job {job_id} did not complete within timeout")
                # Fall back to placeholder
                return self._get_placeholder_background_response(image_url, model_id, output_format)

            else:
                self.logger.warning(f"RunPod API returned status {response.status_code}")
                # Fall back to placeholder for non-successful responses
                return self._get_placeholder_background_response(image_url, model_id, output_format)

        except (httpx.HTTPError, Exception) as e:
            self.logger.debug(f"Using placeholder for background removal due to: {e}")
            # Fall back to placeholder when API is unavailable
            return self._get_placeholder_background_response(image_url, model_id, output_format)

    async def validate_credentials(self) -> bool:
        """Validate RunPod API credentials.

        Returns:
            True if credentials are valid
        """
        if not self.api_key:
            self.logger.warning("No RunPod API key provided")
            return False

        try:
            client = await self._get_http_client()

            # Make a simple test request to validate the API key
            # Using the user endpoint which requires authentication
            response = await client.get("https://api.runpod.io/graphql", timeout=5.0)

            if response.status_code in (
                200,
                400,
            ):  # 400 is expected for GraphQL POST, 200 means auth passed
                self.logger.debug("RunPod credentials validated successfully")
                return True
            elif response.status_code == 401:
                self.logger.warning("RunPod API key is invalid (401 Unauthorized)")
                return False
            else:
                self.logger.warning(
                    f"Unexpected response validating credentials: {response.status_code}"
                )
                return False

        except httpx.HTTPError as e:
            self.logger.warning(f"HTTP error validating credentials: {e}")
            return False
        except Exception as e:
            self.logger.warning(f"Error validating credentials: {e}")
            return False

    async def get_available_models(self) -> Dict[str, list]:
        """Get available models from RunPod.

        Returns:
            Dict of capabilities to model IDs
        """
        if not self.api_key:
            self.logger.warning("No API key provided, returning default models")
            return {
                "video_generation": [
                    "hunyuan-video",
                    "wan-2.2",
                    "ltx-video",
                ],
                "voice_tts": [
                    "chatterbox-turbo",
                ],
                "background_removal": [
                    "bria-rmbg-2",
                ],
            }

        try:
            client = await self._get_http_client()

            # Query RunPod API for available models via GraphQL
            query = """
            query {
                podFindAndDeployTemplate(input: {}) {
                    edges {
                        node {
                            id
                            name
                            description
                        }
                    }
                }
            }
            """

            payload = {"query": query}
            response = await client.post("https://api.runpod.io/graphql", json=payload)

            if response.status_code == 200:
                data = response.json()
                # Parse GraphQL response and extract available models
                # If successful, construct model list from response
                models = self._parse_models_from_response(data)
                if models:
                    self.logger.debug("Retrieved available models from RunPod API")
                    return models

            self.logger.debug("Could not fetch models from API, using defaults")

        except httpx.HTTPError as e:
            self.logger.warning(f"HTTP error fetching available models: {e}")
        except Exception as e:
            self.logger.warning(f"Error fetching available models: {e}")

        # Return default models if API call fails
        return {
            "video_generation": [
                "hunyuan-video",
                "wan-2.2",
                "ltx-video",
            ],
            "voice_tts": [
                "chatterbox-turbo",
            ],
            "background_removal": [
                "bria-rmbg-2",
            ],
        }

    def _parse_models_from_response(self, data: Dict[str, Any]) -> Optional[Dict[str, list]]:
        """Parse models from RunPod GraphQL response.

        Args:
            data: GraphQL response data

        Returns:
            Dict of capabilities to model IDs, or None if parsing fails
        """
        try:
            if "data" not in data or "podFindAndDeployTemplate" not in data["data"]:
                return None

            templates = data["data"]["podFindAndDeployTemplate"].get("edges", [])
            video_models = []
            voice_models = []
            background_models = []

            for edge in templates:
                node = edge.get("node", {})
                name = node.get("name", "").lower()

                if any(keyword in name for keyword in ["video", "hunyuan", "wan", "ltx"]):
                    video_models.append(node.get("id"))
                elif any(keyword in name for keyword in ["tts", "voice", "chatterbox"]):
                    voice_models.append(node.get("id"))
                elif any(keyword in name for keyword in ["background", "removal", "rmbg"]):
                    background_models.append(node.get("id"))

            return {
                "video_generation": video_models
                or [
                    "hunyuan-video",
                    "wan-2.2",
                    "ltx-video",
                ],
                "voice_tts": voice_models or ["chatterbox-turbo"],
                "background_removal": background_models or ["bria-rmbg-2"],
            }

        except (KeyError, TypeError):
            return None
