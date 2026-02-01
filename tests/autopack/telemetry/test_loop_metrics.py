"""Tests for closed-loop observability metrics.

IMP-OBS-001: Tests the LoopMetricsCollector and related components
for tracking feedback loop effectiveness.
"""

import pytest

from autopack.telemetry.loop_metrics import (ConfidenceCalibrationBucket,
                                             InsightRecord, InsightSource,
                                             LoopEffectivenessMetrics,
                                             LoopMetricsCollector, SourceStats,
                                             TaskOutcome)


class TestInsightSource:
    """Tests for InsightSource enum."""

    def test_all_sources_defined(self):
        """Ensure all expected insight sources are defined."""
        expected_sources = [
            "telemetry_analyzer",
            "memory_service",
            "anomaly_detector",
            "causal_analysis",
            "regression_protector",
            "manual",
            "unknown",
        ]
        actual_sources = [s.value for s in InsightSource]
        assert set(expected_sources) == set(actual_sources)


class TestTaskOutcome:
    """Tests for TaskOutcome enum."""

    def test_all_outcomes_defined(self):
        """Ensure all expected task outcomes are defined."""
        expected_outcomes = ["success", "failure", "partial", "pending", "skipped"]
        actual_outcomes = [o.value for o in TaskOutcome]
        assert set(expected_outcomes) == set(actual_outcomes)


class TestLoopEffectivenessMetrics:
    """Tests for LoopEffectivenessMetrics dataclass."""

    def test_default_values(self):
        """Test that default values are all zero/empty."""
        metrics = LoopEffectivenessMetrics()

        assert metrics.insights_detected == 0
        assert metrics.insights_filtered == 0
        assert metrics.tasks_generated == 0
        assert metrics.tasks_succeeded == 0
        assert metrics.tasks_failed == 0
        assert metrics.tasks_partial == 0
        assert metrics.tasks_pending == 0
        assert metrics.failures_prevented == 0
        assert metrics.conversion_rate == 0.0
        assert metrics.success_rate == 0.0
        assert metrics.success_rate_by_source == {}
        assert metrics.confidence_calibration == 0.0

    def test_to_dict(self):
        """Test serialization to dictionary."""
        metrics = LoopEffectivenessMetrics(
            insights_detected=10,
            tasks_generated=5,
            tasks_succeeded=3,
            conversion_rate=0.5,
            success_rate=0.6,
            success_rate_by_source={"telemetry_analyzer": 0.75},
            confidence_calibration=0.85,
        )

        result = metrics.to_dict()

        assert result["insights_detected"] == 10
        assert result["tasks_generated"] == 5
        assert result["tasks_succeeded"] == 3
        assert result["conversion_rate"] == 0.5
        assert result["success_rate"] == 0.6
        assert result["success_rate_by_source"] == {"telemetry_analyzer": 0.75}
        assert result["confidence_calibration"] == 0.85


class TestInsightRecord:
    """Tests for InsightRecord dataclass."""

    def test_default_values(self):
        """Test that InsightRecord has sensible defaults."""
        record = InsightRecord(
            insight_id="test-insight-1",
            source=InsightSource.TELEMETRY_ANALYZER,
        )

        assert record.insight_id == "test-insight-1"
        assert record.source == InsightSource.TELEMETRY_ANALYZER
        assert record.confidence == 1.0
        assert record.was_filtered is False
        assert record.filter_reason is None
        assert record.task_id is None
        assert record.task_outcome is None

    def test_to_dict(self):
        """Test serialization to dictionary."""
        record = InsightRecord(
            insight_id="test-insight-1",
            source=InsightSource.MEMORY_SERVICE,
            confidence=0.85,
            was_filtered=True,
            filter_reason="duplicate",
        )

        result = record.to_dict()

        assert result["insight_id"] == "test-insight-1"
        assert result["source"] == "memory_service"
        assert result["confidence"] == 0.85
        assert result["was_filtered"] is True
        assert result["filter_reason"] == "duplicate"


