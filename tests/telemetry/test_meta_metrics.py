"""Tests for ROAD-K meta-metrics system."""

from datetime import datetime, timedelta

import pytest

from autopack.telemetry.meta_metrics import (
    ComponentStatus,
    FeedbackLoopHealth,
    FeedbackLoopLatency,
    MetaMetricsTracker,
    MetricTrend,
    PipelineLatencyTracker,
    PipelineSLAConfig,
    PipelineStage,
    PipelineStageTimestamp,
    SLABreachAlert,
)


@pytest.fixture
def tracker():
    """Create meta-metrics tracker with default settings."""
    return MetaMetricsTracker(
        min_samples_for_trend=10, degradation_threshold=0.10, improvement_threshold=0.05
    )


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
            "valid_ab_tests": 12,
            "total_ab_tests": 20,
            "regressions_caught": 5,
            "total_changes": 10,
        },
        "road_f": {"effective_promotions": 4, "total_promotions": 10, "rollbacks": 3},
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
def baseline_data():
    """Baseline telemetry for comparison."""
    return {
        "road_b": {"coverage_rate": 0.8, "false_positive_rate": 0.1},
        "road_c": {"completion_rate": 0.7, "rework_rate": 0.3},
        "road_e": {"validity_rate": 0.9, "detection_rate": 0.95},
        "road_f": {"effectiveness_rate": 0.8, "rollback_rate": 0.1},
        "road_g": {"precision": 0.8, "false_positive_rate": 0.15},
        "road_j": {"success_rate": 0.7, "escalation_rate": 0.2},
        "road_l": {"routing_accuracy": 0.8, "avg_tokens_per_success": 1000},
    }


def test_tracker_initialization():
    """Test MetaMetricsTracker initialization."""
    tracker = MetaMetricsTracker(
        min_samples_for_trend=5, degradation_threshold=0.15, improvement_threshold=0.10
    )

    assert tracker.min_samples_for_trend == 5
    assert tracker.degradation_threshold == 0.15
    assert tracker.improvement_threshold == 0.10


def test_compute_trend_improving():
    """Test trend computation for improving metric."""
    tracker = MetaMetricsTracker()

    trend = tracker._compute_trend(
        metric_name="success_rate",
        current_value=0.85,
        baseline_value=0.75,
        sample_count=20,
        lower_is_better=False,
    )

    assert trend.metric_name == "success_rate"
    assert trend.current_value == 0.85
    assert trend.baseline_value == 0.75
    assert trend.trend_direction == "improving"
    assert trend.percent_change > 10.0  # >10% improvement
    assert trend.confidence == 0.9  # High confidence with 20 samples


def test_compute_trend_degrading():
    """Test trend computation for degrading metric."""
    tracker = MetaMetricsTracker()

    trend = tracker._compute_trend(
        metric_name="error_rate",
        current_value=0.25,
        baseline_value=0.10,
        sample_count=15,
        lower_is_better=True,
    )

    assert trend.trend_direction == "degrading"
    assert trend.percent_change > 100.0  # Large increase (bad for error rate)
    assert trend.confidence == 0.9


def test_compute_trend_stable():
    """Test trend computation for stable metric."""
    tracker = MetaMetricsTracker()

    trend = tracker._compute_trend(
        metric_name="coverage_rate",
        current_value=0.82,
        baseline_value=0.80,
        sample_count=25,
        lower_is_better=False,
    )

    assert trend.trend_direction == "stable"
    assert abs(trend.percent_change) < 5.0  # <5% change
    assert trend.confidence == 0.9


def test_compute_trend_low_confidence():
    """Test trend computation with insufficient samples."""
    tracker = MetaMetricsTracker(min_samples_for_trend=10)

    trend = tracker._compute_trend(
        metric_name="test_metric",
        current_value=0.5,
        baseline_value=0.4,
        sample_count=3,
        lower_is_better=False,
    )

    assert trend.confidence == 0.3  # Low confidence with only 3 samples


def test_analyze_feedback_loop_health_healthy(tracker, healthy_telemetry, baseline_data):
    """Test feedback loop health analysis with healthy data."""
    report = tracker.analyze_feedback_loop_health(healthy_telemetry, baseline_data)

    assert report.overall_status == FeedbackLoopHealth.HEALTHY
    assert report.overall_score >= 0.6
    assert len(report.component_reports) == 7  # All ROAD components

    # Check all components have reports
    for component in ["ROAD-B", "ROAD-C", "ROAD-E", "ROAD-F", "ROAD-G", "ROAD-J", "ROAD-L"]:
        assert component in report.component_reports

    # Most components should be stable or improving
    stable_or_improving = sum(
        1
        for r in report.component_reports.values()
        if r.status in [ComponentStatus.STABLE, ComponentStatus.IMPROVING]
    )
    assert stable_or_improving >= 5


