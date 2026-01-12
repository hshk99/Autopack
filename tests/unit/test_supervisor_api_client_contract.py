"""Contract tests for Supervisor API client.

These tests verify the SupervisorApiClient behavior contract for PR-EXE-1.
"""

import pytest
from unittest.mock import MagicMock, patch

from autopack.supervisor.api_client import (
    SupervisorApiClient,
    ApiResult,
    ApiErrorType,
    ApprovalStatus,
    ClarificationStatus,
)


class TestSupervisorApiClientInit:
    """Contract tests for client initialization."""

    def test_strips_trailing_slash_from_url(self):
        """Contract: API URL should not have trailing slash."""
        client = SupervisorApiClient("http://localhost:8000/")
        assert client.api_url == "http://localhost:8000"

    def test_preserves_url_without_trailing_slash(self):
        """Contract: API URL without trailing slash is preserved."""
        client = SupervisorApiClient("http://localhost:8000")
        assert client.api_url == "http://localhost:8000"

    def test_stores_api_key(self):
        """Contract: API key is stored for header generation."""
        client = SupervisorApiClient("http://localhost:8000", api_key="test-key")
        assert client.api_key == "test-key"


class TestHeaderGeneration:
    """Contract tests for header generation."""

    def test_headers_include_api_key_when_set(self):
        """Contract: X-API-Key header is included when api_key is set."""
        client = SupervisorApiClient("http://localhost:8000", api_key="test-key")
        headers = client._headers()
        assert headers["X-API-Key"] == "test-key"

    def test_headers_exclude_api_key_when_not_set(self):
        """Contract: X-API-Key header is omitted when api_key is None."""
        client = SupervisorApiClient("http://localhost:8000", api_key=None)
        headers = client._headers()
        assert "X-API-Key" not in headers

    def test_headers_include_content_type_when_requested(self):
        """Contract: Content-Type header is included when requested."""
        client = SupervisorApiClient("http://localhost:8000")
        headers = client._headers(include_content_type=True)
        assert headers["Content-Type"] == "application/json"

    def test_headers_exclude_content_type_by_default(self):
        """Contract: Content-Type header is omitted by default."""
        client = SupervisorApiClient("http://localhost:8000")
        headers = client._headers()
        assert "Content-Type" not in headers


class TestErrorClassification:
    """Contract tests for error classification."""

    def test_classifies_404_as_not_found(self):
        """Contract: 404 is classified as NOT_FOUND."""
        client = SupervisorApiClient("http://localhost:8000")
        assert client._classify_error(404) == ApiErrorType.NOT_FOUND

    def test_classifies_422_as_schema_validation(self):
        """Contract: 422 is classified as SCHEMA_VALIDATION."""
        client = SupervisorApiClient("http://localhost:8000")
        assert client._classify_error(422) == ApiErrorType.SCHEMA_VALIDATION

    def test_classifies_401_as_unauthorized(self):
        """Contract: 401 is classified as UNAUTHORIZED."""
        client = SupervisorApiClient("http://localhost:8000")
        assert client._classify_error(401) == ApiErrorType.UNAUTHORIZED

    def test_classifies_403_as_unauthorized(self):
        """Contract: 403 is classified as UNAUTHORIZED."""
        client = SupervisorApiClient("http://localhost:8000")
        assert client._classify_error(403) == ApiErrorType.UNAUTHORIZED

    def test_classifies_400_as_client_error(self):
        """Contract: 400 is classified as CLIENT_ERROR."""
        client = SupervisorApiClient("http://localhost:8000")
        assert client._classify_error(400) == ApiErrorType.CLIENT_ERROR

    def test_classifies_500_as_server_error(self):
        """Contract: 500 is classified as SERVER_ERROR."""
        client = SupervisorApiClient("http://localhost:8000")
        assert client._classify_error(500) == ApiErrorType.SERVER_ERROR


