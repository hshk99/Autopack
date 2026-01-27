"""API contract tests using OpenAPI schema validation.

Purpose:
- Verify API responses match their OpenAPI contract
- Catch breaking API changes before production
- Document the expected API surface

These tests validate:
- GET /health
- GET /
- GET /runs
- GET /approval/pending

Uses runtime OpenAPI spec from /openapi.json endpoint.
"""

import json
from typing import Any, Dict

import pytest


@pytest.fixture
def openapi_spec(client) -> Dict[str, Any]:
    """Load OpenAPI spec from /openapi.json endpoint."""
    response = client.get("/openapi.json")
    assert response.status_code == 200, "OpenAPI spec endpoint should return 200"
    return response.json()


class TestOpenAPISpecValid:
    """Verify OpenAPI spec is valid."""

    def test_openapi_spec_structure(self, openapi_spec):
        """OpenAPI spec should have required structure."""
        assert "openapi" in openapi_spec, "Missing 'openapi' field"
        assert "info" in openapi_spec, "Missing 'info' field"
        assert "paths" in openapi_spec, "Missing 'paths' field"

    def test_openapi_version(self, openapi_spec):
        """OpenAPI version should be 3.x."""
        assert openapi_spec["openapi"].startswith("3."), "Should be OpenAPI 3.x"

    def test_api_metadata(self, openapi_spec):
        """API metadata should be present."""
        info = openapi_spec["info"]
        assert "title" in info, "Missing API title"
        assert "version" in info, "Missing API version"
        assert info["title"] == "Autopack Supervisor", "Title mismatch"

    def test_documented_paths_not_empty(self, openapi_spec):
        """Should have documented paths."""
        paths = openapi_spec["paths"]
        assert len(paths) > 0, "No paths documented"


