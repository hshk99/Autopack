"""Supervisor API client - HTTP wrapper for Autopack Supervisor API.

Extracted from autonomous_executor.py as part of PR-EXE-1.
Provides a clean interface for all executor-to-API communication.

This module encapsulates:
- Health checks
- Run status retrieval
- Phase result submission (builder/auditor)
- Phase status updates
- Approval request/polling
- Clarification request/polling
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

import requests
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


class ApiErrorType(Enum):
    """Classification of API errors for retry/circuit-breaker logic."""

    TRANSIENT = "transient"  # Network timeout, 503, etc. - retry
    CLIENT_ERROR = "client_error"  # 4xx - don't retry
    SERVER_ERROR = "server_error"  # 5xx - may retry
    SCHEMA_VALIDATION = "schema_validation"  # 422 - schema mismatch
    NOT_FOUND = "not_found"  # 404 - resource missing
    UNAUTHORIZED = "unauthorized"  # 401/403 - auth issue


@dataclass
class ApiResult:
    """Result of an API call."""

    success: bool
    status_code: Optional[int] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_type: Optional[ApiErrorType] = None


@dataclass
class ApprovalStatus:
    """Status of an approval request."""

    status: str  # "pending", "approved", "rejected"
    approval_id: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class ClarificationStatus:
    """Status of a clarification request."""

    status: str  # "pending", "answered", "rejected"
    clarification_id: Optional[str] = None
    response: Optional[str] = None


class SupervisorApiClient:
    """HTTP client wrapper for Autopack Supervisor API.

    Provides typed methods for all API interactions with consistent
    error handling, retry logic, and header management.
    """

    def __init__(
        self,
        api_url: str,
        api_key: Optional[str] = None,
        default_timeout: int = 10,
    ):
        """Initialize the API client.

        Args:
            api_url: Base URL of the Supervisor API (e.g., "http://localhost:8000")
            api_key: Optional API key for authentication
            default_timeout: Default timeout in seconds for API calls
        """
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.default_timeout = default_timeout

    def _headers(self, include_content_type: bool = False) -> Dict[str, str]:
        """Build request headers."""
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if include_content_type:
            headers["Content-Type"] = "application/json"
        return headers

    def _classify_error(self, status_code: int) -> ApiErrorType:
        """Classify HTTP status code into error type."""
        if status_code == 404:
            return ApiErrorType.NOT_FOUND
        if status_code == 422:
            return ApiErrorType.SCHEMA_VALIDATION
        if status_code in (401, 403):
            return ApiErrorType.UNAUTHORIZED
        if 400 <= status_code < 500:
            return ApiErrorType.CLIENT_ERROR
        if status_code >= 500:
            return ApiErrorType.SERVER_ERROR
        return ApiErrorType.TRANSIENT

    # =========================================================================
    # Health Check
    # =========================================================================

    def check_health(self, timeout: int = 2) -> ApiResult:
        """Check if the Supervisor API is healthy.

        Args:
            timeout: Request timeout in seconds

        Returns:
            ApiResult with success=True if API is healthy and returns service="autopack"
        """
        try:
            response = requests.get(f"{self.api_url}/health", timeout=timeout)
            if response.status_code == 200:
                payload = response.json()
                if payload.get("service") == "autopack":
                    return ApiResult(success=True, status_code=200, data=payload)
                return ApiResult(
                    success=False,
                    status_code=200,
                    error="Health check returned unexpected service identity",
                    error_type=ApiErrorType.CLIENT_ERROR,
                )
            return ApiResult(
                success=False,
                status_code=response.status_code,
                error=f"Health check failed with status {response.status_code}",
                error_type=self._classify_error(response.status_code),
            )
        except RequestException as e:
            return ApiResult(
                success=False,
                error=f"Health check request failed: {e}",
                error_type=ApiErrorType.TRANSIENT,
            )

    # =========================================================================
    # Run Operations
    # =========================================================================

    def get_run(
        self,
        run_id: str,
        timeout: Optional[int] = None,
        max_retries: int = 3,
    ) -> ApiResult:
        """Get run details from the API.

        Args:
            run_id: The run ID to fetch
            timeout: Request timeout (defaults to default_timeout)
            max_retries: Maximum retry attempts for transient errors

        Returns:
            ApiResult with run data on success
        """
        url = f"{self.api_url}/runs/{run_id}"
        timeout = timeout or self.default_timeout

        for attempt in range(max_retries):
            try:
                response = requests.get(
                    url, headers=self._headers(), timeout=timeout
                )
                if response.status_code == 200:
                    return ApiResult(
                        success=True, status_code=200, data=response.json()
                    )

                error_type = self._classify_error(response.status_code)

                # Don't retry client errors
                if error_type in (
                    ApiErrorType.NOT_FOUND,
                    ApiErrorType.CLIENT_ERROR,
                    ApiErrorType.UNAUTHORIZED,
                ):
                    return ApiResult(
                        success=False,
                        status_code=response.status_code,
                        error=f"Run fetch failed: {response.status_code}",
                        error_type=error_type,
                    )

                # Retry transient/server errors with backoff
                if attempt < max_retries - 1:
                    backoff = 2**attempt
                    logger.warning(
                        f"[API] Run fetch attempt {attempt + 1} failed, retrying in {backoff}s"
                    )
                    time.sleep(backoff)
                    continue

            except RequestException as e:
                if attempt < max_retries - 1:
                    backoff = 2**attempt
                    logger.warning(
                        f"[API] Run fetch attempt {attempt + 1} failed: {e}, retrying in {backoff}s"
                    )
                    time.sleep(backoff)
                    continue
                return ApiResult(
                    success=False,
                    error=f"Run fetch failed after {max_retries} attempts: {e}",
                    error_type=ApiErrorType.TRANSIENT,
                )

        return ApiResult(
            success=False,
            error=f"Run fetch failed after {max_retries} attempts",
            error_type=ApiErrorType.TRANSIENT,
        )

    def run_exists(self, run_id: str, timeout: int = 2) -> bool:
        """Check if a run exists in the API database.

        Args:
            run_id: The run ID to check
            timeout: Request timeout

        Returns:
            True if run exists, False otherwise
        """
        result = self.get_run(run_id, timeout=timeout, max_retries=1)
        return result.success

    # =========================================================================
    # Phase Result Submission
    # =========================================================================

    def submit_builder_result(
        self,
        run_id: str,
        phase_id: str,
        payload: Dict[str, Any],
        timeout: int = 10,
        max_retries: int = 3,
    ) -> ApiResult:
        """Submit builder result for a phase.

        Args:
            run_id: The run ID
            phase_id: The phase ID
            payload: Builder result payload containing:
                - phase_id, run_id, run_type
                - allowed_paths, patch_content, files_changed
                - lines_added, lines_removed
                - builder_attempts, tokens_used, duration_minutes
                - probe_results, suggested_issues
                - status ("success" or "failed")
                - notes
            timeout: Request timeout
            max_retries: Maximum retry attempts

        Returns:
            ApiResult with submission status
        """
        url = f"{self.api_url}/runs/{run_id}/phases/{phase_id}/builder_result"

        for attempt in range(max_retries):
            try:
                response = requests.post(
                    url,
                    headers=self._headers(include_content_type=True),
                    json=payload,
                    timeout=timeout,
                )

                if response.status_code == 200:
                    return ApiResult(
                        success=True, status_code=200, data=response.json()
                    )

                error_type = self._classify_error(response.status_code)

                # Log schema validation errors with detail
                if error_type == ApiErrorType.SCHEMA_VALIDATION:
                    try:
                        detail = response.json().get("detail", "Unknown schema error")
                        logger.error(f"[API] Builder result schema error: {detail}")
                    except Exception:
                        pass
                    return ApiResult(
                        success=False,
                        status_code=422,
                        error="Schema validation error",
                        error_type=error_type,
                    )

                # Don't retry client errors
                if error_type in (ApiErrorType.CLIENT_ERROR, ApiErrorType.UNAUTHORIZED):
                    return ApiResult(
                        success=False,
                        status_code=response.status_code,
                        error=f"Builder result submission failed: {response.status_code}",
                        error_type=error_type,
                    )

                # Retry transient/server errors
                if attempt < max_retries - 1:
                    backoff = 2**attempt
                    time.sleep(backoff)
                    continue

            except RequestException as e:
                if attempt < max_retries - 1:
                    backoff = 2**attempt
                    time.sleep(backoff)
                    continue
                return ApiResult(
                    success=False,
                    error=f"Builder result submission failed: {e}",
                    error_type=ApiErrorType.TRANSIENT,
                )

        return ApiResult(
            success=False,
            error=f"Builder result submission failed after {max_retries} attempts",
            error_type=ApiErrorType.TRANSIENT,
        )

    def submit_auditor_result(
        self,
        run_id: str,
        phase_id: str,
        payload: Dict[str, Any],
        timeout: int = 10,
        max_retries: int = 3,
    ) -> ApiResult:
        """Submit auditor result for a phase.

        Args:
            run_id: The run ID
            phase_id: The phase ID
            payload: Auditor result payload containing:
                - phase_id, run_id, run_type
                - allowed_paths, quality_score, issues_found
                - suggested_patches, auditor_attempts, tokens_used
                - recommendation, confidence, review_notes
            timeout: Request timeout
            max_retries: Maximum retry attempts

        Returns:
            ApiResult with submission status
        """
        url = f"{self.api_url}/runs/{run_id}/phases/{phase_id}/auditor_result"

        for attempt in range(max_retries):
            try:
                response = requests.post(
                    url,
                    headers=self._headers(include_content_type=True),
                    json=payload,
                    timeout=timeout,
                )

                if response.status_code == 200:
                    return ApiResult(
                        success=True, status_code=200, data=response.json()
                    )

                error_type = self._classify_error(response.status_code)

                # Handle 422 with backwards-compat fallback
                if error_type == ApiErrorType.SCHEMA_VALIDATION:
                    # Try legacy format
                    fallback_payload = {
                        "success": True,
                        "output": payload.get("review_notes", ""),
                        "files_modified": [],
                        "metadata": payload,
                    }
                    try:
                        fallback_resp = requests.post(
                            url,
                            headers=self._headers(include_content_type=True),
                            json=fallback_payload,
                            timeout=timeout,
                        )
                        if fallback_resp.status_code == 200:
                            return ApiResult(
                                success=True, status_code=200, data=fallback_resp.json()
                            )
                    except Exception:
                        pass

                    return ApiResult(
                        success=False,
                        status_code=422,
                        error="Schema validation error (legacy fallback also failed)",
                        error_type=error_type,
                    )

                # Don't retry client errors
                if error_type in (ApiErrorType.CLIENT_ERROR, ApiErrorType.UNAUTHORIZED):
                    return ApiResult(
                        success=False,
                        status_code=response.status_code,
                        error=f"Auditor result submission failed: {response.status_code}",
                        error_type=error_type,
                    )

                # Retry transient/server errors
                if attempt < max_retries - 1:
                    backoff = 2**attempt
                    time.sleep(backoff)
                    continue

            except RequestException as e:
                if attempt < max_retries - 1:
                    backoff = 2**attempt
                    time.sleep(backoff)
                    continue
                return ApiResult(
                    success=False,
                    error=f"Auditor result submission failed: {e}",
                    error_type=ApiErrorType.TRANSIENT,
                )

        return ApiResult(
            success=False,
            error=f"Auditor result submission failed after {max_retries} attempts",
            error_type=ApiErrorType.TRANSIENT,
        )

    # =========================================================================
    # Phase Status Updates
    # =========================================================================

    def update_phase_status(
        self,
        run_id: str,
        phase_id: str,
        status: str,
        timeout: int = 30,
    ) -> ApiResult:
        """Update phase status.

        Args:
            run_id: The run ID
            phase_id: The phase ID
            status: New phase state (QUEUED, EXECUTING, GATE, CI_RUNNING, COMPLETE, FAILED, SKIPPED)
            timeout: Request timeout

        Returns:
            ApiResult with update status
        """
        url = f"{self.api_url}/runs/{run_id}/phases/{phase_id}/update_status"

        # Normalize BLOCKED to FAILED
        if status == "BLOCKED":
            status = "FAILED"

        try:
            response = requests.post(
                url,
                headers=self._headers(include_content_type=True),
                json={"state": status},
                timeout=timeout,
            )

            if response.status_code == 200:
                return ApiResult(success=True, status_code=200, data=response.json())

            return ApiResult(
                success=False,
                status_code=response.status_code,
                error=f"Phase status update failed: {response.status_code}",
                error_type=self._classify_error(response.status_code),
            )

        except RequestException as e:
            logger.warning(f"[API] Phase status update failed: {e}")
            return ApiResult(
                success=False,
                error=f"Phase status update failed: {e}",
                error_type=ApiErrorType.TRANSIENT,
            )

    # =========================================================================
    # Approval Requests
    # =========================================================================

    def request_approval(
        self,
        run_id: str,
        phase_id: str,
        context: str,
        payload: Dict[str, Any],
        timeout: int = 30,
    ) -> ApiResult:
        """Request approval for an action.

        Args:
            run_id: The run ID
            phase_id: The phase ID
            context: Approval context (e.g., "general", "build113_risky_decision")
            payload: Additional approval request data
            timeout: Request timeout

        Returns:
            ApiResult with approval_id on success
        """
        url = f"{self.api_url}/approval/request"

        request_payload = {
            "phase_id": phase_id,
            "run_id": run_id,
            "context": context,
            **payload,
        }

        try:
            response = requests.post(
                url,
                headers=self._headers(include_content_type=True),
                json=request_payload,
                timeout=timeout,
            )
            response.raise_for_status()
            result = response.json()

            if result.get("status") == "rejected":
                return ApiResult(
                    success=False,
                    status_code=response.status_code,
                    data=result,
                    error=f"Approval request rejected: {result.get('reason')}",
                    error_type=ApiErrorType.CLIENT_ERROR,
                )

            return ApiResult(
                success=True,
                status_code=response.status_code,
                data=result,
            )

        except RequestException as e:
            return ApiResult(
                success=False,
                error=f"Approval request failed: {e}",
                error_type=ApiErrorType.TRANSIENT,
            )

    def poll_approval_status(
        self,
        approval_id: str,
        timeout_seconds: int = 3600,
        poll_interval: int = 10,
    ) -> ApprovalStatus:
        """Poll for approval decision.

        Args:
            approval_id: The approval ID to poll
            timeout_seconds: Maximum time to wait for decision
            poll_interval: Seconds between poll attempts

        Returns:
            ApprovalStatus with final decision
        """
        url = f"{self.api_url}/approval/status/{approval_id}"
        elapsed = 0

        while elapsed < timeout_seconds:
            try:
                response = requests.get(
                    url, headers=self._headers(), timeout=10
                )
                response.raise_for_status()
                status_data = response.json()

                status = status_data.get("status")
                if status == "approved":
                    logger.info("✅ Approval GRANTED by user")
                    return ApprovalStatus(
                        status="approved",
                        approval_id=approval_id,
                    )
                if status == "rejected":
                    logger.warning("❌ Approval REJECTED by user")
                    return ApprovalStatus(
                        status="rejected",
                        approval_id=approval_id,
                        reason=status_data.get("reason"),
                    )

                # Still pending, continue polling
                time.sleep(poll_interval)
                elapsed += poll_interval

            except RequestException as e:
                logger.warning(f"[API] Approval poll failed: {e}")
                time.sleep(poll_interval)
                elapsed += poll_interval

        logger.warning(f"Approval timed out after {timeout_seconds}s")
        return ApprovalStatus(status="timeout", approval_id=approval_id)

    # =========================================================================
    # Clarification Requests
    # =========================================================================

    def request_clarification(
        self,
        run_id: str,
        phase_id: str,
        context: str,
        payload: Dict[str, Any],
        timeout: int = 30,
    ) -> ApiResult:
        """Request clarification from user.

        Args:
            run_id: The run ID
            phase_id: The phase ID
            context: Clarification context (e.g., "build113_ambiguous_decision")
            payload: Additional clarification request data
            timeout: Request timeout

        Returns:
            ApiResult with clarification_id on success
        """
        url = f"{self.api_url}/clarification/request"

        request_payload = {
            "phase_id": phase_id,
            "run_id": run_id,
            "context": context,
            **payload,
        }

        try:
            response = requests.post(
                url,
                headers=self._headers(include_content_type=True),
                json=request_payload,
                timeout=timeout,
            )
            response.raise_for_status()
            result = response.json()

            if result.get("status") == "rejected":
                return ApiResult(
                    success=False,
                    status_code=response.status_code,
                    data=result,
                    error=f"Clarification request rejected: {result.get('reason')}",
                    error_type=ApiErrorType.CLIENT_ERROR,
                )

            return ApiResult(
                success=True,
                status_code=response.status_code,
                data=result,
            )

        except RequestException as e:
            return ApiResult(
                success=False,
                error=f"Clarification request failed: {e}",
                error_type=ApiErrorType.TRANSIENT,
            )

    def poll_clarification_status(
        self,
        phase_id: str,
        timeout_seconds: int = 3600,
        poll_interval: int = 10,
    ) -> ClarificationStatus:
        """Poll for clarification response.

        Args:
            phase_id: The phase ID to poll (clarification is keyed by phase)
            timeout_seconds: Maximum time to wait for response
            poll_interval: Seconds between poll attempts

        Returns:
            ClarificationStatus with response if answered
        """
        url = f"{self.api_url}/clarification/status/{phase_id}"
        elapsed = 0

        while elapsed < timeout_seconds:
            try:
                response = requests.get(
                    url, headers=self._headers(), timeout=10
                )
                response.raise_for_status()
                status_data = response.json()

                status = status_data.get("status")
                if status == "answered":
                    clarification_text = status_data.get("response", "")
                    logger.info(f"✅ Clarification received: {clarification_text[:100]}...")
                    return ClarificationStatus(
                        status="answered",
                        clarification_id=phase_id,
                        response=clarification_text,
                    )
                if status == "rejected":
                    logger.warning("❌ Clarification request rejected by user")
                    return ClarificationStatus(
                        status="rejected",
                        clarification_id=phase_id,
                    )

                # Still pending, continue polling
                time.sleep(poll_interval)
                elapsed += poll_interval

            except RequestException as e:
                logger.warning(f"[API] Clarification poll failed: {e}")
                time.sleep(poll_interval)
                elapsed += poll_interval

        logger.warning(f"Clarification timed out after {timeout_seconds}s")
        return ClarificationStatus(status="timeout", clarification_id=phase_id)
