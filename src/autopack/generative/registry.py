"""Model metadata registry for generative AI capabilities."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .exceptions import InvalidConfigurationError


@dataclass
class Provider:
    """Provider configuration and metadata."""

    name: str
    endpoint: str
    api_key_env: Optional[str] = None
    timeout_seconds: int = 120
    max_retries: int = 3
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class ModelCapability:
    """A specific AI capability/model within a capability type."""

    model_id: str
    provider: str
    name: str
    quality_score: float  # 0.0 to 1.0
    cost_per_unit: float
    license: str
    supported_params: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate configuration."""
        if not 0.0 <= self.quality_score <= 1.0:
            raise InvalidConfigurationError(
                f"Quality score must be between 0.0 and 1.0, got {self.quality_score}"
            )
        if self.cost_per_unit < 0:
            raise InvalidConfigurationError(f"Cost must be non-negative, got {self.cost_per_unit}")


@dataclass
class CapabilityGroup:
    """Group of models for a specific AI capability."""

    capability_type: str  # 'image_generation', 'video_generation', etc.
    default_model: str
    fallback_chain: List[str]
    min_acceptable_quality: float = 0.80
    prefer_open_source_if_above: float = 0.85
    models: Dict[str, ModelCapability] = field(default_factory=dict)

    def __post_init__(self):
        """Validate configuration."""
        if not self.fallback_chain:
            raise InvalidConfigurationError(f"Fallback chain required for {self.capability_type}")
        if self.default_model not in self.fallback_chain:
            raise InvalidConfigurationError(
                f"Default model '{self.default_model}' not in fallback chain"
            )
        if not 0.0 <= self.min_acceptable_quality <= 1.0:
            raise InvalidConfigurationError(
                f"min_acceptable_quality must be 0.0-1.0, got {self.min_acceptable_quality}"
            )
        if not 0.0 <= self.prefer_open_source_if_above <= 1.0:
            raise InvalidConfigurationError(
                f"prefer_open_source_if_above must be 0.0-1.0, got {self.prefer_open_source_if_above}"
            )

    def get_best_available_model(self) -> str:
        """Get the best available model from the fallback chain."""
        for model_id in self.fallback_chain:
            if model_id in self.models:
                return model_id
        raise InvalidConfigurationError(
            f"No valid models in fallback chain for {self.capability_type}"
        )

    def get_model_by_quality(self, min_quality: float) -> Optional[str]:
        """Get a model meeting minimum quality threshold."""
        candidates = [
            (model_id, model)
            for model_id, model in self.models.items()
            if model.quality_score >= min_quality
        ]

        if not candidates:
            return None

        # Sort by quality (descending)
        candidates.sort(key=lambda x: x[1].quality_score, reverse=True)

        # Prefer models from fallback chain order
        for model_id in self.fallback_chain:
            for cand_id, cand_model in candidates:
                if cand_id == model_id:
                    return cand_id

        # If no chain preference match, return the best quality
        return candidates[0][0]


class ModelRegistry:
    """Central registry for all generative AI models and capabilities."""

    def __init__(self):
        """Initialize the registry."""
        self.providers: Dict[str, Provider] = {}
        self.capabilities: Dict[str, CapabilityGroup] = {}

    def register_provider(self, provider: Provider) -> None:
        """Register a provider."""
        if provider.name in self.providers:
            raise InvalidConfigurationError(f"Provider '{provider.name}' already registered")
        self.providers[provider.name] = provider

    def register_capability(self, capability: CapabilityGroup) -> None:
        """Register a capability group."""
        if capability.capability_type in self.capabilities:
            raise InvalidConfigurationError(
                f"Capability '{capability.capability_type}' already registered"
            )
        self.capabilities[capability.capability_type] = capability

    def get_provider(self, provider_name: str) -> Provider:
        """Get provider by name."""
        if provider_name not in self.providers:
            raise InvalidConfigurationError(f"Provider '{provider_name}' not found")
        return self.providers[provider_name]

    def get_capability(self, capability_type: str) -> CapabilityGroup:
        """Get capability group by type."""
        if capability_type not in self.capabilities:
            raise InvalidConfigurationError(f"Capability '{capability_type}' not found")
        return self.capabilities[capability_type]

    def list_providers(self) -> List[str]:
        """List all registered provider names."""
        return list(self.providers.keys())

    def list_capabilities(self) -> List[str]:
        """List all registered capability types."""
        return list(self.capabilities.keys())
