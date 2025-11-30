"""Custom exceptions for the Autopack framework."""


class AutopackError(Exception):
    """Base exception for all Autopack errors."""

    pass


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