class TestSourceStats:
    """Tests for SourceStats dataclass."""

    def test_conversion_rate_zero_insights(self):
        """Test conversion rate with zero insights."""
        stats = SourceStats(source=InsightSource.TELEMETRY_ANALYZER)
        assert stats.conversion_rate == 0.0

    def test_conversion_rate_calculation(self):
        """Test conversion rate calculation."""
        stats = SourceStats(
            source=InsightSource.TELEMETRY_ANALYZER,
            insights_count=10,
            tasks_generated=5,
        )
        assert stats.conversion_rate == 0.5

    def test_success_rate_zero_completed(self):
        """Test success rate with zero completed tasks."""
        stats = SourceStats(source=InsightSource.TELEMETRY_ANALYZER)
        assert stats.success_rate == 0.0

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        stats = SourceStats(
            source=InsightSource.TELEMETRY_ANALYZER,
            tasks_succeeded=3,
            tasks_failed=1,
            tasks_partial=1,
        )
        # 3 / (3 + 1 + 1) = 0.6
        assert stats.success_rate == 0.6

    def test_avg_confidence_zero_insights(self):
        """Test average confidence with zero insights."""
        stats = SourceStats(source=InsightSource.TELEMETRY_ANALYZER)
        assert stats.avg_confidence == 0.0

    def test_avg_confidence_calculation(self):
        """Test average confidence calculation."""
        stats = SourceStats(
            source=InsightSource.TELEMETRY_ANALYZER,
            insights_count=4,
            total_confidence=3.2,  # 0.8 avg
        )
        assert stats.avg_confidence == 0.8


class TestConfidenceCalibrationBucket:
    """Tests for ConfidenceCalibrationBucket dataclass."""

    def test_midpoint_calculation(self):
        """Test midpoint calculation."""
        bucket = ConfidenceCalibrationBucket(min_confidence=0.6, max_confidence=0.8)
        assert bucket.midpoint == 0.7

    def test_actual_success_rate_zero_samples(self):
        """Test actual success rate with zero samples."""
        bucket = ConfidenceCalibrationBucket(min_confidence=0.6, max_confidence=0.8)
        assert bucket.actual_success_rate == 0.0

    def test_actual_success_rate_calculation(self):
        """Test actual success rate calculation."""
        bucket = ConfidenceCalibrationBucket(
            min_confidence=0.6,
            max_confidence=0.8,
            insight_count=10,
            success_count=7,
            failure_count=3,
        )
        assert bucket.actual_success_rate == 0.7

    def test_calibration_error_zero_samples(self):
        """Test calibration error with zero samples."""
        bucket = ConfidenceCalibrationBucket(min_confidence=0.6, max_confidence=0.8)
        assert bucket.calibration_error == 0.0

    def test_calibration_error_perfect_calibration(self):
        """Test calibration error with perfect calibration."""
        # Midpoint is 0.7, actual success rate is 0.7 -> error = 0
        bucket = ConfidenceCalibrationBucket(
            min_confidence=0.6,
            max_confidence=0.8,
            insight_count=10,
            success_count=7,
            failure_count=3,
        )
        assert bucket.calibration_error == 0.0

    def test_calibration_error_calculation(self):
        """Test calibration error calculation."""
        # Midpoint is 0.7, actual success rate is 0.5 -> error = 0.2
        bucket = ConfidenceCalibrationBucket(
            min_confidence=0.6,
            max_confidence=0.8,
            insight_count=10,
            success_count=5,
            failure_count=5,
        )
        assert bucket.calibration_error == pytest.approx(0.2)