class TestHealthCheck:
    """Contract tests for health check endpoint."""

    def test_health_check_success(self):
        """Contract: Health check returns success when service is autopack."""
        client = SupervisorApiClient("http://localhost:8000")

        with patch("autopack.supervisor.api_client.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"service": "autopack", "status": "healthy"}
            mock_get.return_value = mock_response

            result = client.check_health()

            assert result.success is True
            assert result.status_code == 200
            assert result.data["service"] == "autopack"

    def test_health_check_wrong_service(self):
        """Contract: Health check fails when service is not autopack."""
        client = SupervisorApiClient("http://localhost:8000")

        with patch("autopack.supervisor.api_client.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"service": "other", "status": "healthy"}
            mock_get.return_value = mock_response

            result = client.check_health()

            assert result.success is False
            assert "unexpected service" in result.error.lower()

    def test_health_check_non_200(self):
        """Contract: Health check fails on non-200 status."""
        client = SupervisorApiClient("http://localhost:8000")

        with patch("autopack.supervisor.api_client.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_get.return_value = mock_response

            result = client.check_health()

            assert result.success is False
            assert result.status_code == 503


class TestGetRun:
    """Contract tests for get_run endpoint."""

    def test_get_run_success(self):
        """Contract: get_run returns run data on success."""
        client = SupervisorApiClient("http://localhost:8000", api_key="test-key")

        with patch("autopack.supervisor.api_client.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"id": "run-123", "state": "running"}
            mock_get.return_value = mock_response

            result = client.get_run("run-123")

            assert result.success is True
            assert result.data["id"] == "run-123"
            mock_get.assert_called_once()
            # Verify URL is correct
            call_args = mock_get.call_args
            assert "runs/run-123" in call_args[0][0]

    def test_get_run_404(self):
        """Contract: get_run returns NOT_FOUND error on 404."""
        client = SupervisorApiClient("http://localhost:8000")

        with patch("autopack.supervisor.api_client.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response

            result = client.get_run("nonexistent")

            assert result.success is False
            assert result.error_type == ApiErrorType.NOT_FOUND

    def test_run_exists_true(self):
        """Contract: run_exists returns True when run exists."""
        client = SupervisorApiClient("http://localhost:8000")

        with patch("autopack.supervisor.api_client.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"id": "run-123"}
            mock_get.return_value = mock_response

            assert client.run_exists("run-123") is True

    def test_run_exists_false(self):
        """Contract: run_exists returns False when run doesn't exist."""
        client = SupervisorApiClient("http://localhost:8000")

        with patch("autopack.supervisor.api_client.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response

            assert client.run_exists("nonexistent") is False


class TestSubmitBuilderResult:
    """Contract tests for submit_builder_result endpoint."""

    def test_submit_builder_result_success(self):
        """Contract: submit_builder_result returns success on 200."""
        client = SupervisorApiClient("http://localhost:8000", api_key="test-key")

        with patch("autopack.supervisor.api_client.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"message": "Builder result submitted"}
            mock_post.return_value = mock_response

            payload = {"status": "success", "tokens_used": 1000}
            result = client.submit_builder_result("run-123", "phase-1", payload)

            assert result.success is True
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "runs/run-123/phases/phase-1/builder_result" in call_args[0][0]

    def test_submit_builder_result_schema_error(self):
        """Contract: submit_builder_result returns SCHEMA_VALIDATION on 422."""
        client = SupervisorApiClient("http://localhost:8000")

        with patch("autopack.supervisor.api_client.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 422
            mock_response.json.return_value = {"detail": "Missing field"}
            mock_post.return_value = mock_response

            result = client.submit_builder_result("run-123", "phase-1", {})

            assert result.success is False
            assert result.error_type == ApiErrorType.SCHEMA_VALIDATION


class TestSubmitAuditorResult:
    """Contract tests for submit_auditor_result endpoint."""

    def test_submit_auditor_result_success(self):
        """Contract: submit_auditor_result returns success on 200."""
        client = SupervisorApiClient("http://localhost:8000", api_key="test-key")

        with patch("autopack.supervisor.api_client.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"message": "Auditor result submitted"}
            mock_post.return_value = mock_response

            payload = {"recommendation": "approve", "tokens_used": 500}
            result = client.submit_auditor_result("run-123", "phase-1", payload)

            assert result.success is True


class TestUpdatePhaseStatus:
    """Contract tests for update_phase_status endpoint."""

    def test_update_phase_status_success(self):
        """Contract: update_phase_status returns success on 200."""
        client = SupervisorApiClient("http://localhost:8000", api_key="test-key")

        with patch("autopack.supervisor.api_client.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"message": "Phase updated"}
            mock_post.return_value = mock_response

            result = client.update_phase_status("run-123", "phase-1", "EXECUTING")

            assert result.success is True
            call_args = mock_post.call_args
            assert call_args[1]["json"]["state"] == "EXECUTING"

    def test_update_phase_status_normalizes_blocked(self):
        """Contract: BLOCKED status is normalized to FAILED."""
        client = SupervisorApiClient("http://localhost:8000")

        with patch("autopack.supervisor.api_client.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"message": "Phase updated"}
            mock_post.return_value = mock_response

            client.update_phase_status("run-123", "phase-1", "BLOCKED")

            call_args = mock_post.call_args
            assert call_args[1]["json"]["state"] == "FAILED"


class TestApprovalRequest:
    """Contract tests for approval request endpoint."""

    def test_request_approval_success(self):
        """Contract: request_approval returns approval_id on success."""
        client = SupervisorApiClient("http://localhost:8000", api_key="test-key")

        with patch("autopack.supervisor.api_client.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "status": "pending",
                "approval_id": "approval-123"
            }
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            result = client.request_approval(
                run_id="run-123",
                phase_id="phase-1",
                context="general",
                payload={"info": "test"}
            )

            assert result.success is True
            assert result.data["approval_id"] == "approval-123"

    def test_request_approval_rejected(self):
        """Contract: request_approval returns error when rejected."""
        client = SupervisorApiClient("http://localhost:8000")

        with patch("autopack.supervisor.api_client.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "status": "rejected",
                "reason": "Not allowed"
            }
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            result = client.request_approval(
                run_id="run-123",
                phase_id="phase-1",
                context="general",
                payload={}
            )

            assert result.success is False
            assert "rejected" in result.error.lower()


class TestApprovalPolling:
    """Contract tests for approval polling."""

    def test_poll_approval_approved(self):
        """Contract: poll_approval_status returns approved status."""
        client = SupervisorApiClient("http://localhost:8000")

        with patch("autopack.supervisor.api_client.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "approved"}
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            status = client.poll_approval_status("approval-123", timeout_seconds=10)

            assert status.status == "approved"
            assert status.approval_id == "approval-123"

    def test_poll_approval_rejected(self):
        """Contract: poll_approval_status returns rejected status."""
        client = SupervisorApiClient("http://localhost:8000")

        with patch("autopack.supervisor.api_client.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "rejected", "reason": "Denied"}
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            status = client.poll_approval_status("approval-123", timeout_seconds=10)

            assert status.status == "rejected"
            assert status.reason == "Denied"


class TestClarificationRequest:
    """Contract tests for clarification request endpoint."""

    def test_request_clarification_success(self):
        """Contract: request_clarification returns clarification_id on success."""
        client = SupervisorApiClient("http://localhost:8000", api_key="test-key")

        with patch("autopack.supervisor.api_client.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "status": "pending",
                "clarification_id": "clarify-123"
            }
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            result = client.request_clarification(
                run_id="run-123",
                phase_id="phase-1",
                context="build113_ambiguous_decision",
                payload={"questions": ["What should I do?"]}
            )

            assert result.success is True
            assert result.data["clarification_id"] == "clarify-123"


class TestClarificationPolling:
    """Contract tests for clarification polling."""

    def test_poll_clarification_answered(self):
        """Contract: poll_clarification_status returns response when answered."""
        client = SupervisorApiClient("http://localhost:8000")

        with patch("autopack.supervisor.api_client.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "status": "answered",
                "response": "Do option A"
            }
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            status = client.poll_clarification_status("phase-1", timeout_seconds=10)

            assert status.status == "answered"
            assert status.response == "Do option A"

    def test_poll_clarification_rejected(self):
        """Contract: poll_clarification_status returns rejected status."""
        client = SupervisorApiClient("http://localhost:8000")

        with patch("autopack.supervisor.api_client.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "rejected"}
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            status = client.poll_clarification_status("phase-1", timeout_seconds=10)

            assert status.status == "rejected"