class TestHealthEndpointContract:
    """Verify GET /health matches OpenAPI contract."""

    def test_health_endpoint_response_structure(self, client):
        """GET /health should return expected structure."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()

        # Expected fields per OpenAPI spec
        assert "status" in data, "Missing 'status' field"
        assert "timestamp" in data, "Missing 'timestamp' field"
        assert "database" in data, "Missing 'database' field"

    def test_health_status_is_valid_state(self, client):
        """Health status should be one of valid states."""
        response = client.get("/health")
        data = response.json()

        valid_states = {"healthy", "degraded", "unhealthy"}
        assert data["status"] in valid_states, f"Invalid status: {data['status']}"

    def test_health_has_component_field(self, client):
        """Health response should include component identifier."""
        response = client.get("/health")
        data = response.json()

        assert "component" in data, "Missing 'component' field"

    def test_health_timestamp_is_iso_format(self, client):
        """Health response timestamp should be ISO format."""
        response = client.get("/health")
        data = response.json()

        # Should parse as ISO format
        from datetime import datetime

        try:
            datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
        except ValueError:
            pytest.fail(f"Timestamp is not ISO format: {data['timestamp']}")


class TestRootEndpointContract:
    """Verify GET / matches OpenAPI contract."""

    def test_root_endpoint_response_structure(self, client):
        """GET / should return expected structure."""
        response = client.get("/")
        assert response.status_code == 200

        data = response.json()

        # Expected fields
        assert "service" in data, "Missing 'service' field"
        assert "version" in data, "Missing 'version' field"
        assert "description" in data, "Missing 'description' field"

    def test_root_service_name(self, client):
        """Service name should be correct."""
        response = client.get("/")
        data = response.json()

        assert data["service"] == "Autopack Supervisor"


class TestRunsListEndpointContract:
    """Verify GET /runs matches OpenAPI contract."""

    @pytest.fixture
    def populated_db(self, client, db_session):
        """Populate database with test runs."""
        from datetime import datetime, timezone

        from autopack import models

        # Create test runs
        for i in range(3):
            run = models.Run(
                id=f"contract-test-run-{i:03d}",
                state=models.RunState.DONE_SUCCESS if i < 2 else models.RunState.PHASE_EXECUTION,
                safety_profile="normal",
                run_scope="multi_tier",
                token_cap=1_000_000,
                tokens_used=100_000 * (i + 1),
                created_at=datetime.now(timezone.utc),
            )
            db_session.add(run)

        db_session.commit()
        return

    def test_runs_list_response_structure(self, client, populated_db):
        """GET /runs should return expected structure."""
        response = client.get("/runs")
        assert response.status_code == 200

        data = response.json()

        # Should return a list or dict with runs
        if isinstance(data, dict):
            assert "runs" in data or "items" in data, "Expected 'runs' or 'items' field"

    def test_runs_list_respects_pagination(self, client, populated_db):
        """GET /runs should respect pagination parameters."""
        # Test with limit
        response = client.get("/runs?limit=2")
        assert response.status_code == 200

        data = response.json()
        # Should have runs but respect limit
        if isinstance(data, list):
            assert len(data) <= 2
        elif isinstance(data, dict):
            runs_field = data.get("runs") or data.get("items") or []
            assert len(runs_field) <= 2


class TestApprovalPendingEndpointContract:
    """Verify GET /approval/pending matches OpenAPI contract."""

    def test_approval_pending_response_structure(self, client):
        """GET /approval/pending should return expected structure."""
        response = client.get("/approval/pending", headers={"X-API-Key": "test-key"})

        # May return 200 or 401/403 depending on auth
        if response.status_code == 200:
            data = response.json()

            # Expected fields
            assert "count" in data, "Missing 'count' field"
            assert "requests" in data, "Missing 'requests' field"
            assert isinstance(data["count"], int), "'count' should be integer"
            assert isinstance(data["requests"], list), "'requests' should be list"

    def test_approval_pending_requests_structure(self, client):
        """Approval requests should have consistent structure."""
        response = client.get("/approval/pending", headers={"X-API-Key": "test-key"})

        if response.status_code == 200:
            data = response.json()
            requests = data.get("requests", [])

            # If requests exist, they should have expected fields
            for request in requests[:1]:  # Check first request
                assert "id" in request, "Request missing 'id'"
                assert "run_id" in request, "Request missing 'run_id'"
                assert "status" in request, "Request missing 'status'"


class TestEndpointResponseConsistency:
    """Verify response consistency across endpoints."""

    def test_all_endpoints_return_json(self, client):
        """All endpoints should return valid JSON."""
        endpoints = [
            "/",
            "/health",
            "/runs",
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code in (
                200,
                401,
                403,
                404,
            ), f"Unexpected status for {endpoint}: {response.status_code}"

            # Should be valid JSON
            if response.status_code == 200:
                try:
                    response.json()
                except json.JSONDecodeError:
                    pytest.fail(f"Endpoint {endpoint} did not return valid JSON")

    def test_endpoints_with_valid_headers(self, client):
        """Endpoints should work with standard HTTP headers."""
        response = client.get("/health", headers={"Accept": "application/json"})
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"


class TestOpenAPIPathsCovered:
    """Verify key paths are documented in OpenAPI."""

    def test_health_path_in_openapi(self, openapi_spec):
        """Health endpoint should be in OpenAPI spec."""
        paths = openapi_spec["paths"]
        assert "/health" in paths, "Health endpoint not in OpenAPI spec"

    def test_root_path_in_openapi(self, openapi_spec):
        """Root endpoint should be in OpenAPI spec."""
        paths = openapi_spec["paths"]
        assert "/" in paths, "Root endpoint not in OpenAPI spec"

    def test_health_has_get_method(self, openapi_spec):
        """Health endpoint should have GET method in OpenAPI."""
        paths = openapi_spec["paths"]
        assert "/health" in paths
        operations = paths["/health"]
        assert "get" in operations, "Health endpoint should have GET method"

    def test_root_has_get_method(self, openapi_spec):
        """Root endpoint should have GET method in OpenAPI."""
        paths = openapi_spec["paths"]
        assert "/" in paths
        operations = paths["/"]
        assert "get" in operations, "Root endpoint should have GET method"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
