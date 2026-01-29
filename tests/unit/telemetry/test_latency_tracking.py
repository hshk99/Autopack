"""Unit tests for pipeline latency tracking integration.

IMP-TELE-001: Tests for PipelineLatencyTracker integration with FeedbackPipeline
and AutonomousLoop for loop cycle time measurement.
"""

from datetime import datetime, timedelta
from unittest.mock import Mock

from autopack.feedback_pipeline import FeedbackPipeline, PhaseOutcome
from autopack.telemetry.meta_metrics import (PipelineLatencyTracker,
                                             PipelineSLAConfig, PipelineStage)


class TestPipelineLatencyTrackerIntegration:
    """Tests for PipelineLatencyTracker integration with FeedbackPipeline."""

    def test_feedback_pipeline_accepts_latency_tracker(self):
        """FeedbackPipeline should accept latency_tracker parameter."""
        tracker = PipelineLatencyTracker()
        pipeline = FeedbackPipeline(latency_tracker=tracker)

        assert pipeline.latency_tracker is tracker

    def test_feedback_pipeline_set_latency_tracker(self):
        """FeedbackPipeline should allow setting latency tracker after init."""
        pipeline = FeedbackPipeline()
        assert pipeline.latency_tracker is None

        tracker = PipelineLatencyTracker()
        pipeline.set_latency_tracker(tracker)

        assert pipeline.latency_tracker is tracker

    def test_feedback_pipeline_records_phase_complete_stage(self):
        """FeedbackPipeline should record PHASE_COMPLETE stage on outcome processing."""
        tracker = PipelineLatencyTracker()
        pipeline = FeedbackPipeline(latency_tracker=tracker, enabled=True)

        outcome = PhaseOutcome(
            phase_id="test_phase_1",
            phase_type="build",
            success=True,
            status="completed",
        )

        pipeline.process_phase_outcome(outcome)

        # Verify PHASE_COMPLETE was recorded
        stage_ts = tracker.get_stage_timestamp(PipelineStage.PHASE_COMPLETE)
        assert stage_ts is not None
        assert stage_ts.metadata.get("phase_id") == "test_phase_1"
        assert stage_ts.metadata.get("success") is True

    def test_feedback_pipeline_records_telemetry_collected_stage(self):
        """FeedbackPipeline should record TELEMETRY_COLLECTED stage."""
        tracker = PipelineLatencyTracker()
        pipeline = FeedbackPipeline(latency_tracker=tracker, enabled=True)

        outcome = PhaseOutcome(
            phase_id="test_phase_2",
            phase_type="test",
            success=False,
            status="failed",
        )

        pipeline.process_phase_outcome(outcome)

        # Verify TELEMETRY_COLLECTED was recorded
        stage_ts = tracker.get_stage_timestamp(PipelineStage.TELEMETRY_COLLECTED)
        assert stage_ts is not None
        assert stage_ts.metadata.get("insight_count") == 1

    def test_feedback_pipeline_records_memory_persisted_stage_with_memory_service(self):
        """FeedbackPipeline should record MEMORY_PERSISTED stage when memory service is present."""
        tracker = PipelineLatencyTracker()

        # Create mock memory service
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_task_execution_feedback = Mock()
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(
            latency_tracker=tracker,
            memory_service=mock_memory,
            enabled=True,
        )

        outcome = PhaseOutcome(
            phase_id="test_phase_3",
            phase_type="deploy",
            success=True,
            status="completed",
        )

        pipeline.process_phase_outcome(outcome)

        # Verify MEMORY_PERSISTED was recorded
        stage_ts = tracker.get_stage_timestamp(PipelineStage.MEMORY_PERSISTED)
        assert stage_ts is not None

    def test_feedback_pipeline_get_latency_metrics(self):
        """FeedbackPipeline.get_latency_metrics() should return tracker metrics."""
        tracker = PipelineLatencyTracker(pipeline_id="test_run")
        pipeline = FeedbackPipeline(latency_tracker=tracker, enabled=True)

        outcome = PhaseOutcome(
            phase_id="test_phase_4",
            phase_type="build",
            success=True,
            status="completed",
        )

        pipeline.process_phase_outcome(outcome)

        metrics = pipeline.get_latency_metrics()
        assert metrics is not None
        assert metrics.get("pipeline_id") == "test_run"
        assert "stages" in metrics
        assert "stage_latencies" in metrics

    def test_feedback_pipeline_get_latency_metrics_returns_none_without_tracker(self):
        """FeedbackPipeline.get_latency_metrics() should return None without tracker."""
        pipeline = FeedbackPipeline()

        metrics = pipeline.get_latency_metrics()
        assert metrics is None

    def test_disabled_pipeline_does_not_record_stages(self):
        """Disabled FeedbackPipeline should not record latency stages."""
        tracker = PipelineLatencyTracker()
        pipeline = FeedbackPipeline(latency_tracker=tracker, enabled=False)

        outcome = PhaseOutcome(
            phase_id="test_phase_5",
            phase_type="build",
            success=True,
            status="completed",
        )

        pipeline.process_phase_outcome(outcome)

        # No stages should be recorded when pipeline is disabled
        assert tracker.get_stage_timestamp(PipelineStage.PHASE_COMPLETE) is None
        assert tracker.get_stage_timestamp(PipelineStage.TELEMETRY_COLLECTED) is None


