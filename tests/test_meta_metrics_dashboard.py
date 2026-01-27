"""Tests for ROAD-K meta-metrics dashboard (IMP-ARCH-007)."""

from datetime import datetime, timedelta

import pytest

from autopack.roadk.dashboard_data import DashboardDataProvider, LoopHealthMetrics, TrendPoint
from autopack.roadk.meta_metrics_dashboard import MetaMetricsDashboard
from autopack.telemetry.meta_metrics import PipelineLatencyTracker, PipelineSLAConfig, PipelineStage


@pytest.fixture
def healthy_telemetry():
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
        "road_f": {
            "effective_promotions": 8,
            "total_promotions": 10,
            "rollbacks": 1,
            "avg_promotion_time_hours": 24.0,
        },
        "road_g": {"actionable_alerts": 16, "total_alerts": 20, "false_positives": 3},
        "road_j": {"successful_heals": 14, "total_heal_attempts": 20, "escalations": 4},
        "road_l": {
            "optimal_routings": 85,
            "total_routings": 100,
            "avg_tokens_per_success": 800,
            "sample_count": 50,
        },
        "generation_trend": [
            {"timestamp": "2024-01-01T00:00:00", "value": 5},
            {"timestamp": "2024-01-02T00:00:00", "value": 7},
            {"timestamp": "2024-01-03T00:00:00", "value": 8},
        ],
        "success_trend": [
            {"timestamp": "2024-01-01T00:00:00", "value": 0.85},
            {"timestamp": "2024-01-02T00:00:00", "value": 0.88},
            {"timestamp": "2024-01-03T00:00:00", "value": 0.90},
        ],
    }


@pytest.fixture
def degraded_telemetry():
    """Sample telemetry data showing degraded system."""
    return {
        "road_b": {
            "phases_analyzed": 50,
            "total_phases": 100,
            "false_positives": 15,
            "total_issues": 50,
        },
        "road_c": {"completed_tasks": 3, "total_tasks": 10, "rework_count": 6},
        "road_e": {
            "valid_ab_tests": 8,
            "total_ab_tests": 20,
            "regressions_caught": 5,
            "total_changes": 10,
        },
        "road_f": {
            "effective_promotions": 3,
            "total_promotions": 10,
            "rollbacks": 4,
            "avg_promotion_time_hours": 72.0,
        },
        "road_g": {"actionable_alerts": 10, "total_alerts": 20, "false_positives": 8},
        "road_j": {"successful_heals": 8, "total_heal_attempts": 20, "escalations": 10},
        "road_l": {
            "optimal_routings": 60,
            "total_routings": 100,
            "avg_tokens_per_success": 1500,
            "sample_count": 50,
        },
    }


@pytest.fixture
def healthy_provider(healthy_telemetry):
    """Create data provider with healthy telemetry."""
    return DashboardDataProvider(telemetry_data=healthy_telemetry)


@pytest.fixture
def degraded_provider(degraded_telemetry):
    """Create data provider with degraded telemetry."""
    return DashboardDataProvider(telemetry_data=degraded_telemetry)


class TestLoopHealthMetrics:
    """Tests for LoopHealthMetrics data class."""

    def test_metrics_creation(self):
        """Test LoopHealthMetrics instantiation."""
        now = datetime.utcnow()
        start = now - timedelta(days=30)

        metrics = LoopHealthMetrics(
            period_start=start,
            period_end=now,
            tasks_generated=10,
            tasks_validated=8,
            tasks_promoted=6,
            tasks_rolled_back=1,
            validation_success_rate=0.8,
            promotion_rate=0.6,
            rollback_rate=0.1,
            avg_time_to_promotion_hours=24.0,
        )

        assert metrics.tasks_generated == 10
        assert metrics.tasks_validated == 8
        assert metrics.tasks_promoted == 6
        assert metrics.tasks_rolled_back == 1
        assert metrics.validation_success_rate == 0.8
        assert metrics.promotion_rate == 0.6
        assert metrics.rollback_rate == 0.1
        assert metrics.avg_time_to_promotion_hours == 24.0


