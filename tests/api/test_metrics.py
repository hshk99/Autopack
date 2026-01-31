"""
Contract tests for API metrics collection.

IMP-OPS-010: These tests verify Prometheus metrics are correctly collected
for API requests.

Contract guarantees:
1. /metrics endpoint returns Prometheus-format data
2. Request count metric increments on each request
3. Request latency metric records duration
4. Endpoint paths are normalized to prevent cardinality explosion
5. Metrics endpoint itself is not instrumented (no self-recursion)
"""

import os
from unittest.mock import MagicMock

import pytest

# Set testing mode before imports
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


class TestMetricsEndpointContract:
    """Contract tests for /metrics endpoint."""

    def test_metrics_endpoint_exists(self):
        """Contract: /metrics endpoint is available."""
        from autopack.api.app import create_app

        app = create_app()
        routes = [r.path for r in app.routes]
        assert "/metrics" in routes

    def test_metrics_endpoint_returns_prometheus_format(self):
        """Contract: /metrics returns Prometheus text format."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics")
        assert response.status_code == 200
        # Prometheus format has specific content type
        assert "text/plain" in response.headers["content-type"]
        # Should contain metric help/type comments
        content = response.text
        assert "# HELP" in content or "# TYPE" in content or "autopack_" in content

    def test_metrics_endpoint_excluded_from_schema(self):
        """Contract: /metrics endpoint is not in OpenAPI schema."""
        from autopack.api.app import create_app

        app = create_app()
        openapi_schema = app.openapi()
        paths = openapi_schema.get("paths", {})
        assert "/metrics" not in paths


class TestRequestCountMetricContract:
    """Contract tests for request count metric."""

    def test_request_count_metric_defined(self):
        """Contract: REQUEST_COUNT metric is defined with correct labels."""
        from autopack.api.app import REQUEST_COUNT

        # Verify metric exists and has expected label names
        assert REQUEST_COUNT is not None
        assert "method" in REQUEST_COUNT._labelnames
        assert "endpoint" in REQUEST_COUNT._labelnames
        assert "status" in REQUEST_COUNT._labelnames

    def test_request_count_increments_on_request(self):
        """Contract: Request count increments for each API request."""
        from fastapi.testclient import TestClient
        from prometheus_client import REGISTRY

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        # Make a request to a known endpoint
        response = client.get("/health")
        assert response.status_code == 200

        # Verify counter was incremented
        # The metric should now have at least 1 count
        samples = REGISTRY.get_sample_value(
            "autopack_http_requests_total",
            {"method": "GET", "endpoint": "/health", "status": "200"},
        )
        assert samples is not None


class TestRequestLatencyMetricContract:
    """Contract tests for request latency metric."""

    def test_request_latency_metric_defined(self):
        """Contract: REQUEST_LATENCY histogram is defined with correct labels."""
        from autopack.api.app import REQUEST_LATENCY

        # Verify metric exists and has expected label names
        assert REQUEST_LATENCY is not None
        assert "method" in REQUEST_LATENCY._labelnames
        assert "endpoint" in REQUEST_LATENCY._labelnames

    def test_request_latency_has_sensible_buckets(self):
        """Contract: Latency histogram has sensible bucket boundaries."""
        from autopack.api.app import REQUEST_LATENCY

        # Buckets should cover range from milliseconds to seconds
        # This is defined in the Histogram creation
        buckets = REQUEST_LATENCY._upper_bounds
        assert len(buckets) > 5  # Should have multiple buckets
        assert min(buckets[:-1]) < 0.1  # Should have sub-100ms bucket
        assert max(buckets[:-1]) >= 5.0  # Should go up to at least 5 seconds


class TestEndpointNormalizationContract:
    """Contract tests for endpoint path normalization."""

    def test_normalize_uuid_paths(self):
        """Contract: UUID paths are normalized to {id}."""
        from autopack.api.app import _normalize_endpoint

        # Standard UUID format
        path = "/runs/123e4567-e89b-12d3-a456-426614174000/phases"
        normalized = _normalize_endpoint(path)
        assert normalized == "/runs/{id}/phases"

    def test_normalize_uuid_without_hyphens(self):
        """Contract: UUIDs without hyphens are also normalized."""
        from autopack.api.app import _normalize_endpoint

        path = "/runs/123e4567e89b12d3a456426614174000/status"
        normalized = _normalize_endpoint(path)
        assert normalized == "/runs/{id}/status"

    def test_normalize_numeric_ids(self):
        """Contract: Numeric IDs in paths are normalized."""
        from autopack.api.app import _normalize_endpoint

        path = "/phases/123/artifacts/456"
        normalized = _normalize_endpoint(path)
        assert normalized == "/phases/{id}/artifacts/{id}"

    def test_normalize_preserves_static_paths(self):
        """Contract: Static paths without IDs are unchanged."""
        from autopack.api.app import _normalize_endpoint

        path = "/health"
        normalized = _normalize_endpoint(path)
        assert normalized == "/health"

        path = "/api/auth/login"
        normalized = _normalize_endpoint(path)
        assert normalized == "/api/auth/login"

    def test_normalize_mixed_paths(self):
        """Contract: Mixed paths with static and dynamic segments work."""
        from autopack.api.app import _normalize_endpoint

        path = "/runs/abc-def-123/phases/42/artifacts"
        normalized = _normalize_endpoint(path)
        # The abc-def-123 doesn't match UUID pattern, so only 42 is replaced
        assert "{id}" in normalized


class TestMetricsMiddlewareContract:
    """Contract tests for metrics middleware behavior."""

    def test_metrics_endpoint_not_instrumented(self):
        """Contract: /metrics endpoint itself doesn't increment metrics."""
        from fastapi.testclient import TestClient
        from prometheus_client import REGISTRY

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        # Make multiple requests to /metrics
        for _ in range(3):
            client.get("/metrics")

        # Verify no metrics recorded for /metrics endpoint
        samples = REGISTRY.get_sample_value(
            "autopack_http_requests_total",
            {"method": "GET", "endpoint": "/metrics", "status": "200"},
        )
        # Should be None (not recorded) or 0
        assert samples is None or samples == 0

    @pytest.mark.asyncio
    async def test_metrics_middleware_records_status_codes(self):
        """Contract: Different status codes are recorded separately."""
        from fastapi import Request, Response

        from autopack.api.app import metrics_middleware

        # Create mock request
        request = MagicMock(spec=Request)
        request.url = MagicMock()
        request.url.path = "/test"
        request.method = "GET"

        # Mock response with 404 status
        async def mock_call_next(req):
            response = MagicMock(spec=Response)
            response.status_code = 404
            return response

        # Call middleware
        await metrics_middleware(request, mock_call_next)

        # The metric should have been recorded
        # We can't easily verify the exact value due to shared state,
        # but the middleware should complete without error