def test_analyze_feedback_loop_health_degraded(tracker, degraded_telemetry, baseline_data):
    """Test feedback loop health analysis with degraded data."""
    report = tracker.analyze_feedback_loop_health(degraded_telemetry, baseline_data)

    assert report.overall_status in [
        FeedbackLoopHealth.DEGRADED,
        FeedbackLoopHealth.ATTENTION_REQUIRED,
    ]
    assert report.overall_score < 0.7  # Below acceptable threshold

    # Should have critical issues identified
    assert len(report.critical_issues) > 0 or len(report.warnings) > 0

    # At least some components should be degrading
    degrading_count = sum(
        1 for r in report.component_reports.values() if r.status == ComponentStatus.DEGRADING
    )
    assert degrading_count >= 1


def test_analyze_telemetry_analysis_healthy(tracker, healthy_telemetry, baseline_data):
    """Test ROAD-B analysis with healthy metrics."""
    report = tracker._analyze_telemetry_analysis(healthy_telemetry, baseline_data)

    assert report.component == "ROAD-B"
    assert report.status in [ComponentStatus.STABLE, ComponentStatus.IMPROVING]
    assert report.overall_score >= 0.6
    assert len(report.metrics) > 0

    # No critical issues for healthy data
    assert len([issue for issue in report.issues if "Low" in issue or "High" in issue]) == 0


def test_analyze_telemetry_analysis_degraded(tracker):
    """Test ROAD-B analysis with degraded metrics."""
    degraded_data = {
        "road_b": {
            "phases_analyzed": 40,
            "total_phases": 100,
            "false_positives": 15,
            "total_issues": 50,
        }
    }

    report = tracker._analyze_telemetry_analysis(degraded_data, {})

    assert report.status == ComponentStatus.DEGRADING
    assert report.overall_score < 0.7
    assert len(report.issues) > 0
    assert len(report.recommendations) > 0


def test_analyze_task_generation_healthy(tracker, healthy_telemetry, baseline_data):
    """Test ROAD-C analysis with healthy metrics."""
    report = tracker._analyze_task_generation(healthy_telemetry, baseline_data)

    assert report.component == "ROAD-C"
    assert report.status in [ComponentStatus.STABLE, ComponentStatus.IMPROVING]
    assert len(report.metrics) >= 2  # At least completion rate and rework rate


def test_analyze_task_generation_low_completion(tracker):
    """Test ROAD-C analysis with low completion rate."""
    degraded_data = {"road_c": {"completed_tasks": 2, "total_tasks": 10, "rework_count": 7}}

    report = tracker._analyze_task_generation(degraded_data, {})

    assert report.status == ComponentStatus.DEGRADING
    assert any("Low task completion rate" in issue for issue in report.issues)
    assert any("rework" in rec.lower() for rec in report.recommendations)


def test_analyze_validation_coverage_healthy(tracker, healthy_telemetry, baseline_data):
    """Test ROAD-E analysis with healthy metrics."""
    report = tracker._analyze_validation_coverage(healthy_telemetry, baseline_data)

    assert report.component == "ROAD-E"
    assert report.status in [ComponentStatus.STABLE, ComponentStatus.IMPROVING]


def test_analyze_validation_coverage_low_validity(tracker):
    """Test ROAD-E analysis with low A-B test validity."""
    degraded_data = {
        "road_e": {
            "valid_ab_tests": 10,
            "total_ab_tests": 20,
            "regressions_caught": 7,
            "total_changes": 10,
        }
    }

    report = tracker._analyze_validation_coverage(degraded_data, {})

    assert any("validity rate" in issue.lower() for issue in report.issues)


def test_analyze_policy_promotion_healthy(tracker, healthy_telemetry, baseline_data):
    """Test ROAD-F analysis with healthy metrics."""
    report = tracker._analyze_policy_promotion(healthy_telemetry, baseline_data)

    assert report.component == "ROAD-F"
    assert report.status in [ComponentStatus.STABLE, ComponentStatus.IMPROVING]


