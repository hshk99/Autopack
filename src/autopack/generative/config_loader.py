"""Configuration loader for generative AI models."""

import os
from pathlib import Path
from typing import Dict, Optional

import yaml

from .exceptions import InvalidConfigurationError
from .registry import CapabilityGroup, ModelCapability, ModelRegistry, Provider


class ConfigLoader:
    """Load and parse generative models configuration from YAML."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize config loader.

        Args:
            config_path: Path to generative_models.yaml. If None, uses default.
        """
        self.config_path = config_path or self._get_default_config_path()
        self.registry = ModelRegistry()
        self._load_config()

    def _get_default_config_path(self) -> str:
        """Get default config path."""
        # Try multiple locations
        candidates = [
            Path("config/generative_models.yaml"),
            Path(__file__).parent.parent.parent.parent / "config/generative_models.yaml",
            Path(__file__).parent.parent.parent.parent.parent / "config/generative_models.yaml",
        ]

        for path in candidates:
            if path.exists():
                return str(path)

        raise InvalidConfigurationError(f"generative_models.yaml not found. Searched: {candidates}")

    def _load_config(self) -> None:
        """Load and parse the YAML configuration file."""
        if not os.path.exists(self.config_path):
            raise InvalidConfigurationError(f"Configuration file not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            config = yaml.safe_load(f)

        if not config:
            raise InvalidConfigurationError(f"Configuration file is empty: {self.config_path}")

        # Load providers
        self._load_providers(config.get("providers", {}))

        # Load capabilities and models
        self._load_capabilities(config.get("capabilities", {}))

        # Load quality thresholds
        self._load_quality_thresholds(config.get("quality_thresholds", {}))

    def _load_providers(self, providers_config: Dict) -> None:
        """Load provider definitions."""
        for provider_name, provider_def in providers_config.items():
            try:
                provider = Provider(
                    name=provider_name,
                    endpoint=provider_def.get("endpoint", ""),
                    api_key_env=provider_def.get("api_key_env"),
                    timeout_seconds=provider_def.get("timeout_seconds", 120),
                    max_retries=provider_def.get("max_retries", 3),
                    metadata=provider_def.get("metadata", {}),
                )
                self.registry.register_provider(provider)
            except Exception as e:
                raise InvalidConfigurationError(f"Failed to load provider '{provider_name}': {e}")

    def _load_capabilities(self, capabilities_config: Dict) -> None:
        """Load capability and model definitions."""
        for capability_type, capability_def in capabilities_config.items():
            try:
                # Create model objects first
                models = {}
                for model_id, model_def in capability_def.get("models", {}).items():
                    model = ModelCapability(
                        model_id=model_id,
                        provider=model_def.get("provider", ""),
                        name=model_def.get("name", model_id),
                        quality_score=float(model_def.get("quality_score", 0.0)),
                        cost_per_unit=float(model_def.get("cost_per_unit", 0.0)),
                        license=model_def.get("license", "unknown"),
                        supported_params=model_def.get("supported_params", []),
                    )
                    models[model_id] = model

                # Create capability group
                capability = CapabilityGroup(
                    capability_type=capability_type,
                    default_model=capability_def.get("default_model", ""),
                    fallback_chain=capability_def.get("fallback_chain", []),
                    min_acceptable_quality=float(
                        capability_def.get("min_acceptable_quality", 0.80)
                    ),
                    prefer_open_source_if_above=float(
                        capability_def.get("prefer_open_source_if_above", 0.85)
                    ),
                    models=models,
                )
                self.registry.register_capability(capability)
            except Exception as e:
                raise InvalidConfigurationError(
                    f"Failed to load capability '{capability_type}': {e}"
                )

    def _load_quality_thresholds(self, thresholds_config: Dict) -> None:
        """Load global quality thresholds (for future use)."""
        # Store in registry for reference
        self.registry.quality_thresholds = thresholds_config

    def get_registry(self) -> ModelRegistry:
        """Get the loaded model registry."""
        return self.registry
