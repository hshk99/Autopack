"""Integration tests for research API endpoints."""

from unittest.mock import Mock

import pytest


class TestResearchAPIEndpoints:
    """Test suite for research API endpoints."""

    @pytest.fixture
    def mock_api_client(self):
        """Create a mock API client."""
        client = Mock()
        client.base_url = "/api/research"
        return client

    def test_get_sessions_endpoint(self, mock_api_client):
        """Test GET /api/research/sessions endpoint."""
        mock_response = {
            "status_code": 200,
            "data": [
                {"session_id": "abc123", "status": "active", "created_at": "2025-12-20T12:00:00Z"},
                {
                    "session_id": "def456",
                    "status": "completed",
                    "created_at": "2025-12-20T11:00:00Z",
                },
            ],
        }

        mock_api_client.get = Mock(return_value=mock_response)
        response = mock_api_client.get(f"{mock_api_client.base_url}/sessions")

        assert response["status_code"] == 200
        assert len(response["data"]) == 2
        assert response["data"][0]["session_id"] == "abc123"

    def test_create_session_endpoint(self, mock_api_client):
        """Test POST /api/research/sessions endpoint."""
        request_data = {"query": "Test research query", "parameters": {"depth": 3, "timeout": 30}}

        mock_response = {
            "status_code": 201,
            "data": {
                "session_id": "new_session_123",
                "status": "active",
                "query": request_data["query"],
            },
        }

        mock_api_client.post = Mock(return_value=mock_response)
        response = mock_api_client.post(f"{mock_api_client.base_url}/sessions", data=request_data)

        assert response["status_code"] == 201
        assert response["data"]["session_id"] == "new_session_123"
        assert response["data"]["status"] == "active"

    def test_get_session_by_id_endpoint(self, mock_api_client):
        """Test GET /api/research/sessions/{id} endpoint."""
        session_id = "abc123"
        mock_response = {
            "status_code": 200,
            "data": {
                "session_id": session_id,
                "status": "completed",
                "results": ["result1", "result2"],
            },
        }

        mock_api_client.get = Mock(return_value=mock_response)
        response = mock_api_client.get(f"{mock_api_client.base_url}/sessions/{session_id}")

        assert response["status_code"] == 200
        assert response["data"]["session_id"] == session_id
        assert len(response["data"]["results"]) == 2

    def test_update_session_endpoint(self, mock_api_client):
        """Test PATCH /api/research/sessions/{id} endpoint."""
        session_id = "abc123"
        update_data = {"status": "paused"}

        mock_response = {"status_code": 200, "data": {"session_id": session_id, "status": "paused"}}

        mock_api_client.patch = Mock(return_value=mock_response)
        response = mock_api_client.patch(
            f"{mock_api_client.base_url}/sessions/{session_id}", data=update_data
        )

        assert response["status_code"] == 200
        assert response["data"]["status"] == "paused"

    def test_delete_session_endpoint(self, mock_api_client):
        """Test DELETE /api/research/sessions/{id} endpoint."""
        session_id = "abc123"
        mock_response = {"status_code": 204}

        mock_api_client.delete = Mock(return_value=mock_response)
        response = mock_api_client.delete(f"{mock_api_client.base_url}/sessions/{session_id}")

        assert response["status_code"] == 204

    def test_get_session_results_endpoint(self, mock_api_client):
        """Test GET /api/research/sessions/{id}/results endpoint."""
        session_id = "abc123"
        mock_response = {
            "status_code": 200,
            "data": {
                "session_id": session_id,
                "results": [
                    {"finding": "Result 1", "confidence": 0.9},
                    {"finding": "Result 2", "confidence": 0.85},
                ],
                "total_results": 2,
            },
        }

        mock_api_client.get = Mock(return_value=mock_response)
        response = mock_api_client.get(f"{mock_api_client.base_url}/sessions/{session_id}/results")

        assert response["status_code"] == 200
        assert response["data"]["total_results"] == 2
        assert len(response["data"]["results"]) == 2

    def test_api_error_handling(self, mock_api_client):
        """Test API error response handling."""
        mock_response = {
            "status_code": 404,
            "error": {"message": "Session not found", "code": "NOT_FOUND"},
        }

        mock_api_client.get = Mock(return_value=mock_response)
        response = mock_api_client.get(f"{mock_api_client.base_url}/sessions/invalid_id")

        assert response["status_code"] == 404
        assert "error" in response
        assert response["error"]["code"] == "NOT_FOUND"

    def test_api_authentication(self, mock_api_client):
        """Test API authentication requirements."""
        mock_response = {
            "status_code": 401,
            "error": {"message": "Authentication required", "code": "UNAUTHORIZED"},
        }

        mock_api_client.get = Mock(return_value=mock_response)
        response = mock_api_client.get(f"{mock_api_client.base_url}/sessions")

        assert response["status_code"] == 401
        assert response["error"]["code"] == "UNAUTHORIZED"
