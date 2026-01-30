"""
Contract tests for Pipeline Health Dashboard API.

IMP-TELE-010: These tests verify the real-time pipeline health dashboard
endpoint returns correct metrics for operational visibility.

Contract guarantees:
1. /metrics/pipeline-health endpoint returns PipelineHealthResponse
2. Response includes latency metrics with SLA threshold
3. Response includes SLA compliance status
4. Response includes component health for all ROAD components
5. Response includes overall health score and status
"""

import os

import pytest

# Set testing mode before imports
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


class TestPipelineHealthEndpointContract:
    """Contract tests for /metrics/pipeline-health endpoint."""

    def test_pipeline_health_endpoint_exists(self):
        """Contract: /metrics/pipeline-health endpoint is available."""
        from autopack.api.app import create_app

        app = create_app()
        routes = [r.path for r in app.routes]
        assert "/metrics/pipeline-health" in routes

    def test_pipeline_health_returns_json(self):
        """Contract: /metrics/pipeline-health returns JSON response."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/pipeline-health")
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

    def test_pipeline_health_response_structure(self):
        """Contract: Response has required fields for dashboard."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/pipeline-health")
        assert response.status_code == 200
        data = response.json()

        # Required top-level fields
        assert "timestamp" in data
        assert "latency" in data
        assert "sla_compliance" in data
        assert "component_health" in data
        assert "overall_health_score" in data
        assert "overall_status" in data

    def test_pipeline_health_latency_metrics(self):
        """Contract: Latency metrics include expected fields."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/pipeline-health")
        assert response.status_code == 200
        data = response.json()

        latency = data["latency"]
        assert "telemetry_to_analysis_ms" in latency
        assert "analysis_to_task_ms" in latency
        assert "total_latency_ms" in latency
        assert "sla_threshold_ms" in latency
        assert "stage_latencies" in latency

        # All latencies should be numbers
        assert isinstance(latency["telemetry_to_analysis_ms"], (int, float))
        assert isinstance(latency["analysis_to_task_ms"], (int, float))
        assert isinstance(latency["total_latency_ms"], (int, float))
        assert isinstance(latency["sla_threshold_ms"], (int, float))

    def test_pipeline_health_sla_compliance(self):
        """Contract: SLA compliance metrics include expected fields."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/pipeline-health")
        assert response.status_code == 200
        data = response.json()

        sla = data["sla_compliance"]
        assert "status" in sla
        assert "is_within_sla" in sla
        assert "breach_amount_ms" in sla
        assert "threshold_ms" in sla
        assert "active_breaches" in sla

        # Types
        assert isinstance(sla["status"], str)
        assert isinstance(sla["is_within_sla"], bool)
        assert isinstance(sla["active_breaches"], list)

    def test_pipeline_health_component_health(self):
        """Contract: Component health includes all ROAD components."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/pipeline-health")
        assert response.status_code == 200
        data = response.json()

        component_health = data["component_health"]
        assert isinstance(component_health, dict)

        # All components should have required fields
        for component_name, component_data in component_health.items():
            assert "component" in component_data
            assert "status" in component_data
            assert "score" in component_data
            assert "issues" in component_data
            # Score should be 0.0-1.0
            assert 0.0 <= component_data["score"] <= 1.0

    def test_pipeline_health_overall_metrics(self):
        """Contract: Overall health metrics are valid."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/pipeline-health")
        assert response.status_code == 200
        data = response.json()

        # Overall health score should be 0.0-1.0
        assert 0.0 <= data["overall_health_score"] <= 1.0

        # Overall status should be one of the expected values
        valid_statuses = ["healthy", "degraded", "attention_required", "unknown"]
        assert data["overall_status"] in valid_statuses

    def test_pipeline_health_timestamp_format(self):
        """Contract: Timestamp is in ISO 8601 format."""
        from datetime import datetime

        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/pipeline-health")
        assert response.status_code == 200
        data = response.json()

        # Should be parseable as ISO 8601
        timestamp = data["timestamp"]
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            pytest.fail(f"Timestamp {timestamp} is not valid ISO 8601 format")


