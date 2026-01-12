"""
Supervisor API Client for Executor.

This module provides a typed interface for the executor to communicate with
the Autopack Supervisor API, replacing direct requests.* calls scattered
throughout autonomous_executor.py.

Design rationale:
- Centralize HTTP logic and URL construction
- Provide typed exceptions for network/timeout/API errors
- Enable easier testing via dependency injection
- Enforce "executor never talks raw HTTP" contract (BUILD-135)
"""

import logging
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)


class SupervisorApiError(Exception):
    """Base exception for Supervisor API client errors."""

    pass


class SupervisorApiTimeoutError(SupervisorApiError):
    """Raised when API request times out."""

    pass


class SupervisorApiNetworkError(SupervisorApiError):
    """Raised when network-level error occurs (connection refused, etc)."""

    pass


class SupervisorApiHttpError(SupervisorApiError):
    """Raised when API returns non-2xx HTTP status."""

    def __init__(self, status_code: int, message: str, response_body: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class SupervisorApiClient:
    """
    Client for communicating with the Autopack Supervisor API.

    The executor uses this client to:
    - Check API health and readiness
    - Update phase status and submit results
    - Request and poll approvals/clarifications
    - Fetch run metadata

    All methods return structured data or raise typed exceptions.
    No raw requests.* calls should escape the executor.
    """

    def __init__(self, base_url: str, api_key: Optional[str] = None, default_timeout: float = 10.0):
        """
        Initialize Supervisor API client.

        Args:
            base_url: Base URL of the supervisor API (e.g., "http://localhost:8000")
            api_key: Optional API key for X-API-Key header
            default_timeout: Default request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_timeout = default_timeout

    def _headers(self) -> Dict[str, str]:
        """Build request headers (includes API key if configured)."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _url(self, path: str) -> str:
        """
        Build full URL from path.

        Args:
            path: API path (e.g., "/health", "/runs/123")

        Returns:
            Full URL (e.g., "http://localhost:8000/health")
        """
        # Ensure path starts with /
        if not path.startswith("/"):
            path = "/" + path
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def _request(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> requests.Response:
        """
        Execute HTTP request with error mapping.

        Args:
            method: HTTP method (GET, POST, etc)
            path: API path
            json: Optional JSON body for POST/PUT
            timeout: Request timeout (uses default if None)

        Returns:
            requests.Response object

        Raises:
            SupervisorApiTimeoutError: On timeout
            SupervisorApiNetworkError: On network errors
            SupervisorApiHttpError: On non-2xx HTTP status
        """
        url = self._url(path)
        headers = self._headers()
        timeout_val = timeout if timeout is not None else self.default_timeout

        try:
            response = requests.request(
                method=method, url=url, headers=headers, json=json, timeout=timeout_val
            )
            response.raise_for_status()
            return response

        except requests.Timeout as e:
            raise SupervisorApiTimeoutError(
                f"{method} {path} timed out after {timeout_val}s"
            ) from e

        except requests.ConnectionError as e:
            raise SupervisorApiNetworkError(f"{method} {path} failed: {e}") from e

        except requests.HTTPError as e:
            # Extract response body for debugging
            body = None
            if e.response is not None:
                try:
                    body = e.response.text
                except Exception:
                    pass

            raise SupervisorApiHttpError(
                status_code=e.response.status_code if e.response else 0,
                message=f"{method} {path} returned {e.response.status_code if e.response else 'unknown'}",
                response_body=body,
            ) from e

    def check_health(self, timeout: float = 2.0) -> Dict[str, Any]:
        """
        Check API health and readiness.

        Args:
            timeout: Request timeout in seconds (default: 2.0)

        Returns:
            Health check payload (e.g., {"service": "autopack", "status": "healthy", "db_ok": true})

        Raises:
            SupervisorApiTimeoutError: On timeout
            SupervisorApiNetworkError: On network errors
            SupervisorApiHttpError: On non-2xx HTTP status
        """
        response = self._request("GET", "/health", timeout=timeout)
        return response.json()

    def get_run(self, run_id: str, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Get run metadata.

        Args:
            run_id: Run ID
            timeout: Request timeout (uses default if None)

        Returns:
            Run object (dict)

        Raises:
            SupervisorApiHttpError: On 404 (run not found) or other errors
        """
        response = self._request("GET", f"/runs/{run_id}", timeout=timeout)
        return response.json()

    def update_phase_status(
        self, run_id: str, phase_id: str, status: str, timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        Update phase status.

        Args:
            run_id: Run ID
            phase_id: Phase ID
            status: New status (e.g., "in_progress", "completed", "failed")
            timeout: Request timeout in seconds (default: 30.0)

        Returns:
            API response payload

        Raises:
            SupervisorApiHttpError: On 404 (phase not found) or other errors
        """
        response = self._request(
            "POST",
            f"/runs/{run_id}/phases/{phase_id}/update_status",
            json={"state": status},
            timeout=timeout,
        )
        return response.json()

    def submit_builder_result(
        self, run_id: str, phase_id: str, payload: Dict[str, Any], timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Submit builder phase result.

        Args:
            run_id: Run ID
            phase_id: Phase ID
            payload: Builder result payload
            timeout: Request timeout (uses default if None)

        Returns:
            API response payload

        Raises:
            SupervisorApiHttpError: On 404, 422, or other errors
        """
        response = self._request(
            "POST",
            f"/runs/{run_id}/phases/{phase_id}/builder_result",
            json=payload,
            timeout=timeout,
        )
        return response.json()

    def submit_auditor_result(
        self, run_id: str, phase_id: str, payload: Dict[str, Any], timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Submit auditor review result.

        Args:
            run_id: Run ID
            phase_id: Phase ID
            payload: Auditor result payload
            timeout: Request timeout (uses default if None)

        Returns:
            API response payload

        Raises:
            SupervisorApiHttpError: On 404, 422, or other errors
        """
        response = self._request(
            "POST",
            f"/runs/{run_id}/phases/{phase_id}/auditor_result",
            json=payload,
            timeout=timeout,
        )
        return response.json()

    def request_approval(
        self, payload: Dict[str, Any], timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Request human approval.

        Args:
            payload: Approval request payload (includes type, context, options, etc)
            timeout: Request timeout (uses default if None)

        Returns:
            Approval response (e.g., {"approval_id": "...", "status": "pending"})

        Raises:
            SupervisorApiHttpError: On error
        """
        response = self._request("POST", "/approval/request", json=payload, timeout=timeout)
        return response.json()

    def poll_approval_status(
        self, approval_id: str, timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Poll approval status.

        Args:
            approval_id: Approval ID
            timeout: Request timeout (uses default if None)

        Returns:
            Approval status payload (e.g., {"status": "approved", "decision": "..."})

        Raises:
            SupervisorApiHttpError: On 404 (approval not found) or other errors
        """
        response = self._request("GET", f"/approval/status/{approval_id}", timeout=timeout)
        return response.json()

    def request_clarification(
        self, payload: Dict[str, Any], timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Request clarification for Build-113 scenarios.

        Args:
            payload: Clarification request payload
            timeout: Request timeout (uses default if None)

        Returns:
            Clarification response (e.g., {"phase_id": "...", "status": "pending"})

        Raises:
            SupervisorApiHttpError: On error
        """
        response = self._request("POST", "/clarification/request", json=payload, timeout=timeout)
        return response.json()

    def poll_clarification_status(
        self, phase_id: str, timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Poll clarification status.

        Args:
            phase_id: Phase ID for clarification
            timeout: Request timeout (uses default if None)

        Returns:
            Clarification status payload

        Raises:
            SupervisorApiHttpError: On 404 or other errors
        """
        response = self._request("GET", f"/clarification/status/{phase_id}", timeout=timeout)
        return response.json()