class TestLoopMetricsCollector:
    """Tests for LoopMetricsCollector class."""

    @pytest.fixture
    def collector(self):
        """Create a fresh collector for each test."""
        return LoopMetricsCollector()

    def test_initial_state(self, collector):
        """Test that collector starts in empty state."""
        metrics = collector.get_metrics()

        assert metrics.insights_detected == 0
        assert metrics.tasks_generated == 0
        assert metrics.tasks_succeeded == 0
        assert metrics.conversion_rate == 0.0
        assert metrics.success_rate == 0.0

    def test_record_insight_detected(self, collector):
        """Test recording insight detection."""
        record = collector.record_insight_detected(
            insight_id="insight-1",
            source=InsightSource.TELEMETRY_ANALYZER,
            confidence=0.85,
        )

        assert record.insight_id == "insight-1"
        assert record.source == InsightSource.TELEMETRY_ANALYZER
        assert record.confidence == 0.85

        metrics = collector.get_metrics()
        assert metrics.insights_detected == 1

    def test_record_insight_detected_with_string_source(self, collector):
        """Test recording insight with string source (auto-conversion)."""
        record = collector.record_insight_detected(
            insight_id="insight-1",
            source="telemetry_analyzer",
            confidence=0.85,
        )

        assert record.source == InsightSource.TELEMETRY_ANALYZER

    def test_record_insight_detected_with_unknown_source(self, collector):
        """Test recording insight with unknown source string."""
        record = collector.record_insight_detected(
            insight_id="insight-1",
            source="some_unknown_source",
            confidence=0.85,
        )

        assert record.source == InsightSource.UNKNOWN

    def test_record_insight_filtered(self, collector):
        """Test recording insight filtering."""
        collector.record_insight_detected(
            insight_id="insight-1",
            source=InsightSource.TELEMETRY_ANALYZER,
        )

        record = collector.record_insight_filtered(
            insight_id="insight-1",
            reason="low_confidence",
        )

        assert record.was_filtered is True
        assert record.filter_reason == "low_confidence"

        metrics = collector.get_metrics()
        assert metrics.insights_detected == 1
        assert metrics.insights_filtered == 1

    def test_record_insight_filtered_unknown_insight(self, collector):
        """Test filtering unknown insight returns None."""
        result = collector.record_insight_filtered(
            insight_id="nonexistent",
            reason="test",
        )

        assert result is None

    def test_record_task_generated(self, collector):
        """Test recording task generation."""
        collector.record_insight_detected(
            insight_id="insight-1",
            source=InsightSource.TELEMETRY_ANALYZER,
        )

        record = collector.record_task_generated(
            insight_id="insight-1",
            task_id="task-1",
        )

        assert record.task_id == "task-1"
        assert record.task_outcome == TaskOutcome.PENDING

        metrics = collector.get_metrics()
        assert metrics.tasks_generated == 1
        assert metrics.tasks_pending == 1

    def test_record_task_generated_auto_creates_insight(self, collector):
        """Test that task generation auto-creates missing insight."""
        record = collector.record_task_generated(
            insight_id="new-insight",
            task_id="task-1",
        )

        assert record is not None
        assert record.source == InsightSource.UNKNOWN

    def test_record_task_outcome_success(self, collector):
        """Test recording successful task outcome."""
        collector.record_insight_detected(
            insight_id="insight-1",
            source=InsightSource.TELEMETRY_ANALYZER,
        )
        collector.record_task_generated(
            insight_id="insight-1",
            task_id="task-1",
        )

        record = collector.record_task_outcome(
            task_id="task-1",
            outcome=TaskOutcome.SUCCESS,
        )

        assert record.task_outcome == TaskOutcome.SUCCESS

        metrics = collector.get_metrics()
        assert metrics.tasks_succeeded == 1
        assert metrics.tasks_pending == 0

    def test_record_task_outcome_failure(self, collector):
        """Test recording failed task outcome."""
        collector.record_insight_detected(
            insight_id="insight-1",
            source=InsightSource.TELEMETRY_ANALYZER,
        )
        collector.record_task_generated(
            insight_id="insight-1",
            task_id="task-1",
        )

        collector.record_task_outcome(
            task_id="task-1",
            outcome=TaskOutcome.FAILURE,
        )

        metrics = collector.get_metrics()
        assert metrics.tasks_failed == 1

    def test_record_task_outcome_with_string(self, collector):
        """Test recording task outcome with string (auto-conversion)."""
        collector.record_insight_detected(
            insight_id="insight-1",
            source=InsightSource.TELEMETRY_ANALYZER,
        )
        collector.record_task_generated(
            insight_id="insight-1",
            task_id="task-1",
        )

        record = collector.record_task_outcome(
            task_id="task-1",
            outcome="success",
        )

        assert record.task_outcome == TaskOutcome.SUCCESS

    def test_record_task_outcome_unknown_task(self, collector):
        """Test recording outcome for unknown task returns None."""
        result = collector.record_task_outcome(
            task_id="nonexistent",
            outcome=TaskOutcome.SUCCESS,
        )

        assert result is None

    def test_record_failure_prevented(self, collector):
        """Test recording failures prevented."""
        collector.record_failure_prevented(count=3)
        collector.record_failure_prevented(count=2)

        metrics = collector.get_metrics()
        assert metrics.failures_prevented == 5

    def test_conversion_rate_calculation(self, collector):
        """Test conversion rate is calculated correctly."""
        # 10 insights, 4 converted to tasks
        for i in range(10):
            collector.record_insight_detected(
                insight_id=f"insight-{i}",
                source=InsightSource.TELEMETRY_ANALYZER,
            )

        for i in range(4):
            collector.record_task_generated(
                insight_id=f"insight-{i}",
                task_id=f"task-{i}",
            )

        metrics = collector.get_metrics()
        assert metrics.conversion_rate == 0.4

    def test_success_rate_calculation(self, collector):
        """Test success rate is calculated correctly."""
        # 4 tasks: 2 success, 1 failure, 1 partial
        for i in range(4):
            collector.record_insight_detected(
                insight_id=f"insight-{i}",
                source=InsightSource.TELEMETRY_ANALYZER,
            )
            collector.record_task_generated(
                insight_id=f"insight-{i}",
                task_id=f"task-{i}",
            )

        collector.record_task_outcome("task-0", TaskOutcome.SUCCESS)
        collector.record_task_outcome("task-1", TaskOutcome.SUCCESS)
        collector.record_task_outcome("task-2", TaskOutcome.FAILURE)
        collector.record_task_outcome("task-3", TaskOutcome.PARTIAL)

        metrics = collector.get_metrics()
        # 2 success / 4 completed = 0.5
        assert metrics.success_rate == 0.5

    def test_success_rate_by_source(self, collector):
        """Test success rate breakdown by source."""
        # 2 insights from telemetry_analyzer: 1 success, 1 failure
        # 2 insights from memory_service: 2 success
        for i in range(2):
            collector.record_insight_detected(
                insight_id=f"telemetry-{i}",
                source=InsightSource.TELEMETRY_ANALYZER,
            )
            collector.record_task_generated(
                insight_id=f"telemetry-{i}",
                task_id=f"telemetry-task-{i}",
            )

        for i in range(2):
            collector.record_insight_detected(
                insight_id=f"memory-{i}",
                source=InsightSource.MEMORY_SERVICE,
            )
            collector.record_task_generated(
                insight_id=f"memory-{i}",
                task_id=f"memory-task-{i}",
            )

        collector.record_task_outcome("telemetry-task-0", TaskOutcome.SUCCESS)
        collector.record_task_outcome("telemetry-task-1", TaskOutcome.FAILURE)
        collector.record_task_outcome("memory-task-0", TaskOutcome.SUCCESS)
        collector.record_task_outcome("memory-task-1", TaskOutcome.SUCCESS)

        metrics = collector.get_metrics()
        assert metrics.success_rate_by_source["telemetry_analyzer"] == 0.5
        assert metrics.success_rate_by_source["memory_service"] == 1.0

    def test_get_source_breakdown(self, collector):
        """Test getting per-source metrics breakdown."""
        collector.record_insight_detected(
            insight_id="insight-1",
            source=InsightSource.TELEMETRY_ANALYZER,
            confidence=0.8,
        )
        collector.record_task_generated(insight_id="insight-1", task_id="task-1")
        collector.record_task_outcome("task-1", TaskOutcome.SUCCESS)

        breakdown = collector.get_source_breakdown()

        assert len(breakdown) == 1
        assert breakdown[0]["source"] == "telemetry_analyzer"
        assert breakdown[0]["insights_count"] == 1
        assert breakdown[0]["tasks_generated"] == 1
        assert breakdown[0]["tasks_succeeded"] == 1

    def test_get_calibration_breakdown(self, collector):
        """Test getting confidence calibration breakdown."""
        # Add insights with various confidence levels and outcomes
        # High confidence (0.8-1.0) insight that succeeds
        collector.record_insight_detected(
            insight_id="high-conf-1",
            source=InsightSource.TELEMETRY_ANALYZER,
            confidence=0.9,
        )
        collector.record_task_generated("high-conf-1", "task-1")
        collector.record_task_outcome("task-1", TaskOutcome.SUCCESS)

        # Low confidence (0.2-0.4) insight that fails
        collector.record_insight_detected(
            insight_id="low-conf-1",
            source=InsightSource.TELEMETRY_ANALYZER,
            confidence=0.3,
        )
        collector.record_task_generated("low-conf-1", "task-2")
        collector.record_task_outcome("task-2", TaskOutcome.FAILURE)

        breakdown = collector.get_calibration_breakdown()

        assert len(breakdown) == 5  # 5 buckets
        # Find the 0.8-1.0 bucket
        high_bucket = next(b for b in breakdown if b["confidence_range"] == "0.8-1.0")
        assert high_bucket["success_count"] == 1
        assert high_bucket["failure_count"] == 0

        # Find the 0.2-0.4 bucket
        low_bucket = next(b for b in breakdown if b["confidence_range"] == "0.2-0.4")
        assert low_bucket["success_count"] == 0
        assert low_bucket["failure_count"] == 1

    def test_get_conversion_funnel(self, collector):
        """Test getting conversion funnel data."""
        # Create 10 insights, filter 2, generate 6 tasks, complete 4, succeed 3
        for i in range(10):
            collector.record_insight_detected(
                insight_id=f"insight-{i}",
                source=InsightSource.TELEMETRY_ANALYZER,
            )

        collector.record_insight_filtered("insight-0", "duplicate")
        collector.record_insight_filtered("insight-1", "low_confidence")

        for i in range(2, 8):
            collector.record_task_generated(f"insight-{i}", f"task-{i}")

        collector.record_task_outcome("task-2", TaskOutcome.SUCCESS)
        collector.record_task_outcome("task-3", TaskOutcome.SUCCESS)
        collector.record_task_outcome("task-4", TaskOutcome.SUCCESS)
        collector.record_task_outcome("task-5", TaskOutcome.FAILURE)
        # task-6 and task-7 remain pending

        funnel = collector.get_conversion_funnel()

        assert funnel["stages"][0]["name"] == "Insights Detected"
        assert funnel["stages"][0]["count"] == 10

        assert funnel["stages"][1]["name"] == "Passed Filtering"
        assert funnel["stages"][1]["count"] == 8

        assert funnel["stages"][2]["name"] == "Tasks Generated"
        assert funnel["stages"][2]["count"] == 6

        assert funnel["stages"][3]["name"] == "Tasks Completed"
        assert funnel["stages"][3]["count"] == 4

        assert funnel["stages"][4]["name"] == "Tasks Succeeded"
        assert funnel["stages"][4]["count"] == 3

        assert funnel["conversion_rates"]["end_to_end"] == 0.3

    def test_get_insight_record(self, collector):
        """Test retrieving a specific insight record."""
        collector.record_insight_detected(
            insight_id="insight-1",
            source=InsightSource.TELEMETRY_ANALYZER,
            confidence=0.85,
        )

        record = collector.get_insight_record("insight-1")

        assert record is not None
        assert record.insight_id == "insight-1"
        assert record.confidence == 0.85

    def test_get_insight_record_not_found(self, collector):
        """Test retrieving non-existent insight returns None."""
        record = collector.get_insight_record("nonexistent")
        assert record is None

    def test_get_summary(self, collector):
        """Test getting comprehensive summary."""
        collector.record_insight_detected(
            insight_id="insight-1",
            source=InsightSource.TELEMETRY_ANALYZER,
        )
        collector.record_task_generated("insight-1", "task-1")
        collector.record_task_outcome("task-1", TaskOutcome.SUCCESS)
        collector.record_failure_prevented(2)

        summary = collector.get_summary()

        assert "metrics" in summary
        assert "source_breakdown" in summary
        assert "calibration_breakdown" in summary
        assert "conversion_funnel" in summary
        assert summary["failures_prevented"] == 2

    def test_reset(self, collector):
        """Test resetting the collector."""
        collector.record_insight_detected(
            insight_id="insight-1",
            source=InsightSource.TELEMETRY_ANALYZER,
        )
        collector.record_task_generated("insight-1", "task-1")
        collector.record_failure_prevented(5)

        collector.reset()

        metrics = collector.get_metrics()
        assert metrics.insights_detected == 0
        assert metrics.tasks_generated == 0
        assert metrics.failures_prevented == 0

    def test_confidence_calibration_score(self, collector):
        """Test that confidence calibration score is calculated correctly."""
        # Create insights with confidence that matches their actual success rate
        # This should result in a high calibration score

        # High confidence (0.8-1.0) insights that succeed (good calibration)
        for i in range(5):
            collector.record_insight_detected(
                insight_id=f"high-{i}",
                source=InsightSource.TELEMETRY_ANALYZER,
                confidence=0.9,
            )
            collector.record_task_generated(f"high-{i}", f"high-task-{i}")
            collector.record_task_outcome(f"high-task-{i}", TaskOutcome.SUCCESS)

        # Low confidence (0.0-0.2) insights that fail (good calibration)
        for i in range(5):
            collector.record_insight_detected(
                insight_id=f"low-{i}",
                source=InsightSource.TELEMETRY_ANALYZER,
                confidence=0.1,
            )
            collector.record_task_generated(f"low-{i}", f"low-task-{i}")
            collector.record_task_outcome(f"low-task-{i}", TaskOutcome.FAILURE)

        metrics = collector.get_metrics()
        # With good calibration, score should be relatively high
        assert metrics.confidence_calibration > 0.5

    def test_duplicate_insight_update(self, collector):
        """Test that recording same insight twice updates rather than duplicates."""
        collector.record_insight_detected(
            insight_id="insight-1",
            source=InsightSource.TELEMETRY_ANALYZER,
            confidence=0.5,
        )

        # Record same insight again - should update existing record
        collector.record_insight_detected(
            insight_id="insight-1",
            source=InsightSource.TELEMETRY_ANALYZER,
            confidence=0.9,
        )

        metrics = collector.get_metrics()
        # Should count as 1 since we're updating existing insight, not duplicating
        # The source stats will show 2 detections for tracking purposes
        assert metrics.insights_detected == 1

        # The insight record should still exist
        record = collector.get_insight_record("insight-1")
        assert record is not None
        assert record.insight_id == "insight-1"