def test_analyze_policy_promotion_high_rollback(tracker):
    """Test ROAD-F analysis with high rollback rate."""
    degraded_data = {"road_f": {"effective_promotions": 5, "total_promotions": 10, "rollbacks": 4}}

    report = tracker._analyze_policy_promotion(degraded_data, {})

    assert any("rollback rate" in issue.lower() for issue in report.issues)
    assert any("validation" in rec.lower() for rec in report.recommendations)


def test_analyze_anomaly_detection_healthy(tracker, healthy_telemetry, baseline_data):
    """Test ROAD-G analysis with healthy metrics."""
    report = tracker._analyze_anomaly_detection(healthy_telemetry, baseline_data)

    assert report.component == "ROAD-G"
    assert report.status in [ComponentStatus.STABLE, ComponentStatus.IMPROVING]


def test_analyze_anomaly_detection_low_precision(tracker):
    """Test ROAD-G analysis with low alert precision."""
    degraded_data = {"road_g": {"actionable_alerts": 8, "total_alerts": 20, "false_positives": 10}}

    report = tracker._analyze_anomaly_detection(degraded_data, {})

    assert any("precision" in issue.lower() for issue in report.issues)


def test_analyze_auto_healing_healthy(tracker, healthy_telemetry, baseline_data):
    """Test ROAD-J analysis with healthy metrics."""
    report = tracker._analyze_auto_healing(healthy_telemetry, baseline_data)

    assert report.component == "ROAD-J"
    assert report.status in [ComponentStatus.STABLE, ComponentStatus.IMPROVING]


def test_analyze_auto_healing_low_success(tracker):
    """Test ROAD-J analysis with low healing success rate."""
    degraded_data = {
        "road_j": {"successful_heals": 6, "total_heal_attempts": 20, "escalations": 12}
    }

    report = tracker._analyze_auto_healing(degraded_data, {})

    assert report.status == ComponentStatus.DEGRADING
    assert any("success rate" in issue.lower() for issue in report.issues)


def test_analyze_model_optimization_healthy(tracker, healthy_telemetry, baseline_data):
    """Test ROAD-L analysis with healthy metrics."""
    report = tracker._analyze_model_optimization(healthy_telemetry, baseline_data)

    assert report.component == "ROAD-L"
    assert report.status in [ComponentStatus.STABLE, ComponentStatus.IMPROVING]


def test_analyze_model_optimization_low_accuracy(tracker):
    """Test ROAD-L analysis with low routing accuracy."""
    degraded_data = {
        "road_l": {
            "optimal_routings": 50,
            "total_routings": 100,
            "avg_tokens_per_success": 1800,
            "sample_count": 30,
        }
    }

    report = tracker._analyze_model_optimization(degraded_data, {})

    assert report.status == ComponentStatus.DEGRADING
    assert any("routing accuracy" in issue.lower() for issue in report.issues)


def test_determine_component_status_insufficient_data(tracker):
    """Test component status determination with insufficient data."""
    metrics = [
        MetricTrend(
            metric_name="test",
            current_value=0.5,
            baseline_value=0.4,
            trend_direction="improving",
            percent_change=25.0,
            sample_count=3,  # Below min_samples_for_trend
            confidence=0.3,
        )
    ]

    status = tracker._determine_component_status(metrics)
    assert status == ComponentStatus.INSUFFICIENT_DATA


def test_determine_component_status_degrading(tracker):
    """Test component status determination with degrading metrics."""
    metrics = [
        MetricTrend(
            metric_name="metric1",
            current_value=0.5,
            baseline_value=0.7,
            trend_direction="degrading",
            percent_change=-28.6,
            sample_count=20,
            confidence=0.9,
        )
    ]

    status = tracker._determine_component_status(metrics)
    assert status == ComponentStatus.DEGRADING


def test_determine_component_status_improving(tracker):
    """Test component status determination with improving metrics."""
    metrics = [
        MetricTrend(
            metric_name="metric1",
            current_value=0.85,
            baseline_value=0.75,
            trend_direction="improving",
            percent_change=13.3,
            sample_count=25,
            confidence=0.9,
        )
    ]

    status = tracker._determine_component_status(metrics)
    assert status == ComponentStatus.IMPROVING


def test_compute_component_score_no_data(tracker):
    """Test component score computation with no data."""
    score = tracker._compute_component_score([])
    assert score == 0.5  # Neutral score


