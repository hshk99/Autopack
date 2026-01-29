"""Tests for IMP-TEL-001: SLA Enforcement in Pipeline Latency Tracking.

Tests the SLA breach detection, alerting, and enforcement mechanisms
in the PipelineLatencyTracker and ResultHandler.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from autopack.executor.result_handler import ResultHandler, SLABreachInfo
from autopack.telemetry.meta_metrics import (
    PipelineLatencyTracker,
    PipelineSLAConfig,
    PipelineStage,
    SLABreachAlert,
)


class TestSLABreachInfo:
    """Tests for SLABreachInfo dataclass."""

    def test_sla_breach_info_defaults(self):
        """Test SLABreachInfo default values."""
        info = SLABreachInfo()
        assert info.breached is False
        assert info.level == ""
        assert info.threshold_ms == 0.0
        assert info.actual_ms == 0.0
        assert info.breach_amount_ms == 0.0
        assert info.message == ""
        assert info.stage_from is None
        assert info.stage_to is None

    def test_sla_breach_info_creation(self):
        """Test SLABreachInfo with values."""
        info = SLABreachInfo(
            breached=True,
            level="critical",
            threshold_ms=300000,
            actual_ms=600000,
            breach_amount_ms=300000,
            message="End-to-end SLA breached",
            stage_from="phase_complete",
            stage_to="task_executed",
        )
        assert info.breached is True
        assert info.level == "critical"
        assert info.threshold_ms == 300000
        assert info.actual_ms == 600000

    def test_sla_breach_info_to_dict(self):
        """Test SLABreachInfo serialization."""
        info = SLABreachInfo(
            breached=True,
            level="warning",
            threshold_ms=60000,
            actual_ms=90000,
            breach_amount_ms=30000,
            message="Stage SLA breached",
            stage_from="phase_complete",
            stage_to="telemetry_collected",
        )
        result = info.to_dict()

        assert result["breached"] is True
        assert result["level"] == "warning"
        assert result["threshold_ms"] == 60000
        assert result["actual_ms"] == 90000
        assert result["breach_amount_ms"] == 30000
        assert result["stage_from"] == "phase_complete"
        assert result["stage_to"] == "telemetry_collected"


class TestResultHandlerSLABreach:
    """Tests for ResultHandler SLA breach methods."""

    @pytest.fixture
    def result_handler(self):
        """Create a ResultHandler with mocked dependencies."""
        return ResultHandler(
            builder_result_poster=MagicMock(),
            auditor_result_poster=MagicMock(),
            phase_state_mgr=MagicMock(),
            learning_pipeline=MagicMock(),
            api_client=MagicMock(),
            run_id="test-run-001",
        )

    def test_emit_sla_breach_alert_no_breach(self, result_handler):
        """Test that no alert is emitted when there's no breach."""
        info = SLABreachInfo(breached=False)

        with patch("autopack.executor.result_handler.logger") as mock_logger:
            result_handler.emit_sla_breach_alert("phase-001", info)
            mock_logger.critical.assert_not_called()
            mock_logger.warning.assert_not_called()

    def test_emit_sla_breach_alert_warning(self, result_handler):
        """Test that warning level alert is logged correctly."""
        info = SLABreachInfo(
            breached=True,
            level="warning",
            threshold_ms=60000,
            actual_ms=80000,
            breach_amount_ms=20000,
            message="Stage SLA breached",
        )

        with patch("autopack.executor.result_handler.logger") as mock_logger:
            result_handler.emit_sla_breach_alert("phase-001", info)
            mock_logger.warning.assert_called_once()
            mock_logger.critical.assert_not_called()

    def test_emit_sla_breach_alert_critical(self, result_handler):
        """Test that critical level alert is logged correctly."""
        info = SLABreachInfo(
            breached=True,
            level="critical",
            threshold_ms=300000,
            actual_ms=600000,
            breach_amount_ms=300000,
            message="End-to-end SLA breached",
        )

        with patch("autopack.executor.result_handler.logger") as mock_logger:
            result_handler.emit_sla_breach_alert("phase-001", info)
            mock_logger.critical.assert_called_once()

    def test_check_and_emit_sla_breaches_no_tracker(self, result_handler):
        """Test that no breaches returned when tracker is None."""
        breaches = result_handler.check_and_emit_sla_breaches("phase-001", None)
        assert breaches == []

    def test_check_and_emit_sla_breaches_with_tracker(self, result_handler):
        """Test breach detection with actual tracker."""
        tracker = PipelineLatencyTracker(
            pipeline_id="test",
            sla_config=PipelineSLAConfig(end_to_end_threshold_ms=60000),  # 1 minute
        )

        base_time = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base_time)
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base_time + timedelta(seconds=120),  # 2 minutes > 1 minute threshold
        )

        with patch("autopack.executor.result_handler.logger"):
            breaches = result_handler.check_and_emit_sla_breaches("phase-001", tracker)

        # Should have at least the end-to-end breach
        e2e_breaches = [b for b in breaches if b.stage_to == "task_executed"]
        assert len(e2e_breaches) == 1
        assert e2e_breaches[0].breached is True
        assert e2e_breaches[0].level == "critical"

    def test_check_and_emit_sla_breaches_handles_exception(self, result_handler):
        """Test that exceptions in SLA checking are handled gracefully."""
        tracker = MagicMock()
        tracker.check_sla_breaches.side_effect = Exception("Test error")

        with patch("autopack.executor.result_handler.logger") as mock_logger:
            breaches = result_handler.check_and_emit_sla_breaches("phase-001", tracker)

        assert breaches == []
        mock_logger.warning.assert_called_once()


