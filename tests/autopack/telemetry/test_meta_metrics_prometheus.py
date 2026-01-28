"""Tests for Prometheus metrics export functionality.

IMP-OBS-001: Tests for feedback loop observability dashboard and Prometheus metrics.

These tests verify:
1. MetaMetricsTracker.export_to_prometheus() returns correct metric format
2. /metrics/feedback-loop endpoint returns Prometheus-compatible data
3. Component health scores are properly exported
"""

import os
from typing import Any, Dict

import pytest

# Set testing mode before imports
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from autopack.telemetry.meta_metrics import MetaMetricsTracker


class TestExportToPrometheus:
    """Tests for MetaMetricsTracker.export_to_prometheus() method."""

    @pytest.fixture
    def tracker(self) -> MetaMetricsTracker:
        """Create a MetaMetricsTracker instance."""
        return MetaMetricsTracker()

    @pytest.fixture
    def healthy_telemetry(self) -> Dict[str, Any]:
        """Sample telemetry data showing healthy system."""
        return {
            "road_b": {
                "phases_analyzed": 95,
                "total_phases": 100,
                "false_positives": 5,
                "total_issues": 50,
            },
            "road_c": {"completed_tasks": 8, "total_tasks": 10, "rework_count": 2},
            "road_e": {
                "valid_ab_tests": 18,
                "total_ab_tests": 20,
                "regressions_caught": 9,
                "total_changes": 10,
            },
            "road_f": {"effective_promotions": 8, "total_promotions": 10, "rollbacks": 1},
            "road_g": {"actionable_alerts": 16, "total_alerts": 20, "false_positives": 3},
            "road_j": {"successful_heals": 14, "total_heal_attempts": 20, "escalations": 4},
            "road_l": {
                "optimal_routings": 85,
                "total_routings": 100,
                "avg_tokens_per_success": 800,
                "sample_count": 50,
            },
        }

    def test_export_returns_dict(self, tracker: MetaMetricsTracker):
        """Test that export_to_prometheus returns a dictionary."""
        result = tracker.export_to_prometheus()
        assert isinstance(result, dict)

    def test_export_contains_overall_health_metric(self, tracker: MetaMetricsTracker):
        """Test that export includes overall feedback loop health."""
        result = tracker.export_to_prometheus()
        assert "autopack_feedback_loop_health" in result
        assert isinstance(result["autopack_feedback_loop_health"], (int, float))
        assert 0.0 <= result["autopack_feedback_loop_health"] <= 1.0

    def test_export_contains_all_component_metrics(self, tracker: MetaMetricsTracker):
        """Test that export includes all ROAD component health metrics."""
        result = tracker.export_to_prometheus()

        expected_metrics = [
            "autopack_telemetry_health",  # ROAD-B
            "autopack_task_gen_health",  # ROAD-C
            "autopack_validation_health",  # ROAD-E
            "autopack_policy_health",  # ROAD-F
            "autopack_anomaly_health",  # ROAD-G
            "autopack_healing_health",  # ROAD-J
            "autopack_model_health",  # ROAD-L
        ]

        for metric in expected_metrics:
            assert metric in result, f"Missing metric: {metric}"
            assert isinstance(result[metric], (int, float))
            assert 0.0 <= result[metric] <= 1.0

    def test_export_with_healthy_telemetry(
        self, tracker: MetaMetricsTracker, healthy_telemetry: Dict[str, Any]
    ):
        """Test export with healthy telemetry data produces good scores."""
        result = tracker.export_to_prometheus(healthy_telemetry)

        # With healthy data, overall health should be above threshold
        assert result["autopack_feedback_loop_health"] >= 0.5

    def test_export_with_empty_telemetry(self, tracker: MetaMetricsTracker):
        """Test export works with empty telemetry data."""
        result = tracker.export_to_prometheus({})

        # Should still return valid metrics with baseline scores
        assert "autopack_feedback_loop_health" in result
        assert len(result) == 8  # 1 overall + 7 components

    def test_export_with_none_telemetry(self, tracker: MetaMetricsTracker):
        """Test export works when telemetry is None."""
        result = tracker.export_to_prometheus(None)

        # Should still return valid metrics with baseline scores
        assert "autopack_feedback_loop_health" in result
        assert len(result) == 8

    def test_export_metric_values_are_prometheus_compatible(self, tracker: MetaMetricsTracker):
        """Test that exported metric values are Prometheus Gauge compatible."""
        result = tracker.export_to_prometheus()

        for metric_name, value in result.items():
            # Prometheus Gauges accept float values
            assert isinstance(value, (int, float)), f"{metric_name} is not numeric"
            # Values should be finite (not NaN or Inf)
            assert value == value, f"{metric_name} is NaN"  # NaN != NaN
            assert abs(value) != float("inf"), f"{metric_name} is infinite"