def test_compute_component_score_improving(tracker):
    """Test component score computation with improving trends."""
    metrics = [
        MetricTrend(
            metric_name="metric1",
            current_value=0.85,
            baseline_value=0.75,
            trend_direction="improving",
            percent_change=13.3,
            sample_count=20,
            confidence=0.9,
        ),
        MetricTrend(
            metric_name="metric2",
            current_value=0.90,
            baseline_value=0.80,
            trend_direction="improving",
            percent_change=12.5,
            sample_count=25,
            confidence=0.9,
        ),
    ]

    score = tracker._compute_component_score(metrics)
    assert score > 0.7  # Should be above baseline with improvements


def test_compute_component_score_degrading(tracker):
    """Test component score computation with degrading trends."""
    metrics = [
        MetricTrend(
            metric_name="metric1",
            current_value=0.50,
            baseline_value=0.75,
            trend_direction="degrading",
            percent_change=-33.3,
            sample_count=20,
            confidence=0.9,
        )
    ]

    score = tracker._compute_component_score(metrics)
    assert score < 0.7  # Should be below baseline with degradation


def test_compute_overall_health_no_data(tracker):
    """Test overall health computation with no data."""
    overall_status, overall_score = tracker._compute_overall_health({})

    assert overall_status == FeedbackLoopHealth.UNKNOWN
    assert overall_score == 0.5


def test_compute_overall_health_multiple_degrading(tracker, degraded_telemetry, baseline_data):
    """Test overall health computation with multiple degrading components."""
    report = tracker.analyze_feedback_loop_health(degraded_telemetry, baseline_data)

    # With degraded data, should be DEGRADED or ATTENTION_REQUIRED
    assert report.overall_status in [
        FeedbackLoopHealth.DEGRADED,
        FeedbackLoopHealth.ATTENTION_REQUIRED,
    ]


def test_feedback_loop_health_report_structure(tracker, healthy_telemetry, baseline_data):
    """Test that feedback loop health report has correct structure."""
    report = tracker.analyze_feedback_loop_health(healthy_telemetry, baseline_data)

    # Check required fields
    assert hasattr(report, "timestamp")
    assert hasattr(report, "overall_status")
    assert hasattr(report, "overall_score")
    assert hasattr(report, "component_reports")
    assert hasattr(report, "critical_issues")
    assert hasattr(report, "warnings")
    assert hasattr(report, "metadata")

    # Check metadata
    assert "min_samples_for_trend" in report.metadata
    assert "degradation_threshold" in report.metadata
    assert "improvement_threshold" in report.metadata


def test_metric_trend_structure():
    """Test MetricTrend dataclass structure."""
    trend = MetricTrend(
        metric_name="test_metric",
        current_value=0.75,
        baseline_value=0.70,
        trend_direction="improving",
        percent_change=7.14,
        sample_count=15,
        confidence=0.9,
    )

    assert trend.metric_name == "test_metric"
    assert trend.current_value == 0.75
    assert trend.baseline_value == 0.70
    assert trend.trend_direction == "improving"
    assert trend.percent_change == 7.14
    assert trend.sample_count == 15
    assert trend.confidence == 0.9


def test_component_health_report_structure():
    """Test ComponentHealthReport dataclass structure."""
    from autopack.telemetry.meta_metrics import ComponentHealthReport

    report = ComponentHealthReport(
        component="ROAD-TEST",
        status=ComponentStatus.STABLE,
        overall_score=0.8,
        metrics=[],
        issues=[],
        recommendations=[],
    )

    assert report.component == "ROAD-TEST"
    assert report.status == ComponentStatus.STABLE
    assert report.overall_score == 0.8
    assert isinstance(report.metrics, list)
    assert isinstance(report.issues, list)
    assert isinstance(report.recommendations, list)


# Tests for FeedbackLoopLatency (IMP-LOOP-010)


def test_feedback_loop_latency_structure():
    """Test FeedbackLoopLatency dataclass structure."""
    latency = FeedbackLoopLatency(
        telemetry_to_analysis_ms=50000,
        analysis_to_task_ms=100000,
        total_latency_ms=150000,
        sla_threshold_ms=300000,
    )

    assert latency.telemetry_to_analysis_ms == 50000
    assert latency.analysis_to_task_ms == 100000
    assert latency.total_latency_ms == 150000
    assert latency.sla_threshold_ms == 300000