class TestTrendPoint:
    """Tests for TrendPoint data class."""

    def test_trend_point_creation(self):
        """Test TrendPoint instantiation."""
        timestamp = datetime.utcnow()
        point = TrendPoint(timestamp=timestamp, value=0.85)

        assert point.timestamp == timestamp
        assert point.value == 0.85


class TestDashboardDataProvider:
    """Tests for DashboardDataProvider."""

    def test_provider_initialization_default(self):
        """Test provider initializes with defaults."""
        provider = DashboardDataProvider()

        # Should not raise
        health = provider.get_loop_health(days=7)
        assert health is not None

    def test_provider_initialization_with_data(self, healthy_telemetry):
        """Test provider initializes with injected data."""
        provider = DashboardDataProvider(telemetry_data=healthy_telemetry)
        health = provider.get_loop_health(days=30)

        assert health.tasks_generated == 10
        assert health.validation_success_rate == 0.9  # 18/20

    def test_get_loop_health_calculates_rates(self, healthy_provider):
        """Test loop health rate calculations."""
        health = healthy_provider.get_loop_health(days=30)

        # Validation success rate: 18/20 = 0.9
        assert abs(health.validation_success_rate - 0.9) < 0.01

        # Promotion rate: 8/10 = 0.8
        assert abs(health.promotion_rate - 0.8) < 0.01

        # Rollback rate: 1/10 = 0.1
        assert abs(health.rollback_rate - 0.1) < 0.01

    def test_get_loop_health_period(self, healthy_provider):
        """Test loop health period is set correctly."""
        health = healthy_provider.get_loop_health(days=7)

        # Period should span 7 days
        delta = health.period_end - health.period_start
        assert abs(delta.days - 7) <= 1  # Allow small variance

    def test_get_generation_trend(self, healthy_provider):
        """Test generation trend retrieval."""
        trend = healthy_provider.get_generation_trend(days=30)

        assert len(trend) == 3
        assert all(isinstance(p, TrendPoint) for p in trend)
        assert trend[0].value == 5
        assert trend[2].value == 8

    def test_get_success_trend(self, healthy_provider):
        """Test success trend retrieval."""
        trend = healthy_provider.get_success_trend(days=30)

        assert len(trend) == 3
        assert all(isinstance(p, TrendPoint) for p in trend)
        assert abs(trend[0].value - 0.85) < 0.01
        assert abs(trend[2].value - 0.90) < 0.01

    def test_get_full_health_report(self, healthy_provider):
        """Test full health report from MetaMetricsTracker."""
        report = healthy_provider.get_full_health_report()

        assert report is not None
        assert hasattr(report, "overall_status")
        assert hasattr(report, "overall_score")
        assert hasattr(report, "component_reports")

    def test_empty_telemetry_data(self):
        """Test provider handles empty telemetry gracefully."""
        provider = DashboardDataProvider(telemetry_data={})
        health = provider.get_loop_health(days=30)

        assert health.tasks_generated == 0
        assert health.validation_success_rate == 0.0
        assert health.promotion_rate == 0.0
        assert health.rollback_rate == 0.0


