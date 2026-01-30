"""
API Availability Checker for research pipeline.

Validates API availability and quota limits before recommending them.
Prevents suggesting unavailable or quota-exhausted APIs.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class APIStatus(Enum):
    """Status of an API availability check."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class APIAvailabilityCheck:
    """Result of API availability check."""

    api_name: str
    is_available: bool
    status: APIStatus
    http_status: Optional[int] = None
    quota_limit: Optional[int] = None
    quota_remaining: Optional[int] = None
    response_time_ms: Optional[float] = None
    error_message: Optional[str] = None
    last_checked: datetime = field(default_factory=datetime.now)
    can_authenticate: bool = False
    authentication_required: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "api_name": self.api_name,
            "is_available": self.is_available,
            "status": self.status.value,
            "http_status": self.http_status,
            "quota_limit": self.quota_limit,
            "quota_remaining": self.quota_remaining,
            "response_time_ms": self.response_time_ms,
            "error_message": self.error_message,
            "last_checked": self.last_checked.isoformat(),
            "can_authenticate": self.can_authenticate,
            "authentication_required": self.authentication_required,
        }


class APIAvailabilityChecker:
    """Validates API availability and quotas."""

    # Common API endpoints and their health check paths
    API_ENDPOINTS = {
        "openai": {
            "base_url": "https://api.openai.com",
            "health_path": "/v1/models",
            "authentication_required": True,
            "quota_header": "x-ratelimit-remaining-requests",
            "limit_header": "x-ratelimit-limit-requests",
        },
        "github": {
            "base_url": "https://api.github.com",
            "health_path": "/",
            "authentication_required": False,
            "quota_header": "x-ratelimit-remaining",
            "limit_header": "x-ratelimit-limit",
        },
        "stripe": {
            "base_url": "https://api.stripe.com",
            "health_path": "/v1/charges",
            "authentication_required": True,
            "quota_header": None,
            "limit_header": None,
        },
        "sendgrid": {
            "base_url": "https://api.sendgrid.com",
            "health_path": "/v3/mail/send",
            "authentication_required": True,
            "quota_header": None,
            "limit_header": None,
        },
        "slack": {
            "base_url": "https://slack.com",
            "health_path": "/api/auth.test",
            "authentication_required": True,
            "quota_header": None,
            "limit_header": None,
        },
        "aws": {
            "base_url": "https://sts.amazonaws.com",
            "health_path": "/",
            "authentication_required": True,
            "quota_header": None,
            "limit_header": None,
        },
        "google": {
            "base_url": "https://www.googleapis.com",
            "health_path": "/",
            "authentication_required": True,
            "quota_header": None,
            "limit_header": None,
        },
        "cloudflare": {
            "base_url": "https://api.cloudflare.com",
            "health_path": "/client/v4/user",
            "authentication_required": True,
            "quota_header": None,
            "limit_header": None,
        },
    }

    def __init__(
        self,
        timeout: float = 10.0,
        retries: int = 2,
        api_tokens: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Initialize APIAvailabilityChecker.

        Args:
            timeout: Request timeout in seconds
            retries: Number of retries for failed requests
            api_tokens: Dictionary mapping API names to authentication tokens
        """
        self._timeout = timeout
        self._retries = retries
        self._api_tokens = api_tokens or {}
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create httpx async client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def check_availability(self, api_name: str, custom_endpoint: Optional[str] = None) -> APIAvailabilityCheck:
        """
        Check if API is available and has quota.

        Args:
            api_name: Name of the API to check
            custom_endpoint: Optional custom endpoint URL

        Returns:
            APIAvailabilityCheck result
        """
        try:
            client = await self._get_client()

            # Determine endpoint
            if custom_endpoint:
                url = custom_endpoint
                config = {"authentication_required": False}
            else:
                api_name_lower = api_name.lower()
                if api_name_lower not in self.API_ENDPOINTS:
                    return self._unavailable_check(api_name, "API not in known endpoints list")
                config = self.API_ENDPOINTS[api_name_lower]
                url = config["base_url"] + config["health_path"]

            # Prepare headers
            headers = {}
            if config.get("authentication_required") and api_name.lower() in self._api_tokens:
                token = self._api_tokens[api_name.lower()]
                if api_name.lower() == "openai":
                    headers["Authorization"] = f"Bearer {token}"
                elif api_name.lower() == "github":
                    headers["Authorization"] = f"token {token}"
                elif api_name.lower() in ["stripe", "sendgrid", "cloudflare"]:
                    headers["Authorization"] = f"Bearer {token}"

            # Make request with retries
            response = None
            for attempt in range(self._retries):
                try:
                    response = await client.get(url, headers=headers, follow_redirects=True)
                    break
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    if attempt == self._retries - 1:
                        logger.warning(f"Timeout checking {api_name}: {e}")
                        return self._timeout_check(api_name, str(e))
                    await asyncio.sleep(0.5 * (attempt + 1))

            if response is None:
                return self._unavailable_check(api_name, "Failed to connect after retries")

            # Parse response
            return self._parse_response(api_name, response, config, custom_endpoint is not None)

        except Exception as e:
            logger.error(f"Error checking {api_name}: {e}")
            return APIAvailabilityCheck(
                api_name=api_name,
                is_available=False,
                status=APIStatus.UNKNOWN,
                error_message=f"Unexpected error: {str(e)}",
            )

    async def check_multiple(self, api_names: List[str]) -> List[APIAvailabilityCheck]:
        """
        Check multiple APIs concurrently.

        Args:
            api_names: List of API names to check

        Returns:
            List of APIAvailabilityCheck results
        """
        tasks = [self.check_availability(api_name) for api_name in api_names]
        return await asyncio.gather(*tasks)

    def _parse_response(
        self,
        api_name: str,
        response: httpx.Response,
        config: Dict[str, Any],
        is_custom: bool = False,
    ) -> APIAvailabilityCheck:
        """Parse HTTP response into APIAvailabilityCheck."""
        response_time = getattr(response, "elapsed", None)
        response_time_ms = response_time.total_seconds() * 1000 if response_time else None

        # Determine availability based on status code
        is_available = 200 <= response.status_code < 400
        status = APIStatus.AVAILABLE if is_available else APIStatus.UNAVAILABLE

        # Special case: 401 means auth required, but API is up
        if response.status_code == 401:
            status = APIStatus.AVAILABLE
            is_available = True
            authentication_required = True
        else:
            authentication_required = False

        # Extract quota information if available
        quota_limit = None
        quota_remaining = None

        if not is_custom and config.get("limit_header"):
            limit_header = config["limit_header"]
            remaining_header = config["quota_header"]

            if limit_header in response.headers:
                try:
                    quota_limit = int(response.headers[limit_header])
                except (ValueError, TypeError):
                    pass

            if remaining_header and remaining_header in response.headers:
                try:
                    quota_remaining = int(response.headers[remaining_header])
                except (ValueError, TypeError):
                    pass

        can_authenticate = response.status_code in [401, 403] and not is_custom

        return APIAvailabilityCheck(
            api_name=api_name,
            is_available=is_available,
            status=status,
            http_status=response.status_code,
            quota_limit=quota_limit,
            quota_remaining=quota_remaining,
            response_time_ms=response_time_ms,
            can_authenticate=can_authenticate,
            authentication_required=authentication_required,
        )

    def _unavailable_check(self, api_name: str, error: str) -> APIAvailabilityCheck:
        """Create an unavailable check result."""
        return APIAvailabilityCheck(
            api_name=api_name,
            is_available=False,
            status=APIStatus.UNAVAILABLE,
            error_message=error,
        )

    def _timeout_check(self, api_name: str, error: str) -> APIAvailabilityCheck:
        """Create a timeout check result."""
        return APIAvailabilityCheck(
            api_name=api_name,
            is_available=False,
            status=APIStatus.TIMEOUT,
            error_message=error,
        )

    async def get_health_status(self, api_name: str) -> Dict[str, Any]:
        """
        Get detailed health status for an API.

        Args:
            api_name: Name of the API

        Returns:
            Dictionary with detailed status information
        """
        check = await self.check_availability(api_name)
        return {
            "api_name": api_name,
            "healthy": check.is_available,
            "status": check.status.value,
            "details": check.to_dict(),
        }

    async def validate_apis_for_recommendation(
        self,
        api_names: List[str],
        min_quota_remaining: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Validate APIs before recommending them.

        Args:
            api_names: List of API names to validate
            min_quota_remaining: Minimum quota remaining to consider API usable

        Returns:
            Dictionary with validation results
        """
        checks = await self.check_multiple(api_names)

        valid_apis = []
        unavailable_apis = []
        quota_exhausted = []

        for check in checks:
            if not check.is_available:
                unavailable_apis.append(check.api_name)
            elif (
                min_quota_remaining is not None
                and check.quota_remaining is not None
                and check.quota_remaining < min_quota_remaining
            ):
                quota_exhausted.append(
                    {
                        "api": check.api_name,
                        "remaining": check.quota_remaining,
                        "limit": check.quota_limit,
                    }
                )
            else:
                valid_apis.append(check.api_name)

        return {
            "valid_apis": valid_apis,
            "unavailable_apis": unavailable_apis,
            "quota_exhausted": quota_exhausted,
            "checks": [check.to_dict() for check in checks],
            "recommendation": "proceed" if valid_apis else "blocked",
        }