def test_feedback_loop_latency_default_sla():
    """Test FeedbackLoopLatency default SLA threshold (5 minutes)."""
    latency = FeedbackLoopLatency(
        telemetry_to_analysis_ms=50000,
        analysis_to_task_ms=100000,
        total_latency_ms=150000,
    )

    assert latency.sla_threshold_ms == 300000  # 5 minutes in milliseconds


def test_feedback_loop_latency_is_healthy_within_sla():
    """Test is_healthy returns True when latency is within SLA."""
    latency = FeedbackLoopLatency(
        telemetry_to_analysis_ms=50000,
        analysis_to_task_ms=100000,
        total_latency_ms=150000,  # 2.5 minutes, well within 5-minute SLA
        sla_threshold_ms=300000,
    )

    assert latency.is_healthy() is True


def test_feedback_loop_latency_is_healthy_at_sla_boundary():
    """Test is_healthy returns True when latency equals SLA exactly."""
    latency = FeedbackLoopLatency(
        telemetry_to_analysis_ms=150000,
        analysis_to_task_ms=150000,
        total_latency_ms=300000,  # Exactly at 5-minute SLA
        sla_threshold_ms=300000,
    )

    assert latency.is_healthy() is True


def test_feedback_loop_latency_is_healthy_breached():
    """Test is_healthy returns False when latency exceeds SLA."""
    latency = FeedbackLoopLatency(
        telemetry_to_analysis_ms=200000,
        analysis_to_task_ms=200000,
        total_latency_ms=400000,  # 6.67 minutes, exceeds 5-minute SLA
        sla_threshold_ms=300000,
    )

    assert latency.is_healthy() is False


def test_feedback_loop_latency_get_sla_status_excellent():
    """Test get_sla_status returns 'excellent' when under 50% of SLA."""
    latency = FeedbackLoopLatency(
        telemetry_to_analysis_ms=30000,
        analysis_to_task_ms=50000,
        total_latency_ms=80000,  # ~27% of SLA
        sla_threshold_ms=300000,
    )

    assert latency.get_sla_status() == "excellent"


def test_feedback_loop_latency_get_sla_status_good():
    """Test get_sla_status returns 'good' when between 50-80% of SLA."""
    latency = FeedbackLoopLatency(
        telemetry_to_analysis_ms=100000,
        analysis_to_task_ms=100000,
        total_latency_ms=200000,  # ~67% of SLA
        sla_threshold_ms=300000,
    )

    assert latency.get_sla_status() == "good"


def test_feedback_loop_latency_get_sla_status_acceptable():
    """Test get_sla_status returns 'acceptable' when between 80-100% of SLA."""
    latency = FeedbackLoopLatency(
        telemetry_to_analysis_ms=140000,
        analysis_to_task_ms=140000,
        total_latency_ms=280000,  # ~93% of SLA
        sla_threshold_ms=300000,
    )

    assert latency.get_sla_status() == "acceptable"


def test_feedback_loop_latency_get_sla_status_breached():
    """Test get_sla_status returns 'breached' when exceeding SLA."""
    latency = FeedbackLoopLatency(
        telemetry_to_analysis_ms=200000,
        analysis_to_task_ms=200000,
        total_latency_ms=400000,  # 133% of SLA
        sla_threshold_ms=300000,
    )

    assert latency.get_sla_status() == "breached"


def test_feedback_loop_latency_get_breach_amount_within_sla():
    """Test get_breach_amount_ms returns 0 when within SLA."""
    latency = FeedbackLoopLatency(
        telemetry_to_analysis_ms=50000,
        analysis_to_task_ms=100000,
        total_latency_ms=150000,
        sla_threshold_ms=300000,
    )

    assert latency.get_breach_amount_ms() == 0


def test_feedback_loop_latency_get_breach_amount_exceeded():
    """Test get_breach_amount_ms returns correct breach amount."""
    latency = FeedbackLoopLatency(
        telemetry_to_analysis_ms=200000,
        analysis_to_task_ms=200000,
        total_latency_ms=400000,  # 100000ms over SLA
        sla_threshold_ms=300000,
    )

    assert latency.get_breach_amount_ms() == 100000


def test_feedback_loop_latency_custom_sla():
    """Test FeedbackLoopLatency with custom SLA threshold."""
    # Use a 10-minute SLA instead of default 5 minutes
    latency = FeedbackLoopLatency(
        telemetry_to_analysis_ms=200000,
        analysis_to_task_ms=200000,
        total_latency_ms=400000,
        sla_threshold_ms=600000,  # 10 minutes
    )

    assert latency.is_healthy() is True
    assert latency.get_sla_status() == "good"  # 67% of custom SLA
    assert latency.get_breach_amount_ms() == 0