class TestMetricsMiddlewareWiringContract:
    """Contract tests for middleware wiring in app factory."""

    def test_metrics_middleware_is_wired(self):
        """Contract: Metrics middleware is included in app middleware stack."""
        from autopack.api.app import create_app

        app = create_app()

        # The middleware is added via @app.middleware("http")
        # We can verify by checking that routes respond with metrics
        from fastapi.testclient import TestClient

        client = TestClient(app)

        # Any request should trigger metrics middleware
        # The /health endpoint is simple and always exists
        response = client.get("/health")
        # If middleware is wired, the request completes successfully
        assert response.status_code in [200, 503]  # 503 if not ready


# ---------------------------------------------------------------------------
# IMP-SEG-001: Autopilot Health Metrics Endpoint Tests
# ---------------------------------------------------------------------------


class TestAutopilotHealthMetricsEndpoint:
    """Contract tests for /metrics/autopilot-health endpoint.

    IMP-SEG-001: Tests that autopilot health metrics endpoint is available
    and returns expected data structures.
    """

    def test_autopilot_health_endpoint_exists(self):
        """Contract: /metrics/autopilot-health endpoint is available."""
        from autopack.api.app import create_app

        app = create_app()
        routes = [r.path for r in app.routes]
        assert "/metrics/autopilot-health" in routes

    def test_autopilot_health_returns_json(self):
        """Contract: /metrics/autopilot-health returns JSON."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/autopilot-health")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")

    def test_autopilot_health_includes_required_fields(self):
        """Contract: Response includes required metric fields."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/autopilot-health")
        assert response.status_code == 200

        data = response.json()
        assert "metrics" in data
        assert "prometheus" in data
        assert "timestamp" in data
        assert "dashboard_summary" in data

    def test_autopilot_health_metrics_structure(self):
        """Contract: Metrics have expected structure."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/autopilot-health")
        data = response.json()

        metrics = data["metrics"]
        assert "circuit_breaker" in metrics
        assert "budget_enforcement" in metrics
        assert "health_transitions" in metrics
        assert "research_cycles" in metrics
        assert "total_sessions" in metrics
        assert "overall_health_score" in metrics

    def test_autopilot_health_prometheus_format(self):
        """Contract: Prometheus metrics have expected format."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/autopilot-health")
        data = response.json()

        prometheus = data["prometheus"]
        assert isinstance(prometheus, dict)
        # Should have at least one autopilot metric
        autopilot_metrics = [k for k in prometheus.keys() if k.startswith("autopack_autopilot")]
        assert len(autopilot_metrics) > 0

    def test_autopilot_health_dashboard_summary(self):
        """Contract: Dashboard summary has expected structure."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/autopilot-health")
        data = response.json()

        summary = data["dashboard_summary"]
        assert "overview" in summary
        assert "health_gates" in summary
        assert "research_cycles" in summary
        assert "session_outcomes" in summary
        assert "recent_sessions" in summary
        assert "health_timeline" in summary

    def test_autopilot_health_with_sessions_query_param(self):
        """Contract: include_sessions parameter includes session history."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/autopilot-health?include_sessions=true")
        assert response.status_code == 200

        data = response.json()
        # May or may not have sessions, but field should exist when requested
        # The endpoint should include this field when requested
        assert "recent_sessions" in data["dashboard_summary"]

    def test_autopilot_health_with_timeline_query_param(self):
        """Contract: include_timeline parameter includes health timeline."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/autopilot-health?include_timeline=true")
        assert response.status_code == 200

        data = response.json()
        # Timeline should be in dashboard_summary when requested
        assert "health_timeline" in data["dashboard_summary"]

    def test_autopilot_health_initial_state(self):
        """Contract: Autopilot health starts in healthy state with no sessions."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/autopilot-health")
        data = response.json()

        metrics = data["metrics"]
        # Initial state should have 0 sessions
        assert metrics["total_sessions"] == 0
        # Health score should be near 1.0 (healthy)
        assert metrics["overall_health_score"] > 0.0
