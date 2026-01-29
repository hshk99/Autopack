"""
Contract tests for SupervisorApiClient.

These tests verify that the executor's HTTP client:
- Builds URLs correctly
- Includes X-API-Key when configured
- Maps HTTP/network errors to typed outcomes
- Provides a stable interface for executor integration

This enforces the "executor never talks raw HTTP" contract (BUILD-135).
"""

from unittest.mock import Mock, patch

import pytest
import requests

from autopack.supervisor import (
    SupervisorApiClient,
    SupervisorApiHttpError,
    SupervisorApiNetworkError,
    SupervisorApiTimeoutError,
)


class TestSupervisorApiClientConstruction:
    """Test client initialization and configuration."""

    @pytest.mark.parametrize(
        "base_url,expected_base_url",
        [
            ("http://localhost:8000/", "http://localhost:8000"),
            ("http://localhost:8000", "http://localhost:8000"),
        ],
    )
    def test_base_url_normalization(self, base_url: str, expected_base_url: str) -> None:
        """Test that base URL is normalized correctly."""
        client = SupervisorApiClient(base_url)
        assert client.base_url == expected_base_url

    def test_client_stores_api_key(self):
        """API key should be stored if provided."""
        client = SupervisorApiClient("http://localhost:8000", api_key="test-key-123")
        assert client.api_key == "test-key-123"

    def test_client_allows_none_api_key(self):
        """API key can be None for development."""
        client = SupervisorApiClient("http://localhost:8000", api_key=None)
        assert client.api_key is None

    @pytest.mark.parametrize("timeout", [10.0, 15.0, 30.0])
    def test_client_stores_timeout(self, timeout: float) -> None:
        """Client should store provided timeout."""
        client = SupervisorApiClient("http://localhost:8000", default_timeout=timeout)
        assert client.default_timeout == timeout

    def test_client_has_default_timeout(self):
        """Client should have a default timeout."""
        client = SupervisorApiClient("http://localhost:8000")
        assert client.default_timeout == 10.0


class TestSupervisorApiClientHeaders:
    """Test HTTP header construction."""

    def test_headers_include_content_type(self):
        """Headers should always include Content-Type: application/json."""
        client = SupervisorApiClient("http://localhost:8000")
        headers = client._headers()
        assert headers["Content-Type"] == "application/json"

    def test_headers_include_api_key_when_configured(self):
        """Headers should include X-API-Key when api_key is set."""
        client = SupervisorApiClient("http://localhost:8000", api_key="secret-key")
        headers = client._headers()
        assert headers["X-API-Key"] == "secret-key"

    def test_headers_exclude_api_key_when_none(self):
        """Headers should not include X-API-Key when api_key is None."""
        client = SupervisorApiClient("http://localhost:8000", api_key=None)
        headers = client._headers()
        assert "X-API-Key" not in headers


class TestSupervisorApiClientUrlConstruction:
    """Test URL building logic."""

    @pytest.mark.parametrize(
        "path,expected_url",
        [
            ("/health", "http://localhost:8000/health"),
            ("/runs/123", "http://localhost:8000/runs/123"),
            ("health", "http://localhost:8000/health"),
            (
                "/runs/run-123/phases/phase-456/update_status",
                "http://localhost:8000/runs/run-123/phases/phase-456/update_status",
            ),
        ],
    )
    def test_url_construction(self, path: str, expected_url: str) -> None:
        """Test URL joining handles various path formats."""
        client = SupervisorApiClient("http://localhost:8000")
        assert client._url(path) == expected_url