# Tests for Pipeline SLA Tracking (IMP-LOOP-017)


class TestPipelineStage:
    """Tests for PipelineStage enum."""

    def test_pipeline_stage_values(self):
        """Test PipelineStage enum has expected values."""
        assert PipelineStage.PHASE_COMPLETE.value == "phase_complete"
        assert PipelineStage.TELEMETRY_COLLECTED.value == "telemetry_collected"
        assert PipelineStage.MEMORY_PERSISTED.value == "memory_persisted"
        assert PipelineStage.TASK_GENERATED.value == "task_generated"
        assert PipelineStage.TASK_EXECUTED.value == "task_executed"

    def test_pipeline_stage_count(self):
        """Test PipelineStage has exactly 5 stages."""
        assert len(PipelineStage) == 5


class TestPipelineStageTimestamp:
    """Tests for PipelineStageTimestamp dataclass."""

    def test_timestamp_creation(self):
        """Test PipelineStageTimestamp instantiation."""
        now = datetime.utcnow()
        ts = PipelineStageTimestamp(
            stage=PipelineStage.PHASE_COMPLETE,
            timestamp=now,
            metadata={"phase_name": "test_phase"},
        )

        assert ts.stage == PipelineStage.PHASE_COMPLETE
        assert ts.timestamp == now
        assert ts.metadata == {"phase_name": "test_phase"}

    def test_timestamp_to_dict(self):
        """Test PipelineStageTimestamp serialization."""
        now = datetime.utcnow()
        ts = PipelineStageTimestamp(
            stage=PipelineStage.TELEMETRY_COLLECTED,
            timestamp=now,
        )

        result = ts.to_dict()
        assert result["stage"] == "telemetry_collected"
        assert result["timestamp"] == now.isoformat()
        assert result["metadata"] == {}


class TestPipelineSLAConfig:
    """Tests for PipelineSLAConfig dataclass."""

    def test_default_config(self):
        """Test PipelineSLAConfig default values."""
        config = PipelineSLAConfig()

        assert config.end_to_end_threshold_ms == 300000  # 5 minutes
        assert config.alert_on_breach is True
        # Check default stage thresholds are set
        assert "phase_complete_to_telemetry_collected" in config.stage_thresholds_ms

    def test_custom_config(self):
        """Test PipelineSLAConfig with custom values."""
        config = PipelineSLAConfig(
            end_to_end_threshold_ms=600000,  # 10 minutes
            stage_thresholds_ms={"custom_stage": 30000},
            alert_on_breach=False,
        )

        assert config.end_to_end_threshold_ms == 600000
        assert config.alert_on_breach is False
        assert "custom_stage" in config.stage_thresholds_ms