class TestMetaMetricsDashboard:
    """Tests for MetaMetricsDashboard."""

    def test_dashboard_data_structure(self, healthy_provider):
        """Test dashboard data has correct structure."""
        dashboard = MetaMetricsDashboard(data_provider=healthy_provider)
        data = dashboard.get_dashboard_data(days=7)

        assert "generated_at" in data
        assert "period_days" in data
        assert "summary" in data
        assert "trends" in data
        assert "alerts" in data

    def test_dashboard_summary_fields(self, healthy_provider):
        """Test dashboard summary contains all required fields."""
        dashboard = MetaMetricsDashboard(data_provider=healthy_provider)
        data = dashboard.get_dashboard_data(days=7)

        summary = data["summary"]
        assert "loop_health_score" in summary
        assert "status" in summary
        assert "tasks_generated" in summary
        assert "tasks_validated" in summary
        assert "tasks_promoted" in summary
        assert "tasks_rolled_back" in summary
        assert "validation_success_rate" in summary
        assert "promotion_rate" in summary
        assert "rollback_rate" in summary

    def test_health_score_calculation_healthy(self, healthy_provider):
        """Test health score calculation with healthy data."""
        dashboard = MetaMetricsDashboard(data_provider=healthy_provider)
        health = healthy_provider.get_loop_health(days=30)

        score = dashboard._calculate_health_score(health)

        # With 90% validation, 80% promotion, 10% rollback:
        # (0.9 * 0.4 + 0.8 * 0.4 - 0.1 * 0.2) * 100 = 66
        assert 0 <= score <= 100
        assert score >= 50  # Should be healthy-ish

    def test_health_score_calculation_zero_tasks(self):
        """Test health score with no tasks generated."""
        health = LoopHealthMetrics(
            period_start=datetime.utcnow() - timedelta(days=30),
            period_end=datetime.utcnow(),
            tasks_generated=0,
            tasks_validated=0,
            tasks_promoted=0,
            tasks_rolled_back=0,
            validation_success_rate=0.0,
            promotion_rate=0.0,
            rollback_rate=0.0,
            avg_time_to_promotion_hours=0.0,
        )

        dashboard = MetaMetricsDashboard()
        score = dashboard._calculate_health_score(health)

        assert score == 0.0

    def test_health_score_bounds(self):
        """Test health score is bounded [0, 100]."""
        # Test upper bound (perfect metrics)
        perfect_health = LoopHealthMetrics(
            period_start=datetime.utcnow() - timedelta(days=30),
            period_end=datetime.utcnow(),
            tasks_generated=10,
            tasks_validated=10,
            tasks_promoted=10,
            tasks_rolled_back=0,
            validation_success_rate=1.0,
            promotion_rate=1.0,
            rollback_rate=0.0,
            avg_time_to_promotion_hours=12.0,
        )

        dashboard = MetaMetricsDashboard()
        score = dashboard._calculate_health_score(perfect_health)
        assert score <= 100.0

        # Test lower bound (terrible metrics)
        terrible_health = LoopHealthMetrics(
            period_start=datetime.utcnow() - timedelta(days=30),
            period_end=datetime.utcnow(),
            tasks_generated=10,
            tasks_validated=0,
            tasks_promoted=0,
            tasks_rolled_back=10,
            validation_success_rate=0.0,
            promotion_rate=0.0,
            rollback_rate=1.0,
            avg_time_to_promotion_hours=0.0,
        )

        score = dashboard._calculate_health_score(terrible_health)
        assert score >= 0.0

    def test_health_status_healthy(self, healthy_provider):
        """Test health status is 'healthy' for good metrics."""
        dashboard = MetaMetricsDashboard(data_provider=healthy_provider)
        health = healthy_provider.get_loop_health(days=30)

        status = dashboard._get_health_status(health)

        # With good metrics, should be healthy or degraded
        assert status in ["healthy", "degraded"]

    def test_health_status_degraded(self, degraded_provider):
        """Test health status reflects degraded metrics."""
        dashboard = MetaMetricsDashboard(data_provider=degraded_provider)
        health = degraded_provider.get_loop_health(days=30)

        status = dashboard._get_health_status(health)

        # With degraded metrics, should not be healthy
        assert status in ["degraded", "warning", "critical"]

    def test_alerts_generated_for_high_rollback(self):
        """Test alerts are generated for high rollback rate."""
        health = LoopHealthMetrics(
            period_start=datetime.utcnow() - timedelta(days=30),
            period_end=datetime.utcnow(),
            tasks_generated=10,
            tasks_validated=5,
            tasks_promoted=3,
            tasks_rolled_back=4,
            validation_success_rate=0.5,
            promotion_rate=0.3,
            rollback_rate=0.4,  # High rollback
            avg_time_to_promotion_hours=48.0,
        )

        dashboard = MetaMetricsDashboard()
        alerts = dashboard._generate_alerts(health)

        assert len(alerts) > 0
        rollback_alerts = [a for a in alerts if "rollback" in a["message"].lower()]
        assert len(rollback_alerts) > 0
        assert rollback_alerts[0]["level"] == "warning"

    def test_alerts_generated_for_low_validation(self):
        """Test alerts are generated for low validation success."""
        health = LoopHealthMetrics(
            period_start=datetime.utcnow() - timedelta(days=30),
            period_end=datetime.utcnow(),
            tasks_generated=10,
            tasks_validated=2,  # Low validation
            tasks_promoted=1,
            tasks_rolled_back=1,
            validation_success_rate=0.2,  # Very low
            promotion_rate=0.1,
            rollback_rate=0.1,
            avg_time_to_promotion_hours=48.0,
        )

        dashboard = MetaMetricsDashboard()
        alerts = dashboard._generate_alerts(health)

        validation_alerts = [a for a in alerts if "validation" in a["message"].lower()]
        assert len(validation_alerts) > 0
        assert validation_alerts[0]["level"] == "critical"

    def test_alerts_generated_for_no_tasks(self):
        """Test info alert is generated when no tasks exist."""
        health = LoopHealthMetrics(
            period_start=datetime.utcnow() - timedelta(days=30),
            period_end=datetime.utcnow(),
            tasks_generated=0,
            tasks_validated=0,
            tasks_promoted=0,
            tasks_rolled_back=0,
            validation_success_rate=0.0,
            promotion_rate=0.0,
            rollback_rate=0.0,
            avg_time_to_promotion_hours=0.0,
        )

        dashboard = MetaMetricsDashboard()
        alerts = dashboard._generate_alerts(health)

        no_task_alerts = [a for a in alerts if "no tasks" in a["message"].lower()]
        assert len(no_task_alerts) > 0
        assert no_task_alerts[0]["level"] == "info"

    def test_no_alerts_for_healthy_system(self, healthy_provider):
        """Test minimal/no alerts for healthy system."""
        dashboard = MetaMetricsDashboard(data_provider=healthy_provider)
        data = dashboard.get_dashboard_data(days=30)

        # Healthy system should have few or no critical/warning alerts
        critical_alerts = [a for a in data["alerts"] if a["level"] == "critical"]
        assert len(critical_alerts) == 0

    def test_trends_in_dashboard_data(self, healthy_provider):
        """Test trends are included in dashboard data."""
        dashboard = MetaMetricsDashboard(data_provider=healthy_provider)
        data = dashboard.get_dashboard_data(days=30)

        assert "generation" in data["trends"]
        assert "success_rate" in data["trends"]
        assert len(data["trends"]["generation"]) == 3
        assert len(data["trends"]["success_rate"]) == 3

    def test_detailed_report_structure(self, healthy_provider):
        """Test detailed report includes component breakdown."""
        dashboard = MetaMetricsDashboard(data_provider=healthy_provider)
        report = dashboard.get_detailed_report(days=30)

        assert "detailed_report" in report
        assert "overall_status" in report["detailed_report"]
        assert "overall_score" in report["detailed_report"]
        assert "components" in report["detailed_report"]
        assert "critical_issues" in report["detailed_report"]
        assert "warnings" in report["detailed_report"]

    def test_detailed_report_component_metrics(self, healthy_provider):
        """Test detailed report contains component-level metrics."""
        dashboard = MetaMetricsDashboard(data_provider=healthy_provider)
        report = dashboard.get_detailed_report(days=30)

        components = report["detailed_report"]["components"]

        # Should have all ROAD components
        expected_components = ["ROAD-B", "ROAD-C", "ROAD-E", "ROAD-F", "ROAD-G", "ROAD-J", "ROAD-L"]
        for comp in expected_components:
            assert comp in components
            assert "status" in components[comp]
            assert "score" in components[comp]
            assert "metrics" in components[comp]
            assert "issues" in components[comp]
            assert "recommendations" in components[comp]

    def test_period_days_reflected_in_data(self, healthy_provider):
        """Test that period_days parameter is reflected in output."""
        dashboard = MetaMetricsDashboard(data_provider=healthy_provider)

        data_7 = dashboard.get_dashboard_data(days=7)
        data_30 = dashboard.get_dashboard_data(days=30)

        assert data_7["period_days"] == 7
        assert data_30["period_days"] == 30

    def test_generated_at_timestamp(self, healthy_provider):
        """Test generated_at timestamp is recent."""
        dashboard = MetaMetricsDashboard(data_provider=healthy_provider)
        data = dashboard.get_dashboard_data(days=7)

        # Parse timestamp
        generated_at = datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00"))
        now = datetime.utcnow()

        # Should be within last minute
        delta = abs((now - generated_at.replace(tzinfo=None)).total_seconds())
        assert delta < 60