class TestFeedbackLoopMetricsEndpoint:
    """Tests for /metrics/feedback-loop API endpoint."""

    def test_endpoint_exists(self):
        """Test that /metrics/feedback-loop endpoint is registered."""
        from autopack.api.app import create_app

        app = create_app()
        routes = [r.path for r in app.routes]
        assert "/metrics/feedback-loop" in routes

    def test_endpoint_returns_200(self):
        """Test that endpoint returns 200 OK."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/feedback-loop")
        assert response.status_code == 200

    def test_endpoint_returns_json(self):
        """Test that endpoint returns JSON content."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/feedback-loop")
        assert response.headers["content-type"] == "application/json"

    def test_endpoint_response_structure(self):
        """Test that endpoint returns correct response structure."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/feedback-loop")
        data = response.json()

        # Required fields
        assert "metrics" in data
        assert "timestamp" in data

        # Metrics should contain all expected values
        metrics = data["metrics"]
        assert "autopack_feedback_loop_health" in metrics
        assert "autopack_telemetry_health" in metrics
        assert "autopack_task_gen_health" in metrics

    def test_endpoint_with_include_details(self):
        """Test endpoint with include_details=true query parameter."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/feedback-loop?include_details=true")
        data = response.json()

        assert response.status_code == 200
        assert "details" in data

        details = data["details"]
        assert "overall_status" in details
        assert "overall_score" in details
        assert "component_statuses" in details

    def test_endpoint_without_include_details(self):
        """Test endpoint without include_details parameter."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/feedback-loop")
        data = response.json()

        assert response.status_code == 200
        assert "details" not in data

    def test_endpoint_metrics_are_numeric(self):
        """Test that all metrics in response are numeric values."""
        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/feedback-loop")
        data = response.json()

        for metric_name, value in data["metrics"].items():
            assert isinstance(value, (int, float)), f"{metric_name} is not numeric"

    def test_endpoint_timestamp_is_iso_format(self):
        """Test that timestamp is in ISO 8601 format."""
        from datetime import datetime

        from fastapi.testclient import TestClient

        from autopack.api.app import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/metrics/feedback-loop")
        data = response.json()

        timestamp = data["timestamp"]
        # Should parse without error
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            pytest.fail(f"Timestamp {timestamp} is not valid ISO format")


class TestPrometheusMetricNames:
    """Tests for Prometheus metric naming conventions."""

    def test_metric_names_follow_prometheus_convention(self):
        """Test that metric names follow Prometheus naming conventions."""
        tracker = MetaMetricsTracker()
        result = tracker.export_to_prometheus()

        for metric_name in result.keys():
            # Prometheus metrics should be lowercase
            assert metric_name == metric_name.lower()
            # Should use underscores, not hyphens
            assert "-" not in metric_name
            # Should start with application prefix
            assert metric_name.startswith("autopack_")

    def test_metric_names_are_descriptive(self):
        """Test that metric names clearly describe what they measure."""
        tracker = MetaMetricsTracker()
        result = tracker.export_to_prometheus()

        # Each metric should contain a descriptive word
        descriptive_words = ["health", "rate", "count", "total"]
        for metric_name in result.keys():
            has_descriptive = any(word in metric_name for word in descriptive_words)
            assert has_descriptive, f"Metric {metric_name} lacks descriptive suffix"