class TestPipelineLatencyTracker:
    """Tests for PipelineLatencyTracker class."""

    @pytest.fixture
    def tracker(self):
        """Create a pipeline latency tracker."""
        return PipelineLatencyTracker(pipeline_id="test-pipeline-001")

    def test_tracker_initialization(self, tracker):
        """Test tracker initialization."""
        assert tracker.pipeline_id == "test-pipeline-001"
        assert tracker.sla_config is not None
        assert tracker.sla_config.end_to_end_threshold_ms == 300000

    def test_tracker_with_custom_sla(self):
        """Test tracker with custom SLA config."""
        config = PipelineSLAConfig(end_to_end_threshold_ms=600000)
        tracker = PipelineLatencyTracker(sla_config=config)

        assert tracker.sla_config.end_to_end_threshold_ms == 600000

    def test_record_stage(self, tracker):
        """Test recording a pipeline stage."""
        now = datetime.utcnow()
        result = tracker.record_stage(
            PipelineStage.PHASE_COMPLETE,
            timestamp=now,
            metadata={"test": "value"},
        )

        assert result.stage == PipelineStage.PHASE_COMPLETE
        assert result.timestamp == now
        assert result.metadata == {"test": "value"}

    def test_record_stage_default_timestamp(self, tracker):
        """Test recording a stage without explicit timestamp."""
        before = datetime.utcnow()
        result = tracker.record_stage(PipelineStage.PHASE_COMPLETE)
        after = datetime.utcnow()

        assert before <= result.timestamp <= after

    def test_get_stage_timestamp(self, tracker):
        """Test retrieving a recorded stage timestamp."""
        now = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=now)

        result = tracker.get_stage_timestamp(PipelineStage.PHASE_COMPLETE)
        assert result is not None
        assert result.timestamp == now

        # Non-recorded stage returns None
        result = tracker.get_stage_timestamp(PipelineStage.TASK_EXECUTED)
        assert result is None

    def test_get_stage_latency_ms(self, tracker):
        """Test calculating latency between stages."""
        t1 = datetime.utcnow()
        t2 = t1 + timedelta(seconds=30)  # 30 seconds later

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=t1)
        tracker.record_stage(PipelineStage.TELEMETRY_COLLECTED, timestamp=t2)

        latency = tracker.get_stage_latency_ms(
            PipelineStage.PHASE_COMPLETE,
            PipelineStage.TELEMETRY_COLLECTED,
        )

        assert latency == 30000  # 30 seconds in ms

    def test_get_stage_latency_missing_stage(self, tracker):
        """Test latency calculation with missing stage."""
        tracker.record_stage(PipelineStage.PHASE_COMPLETE)

        latency = tracker.get_stage_latency_ms(
            PipelineStage.PHASE_COMPLETE,
            PipelineStage.TELEMETRY_COLLECTED,  # Not recorded
        )

        assert latency is None

    def test_get_stage_latencies(self, tracker):
        """Test getting all stage-to-stage latencies."""
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.TELEMETRY_COLLECTED,
            timestamp=base + timedelta(seconds=10),
        )
        tracker.record_stage(
            PipelineStage.MEMORY_PERSISTED,
            timestamp=base + timedelta(seconds=20),
        )

        latencies = tracker.get_stage_latencies()

        assert latencies["phase_complete_to_telemetry_collected"] == 10000
        assert latencies["telemetry_collected_to_memory_persisted"] == 10000
        assert latencies["memory_persisted_to_task_generated"] is None

    def test_get_end_to_end_latency(self, tracker):
        """Test end-to-end latency calculation."""
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base + timedelta(minutes=2),
        )

        latency = tracker.get_end_to_end_latency_ms()
        assert latency == 120000  # 2 minutes in ms

    def test_get_end_to_end_latency_incomplete(self, tracker):
        """Test end-to-end latency when pipeline is incomplete."""
        tracker.record_stage(PipelineStage.PHASE_COMPLETE)

        latency = tracker.get_end_to_end_latency_ms()
        assert latency is None

    def test_get_partial_latency(self, tracker):
        """Test partial latency calculation."""
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.MEMORY_PERSISTED,
            timestamp=base + timedelta(seconds=45),
        )

        latency = tracker.get_partial_latency_ms()
        assert latency == 45000

    def test_is_within_sla_true(self, tracker):
        """Test is_within_sla returns True when under threshold."""
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base + timedelta(minutes=2),  # Under 5 min SLA
        )

        assert tracker.is_within_sla() is True

    def test_is_within_sla_false(self, tracker):
        """Test is_within_sla returns False when over threshold."""
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base + timedelta(minutes=10),  # Over 5 min SLA
        )

        assert tracker.is_within_sla() is False

    def test_is_within_sla_incomplete(self, tracker):
        """Test is_within_sla returns True when incomplete."""
        tracker.record_stage(PipelineStage.PHASE_COMPLETE)
        assert tracker.is_within_sla() is True  # Can't determine, assume OK

    def test_check_sla_breaches_none(self, tracker):
        """Test no breaches when within SLA."""
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base + timedelta(minutes=2),
        )

        breaches = tracker.check_sla_breaches()
        # Filter to only end-to-end breaches
        e2e_breaches = [b for b in breaches if b.stage_to == "task_executed"]
        assert len(e2e_breaches) == 0

    def test_check_sla_breaches_end_to_end(self, tracker):
        """Test end-to-end SLA breach detection."""
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base + timedelta(minutes=10),  # Double the SLA
        )

        breaches = tracker.check_sla_breaches()
        e2e_breaches = [b for b in breaches if b.stage_to == "task_executed"]

        assert len(e2e_breaches) == 1
        assert e2e_breaches[0].level == "critical"  # >50% over threshold
        assert e2e_breaches[0].threshold_ms == 300000
        assert e2e_breaches[0].actual_ms == 600000
        assert e2e_breaches[0].breach_amount_ms == 300000

    def test_check_sla_breaches_stage_level(self, tracker):
        """Test stage-level SLA breach detection."""
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.TELEMETRY_COLLECTED,
            timestamp=base + timedelta(minutes=3),  # Over 1 min stage threshold
        )

        breaches = tracker.check_sla_breaches()
        stage_breaches = [b for b in breaches if b.stage_from == "phase_complete"]

        assert len(stage_breaches) >= 1

    def test_get_sla_status_excellent(self, tracker):
        """Test SLA status 'excellent' when under 50%."""
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base + timedelta(minutes=1),  # 1 min = 20% of 5 min
        )

        assert tracker.get_sla_status() == "excellent"

    def test_get_sla_status_good(self, tracker):
        """Test SLA status 'good' when 50-80%."""
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base + timedelta(seconds=200),  # ~67% of 5 min
        )

        assert tracker.get_sla_status() == "good"

    def test_get_sla_status_acceptable(self, tracker):
        """Test SLA status 'acceptable' when 80-100%."""
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base + timedelta(seconds=270),  # 90% of 5 min
        )

        assert tracker.get_sla_status() == "acceptable"

    def test_get_sla_status_warning(self, tracker):
        """Test SLA status 'warning' when 100-150%."""
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base + timedelta(minutes=6),  # 120% of 5 min
        )

        assert tracker.get_sla_status() == "warning"

    def test_get_sla_status_breached(self, tracker):
        """Test SLA status 'breached' when over 150%."""
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base + timedelta(minutes=10),  # 200% of 5 min
        )

        assert tracker.get_sla_status() == "breached"

    def test_get_sla_status_unknown(self, tracker):
        """Test SLA status 'unknown' when incomplete."""
        tracker.record_stage(PipelineStage.PHASE_COMPLETE)
        assert tracker.get_sla_status() == "unknown"

    def test_to_feedback_loop_latency(self, tracker):
        """Test conversion to FeedbackLoopLatency."""
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.TELEMETRY_COLLECTED,
            timestamp=base + timedelta(seconds=30),
        )
        tracker.record_stage(
            PipelineStage.TASK_GENERATED,
            timestamp=base + timedelta(seconds=60),
        )
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base + timedelta(seconds=120),
        )

        latency = tracker.to_feedback_loop_latency()

        assert isinstance(latency, FeedbackLoopLatency)
        assert latency.telemetry_to_analysis_ms == 30000
        assert latency.analysis_to_task_ms == 30000  # telemetry to task_generated
        assert latency.total_latency_ms == 120000
        assert latency.sla_threshold_ms == 300000

    def test_to_dict(self, tracker):
        """Test tracker serialization to dict."""
        base = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base)
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base + timedelta(minutes=2),
        )

        result = tracker.to_dict()

        assert result["pipeline_id"] == "test-pipeline-001"
        assert "stages" in result
        assert "phase_complete" in result["stages"]
        assert "task_executed" in result["stages"]
        assert result["end_to_end_latency_ms"] == 120000
        assert result["sla_status"] == "excellent"
        assert "sla_config" in result
        assert "breaches" in result


