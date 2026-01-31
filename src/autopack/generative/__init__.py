"""Generative AI abstraction layer - unified interface for all AI capabilities.

This module provides a hot-swappable abstraction layer for generative AI capabilities
including image generation, video generation, voice synthesis, and background removal.

Key features:
- Provider-agnostic model abstraction
- Configurable fallback chains
- Health monitoring and automatic recovery
- Quality thresholds and model selection
- Async/await support throughout
"""

from .config_loader import ConfigLoader
from .exceptions import (
    CapabilityNotSupportedError,
    GenerativeModelError,
    HealthCheckFailedError,
    InvalidConfigurationError,
    ModelNotAvailableError,
    ProviderTimeoutError,
)
from .health_monitor import HealthMonitor, ProviderHealth
from .registry import CapabilityGroup, ModelCapability, ModelRegistry, Provider
from .router import AudioResult, GenerativeModelRouter, ImageResult, VideoResult

__all__ = [
    # Main classes
    "GenerativeModelRouter",
    # Configuration
    "ConfigLoader",
    "ModelRegistry",
    "CapabilityGroup",
    "ModelCapability",
    "Provider",
    # Health monitoring
    "HealthMonitor",
    "ProviderHealth",
    # Results
    "ImageResult",
    "VideoResult",
    "AudioResult",
    # Exceptions
    "GenerativeModelError",
    "ModelNotAvailableError",
    "ProviderTimeoutError",
    "InvalidConfigurationError",
    "HealthCheckFailedError",
    "CapabilityNotSupportedError",
]