class TestSupervisorApiClientErrorMapping:
    """Test that HTTP/network errors map to typed exceptions."""

    def test_timeout_raises_supervisor_api_timeout_error(self):
        """Timeout should raise SupervisorApiTimeoutError."""
        client = SupervisorApiClient("http://localhost:8000")

        with patch("requests.request", side_effect=requests.Timeout("Timeout")):
            with pytest.raises(SupervisorApiTimeoutError) as exc_info:
                client._request("GET", "/health", timeout=2.0)

            assert "timed out after 2.0s" in str(exc_info.value)

    def test_connection_error_raises_supervisor_api_network_error(self):
        """Connection errors should raise SupervisorApiNetworkError."""
        client = SupervisorApiClient("http://localhost:8000")

        with patch("requests.request", side_effect=requests.ConnectionError("Connection refused")):
            with pytest.raises(SupervisorApiNetworkError) as exc_info:
                client._request("GET", "/health")

            assert "failed" in str(exc_info.value)

    def test_http_error_raises_supervisor_api_http_error_with_status(self):
        """Non-2xx status should raise SupervisorApiHttpError with status code."""
        client = SupervisorApiClient("http://localhost:8000")

        # Mock response with 404
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        mock_response.raise_for_status.side_effect = requests.HTTPError(response=mock_response)

        with patch("requests.request", return_value=mock_response):
            with pytest.raises(SupervisorApiHttpError) as exc_info:
                client._request("GET", "/runs/nonexistent")

            assert exc_info.value.status_code == 404
            assert exc_info.value.response_body == "Not found"

    def test_http_error_extracts_response_body(self):
        """HTTP errors should extract response body for debugging."""
        client = SupervisorApiClient("http://localhost:8000")

        # Mock 500 error with JSON body
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = '{"error": "Internal server error"}'
        mock_response.raise_for_status.side_effect = requests.HTTPError(response=mock_response)

        with patch("requests.request", return_value=mock_response):
            with pytest.raises(SupervisorApiHttpError) as exc_info:
                client._request(
                    "POST", "/runs/123/phases/456/builder_result", json={"test": "data"}
                )

            assert exc_info.value.status_code == 500
            assert "Internal server error" in exc_info.value.response_body


class TestSupervisorApiClientHealthCheck:
    """Test health check method."""

    def test_check_health_returns_json_payload(self):
        """check_health() should return JSON payload on success."""
        client = SupervisorApiClient("http://localhost:8000")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "service": "autopack",
            "status": "healthy",
            "db_ok": True,
        }
        mock_response.raise_for_status = Mock()

        with patch("requests.request", return_value=mock_response) as mock_request:
            result = client.check_health(timeout=2.0)

            assert result == {"service": "autopack", "status": "healthy", "db_ok": True}
            mock_request.assert_called_once_with(
                method="GET",
                url="http://localhost:8000/health",
                headers={"Content-Type": "application/json"},
                json=None,
                timeout=2.0,
            )

    def test_check_health_uses_custom_timeout(self):
        """check_health() should respect custom timeout."""
        client = SupervisorApiClient("http://localhost:8000")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy"}
        mock_response.raise_for_status = Mock()

        with patch("requests.request", return_value=mock_response) as mock_request:
            client.check_health(timeout=5.0)

            assert mock_request.call_args.kwargs["timeout"] == 5.0


class TestSupervisorApiClientRunMethods:
    """Test run-related methods."""

    def test_get_run_constructs_correct_url(self):
        """get_run() should build correct URL with run_id."""
        client = SupervisorApiClient("http://localhost:8000")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"run_id": "run-123", "status": "in_progress"}
        mock_response.raise_for_status = Mock()

        with patch("requests.request", return_value=mock_response) as mock_request:
            result = client.get_run("run-123")

            assert result["run_id"] == "run-123"
            assert mock_request.call_args.kwargs["url"] == "http://localhost:8000/runs/run-123"


class TestSupervisorApiClientPhaseStatusUpdate:
    """Test phase status update method."""

    def test_update_phase_status_posts_correct_payload(self):
        """update_phase_status() should POST state in correct format."""
        client = SupervisorApiClient("http://localhost:8000")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = Mock()

        with patch("requests.request", return_value=mock_response) as mock_request:
            client.update_phase_status("run-123", "phase-456", "in_progress", timeout=30.0)

            assert mock_request.call_args.kwargs["method"] == "POST"
            assert mock_request.call_args.kwargs["json"] == {"state": "in_progress"}
            assert mock_request.call_args.kwargs["timeout"] == 30.0
            assert "phases/phase-456/update_status" in mock_request.call_args.kwargs["url"]


class TestSupervisorApiClientBuilderResults:
    """Test builder result submission."""

    def test_submit_builder_result_posts_to_correct_endpoint(self):
        """submit_builder_result() should POST to /runs/{run_id}/phases/{phase_id}/builder_result."""
        client = SupervisorApiClient("http://localhost:8000")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = Mock()

        payload = {"files_modified": 3, "tokens_used": 1500}

        with patch("requests.request", return_value=mock_response) as mock_request:
            client.submit_builder_result("run-123", "phase-456", payload)

            assert mock_request.call_args.kwargs["method"] == "POST"
            assert mock_request.call_args.kwargs["json"] == payload
            assert (
                "runs/run-123/phases/phase-456/builder_result"
                in mock_request.call_args.kwargs["url"]
            )