class TestSLABreachAlert:
    """Tests for SLABreachAlert dataclass."""

    def test_breach_alert_creation(self):
        """Test SLABreachAlert instantiation."""
        alert = SLABreachAlert(
            level="warning",
            stage_from="phase_complete",
            stage_to="telemetry_collected",
            threshold_ms=60000,
            actual_ms=90000,
            breach_amount_ms=30000,
            message="Test breach message",
        )

        assert alert.level == "warning"
        assert alert.stage_from == "phase_complete"
        assert alert.stage_to == "telemetry_collected"
        assert alert.threshold_ms == 60000
        assert alert.actual_ms == 90000
        assert alert.breach_amount_ms == 30000
        assert alert.message == "Test breach message"

    def test_breach_alert_to_dict(self):
        """Test SLABreachAlert serialization."""
        alert = SLABreachAlert(
            level="critical",
            stage_from=None,
            stage_to=None,
            threshold_ms=300000,
            actual_ms=600000,
            breach_amount_ms=300000,
            message="End-to-end SLA breached",
        )

        result = alert.to_dict()

        assert result["level"] == "critical"
        assert result["stage_from"] is None
        assert result["threshold_ms"] == 300000
        assert result["actual_ms"] == 600000
        assert result["message"] == "End-to-end SLA breached"
        assert "timestamp" in result