class TestSLAEnforcementScenarios:
    """Integration tests for SLA enforcement scenarios."""

    @pytest.fixture
    def strict_sla_config(self):
        """Create a strict SLA config for testing edge cases."""
        return PipelineSLAConfig(
            end_to_end_threshold_ms=30000,  # 30 seconds
            stage_thresholds_ms={
                "phase_complete_to_telemetry_collected": 5000,  # 5 seconds
                "telemetry_collected_to_memory_persisted": 5000,
                "memory_persisted_to_task_generated": 10000,
                "task_generated_to_task_executed": 10000,
            },
            alert_on_breach=True,
        )

    def test_all_stages_within_sla(self, strict_sla_config):
        """Test that all stages within SLA produces no breaches."""
        tracker = PipelineLatencyTracker(
            pipeline_id="within-sla",
            sla_config=strict_sla_config,
        )

        base_time = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base_time)
        tracker.record_stage(
            PipelineStage.TELEMETRY_COLLECTED,
            timestamp=base_time + timedelta(seconds=3),
        )
        tracker.record_stage(
            PipelineStage.MEMORY_PERSISTED,
            timestamp=base_time + timedelta(seconds=6),
        )
        tracker.record_stage(
            PipelineStage.TASK_GENERATED,
            timestamp=base_time + timedelta(seconds=12),
        )
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base_time + timedelta(seconds=20),
        )

        breaches = tracker.check_sla_breaches()
        assert len(breaches) == 0
        assert tracker.is_within_sla() is True

    def test_single_stage_breach(self, strict_sla_config):
        """Test that a single stage breach is detected correctly."""
        tracker = PipelineLatencyTracker(
            pipeline_id="single-breach",
            sla_config=strict_sla_config,
        )

        base_time = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base_time)
        # This stage takes too long (10s > 5s threshold)
        tracker.record_stage(
            PipelineStage.TELEMETRY_COLLECTED,
            timestamp=base_time + timedelta(seconds=10),
        )

        breaches = tracker.check_sla_breaches()
        stage_breaches = [b for b in breaches if b.stage_from == "phase_complete"]

        assert len(stage_breaches) == 1
        assert stage_breaches[0].actual_ms == 10000
        assert stage_breaches[0].threshold_ms == 5000

    def test_cascade_breach_detection(self, strict_sla_config):
        """Test that cascading delays cause multiple breaches."""
        tracker = PipelineLatencyTracker(
            pipeline_id="cascade",
            sla_config=strict_sla_config,
        )

        base_time = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base_time)
        # Multiple stages exceed their thresholds
        tracker.record_stage(
            PipelineStage.TELEMETRY_COLLECTED,
            timestamp=base_time + timedelta(seconds=15),  # 15s > 5s
        )
        tracker.record_stage(
            PipelineStage.MEMORY_PERSISTED,
            timestamp=base_time + timedelta(seconds=30),  # 15s > 5s between stages
        )
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base_time + timedelta(seconds=60),  # 60s > 30s e2e threshold
        )

        breaches = tracker.check_sla_breaches()

        # Should have multiple breaches (stage level + end-to-end)
        assert len(breaches) >= 2

    def test_sla_breach_severity_levels(self, strict_sla_config):
        """Test correct severity assignment based on breach magnitude."""
        # Test warning level (1-50% over threshold)
        tracker_warning = PipelineLatencyTracker(
            pipeline_id="warning-level",
            sla_config=strict_sla_config,
        )
        base_time = datetime.utcnow()
        tracker_warning.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base_time)
        tracker_warning.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base_time + timedelta(seconds=40),  # 33% over 30s threshold
        )

        breaches_warning = tracker_warning.check_sla_breaches()
        e2e_breaches_warning = [b for b in breaches_warning if b.stage_to == "task_executed"]
        assert len(e2e_breaches_warning) == 1
        assert e2e_breaches_warning[0].level == "warning"

        # Test critical level (>50% over threshold)
        tracker_critical = PipelineLatencyTracker(
            pipeline_id="critical-level",
            sla_config=strict_sla_config,
        )
        tracker_critical.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base_time)
        tracker_critical.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base_time + timedelta(seconds=60),  # 100% over 30s threshold
        )

        breaches_critical = tracker_critical.check_sla_breaches()
        e2e_breaches_critical = [b for b in breaches_critical if b.stage_to == "task_executed"]
        assert len(e2e_breaches_critical) == 1
        assert e2e_breaches_critical[0].level == "critical"

    def test_partial_pipeline_no_end_to_end_breach(self):
        """Test that incomplete pipeline doesn't falsely report end-to-end breach."""
        tracker = PipelineLatencyTracker(pipeline_id="partial")

        base_time = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base_time)
        tracker.record_stage(
            PipelineStage.TELEMETRY_COLLECTED,
            timestamp=base_time + timedelta(minutes=10),  # Long time but no end marker
        )

        # Without TASK_EXECUTED, can't compute end-to-end
        e2e_latency = tracker.get_end_to_end_latency_ms()
        assert e2e_latency is None

        # is_within_sla should return True for incomplete pipelines
        assert tracker.is_within_sla() is True


