"""
Tests for metrics_aggregator.py - Centralized Metrics Aggregation System.

IMP-TEL-001: Tests verify MetricsAggregator correctly tracks:
- Cycle success/failure rates
- PR merge rates
- Cycle start/completion recording
"""

import json
import os
import tempfile

from metrics_aggregator import MetricsAggregator


class TestMetricsAggregatorInit:
    """Test MetricsAggregator initialization."""

    def test_creates_empty_metrics_when_no_file(self):
        """MetricsAggregator creates empty structure when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_path = os.path.join(tmpdir, "test_metrics.json")
            aggregator = MetricsAggregator(metrics_path)

            assert aggregator.metrics["cycles"] == []
            assert aggregator.metrics["summary"]["total_cycles"] == 0
            assert aggregator.metrics["summary"]["successful_cycles"] == 0
            assert aggregator.metrics["summary"]["failed_cycles"] == 0
            assert aggregator.metrics["summary"]["total_prs_created"] == 0
            assert aggregator.metrics["summary"]["total_prs_merged"] == 0

    def test_loads_existing_metrics_file(self):
        """MetricsAggregator loads data from existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_path = os.path.join(tmpdir, "test_metrics.json")
            existing_data = {
                "cycles": [{"cycle_id": "test-1", "status": "success"}],
                "summary": {
                    "total_cycles": 5,
                    "successful_cycles": 3,
                    "failed_cycles": 2,
                    "total_prs_created": 10,
                    "total_prs_merged": 8,
                },
            }
            with open(metrics_path, "w") as f:
                json.dump(existing_data, f)

            aggregator = MetricsAggregator(metrics_path)

            assert len(aggregator.metrics["cycles"]) == 1
            assert aggregator.metrics["summary"]["total_cycles"] == 5


class TestRecordCycleStart:
    """Test recording cycle start."""

    def test_records_cycle_start(self):
        """record_cycle_start adds new cycle with in_progress status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_path = os.path.join(tmpdir, "test_metrics.json")
            aggregator = MetricsAggregator(metrics_path)

            aggregator.record_cycle_start("cycle-001")

            assert len(aggregator.metrics["cycles"]) == 1
            cycle = aggregator.metrics["cycles"][0]
            assert cycle["cycle_id"] == "cycle-001"
            assert cycle["status"] == "in_progress"
            assert cycle["started_at"] is not None
            assert cycle["completed_at"] is None

    def test_persists_cycle_start_to_file(self):
        """record_cycle_start saves to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_path = os.path.join(tmpdir, "test_metrics.json")
            aggregator = MetricsAggregator(metrics_path)

            aggregator.record_cycle_start("cycle-002")

            # Reload from file
            with open(metrics_path, "r") as f:
                saved_data = json.load(f)

            assert len(saved_data["cycles"]) == 1
            assert saved_data["cycles"][0]["cycle_id"] == "cycle-002"


class TestRecordCycleComplete:
    """Test recording cycle completion."""

    def test_records_successful_cycle_complete(self):
        """record_cycle_complete marks cycle as success."""
        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_path = os.path.join(tmpdir, "test_metrics.json")
            aggregator = MetricsAggregator(metrics_path)

            aggregator.record_cycle_start("cycle-001")
            aggregator.record_cycle_complete("cycle-001", success=True, prs_created=2, prs_merged=2)

            cycle = aggregator.metrics["cycles"][0]
            assert cycle["status"] == "success"
            assert cycle["completed_at"] is not None
            assert cycle["prs_created"] == 2
            assert cycle["prs_merged"] == 2

    def test_records_failed_cycle_complete(self):
        """record_cycle_complete marks cycle as failed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_path = os.path.join(tmpdir, "test_metrics.json")
            aggregator = MetricsAggregator(metrics_path)

            aggregator.record_cycle_start("cycle-001")
            aggregator.record_cycle_complete(
                "cycle-001", success=False, prs_created=1, prs_merged=0
            )

            cycle = aggregator.metrics["cycles"][0]
            assert cycle["status"] == "failed"
            assert aggregator.metrics["summary"]["failed_cycles"] == 1

    def test_updates_summary_on_completion(self):
        """record_cycle_complete updates summary statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_path = os.path.join(tmpdir, "test_metrics.json")
            aggregator = MetricsAggregator(metrics_path)

            aggregator.record_cycle_start("cycle-001")
            aggregator.record_cycle_complete("cycle-001", success=True, prs_created=3, prs_merged=2)

            summary = aggregator.metrics["summary"]
            assert summary["total_cycles"] == 1
            assert summary["successful_cycles"] == 1
            assert summary["total_prs_created"] == 3
            assert summary["total_prs_merged"] == 2


class TestGetSuccessRate:
    """Test success rate calculation."""

    def test_returns_zero_when_no_cycles(self):
        """get_success_rate returns 0.0 when no cycles recorded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_path = os.path.join(tmpdir, "test_metrics.json")
            aggregator = MetricsAggregator(metrics_path)

            assert aggregator.get_success_rate() == 0.0

    def test_calculates_correct_success_rate(self):
        """get_success_rate calculates correct percentage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_path = os.path.join(tmpdir, "test_metrics.json")
            aggregator = MetricsAggregator(metrics_path)

            # Record 3 successful, 1 failed
            for i in range(3):
                aggregator.record_cycle_start(f"success-{i}")
                aggregator.record_cycle_complete(f"success-{i}", success=True)

            aggregator.record_cycle_start("failed-1")
            aggregator.record_cycle_complete("failed-1", success=False)

            # 3 out of 4 = 0.75
            assert aggregator.get_success_rate() == 0.75

    def test_returns_one_when_all_successful(self):
        """get_success_rate returns 1.0 when all cycles succeed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_path = os.path.join(tmpdir, "test_metrics.json")
            aggregator = MetricsAggregator(metrics_path)

            aggregator.record_cycle_start("cycle-1")
            aggregator.record_cycle_complete("cycle-1", success=True)

            assert aggregator.get_success_rate() == 1.0


class TestMetricsPersistence:
    """Test metrics file persistence."""

    def test_metrics_persist_across_instances(self):
        """Metrics survive across MetricsAggregator instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_path = os.path.join(tmpdir, "test_metrics.json")

            # First instance
            aggregator1 = MetricsAggregator(metrics_path)
            aggregator1.record_cycle_start("cycle-001")
            aggregator1.record_cycle_complete("cycle-001", success=True, prs_merged=5)

            # Second instance loads saved data
            aggregator2 = MetricsAggregator(metrics_path)

            assert len(aggregator2.metrics["cycles"]) == 1
            assert aggregator2.metrics["summary"]["total_prs_merged"] == 5
            assert aggregator2.get_success_rate() == 1.0
