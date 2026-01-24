"""Custom exceptions for the Autopack framework."""

from typing import Optional, Dict, Any


class AutopackError(Exception):
    """Base exception for all Autopack errors with rich context support."""

    def __init__(
        self,
        message: str,
        run_id: Optional[str] = None,
        phase_id: Optional[str] = None,
        component: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize Autopack error with context.

        Args:
            message: Error message
            run_id: Run ID where error occurred
            phase_id: Phase ID where error occurred
            component: Component name (e.g., 'builder', 'auditor', 'api')
            context: Additional context data
        """
        super().__init__(message)
        self.run_id = run_id
        self.phase_id = phase_id
        self.component = component
        self.context = context or {}


class BuilderError(AutopackError):
    """Base exception for builder-related errors."""

    pass


class NetworkError(BuilderError):
    """Exception raised for network-related errors."""

    def __init__(self, message: str, status_code: int = None):
        """
        Initialize network error.

        Args:
            message: Error message
            status_code: Optional HTTP status code
        """
        super().__init__(message)
        self.status_code = status_code


class APIError(BuilderError):
    """Exception raised for API-related errors."""

    def __init__(self, message: str, status_code: int = None, response_data: dict = None):
        """
        Initialize API error.

        Args:
            message: Error message
            status_code: Optional HTTP status code
            response_data: Optional response data from API
        """
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class PatchValidationError(BuilderError):
    """Exception raised when patch validation fails."""

    pass


class ValidationError(AutopackError):
    """Exception raised for validation errors."""

    pass


class PatchApplicationError(AutopackError):
    """Exception raised when patch application fails."""

    pass


class ApprovalRequiredError(AutopackError):
    """Exception raised when approval required but not granted."""

    pass


class DatabaseError(AutopackError):
    """Exception raised when database operation fails."""

    pass


class LLMAPIError(AutopackError):
    """Exception raised when LLM API call fails."""

    pass


class ConfigurationError(AutopackError):
    """Exception raised when configuration is invalid."""

    pass


class CircuitBreakerOpenError(AutopackError):
    """Exception raised when circuit breaker is open."""

    pass


class ResourceNotFoundError(AutopackError):
    """Exception raised when a required resource is not found."""

    pass


class StateError(AutopackError):
    """Exception raised when operation violates expected state."""

    pass


class IntegrationError(AutopackError):
    """Exception raised when external system integration fails."""

    pass


class TimeoutError(AutopackError):
    """Exception raised when operation times out."""

    pass


class SecurityError(AutopackError):
    """Exception raised for security-related errors."""

    pass


class DataIntegrityError(AutopackError):
    """Exception raised when data integrity is compromised."""

    pass


class ScopeReductionError(AutopackError):
    """Exception raised when scope reduction operation fails."""

    pass


class DiskSpaceError(AutopackError):
    """Exception raised when insufficient disk space is available.

    IMP-SAFETY-007: Prevents disk exhaustion by checking available space before writes.
    """

    def __init__(
        self,
        message: str,
        required_bytes: int = 0,
        available_bytes: int = 0,
        path: Optional[str] = None,
        **kwargs,
    ):
        """Initialize disk space error.

        Args:
            message: Error message
            required_bytes: Bytes required for the operation
            available_bytes: Bytes currently available
            path: Path where the write was attempted
            **kwargs: Additional context for AutopackError
        """
        super().__init__(message, **kwargs)
        self.required_bytes = required_bytes
        self.available_bytes = available_bytes
        self.path = path
