"""Tests for performance metrics collector."""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from telemetry.performance_metrics import (PerformanceCollector,
                                           PerformanceMetric, SlotUtilization,
                                           get_collector,
                                           record_metric_from_ps)


@pytest.fixture
def temp_metrics_file():
    """Create a temporary file for metrics storage."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{}")
        temp_path = f.name
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def collector(temp_metrics_file):
    """Create a PerformanceCollector instance with temp file."""
    return PerformanceCollector(metrics_path=temp_metrics_file)


class TestPerformanceMetric:
    """Tests for PerformanceMetric dataclass."""

    def test_create_metric(self):
        """Test creating a performance metric."""
        metric = PerformanceMetric(
            metric_name="test_metric",
            value=42.5,
            unit="seconds",
            timestamp=datetime.now(),
            context={"key": "value"},
        )

        assert metric.metric_name == "test_metric"
        assert metric.value == 42.5
        assert metric.unit == "seconds"
        assert metric.context["key"] == "value"

    def test_metric_default_context(self):
        """Test that context defaults to empty dict."""
        metric = PerformanceMetric(
            metric_name="test",
            value=1.0,
            unit="count",
            timestamp=datetime.now(),
        )

        assert metric.context == {}


class TestSlotUtilization:
    """Tests for SlotUtilization dataclass."""

    def test_create_slot_utilization(self):
        """Test creating slot utilization."""
        util = SlotUtilization(
            slot_id=1,
            total_time=timedelta(hours=1),
            busy_time=timedelta(minutes=45),
            idle_time=timedelta(minutes=15),
            utilization_percent=75.0,
        )

        assert util.slot_id == 1
        assert util.total_time == timedelta(hours=1)
        assert util.busy_time == timedelta(minutes=45)
        assert util.idle_time == timedelta(minutes=15)
        assert util.utilization_percent == 75.0


class TestPerformanceCollector:
    """Tests for PerformanceCollector class."""

    def test_init_creates_empty_metrics(self, temp_metrics_file):
        """Test that initialization starts with empty metrics."""
        collector = PerformanceCollector(metrics_path=temp_metrics_file)

        assert collector.metrics == []

    def test_init_loads_existing_metrics(self, temp_metrics_file):
        """Test that initialization loads existing metrics from file."""
        existing_data = {
            "metrics": [
                {
                    "metric_name": "test",
                    "value": 10.0,
                    "unit": "seconds",
                    "timestamp": "2024-01-01T12:00:00",
                    "context": {"phase_id": "test-phase"},
                }
            ]
        }
        with open(temp_metrics_file, "w") as f:
            json.dump(existing_data, f)

        collector = PerformanceCollector(metrics_path=temp_metrics_file)

        assert len(collector.metrics) == 1
        assert collector.metrics[0].metric_name == "test"
        assert collector.metrics[0].value == 10.0

    def test_record_phase_duration(self, collector):
        """Test recording phase duration."""
        start = datetime(2024, 1, 1, 12, 0, 0)
        end = datetime(2024, 1, 1, 12, 30, 0)

        metric = collector.record_phase_duration(
            phase_id="phase-1",
            start=start,
            end=end,
            imp_id="IMP-TEST-001",
        )

        assert metric.metric_name == "phase_duration"
        assert metric.value == 1800.0  # 30 minutes in seconds
        assert metric.unit == "seconds"
        assert metric.context["phase_id"] == "phase-1"
        assert metric.context["imp_id"] == "IMP-TEST-001"
        assert len(collector.metrics) == 1

    def test_record_phase_duration_saves_to_file(self, collector, temp_metrics_file):
        """Test that recording saves metrics to file."""
        start = datetime(2024, 1, 1, 12, 0, 0)
        end = datetime(2024, 1, 1, 12, 10, 0)

        collector.record_phase_duration(
            phase_id="phase-2",
            start=start,
            end=end,
        )

        with open(temp_metrics_file) as f:
            data = json.load(f)

        assert len(data["metrics"]) == 1
        assert data["metrics"][0]["metric_name"] == "phase_duration"
        assert data["metrics"][0]["value"] == 600.0

    def test_record_slot_utilization(self, collector):
        """Test recording slot utilization."""
        result = collector.record_slot_utilization(
            slot_id=1,
            busy_time=timedelta(minutes=45),
            idle_time=timedelta(minutes=15),
        )

        assert isinstance(result, SlotUtilization)
        assert result.slot_id == 1
        assert result.utilization_percent == 75.0
        assert result.total_time == timedelta(hours=1)

        # Check metric was recorded
        assert len(collector.metrics) == 1
        assert collector.metrics[0].metric_name == "slot_utilization"
        assert collector.metrics[0].value == 75.0
        assert collector.metrics[0].unit == "percent"

    def test_record_slot_utilization_zero_time(self, collector):
        """Test slot utilization with zero total time."""
        result = collector.record_slot_utilization(
            slot_id=2,
            busy_time=timedelta(0),
            idle_time=timedelta(0),
        )

        assert result.utilization_percent == 0.0

    def test_record_ci_wait_time(self, collector):
        """Test recording CI wait time."""
        metric = collector.record_ci_wait_time(
            pr_number=123,
            wait_seconds=300.0,
            outcome="success",
        )

        assert metric.metric_name == "ci_wait_time"
        assert metric.value == 300.0
        assert metric.unit == "seconds"
        assert metric.context["pr_number"] == 123
        assert metric.context["outcome"] == "success"

    def test_record_ci_wait_time_failure(self, collector):
        """Test recording CI wait time for failures."""
        metric = collector.record_ci_wait_time(
            pr_number=456,
            wait_seconds=600.0,
            outcome="failure",
        )

        assert metric.context["outcome"] == "failure"

    def test_record_wave_throughput(self, collector):
        """Test recording wave throughput."""
        metric = collector.record_wave_throughput(
            wave_number=1,
            phases_completed=10,
            duration=timedelta(hours=2),
        )

        assert metric.metric_name == "wave_throughput"
        assert metric.value == 5.0  # 10 phases / 2 hours
        assert metric.unit == "phases_per_hour"
        assert metric.context["wave_number"] == 1
        assert metric.context["phases_completed"] == 10

    def test_record_wave_throughput_zero_duration(self, collector):
        """Test wave throughput with zero duration."""
        metric = collector.record_wave_throughput(
            wave_number=2,
            phases_completed=5,
            duration=timedelta(0),
        )

        assert metric.value == 0.0

    def test_get_efficiency_report_empty(self, collector):
        """Test efficiency report with no metrics."""
        report = collector.get_efficiency_report()

        assert "error" in report
        assert report["error"] == "No metrics collected yet"

    def test_get_efficiency_report_with_metrics(self, collector):
        """Test efficiency report with collected metrics."""
        # Record various metrics
        start = datetime(2024, 1, 1, 12, 0, 0)
        collector.record_phase_duration("p1", start, start + timedelta(minutes=10))
        collector.record_phase_duration("p2", start, start + timedelta(minutes=20))
        collector.record_ci_wait_time(1, 100.0, "success")
        collector.record_ci_wait_time(2, 200.0, "success")
        collector.record_slot_utilization(1, timedelta(minutes=30), timedelta(minutes=30))
        collector.record_slot_utilization(2, timedelta(minutes=45), timedelta(minutes=15))

        report = collector.get_efficiency_report()

        assert report["phase_completion"]["count"] == 2
        assert report["phase_completion"]["avg_seconds"] == 900.0  # (600 + 1200) / 2
        assert report["phase_completion"]["min_seconds"] == 600.0
        assert report["phase_completion"]["max_seconds"] == 1200.0

        assert report["ci_performance"]["count"] == 2
        assert report["ci_performance"]["avg_wait_seconds"] == 150.0

        assert report["slot_efficiency"]["avg_utilization_percent"] == 62.5  # (50 + 75) / 2

        assert "generated_at" in report


class TestGetCollector:
    """Tests for get_collector() function."""

    def test_get_collector_returns_instance(self, temp_metrics_file):
        """Test that get_collector returns a PerformanceCollector."""
        import telemetry.performance_metrics as module

        module._default_collector = None

        collector = get_collector(metrics_path=temp_metrics_file)

        assert isinstance(collector, PerformanceCollector)

    def test_get_collector_reuses_instance(self, temp_metrics_file):
        """Test that repeated calls return the same instance."""
        import telemetry.performance_metrics as module

        module._default_collector = None

        collector1 = get_collector(metrics_path=temp_metrics_file)
        collector2 = get_collector()

        assert collector1 is collector2

    def test_get_collector_new_path_creates_new(self, temp_metrics_file):
        """Test that providing a new path creates a new instance."""
        import telemetry.performance_metrics as module

        module._default_collector = None

        collector1 = get_collector(metrics_path=temp_metrics_file)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(b"{}")
            new_path = f.name

        try:
            collector2 = get_collector(metrics_path=new_path)
            assert collector1 is not collector2
        finally:
            Path(new_path).unlink(missing_ok=True)


class TestRecordMetricFromPs:
    """Tests for record_metric_from_ps() helper function."""

    def test_record_phase_metric(self, temp_metrics_file):
        """Test recording phase metric from PowerShell helper."""
        import telemetry.performance_metrics as module

        module._default_collector = None
        module._default_collector = PerformanceCollector(temp_metrics_file)

        record_metric_from_ps(
            "phase",
            phase_id="test-phase",
            start="2024-01-01T12:00:00",
            end="2024-01-01T12:30:00",
            imp_id="IMP-TEST-001",
        )

        collector = get_collector()
        assert len(collector.metrics) == 1
        assert collector.metrics[0].metric_name == "phase_duration"

    def test_record_ci_metric(self, temp_metrics_file):
        """Test recording CI metric from PowerShell helper."""
        import telemetry.performance_metrics as module

        module._default_collector = None
        module._default_collector = PerformanceCollector(temp_metrics_file)

        record_metric_from_ps(
            "ci",
            pr_number=123,
            wait_seconds=300.0,
            outcome="success",
        )

        collector = get_collector()
        assert len(collector.metrics) == 1
        assert collector.metrics[0].metric_name == "ci_wait_time"

    def test_record_slot_metric(self, temp_metrics_file):
        """Test recording slot metric from PowerShell helper."""
        import telemetry.performance_metrics as module

        module._default_collector = None
        module._default_collector = PerformanceCollector(temp_metrics_file)

        record_metric_from_ps(
            "slot",
            slot_id=1,
            busy_seconds=1800.0,
            idle_seconds=600.0,
        )

        collector = get_collector()
        assert len(collector.metrics) == 1
        assert collector.metrics[0].metric_name == "slot_utilization"

    def test_record_wave_metric(self, temp_metrics_file):
        """Test recording wave metric from PowerShell helper."""
        import telemetry.performance_metrics as module

        module._default_collector = None
        module._default_collector = PerformanceCollector(temp_metrics_file)

        record_metric_from_ps(
            "wave",
            wave_number=1,
            phases_completed=5,
            duration_seconds=3600.0,
        )

        collector = get_collector()
        assert len(collector.metrics) == 1
        assert collector.metrics[0].metric_name == "wave_throughput"