class TestDashboardSLAMetrics:
    """Tests for dashboard SLA tracking (IMP-LOOP-017)."""

    def test_dashboard_default_sla_threshold(self):
        """Test dashboard has default 5 minute SLA threshold."""
        dashboard = MetaMetricsDashboard()
        assert dashboard._sla_threshold_ms == 300000  # 5 minutes

    def test_dashboard_custom_sla_threshold(self):
        """Test dashboard with custom SLA threshold."""
        dashboard = MetaMetricsDashboard(sla_threshold_ms=600000)  # 10 minutes
        assert dashboard._sla_threshold_ms == 600000

    def test_dashboard_sla_config(self):
        """Test dashboard with custom SLA config."""
        config = PipelineSLAConfig(
            end_to_end_threshold_ms=600000,
            stage_thresholds_ms={"custom": 30000},
        )
        dashboard = MetaMetricsDashboard(sla_config=config)

        assert dashboard._sla_config.end_to_end_threshold_ms == 600000
        assert "custom" in dashboard._sla_config.stage_thresholds_ms

    def test_dashboard_data_includes_sla(self, healthy_provider):
        """Test dashboard data includes SLA section."""
        dashboard = MetaMetricsDashboard(data_provider=healthy_provider)
        data = dashboard.get_dashboard_data(days=7)

        assert "sla" in data
        assert "threshold_ms" in data["sla"]
        assert "threshold_minutes" in data["sla"]
        assert "status" in data["sla"]
        assert "is_within_sla" in data["sla"]

    def test_dashboard_sla_defaults_without_tracker(self, healthy_provider):
        """Test SLA defaults when no pipeline tracker is set."""
        dashboard = MetaMetricsDashboard(data_provider=healthy_provider)
        data = dashboard.get_dashboard_data(days=7)

        sla = data["sla"]
        assert sla["threshold_ms"] == 300000
        assert sla["threshold_minutes"] == 5.0
        assert sla["status"] == "unknown"
        assert sla["current_latency_ms"] is None
        assert sla["is_within_sla"] is True

    def test_dashboard_sla_with_tracker(self, healthy_provider):
        """Test SLA metrics with pipeline tracker."""
        tracker = PipelineLatencyTracker()
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base + timedelta(minutes=2),
        )

        dashboard = MetaMetricsDashboard(
            data_provider=healthy_provider,
            pipeline_tracker=tracker,
        )
        data = dashboard.get_dashboard_data(days=7)

        sla = data["sla"]
        assert sla["status"] == "excellent"
        assert sla["current_latency_ms"] == 120000
        assert sla["current_latency_minutes"] == 2.0
        assert sla["is_within_sla"] is True

    def test_dashboard_sla_breach_alerts(self, healthy_provider):
        """Test SLA breach generates alerts."""
        tracker = PipelineLatencyTracker()
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base + timedelta(minutes=10),  # Over 5 min SLA
        )

        dashboard = MetaMetricsDashboard(
            data_provider=healthy_provider,
            pipeline_tracker=tracker,
        )
        data = dashboard.get_dashboard_data(days=7)

        # Should have SLA breach alert
        sla_alerts = [a for a in data["alerts"] if "SLA" in a["message"]]
        assert len(sla_alerts) >= 1
        assert sla_alerts[0]["level"] in ["warning", "critical"]

    def test_set_pipeline_tracker(self, healthy_provider):
        """Test setting pipeline tracker after initialization."""
        dashboard = MetaMetricsDashboard(data_provider=healthy_provider)
        assert dashboard._pipeline_tracker is None

        tracker = PipelineLatencyTracker()
        dashboard.set_pipeline_tracker(tracker)

        assert dashboard._pipeline_tracker is tracker

    def test_configure_sla(self, healthy_provider):
        """Test configuring SLA thresholds."""
        dashboard = MetaMetricsDashboard(data_provider=healthy_provider)
        dashboard.configure_sla(
            end_to_end_threshold_ms=600000,
            stage_thresholds_ms={"custom_stage": 30000},
        )

        assert dashboard._sla_threshold_ms == 600000
        assert "custom_stage" in dashboard._sla_config.stage_thresholds_ms

    def test_configure_sla_updates_tracker(self, healthy_provider):
        """Test configuring SLA updates tracker config."""
        tracker = PipelineLatencyTracker()
        dashboard = MetaMetricsDashboard(
            data_provider=healthy_provider,
            pipeline_tracker=tracker,
        )

        dashboard.configure_sla(end_to_end_threshold_ms=600000)

        assert tracker.sla_config.end_to_end_threshold_ms == 600000

    def test_detailed_report_includes_sla_details(self, healthy_provider):
        """Test detailed report includes SLA configuration details."""
        dashboard = MetaMetricsDashboard(data_provider=healthy_provider)
        report = dashboard.get_detailed_report(days=7)

        assert "sla_details" in report["detailed_report"]
        sla_details = report["detailed_report"]["sla_details"]
        assert "configuration" in sla_details
        assert sla_details["configuration"]["end_to_end_threshold_ms"] == 300000

    def test_detailed_report_includes_pipeline_state(self, healthy_provider):
        """Test detailed report includes current pipeline state."""
        tracker = PipelineLatencyTracker(pipeline_id="test-123")
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)

        dashboard = MetaMetricsDashboard(
            data_provider=healthy_provider,
            pipeline_tracker=tracker,
        )
        report = dashboard.get_detailed_report(days=7)

        sla_details = report["detailed_report"]["sla_details"]
        assert sla_details["current_pipeline"] is not None
        assert sla_details["current_pipeline"]["pipeline_id"] == "test-123"

    def test_sla_breach_suggestions(self, healthy_provider):
        """Test SLA breach alerts include helpful suggestions."""
        tracker = PipelineLatencyTracker()
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base + timedelta(minutes=10),
        )

        dashboard = MetaMetricsDashboard(
            data_provider=healthy_provider,
            pipeline_tracker=tracker,
        )
        data = dashboard.get_dashboard_data(days=7)

        sla_alerts = [a for a in data["alerts"] if "SLA" in a["message"]]
        for alert in sla_alerts:
            assert "suggestion" in alert
            assert len(alert["suggestion"]) > 0

    def test_sla_stage_latencies_in_dashboard(self, healthy_provider):
        """Test stage latencies are included in SLA metrics."""
        tracker = PipelineLatencyTracker()
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.TELEMETRY_COLLECTED,
            timestamp=base + timedelta(seconds=30),
        )
        tracker.record_stage(
            PipelineStage.MEMORY_PERSISTED,
            timestamp=base + timedelta(seconds=60),
        )

        dashboard = MetaMetricsDashboard(
            data_provider=healthy_provider,
            pipeline_tracker=tracker,
        )
        data = dashboard.get_dashboard_data(days=7)

        stage_latencies = data["sla"]["stage_latencies"]
        assert "phase_complete_to_telemetry_collected" in stage_latencies
        assert stage_latencies["phase_complete_to_telemetry_collected"] == 30000

    def test_sla_breaches_in_dashboard(self, healthy_provider):
        """Test breach details are included in SLA metrics."""
        tracker = PipelineLatencyTracker()
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base + timedelta(minutes=10),
        )

        dashboard = MetaMetricsDashboard(
            data_provider=healthy_provider,
            pipeline_tracker=tracker,
        )
        data = dashboard.get_dashboard_data(days=7)

        breaches = data["sla"]["breaches"]
        assert len(breaches) >= 1
        assert "threshold_ms" in breaches[0]
        assert "actual_ms" in breaches[0]
        assert "breach_amount_ms" in breaches[0]
