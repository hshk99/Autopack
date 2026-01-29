"""Tests for IMP-TEL-001: Pipeline Latency SLA Runtime Enforcement.

Tests the integration of PipelineLatencyTracker into AutonomousLoop
for recording pipeline stage timestamps and detecting SLA breaches.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from autopack.telemetry.meta_metrics import PipelineLatencyTracker, PipelineSLAConfig, PipelineStage


class TestPipelineLatencyIntegration:
    """Tests for pipeline latency tracking integration with autonomous loop."""

    @pytest.fixture
    def latency_tracker(self):
        """Create a PipelineLatencyTracker for testing."""
        return PipelineLatencyTracker(pipeline_id="test-run-001")

    @pytest.fixture
    def mock_executor(self):
        """Create a mock executor for testing."""
        executor = MagicMock()
        executor.run_id = "test-run-001"
        executor._get_project_slug.return_value = "test-project"
        executor._phase_failure_counts = {}
        return executor

    def test_phase_complete_stage_recorded_on_success(self, latency_tracker):
        """Test that PHASE_COMPLETE stage is recorded after successful phase."""
        # Record phase completion
        latency_tracker.record_stage(
            PipelineStage.PHASE_COMPLETE,
            metadata={"phase_id": "test-phase-001", "phase_type": "build"},
        )

        # Verify stage was recorded
        stage_ts = latency_tracker.get_stage_timestamp(PipelineStage.PHASE_COMPLETE)
        assert stage_ts is not None
        assert stage_ts.stage == PipelineStage.PHASE_COMPLETE
        assert stage_ts.metadata["phase_id"] == "test-phase-001"

    def test_telemetry_collected_stage_recorded_after_aggregation(self, latency_tracker):
        """Test that TELEMETRY_COLLECTED stage is recorded after telemetry aggregation."""
        # Record telemetry collection
        latency_tracker.record_stage(
            PipelineStage.TELEMETRY_COLLECTED,
            metadata={"phase_id": "test-phase-001", "forced": False},
        )

        # Verify stage was recorded
        stage_ts = latency_tracker.get_stage_timestamp(PipelineStage.TELEMETRY_COLLECTED)
        assert stage_ts is not None
        assert stage_ts.stage == PipelineStage.TELEMETRY_COLLECTED

    def test_memory_persisted_stage_recorded_after_persistence(self, latency_tracker):
        """Test that MEMORY_PERSISTED stage is recorded after memory persistence."""
        # Record memory persistence
        latency_tracker.record_stage(
            PipelineStage.MEMORY_PERSISTED,
            metadata={"persisted_count": 5, "context": "phase_telemetry"},
        )

        # Verify stage was recorded
        stage_ts = latency_tracker.get_stage_timestamp(PipelineStage.MEMORY_PERSISTED)
        assert stage_ts is not None
        assert stage_ts.metadata["persisted_count"] == 5

    def test_task_generated_stage_recorded(self, latency_tracker):
        """Test that TASK_GENERATED stage is recorded after task generation."""
        latency_tracker.record_stage(
            PipelineStage.TASK_GENERATED,
            metadata={"tasks_generated": 3, "generation_time_ms": 150.0},
        )

        stage_ts = latency_tracker.get_stage_timestamp(PipelineStage.TASK_GENERATED)
        assert stage_ts is not None
        assert stage_ts.metadata["tasks_generated"] == 3

    def test_task_executed_stage_recorded(self, latency_tracker):
        """Test that TASK_EXECUTED stage is recorded after task execution."""
        latency_tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            metadata={"tasks_completed": 2},
        )

        stage_ts = latency_tracker.get_stage_timestamp(PipelineStage.TASK_EXECUTED)
        assert stage_ts is not None
        assert stage_ts.metadata["tasks_completed"] == 2

    def test_full_pipeline_stage_sequence(self, latency_tracker):
        """Test recording all pipeline stages in sequence."""
        base_time = datetime.utcnow()

        # Record all stages in sequence
        stages_and_times = [
            (PipelineStage.PHASE_COMPLETE, base_time),
            (PipelineStage.TELEMETRY_COLLECTED, base_time + timedelta(seconds=10)),
            (PipelineStage.MEMORY_PERSISTED, base_time + timedelta(seconds=20)),
            (PipelineStage.TASK_GENERATED, base_time + timedelta(seconds=30)),
            (PipelineStage.TASK_EXECUTED, base_time + timedelta(seconds=60)),
        ]

        for stage, timestamp in stages_and_times:
            latency_tracker.record_stage(stage, timestamp=timestamp)

        # Verify all stages recorded
        for stage, _ in stages_and_times:
            assert latency_tracker.get_stage_timestamp(stage) is not None

        # Check end-to-end latency
        e2e_latency = latency_tracker.get_end_to_end_latency_ms()
        assert e2e_latency == 60000  # 60 seconds

    def test_stage_latency_calculation(self, latency_tracker):
        """Test calculating latency between consecutive stages."""
        base_time = datetime.utcnow()

        latency_tracker.record_stage(
            PipelineStage.PHASE_COMPLETE,
            timestamp=base_time,
        )
        latency_tracker.record_stage(
            PipelineStage.TELEMETRY_COLLECTED,
            timestamp=base_time + timedelta(seconds=15),
        )

        latency = latency_tracker.get_stage_latency_ms(
            PipelineStage.PHASE_COMPLETE,
            PipelineStage.TELEMETRY_COLLECTED,
        )
        assert latency == 15000  # 15 seconds in milliseconds

    def test_parallel_execution_stage_recording(self, latency_tracker):
        """Test that parallel phase execution records PHASE_COMPLETE with parallel=True."""
        latency_tracker.record_stage(
            PipelineStage.PHASE_COMPLETE,
            metadata={"phase_id": "parallel-phase-001", "parallel": True},
        )

        stage_ts = latency_tracker.get_stage_timestamp(PipelineStage.PHASE_COMPLETE)
        assert stage_ts is not None
        assert stage_ts.metadata.get("parallel") is True


class TestPipelineLatencyWithSLAChecks:
    """Tests for SLA checking integration in pipeline latency tracking."""

    @pytest.fixture
    def tracker_with_short_sla(self):
        """Create a tracker with a short SLA for testing breaches."""
        config = PipelineSLAConfig(
            end_to_end_threshold_ms=60000,  # 1 minute for easier testing
            stage_thresholds_ms={
                "phase_complete_to_telemetry_collected": 10000,  # 10 seconds
                "telemetry_collected_to_memory_persisted": 10000,
                "memory_persisted_to_task_generated": 10000,
                "task_generated_to_task_executed": 30000,
            },
        )
        return PipelineLatencyTracker(
            pipeline_id="test-sla-run",
            sla_config=config,
        )

    def test_no_breach_when_within_sla(self, tracker_with_short_sla):
        """Test no breaches reported when latency is within SLA."""
        base_time = datetime.utcnow()

        # Record stages within SLA thresholds
        tracker_with_short_sla.record_stage(
            PipelineStage.PHASE_COMPLETE,
            timestamp=base_time,
        )
        tracker_with_short_sla.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base_time + timedelta(seconds=30),  # 30s < 60s threshold
        )

        breaches = tracker_with_short_sla.check_sla_breaches()
        e2e_breaches = [b for b in breaches if b.stage_to == "task_executed"]
        assert len(e2e_breaches) == 0

    def test_breach_detected_when_exceeds_sla(self, tracker_with_short_sla):
        """Test breach is detected when latency exceeds SLA threshold."""
        base_time = datetime.utcnow()

        # Record stages that exceed SLA
        tracker_with_short_sla.record_stage(
            PipelineStage.PHASE_COMPLETE,
            timestamp=base_time,
        )
        tracker_with_short_sla.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base_time + timedelta(seconds=120),  # 120s > 60s threshold
        )

        breaches = tracker_with_short_sla.check_sla_breaches()
        e2e_breaches = [b for b in breaches if b.stage_to == "task_executed"]

        assert len(e2e_breaches) == 1
        assert e2e_breaches[0].level == "critical"  # > 50% over threshold
        assert e2e_breaches[0].actual_ms == 120000
        assert e2e_breaches[0].threshold_ms == 60000

    def test_stage_level_breach_detection(self, tracker_with_short_sla):
        """Test that stage-level SLA breaches are detected."""
        base_time = datetime.utcnow()

        # Record with a stage breach (>10s between phase_complete and telemetry_collected)
        tracker_with_short_sla.record_stage(
            PipelineStage.PHASE_COMPLETE,
            timestamp=base_time,
        )
        tracker_with_short_sla.record_stage(
            PipelineStage.TELEMETRY_COLLECTED,
            timestamp=base_time + timedelta(seconds=25),  # 25s > 10s threshold
        )

        breaches = tracker_with_short_sla.check_sla_breaches()
        stage_breaches = [b for b in breaches if b.stage_from == "phase_complete"]

        assert len(stage_breaches) >= 1
        assert stage_breaches[0].actual_ms == 25000

    def test_sla_status_reflects_breach_severity(self, tracker_with_short_sla):
        """Test that SLA status correctly reflects breach severity."""
        base_time = datetime.utcnow()

        # Test excellent status (< 50% of threshold)
        tracker_with_short_sla.record_stage(
            PipelineStage.PHASE_COMPLETE,
            timestamp=base_time,
        )
        tracker_with_short_sla.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base_time + timedelta(seconds=20),  # 33% of 60s threshold
        )
        assert tracker_with_short_sla.get_sla_status() == "excellent"

    def test_warning_level_breach(self, tracker_with_short_sla):
        """Test warning level breach when just over threshold."""
        base_time = datetime.utcnow()

        # Just over threshold but < 50% over (warning level)
        tracker_with_short_sla.record_stage(
            PipelineStage.PHASE_COMPLETE,
            timestamp=base_time,
        )
        tracker_with_short_sla.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base_time + timedelta(seconds=70),  # 70s (17% over 60s)
        )

        breaches = tracker_with_short_sla.check_sla_breaches()
        e2e_breaches = [b for b in breaches if b.stage_to == "task_executed"]

        assert len(e2e_breaches) == 1
        assert e2e_breaches[0].level == "warning"  # < 50% over threshold


class TestAutonomousLoopLatencyIntegration:
    """Tests for AutonomousLoop integration with latency tracking."""

    @pytest.fixture
    def mock_autonomous_loop(self):
        """Create a mock AutonomousLoop with latency tracker."""
        from unittest.mock import MagicMock

        loop = MagicMock()
        loop._latency_tracker = PipelineLatencyTracker(pipeline_id="test-loop")
        loop._emit_alert = MagicMock()
        return loop

    def test_check_and_emit_sla_alerts_no_breaches(self, mock_autonomous_loop):
        """Test that no alerts are emitted when there are no breaches."""
        # Record stages within SLA
        base_time = datetime.utcnow()
        mock_autonomous_loop._latency_tracker.record_stage(
            PipelineStage.PHASE_COMPLETE,
            timestamp=base_time,
        )
        mock_autonomous_loop._latency_tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base_time + timedelta(seconds=60),  # 1 minute < 5 minute SLA
        )

        # Simulate the check
        breaches = mock_autonomous_loop._latency_tracker.check_sla_breaches()
        e2e_breaches = [b for b in breaches if b.stage_to == "task_executed"]

        assert len(e2e_breaches) == 0

    def test_tracker_to_dict_includes_all_data(self):
        """Test that tracker serialization includes all relevant data."""
        tracker = PipelineLatencyTracker(pipeline_id="serialize-test")
        base_time = datetime.utcnow()

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base_time)
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base_time + timedelta(minutes=2),
        )

        result = tracker.to_dict()

        assert result["pipeline_id"] == "serialize-test"
        assert "stages" in result
        assert "phase_complete" in result["stages"]
        assert "task_executed" in result["stages"]
        assert result["end_to_end_latency_ms"] == 120000
        assert result["sla_status"] == "excellent"
        assert "sla_config" in result
        assert "breaches" in result