class TestSupervisorApiClientAuditorResults:
    """Test auditor result submission."""

    def test_submit_auditor_result_posts_to_correct_endpoint(self):
        """submit_auditor_result() should POST to /runs/{run_id}/phases/{phase_id}/auditor_result."""
        client = SupervisorApiClient("http://localhost:8000")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = Mock()

        payload = {"review_passed": True, "issues_found": 0}

        with patch("requests.request", return_value=mock_response) as mock_request:
            client.submit_auditor_result("run-123", "phase-456", payload)

            assert mock_request.call_args.kwargs["method"] == "POST"
            assert mock_request.call_args.kwargs["json"] == payload
            assert (
                "runs/run-123/phases/phase-456/auditor_result"
                in mock_request.call_args.kwargs["url"]
            )


class TestSupervisorApiClientApprovals:
    """Test approval request and polling."""

    def test_request_approval_posts_payload(self):
        """request_approval() should POST approval request payload."""
        client = SupervisorApiClient("http://localhost:8000")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"approval_id": "approval-789", "status": "pending"}
        mock_response.raise_for_status = Mock()

        payload = {"type": "human", "message": "Review needed", "options": ["approve", "reject"]}

        with patch("requests.request", return_value=mock_response) as mock_request:
            result = client.request_approval(payload)

            assert result["approval_id"] == "approval-789"
            assert mock_request.call_args.kwargs["method"] == "POST"
            assert mock_request.call_args.kwargs["url"] == "http://localhost:8000/approval/request"
            assert mock_request.call_args.kwargs["json"] == payload

    def test_poll_approval_status_gets_status(self):
        """poll_approval_status() should GET approval status by ID."""
        client = SupervisorApiClient("http://localhost:8000")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "approved", "decision": "proceed"}
        mock_response.raise_for_status = Mock()

        with patch("requests.request", return_value=mock_response) as mock_request:
            result = client.poll_approval_status("approval-789")

            assert result["status"] == "approved"
            assert mock_request.call_args.kwargs["method"] == "GET"
            assert "approval/status/approval-789" in mock_request.call_args.kwargs["url"]


class TestSupervisorApiClientClarifications:
    """Test clarification request and polling (Build-113 flow)."""

    def test_request_clarification_posts_payload(self):
        """request_clarification() should POST clarification request."""
        client = SupervisorApiClient("http://localhost:8000")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"phase_id": "phase-456", "status": "pending"}
        mock_response.raise_for_status = Mock()

        payload = {"run_id": "run-123", "phase_id": "phase-456", "question": "Need clarification"}

        with patch("requests.request", return_value=mock_response) as mock_request:
            result = client.request_clarification(payload)

            assert result["phase_id"] == "phase-456"
            assert mock_request.call_args.kwargs["method"] == "POST"
            assert (
                mock_request.call_args.kwargs["url"]
                == "http://localhost:8000/clarification/request"
            )

    def test_poll_clarification_status_gets_status_by_phase_id(self):
        """poll_clarification_status() should GET clarification status by phase_id."""
        client = SupervisorApiClient("http://localhost:8000")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "answered", "clarification": "Do this"}
        mock_response.raise_for_status = Mock()

        with patch("requests.request", return_value=mock_response) as mock_request:
            result = client.poll_clarification_status("phase-456")

            assert result["status"] == "answered"
            assert mock_request.call_args.kwargs["method"] == "GET"
            assert "clarification/status/phase-456" in mock_request.call_args.kwargs["url"]


class TestSupervisorApiClientDefaultTimeout:
    """Test that methods use default timeout when not specified."""

    def test_get_run_uses_default_timeout(self):
        """get_run() should use default timeout when not specified."""
        client = SupervisorApiClient("http://localhost:8000", default_timeout=15.0)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"run_id": "run-123"}
        mock_response.raise_for_status = Mock()

        with patch("requests.request", return_value=mock_response) as mock_request:
            client.get_run("run-123")

            assert mock_request.call_args.kwargs["timeout"] == 15.0

    def test_submit_builder_result_uses_default_timeout(self):
        """submit_builder_result() should use default timeout when not specified."""
        client = SupervisorApiClient("http://localhost:8000", default_timeout=20.0)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = Mock()

        with patch("requests.request", return_value=mock_response) as mock_request:
            client.submit_builder_result("run-123", "phase-456", {"test": "data"})

            assert mock_request.call_args.kwargs["timeout"] == 20.0