class TestPipelineLatencyTrackerStageRecording:
    """Tests for PipelineLatencyTracker stage recording."""

    def test_record_stage_with_metadata(self):
        """record_stage should store metadata correctly."""
        tracker = PipelineLatencyTracker()

        tracker.record_stage(
            PipelineStage.PHASE_COMPLETE,
            metadata={"phase_id": "p1", "success": True},
        )

        stage_ts = tracker.get_stage_timestamp(PipelineStage.PHASE_COMPLETE)
        assert stage_ts is not None
        assert stage_ts.metadata["phase_id"] == "p1"
        assert stage_ts.metadata["success"] is True

    def test_record_stage_with_custom_timestamp(self):
        """record_stage should accept custom timestamp."""
        tracker = PipelineLatencyTracker()
        custom_time = datetime(2025, 1, 15, 10, 30, 0)

        tracker.record_stage(
            PipelineStage.TELEMETRY_COLLECTED,
            timestamp=custom_time,
        )

        stage_ts = tracker.get_stage_timestamp(PipelineStage.TELEMETRY_COLLECTED)
        assert stage_ts is not None
        assert stage_ts.timestamp == custom_time

    def test_record_all_pipeline_stages(self):
        """Should be able to record all pipeline stages."""
        tracker = PipelineLatencyTracker()

        stages = [
            PipelineStage.PHASE_COMPLETE,
            PipelineStage.TELEMETRY_COLLECTED,
            PipelineStage.MEMORY_PERSISTED,
            PipelineStage.TASK_GENERATED,
            PipelineStage.TASK_EXECUTED,
        ]

        for stage in stages:
            tracker.record_stage(stage)

        for stage in stages:
            assert tracker.get_stage_timestamp(stage) is not None


class TestPipelineLatencyCalculation:
    """Tests for latency calculation between stages."""

    def test_get_stage_latency_ms(self):
        """get_stage_latency_ms should calculate latency between stages."""
        tracker = PipelineLatencyTracker()

        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 0, 5)  # 5 seconds later

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TELEMETRY_COLLECTED, timestamp=time2)

        latency = tracker.get_stage_latency_ms(
            PipelineStage.PHASE_COMPLETE,
            PipelineStage.TELEMETRY_COLLECTED,
        )

        assert latency == 5000.0  # 5 seconds = 5000 ms

    def test_get_stage_latency_returns_none_for_missing_stage(self):
        """get_stage_latency_ms should return None if stage not recorded."""
        tracker = PipelineLatencyTracker()

        tracker.record_stage(PipelineStage.PHASE_COMPLETE)

        latency = tracker.get_stage_latency_ms(
            PipelineStage.PHASE_COMPLETE,
            PipelineStage.TELEMETRY_COLLECTED,  # Not recorded
        )

        assert latency is None

    def test_get_end_to_end_latency(self):
        """get_end_to_end_latency_ms should return total pipeline latency."""
        tracker = PipelineLatencyTracker()

        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 5, 0)  # 5 minutes later

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TASK_EXECUTED, timestamp=time2)

        latency = tracker.get_end_to_end_latency_ms()

        assert latency == 300000.0  # 5 minutes = 300000 ms

    def test_get_stage_latencies_returns_all_transitions(self):
        """get_stage_latencies should return latencies for all stage transitions."""
        tracker = PipelineLatencyTracker()

        base_time = datetime(2025, 1, 15, 10, 0, 0)
        tracker.record_stage(
            PipelineStage.PHASE_COMPLETE,
            timestamp=base_time,
        )
        tracker.record_stage(
            PipelineStage.TELEMETRY_COLLECTED,
            timestamp=base_time + timedelta(seconds=10),
        )
        tracker.record_stage(
            PipelineStage.MEMORY_PERSISTED,
            timestamp=base_time + timedelta(seconds=20),
        )

        latencies = tracker.get_stage_latencies()

        assert latencies["phase_complete_to_telemetry_collected"] == 10000.0
        assert latencies["telemetry_collected_to_memory_persisted"] == 10000.0


