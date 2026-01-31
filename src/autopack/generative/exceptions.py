"""Custom exceptions for the generative AI abstraction layer."""


class GenerativeModelError(Exception):
    """Base exception for generative model operations."""

    pass


class ModelNotAvailableError(GenerativeModelError):
    """Raised when a requested model is not available."""

    pass


class ProviderTimeoutError(GenerativeModelError):
    """Raised when a provider operation times out."""

    pass


class InvalidConfigurationError(GenerativeModelError):
    """Raised when the generative models configuration is invalid."""

    pass


class HealthCheckFailedError(GenerativeModelError):
    """Raised when provider health check fails."""

    pass


class CapabilityNotSupportedError(GenerativeModelError):
    """Raised when a capability is not supported by the provider."""

    pass
