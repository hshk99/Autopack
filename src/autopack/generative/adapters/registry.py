"""Registry for managing provider adapters."""

import logging
from typing import Dict

from ..exceptions import InvalidConfigurationError
from .base import ProviderAdapter

logger = logging.getLogger(__name__)


class AdapterRegistry:
    """Registry for managing provider adapters.

    Provides dynamic provider selection and adapter instantiation.
    """

    def __init__(self):
        """Initialize the adapter registry."""
        self.adapters: Dict[str, ProviderAdapter] = {}
        self.adapter_classes: Dict[str, type] = {}

    def register_adapter_class(self, provider_name: str, adapter_class: type) -> None:
        """Register an adapter class for dynamic instantiation.

        Args:
            provider_name: Name of the provider (e.g., 'together_ai')
            adapter_class: Adapter class (subclass of ProviderAdapter)

        Raises:
            InvalidConfigurationError: If class is not a ProviderAdapter subclass
        """
        if not issubclass(adapter_class, ProviderAdapter):
            raise InvalidConfigurationError(
                f"Adapter class must be a subclass of ProviderAdapter, got {adapter_class}"
            )

        self.adapter_classes[provider_name] = adapter_class
        logger.debug(f"Registered adapter class for provider '{provider_name}'")

    def register_adapter_instance(self, provider_name: str, adapter: ProviderAdapter) -> None:
        """Register a pre-instantiated adapter.

        Args:
            provider_name: Name of the provider
            adapter: Adapter instance

        Raises:
            InvalidConfigurationError: If adapter is invalid type
        """
        if not isinstance(adapter, ProviderAdapter):
            raise InvalidConfigurationError(
                f"Adapter must be instance of ProviderAdapter, got {type(adapter)}"
            )

        self.adapters[provider_name] = adapter
        logger.debug(f"Registered adapter instance for provider '{provider_name}'")

    def get_adapter(self, provider_name: str, **config) -> ProviderAdapter:
        """Get or create an adapter for a provider.

        Args:
            provider_name: Name of the provider
            **config: Configuration for adapter instantiation

        Returns:
            ProviderAdapter instance for the provider

        Raises:
            InvalidConfigurationError: If provider not registered
        """
        # Return existing instance if available
        if provider_name in self.adapters:
            return self.adapters[provider_name]

        # Try to instantiate from registered class
        if provider_name in self.adapter_classes:
            adapter_class = self.adapter_classes[provider_name]
            adapter = adapter_class(name=provider_name, **config)
            self.adapters[provider_name] = adapter
            return adapter

        raise InvalidConfigurationError(
            f"No adapter registered for provider '{provider_name}'. "
            f"Available providers: {list(self.adapter_classes.keys())}"
        )

    def list_providers(self) -> list:
        """List all registered provider names.

        Returns:
            List of provider names
        """
        return list(set(list(self.adapters.keys()) + list(self.adapter_classes.keys())))

    def has_adapter(self, provider_name: str) -> bool:
        """Check if adapter is registered for a provider.

        Args:
            provider_name: Name of the provider

        Returns:
            True if adapter is registered, False otherwise
        """
        return provider_name in self.adapters or provider_name in self.adapter_classes

    def get_features(self, provider_name: str):
        """Get feature capabilities for a provider.

        Args:
            provider_name: Name of the provider

        Returns:
            ProviderFeatures instance

        Raises:
            InvalidConfigurationError: If provider not registered
        """
        adapter = self.get_adapter(provider_name)
        return adapter.features