class TestPipelineSLAMonitoring:
    """Tests for SLA breach detection."""

    def test_is_within_sla_when_below_threshold(self):
        """is_within_sla should return True when latency is below threshold."""
        config = PipelineSLAConfig(end_to_end_threshold_ms=300000)  # 5 minutes
        tracker = PipelineLatencyTracker(sla_config=config)

        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 3, 0)  # 3 minutes later

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TASK_EXECUTED, timestamp=time2)

        assert tracker.is_within_sla() is True

    def test_is_within_sla_when_above_threshold(self):
        """is_within_sla should return False when latency exceeds threshold."""
        config = PipelineSLAConfig(end_to_end_threshold_ms=300000)  # 5 minutes
        tracker = PipelineLatencyTracker(sla_config=config)

        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 10, 0)  # 10 minutes later

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TASK_EXECUTED, timestamp=time2)

        assert tracker.is_within_sla() is False

    def test_check_sla_breaches_detects_end_to_end_breach(self):
        """check_sla_breaches should detect end-to-end SLA breach."""
        config = PipelineSLAConfig(end_to_end_threshold_ms=300000)  # 5 minutes
        tracker = PipelineLatencyTracker(sla_config=config)

        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 10, 0)  # 10 minutes = 600000 ms

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TASK_EXECUTED, timestamp=time2)

        breaches = tracker.check_sla_breaches()

        assert len(breaches) >= 1
        e2e_breach = [b for b in breaches if b.stage_to == "task_executed"][0]
        assert e2e_breach.actual_ms == 600000.0
        assert e2e_breach.threshold_ms == 300000.0
        assert e2e_breach.breach_amount_ms == 300000.0

    def test_check_sla_breaches_returns_empty_list_when_no_breach(self):
        """check_sla_breaches should return empty list when within SLA."""
        config = PipelineSLAConfig(end_to_end_threshold_ms=300000)
        tracker = PipelineLatencyTracker(sla_config=config)

        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 1, 0)  # 1 minute

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TASK_EXECUTED, timestamp=time2)

        breaches = tracker.check_sla_breaches()

        # No end-to-end breach since 1 min < 5 min threshold
        e2e_breaches = [b for b in breaches if b.stage_to == "task_executed"]
        assert len(e2e_breaches) == 0

    def test_get_sla_status_returns_correct_status(self):
        """get_sla_status should return appropriate status string."""
        config = PipelineSLAConfig(end_to_end_threshold_ms=300000)  # 5 minutes
        tracker = PipelineLatencyTracker(sla_config=config)

        # Test excellent (< 50% of threshold)
        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 2, 0)  # 2 minutes = 40% of 5 min

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TASK_EXECUTED, timestamp=time2)

        assert tracker.get_sla_status() == "excellent"


class TestTrackerSerialization:
    """Tests for tracker serialization."""

    def test_to_dict_includes_all_fields(self):
        """to_dict should include all tracker state and metrics."""
        tracker = PipelineLatencyTracker(pipeline_id="test_pipeline")

        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 1, 0)

        tracker.record_stage(
            PipelineStage.PHASE_COMPLETE,
            timestamp=time1,
            metadata={"phase_id": "p1"},
        )
        tracker.record_stage(
            PipelineStage.TELEMETRY_COLLECTED,
            timestamp=time2,
        )

        result = tracker.to_dict()

        assert result["pipeline_id"] == "test_pipeline"
        assert "stages" in result
        assert "phase_complete" in result["stages"]
        assert "stage_latencies" in result
        assert "sla_status" in result
        assert "sla_config" in result

    def test_to_feedback_loop_latency(self):
        """to_feedback_loop_latency should convert to FeedbackLoopLatency."""
        tracker = PipelineLatencyTracker()

        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 0, 30)  # 30 seconds
        time3 = datetime(2025, 1, 15, 10, 1, 0)  # 1 minute total

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TELEMETRY_COLLECTED, timestamp=time2)
        tracker.record_stage(PipelineStage.TASK_GENERATED, timestamp=time3)

        latency = tracker.to_feedback_loop_latency()

        assert latency.telemetry_to_analysis_ms == 30000.0  # 30 seconds
        assert latency.analysis_to_task_ms == 30000.0  # 30 seconds