class TestSLAConfigCustomization:
    """Tests for customizing SLA configuration."""

    def test_custom_end_to_end_threshold(self):
        """Test custom end-to-end SLA threshold."""
        config = PipelineSLAConfig(end_to_end_threshold_ms=600000)  # 10 minutes
        tracker = PipelineLatencyTracker(pipeline_id="custom", sla_config=config)

        base_time = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base_time)
        tracker.record_stage(
            PipelineStage.TASK_EXECUTED,
            timestamp=base_time + timedelta(minutes=8),  # 8 minutes < 10 minutes
        )

        assert tracker.is_within_sla() is True
        breaches = tracker.check_sla_breaches()
        e2e_breaches = [b for b in breaches if b.stage_to == "task_executed"]
        assert len(e2e_breaches) == 0

    def test_custom_stage_thresholds(self):
        """Test custom per-stage SLA thresholds."""
        config = PipelineSLAConfig(
            stage_thresholds_ms={
                "phase_complete_to_telemetry_collected": 120000,  # 2 minutes
            }
        )
        tracker = PipelineLatencyTracker(pipeline_id="custom-stages", sla_config=config)

        base_time = datetime.utcnow()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=base_time)
        tracker.record_stage(
            PipelineStage.TELEMETRY_COLLECTED,
            timestamp=base_time + timedelta(seconds=90),  # 90s < 120s threshold
        )

        breaches = tracker.check_sla_breaches()
        stage_breaches = [
            b
            for b in breaches
            if b.stage_from == "phase_complete" and b.stage_to == "telemetry_collected"
        ]
        assert len(stage_breaches) == 0

    def test_alert_on_breach_disabled(self):
        """Test that alert_on_breach flag is respected."""
        config = PipelineSLAConfig(
            end_to_end_threshold_ms=30000,
            alert_on_breach=False,
        )
        assert config.alert_on_breach is False


class TestSLABreachAlert:
    """Tests for SLABreachAlert dataclass from meta_metrics."""

    def test_sla_breach_alert_to_dict(self):
        """Test SLABreachAlert serialization."""
        alert = SLABreachAlert(
            level="critical",
            stage_from="phase_complete",
            stage_to="task_executed",
            threshold_ms=300000,
            actual_ms=600000,
            breach_amount_ms=300000,
            message="End-to-end SLA breached: 600000ms > 300000ms threshold",
        )

        result = alert.to_dict()

        assert result["level"] == "critical"
        assert result["stage_from"] == "phase_complete"
        assert result["stage_to"] == "task_executed"
        assert result["threshold_ms"] == 300000
        assert result["actual_ms"] == 600000
        assert result["breach_amount_ms"] == 300000
        assert "timestamp" in result

    def test_sla_breach_alert_default_timestamp(self):
        """Test that timestamp defaults to current time."""
        alert = SLABreachAlert(
            level="warning",
            stage_from=None,
            stage_to=None,
            threshold_ms=60000,
            actual_ms=90000,
            breach_amount_ms=30000,
            message="Test alert",
        )

        assert alert.timestamp is not None
        assert isinstance(alert.timestamp, datetime)
