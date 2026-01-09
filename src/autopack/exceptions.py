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

    def __init__(self, message: str, status_code: Optional[int] = None):
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

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_data: Optional[Dict[str, Any]] = None,
    ):
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