class TestPipelineHealthTrackerContract:
    """Contract tests for PipelineLatencyTracker integration."""

    def test_get_pipeline_latency_tracker_singleton(self):
        """Contract: get_pipeline_latency_tracker returns singleton."""
        from autopack.api.routes.metrics import (
            get_pipeline_latency_tracker,
            reset_pipeline_latency_tracker,
        )

        # Reset to ensure fresh start
        reset_pipeline_latency_tracker()

        tracker1 = get_pipeline_latency_tracker()
        tracker2 = get_pipeline_latency_tracker()

        assert tracker1 is tracker2

    def test_reset_pipeline_latency_tracker(self):
        """Contract: reset_pipeline_latency_tracker clears the tracker."""
        from autopack.api.routes.metrics import (
            get_pipeline_latency_tracker,
            reset_pipeline_latency_tracker,
        )

        tracker1 = get_pipeline_latency_tracker()
        reset_pipeline_latency_tracker()
        tracker2 = get_pipeline_latency_tracker()

        assert tracker1 is not tracker2


class TestPipelineHealthResponseModelContract:
    """Contract tests for PipelineHealthResponse Pydantic model."""

    def test_response_model_validation(self):
        """Contract: PipelineHealthResponse validates fields correctly."""
        from autopack.api.routes.metrics import (
            ComponentHealthMetrics,
            LatencyMetrics,
            PipelineHealthResponse,
            SLAComplianceMetrics,
        )

        # Valid response should be constructable
        response = PipelineHealthResponse(
            timestamp="2024-01-15T12:00:00Z",
            latency=LatencyMetrics(
                telemetry_to_analysis_ms=100.0,
                analysis_to_task_ms=200.0,
                total_latency_ms=300.0,
                sla_threshold_ms=300000.0,
                stage_latencies={},
            ),
            sla_compliance=SLAComplianceMetrics(
                status="excellent",
                is_within_sla=True,
                breach_amount_ms=0.0,
                threshold_ms=300000.0,
                active_breaches=[],
            ),
            component_health={
                "ROAD-B": ComponentHealthMetrics(
                    component="ROAD-B",
                    status="stable",
                    score=0.85,
                    issues=[],
                )
            },
            overall_health_score=0.85,
            overall_status="healthy",
        )

        assert response.overall_health_score == 0.85
        assert response.overall_status == "healthy"
        assert len(response.component_health) == 1

    def test_latency_metrics_defaults(self):
        """Contract: LatencyMetrics has sensible defaults."""
        from autopack.api.routes.metrics import LatencyMetrics

        metrics = LatencyMetrics()

        assert metrics.telemetry_to_analysis_ms == 0.0
        assert metrics.analysis_to_task_ms == 0.0
        assert metrics.total_latency_ms == 0.0
        assert metrics.sla_threshold_ms == 300000.0
        assert metrics.stage_latencies == {}

    def test_sla_compliance_defaults(self):
        """Contract: SLAComplianceMetrics has sensible defaults."""
        from autopack.api.routes.metrics import SLAComplianceMetrics

        metrics = SLAComplianceMetrics()

        assert metrics.status == "unknown"
        assert metrics.is_within_sla is True
        assert metrics.breach_amount_ms == 0.0
        assert metrics.active_breaches == []


class TestPipelineHealthIntegration:
    """Integration tests for pipeline health dashboard."""

    def test_metrics_route_in_openapi_schema(self):
        """Contract: /metrics/pipeline-health is documented in OpenAPI."""
        from autopack.api.app import create_app

        app = create_app()
        openapi_schema = app.openapi()
        paths = openapi_schema.get("paths", {})

        assert "/metrics/pipeline-health" in paths
        assert "get" in paths["/metrics/pipeline-health"]

    def test_metrics_returns_expected_road_components(self):
        """Contract: Response includes standard ROAD component health."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/pipeline-health")
        assert response.status_code == 200
        data = response.json()

        component_health = data["component_health"]
        # Should have ROAD-B, ROAD-C, ROAD-E, ROAD-F, ROAD-G, ROAD-J, ROAD-L
        expected_components = [
            "ROAD-B",
            "ROAD-C",
            "ROAD-E",
            "ROAD-F",
            "ROAD-G",
            "ROAD-J",
            "ROAD-L",
        ]
        for component in expected_components:
            assert component in component_health, f"Missing component: {component}"
