"""Unit tests for pipeline SLA monitoring and alerting.

IMP-LOOP-022: Tests for feedback pipeline SLA breach detection and alerting
functionality that monitors the feedback pipeline for latency issues.
"""

from datetime import datetime
from unittest.mock import Mock, patch


from autopack.feedback_pipeline import FeedbackPipeline
from autopack.telemetry.meta_metrics import (PipelineLatencyTracker,
                                             PipelineSLAConfig, PipelineStage)


class TestSLABreachDetection:
    """Tests for _check_and_alert_sla_breaches method."""

    def test_check_sla_breaches_returns_empty_without_tracker(self):
        """Should return empty list when no latency tracker configured."""
        pipeline = FeedbackPipeline(enabled=True)

        alerts = pipeline._check_and_alert_sla_breaches()

        assert alerts == []

    def test_check_sla_breaches_returns_empty_when_no_breach(self):
        """Should return empty list when pipeline is within SLA."""
        config = PipelineSLAConfig(end_to_end_threshold_ms=300000)  # 5 minutes
        tracker = PipelineLatencyTracker(sla_config=config)

        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 1, 0)  # 1 minute later

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TASK_EXECUTED, timestamp=time2)

        pipeline = FeedbackPipeline(latency_tracker=tracker, enabled=True)

        alerts = pipeline._check_and_alert_sla_breaches()

        # Filter to only end-to-end breaches
        e2e_alerts = [a for a in alerts if a.get("stage_to") == "task_executed"]
        assert len(e2e_alerts) == 0

    def test_check_sla_breaches_detects_breach(self):
        """Should detect and return alerts when SLA is breached."""
        config = PipelineSLAConfig(end_to_end_threshold_ms=300000)  # 5 minutes
        tracker = PipelineLatencyTracker(sla_config=config)

        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 10, 0)  # 10 minutes later (breached)

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TASK_EXECUTED, timestamp=time2)

        pipeline = FeedbackPipeline(latency_tracker=tracker, enabled=True)

        alerts = pipeline._check_and_alert_sla_breaches()

        # Should have at least one breach alert
        assert len(alerts) >= 1
        e2e_alerts = [a for a in alerts if a.get("stage_to") == "task_executed"]
        assert len(e2e_alerts) == 1
        assert e2e_alerts[0]["threshold_ms"] == 300000
        assert e2e_alerts[0]["actual_ms"] == 600000

    def test_check_sla_breaches_logs_critical_alert(self, caplog):
        """Should log error for critical SLA breach."""
        config = PipelineSLAConfig(end_to_end_threshold_ms=300000)  # 5 minutes
        tracker = PipelineLatencyTracker(sla_config=config)

        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 10, 0)  # 10 minutes (>50% over threshold)

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TASK_EXECUTED, timestamp=time2)

        pipeline = FeedbackPipeline(latency_tracker=tracker, enabled=True)

        with caplog.at_level("ERROR"):
            pipeline._check_and_alert_sla_breaches()

        assert "CRITICAL SLA BREACH" in caplog.text

    def test_check_sla_breaches_logs_warning_alert(self, caplog):
        """Should log warning for non-critical SLA breach."""
        config = PipelineSLAConfig(end_to_end_threshold_ms=300000)  # 5 minutes
        tracker = PipelineLatencyTracker(sla_config=config)

        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 6, 0)  # 6 minutes (20% over threshold)

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TASK_EXECUTED, timestamp=time2)

        pipeline = FeedbackPipeline(latency_tracker=tracker, enabled=True)

        with caplog.at_level("WARNING"):
            pipeline._check_and_alert_sla_breaches()

        assert "SLA BREACH WARNING" in caplog.text

    def test_check_sla_breaches_persists_insight_with_memory_service(self):
        """Should persist breach insight when memory service is available."""
        config = PipelineSLAConfig(end_to_end_threshold_ms=300000)
        tracker = PipelineLatencyTracker(sla_config=config)

        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 10, 0)

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TASK_EXECUTED, timestamp=time2)

        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(
            latency_tracker=tracker,
            memory_service=mock_memory,
            enabled=True,
        )

        pipeline._check_and_alert_sla_breaches()

        # Should have called write_telemetry_insight for each breach
        assert mock_memory.write_telemetry_insight.called

        # Verify the insight structure
        call_args = mock_memory.write_telemetry_insight.call_args
        insight = call_args[1]["insight"]
        assert insight["insight_type"] == "sla_breach"
        assert insight["severity"] in ["critical", "high"]

    def test_check_sla_breaches_handles_memory_service_error(self, caplog):
        """Should handle memory service errors gracefully."""
        config = PipelineSLAConfig(end_to_end_threshold_ms=300000)
        tracker = PipelineLatencyTracker(sla_config=config)

        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 10, 0)

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TASK_EXECUTED, timestamp=time2)

        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock(side_effect=Exception("DB error"))

        pipeline = FeedbackPipeline(
            latency_tracker=tracker,
            memory_service=mock_memory,
            enabled=True,
        )

        with caplog.at_level("WARNING"):
            alerts = pipeline._check_and_alert_sla_breaches()

        # Should still return alerts even if persistence fails
        assert len(alerts) >= 1
        assert "Failed to persist SLA breach insight" in caplog.text


class TestSLABreachActions:
    """Tests for _generate_sla_breach_action method."""

    def test_generate_action_for_telemetry_stage_breach(self):
        """Should generate appropriate action for telemetry collection stage breach."""
        pipeline = FeedbackPipeline(enabled=True)

        breach = Mock()
        breach.stage_from = "phase_complete"
        breach.stage_to = "telemetry_collected"
        breach.level = "warning"

        action = pipeline._generate_sla_breach_action(breach)

        assert "telemetry" in action.lower()
        assert "event handler" in action.lower() or "logging" in action.lower()

    def test_generate_action_for_memory_stage_breach(self):
        """Should generate appropriate action for memory persistence stage breach."""
        pipeline = FeedbackPipeline(enabled=True)

        breach = Mock()
        breach.stage_from = "telemetry_collected"
        breach.stage_to = "memory_persisted"
        breach.level = "warning"

        action = pipeline._generate_sla_breach_action(breach)

        assert "memory" in action.lower()
        assert "database" in action.lower() or "vector" in action.lower()

    def test_generate_action_for_task_generation_stage_breach(self):
        """Should generate appropriate action for task generation stage breach."""
        pipeline = FeedbackPipeline(enabled=True)

        breach = Mock()
        breach.stage_from = "memory_persisted"
        breach.stage_to = "task_generated"
        breach.level = "warning"

        action = pipeline._generate_sla_breach_action(breach)

        assert "task" in action.lower()

    def test_generate_action_for_task_execution_stage_breach(self):
        """Should generate appropriate action for task execution stage breach."""
        pipeline = FeedbackPipeline(enabled=True)

        breach = Mock()
        breach.stage_from = "task_generated"
        breach.stage_to = "task_executed"
        breach.level = "warning"

        action = pipeline._generate_sla_breach_action(breach)

        assert "execution" in action.lower() or "task" in action.lower()

    def test_generate_action_for_critical_end_to_end_breach(self):
        """Should generate urgent action for critical end-to-end breach."""
        pipeline = FeedbackPipeline(enabled=True)

        breach = Mock()
        breach.stage_from = None
        breach.stage_to = None
        breach.level = "critical"

        action = pipeline._generate_sla_breach_action(breach)

        assert "urgent" in action.lower()
        assert "pipeline" in action.lower()

    def test_generate_action_for_warning_end_to_end_breach(self):
        """Should generate monitoring action for warning level breach."""
        pipeline = FeedbackPipeline(enabled=True)

        breach = Mock()
        breach.stage_from = None
        breach.stage_to = None
        breach.level = "warning"

        action = pipeline._generate_sla_breach_action(breach)

        assert "monitor" in action.lower() or "pipeline" in action.lower()


class TestCheckSLAStatus:
    """Tests for check_sla_status method."""

    def test_check_sla_status_without_tracker(self):
        """Should return unknown status when no tracker configured."""
        pipeline = FeedbackPipeline(enabled=True)

        status = pipeline.check_sla_status()

        assert status["is_healthy"] is True
        assert status["sla_status"] == "unknown"
        assert status["breaches"] == []
        assert "No latency tracker configured" in status["message"]

    def test_check_sla_status_healthy(self):
        """Should return healthy status when within SLA."""
        config = PipelineSLAConfig(end_to_end_threshold_ms=300000)
        tracker = PipelineLatencyTracker(sla_config=config)

        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 1, 0)

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TASK_EXECUTED, timestamp=time2)

        pipeline = FeedbackPipeline(latency_tracker=tracker, enabled=True)

        status = pipeline.check_sla_status()

        assert status["is_healthy"] is True
        assert status["sla_status"] == "excellent"
        assert "latency_metrics" in status

    def test_check_sla_status_breached(self):
        """Should return breached status when over SLA."""
        config = PipelineSLAConfig(end_to_end_threshold_ms=300000)
        tracker = PipelineLatencyTracker(sla_config=config)

        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 10, 0)

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TASK_EXECUTED, timestamp=time2)

        pipeline = FeedbackPipeline(latency_tracker=tracker, enabled=True)

        status = pipeline.check_sla_status()

        assert status["is_healthy"] is False
        assert status["sla_status"] == "breached"
        assert len(status["breaches"]) >= 1

    def test_check_sla_status_handles_error(self, caplog):
        """Should handle errors gracefully when checking status."""
        mock_tracker = Mock()
        mock_tracker.check_sla_breaches = Mock(side_effect=Exception("Test error"))

        pipeline = FeedbackPipeline(enabled=True)
        pipeline._latency_tracker = mock_tracker

        with caplog.at_level("WARNING"):
            status = pipeline.check_sla_status()

        assert status["sla_status"] == "error"
        assert "error" in status


class TestAutoFlushSLAIntegration:
    """Tests for SLA checking during auto-flush."""

    def test_auto_flush_calls_sla_check(self):
        """_auto_flush should check for SLA breaches."""
        config = PipelineSLAConfig(end_to_end_threshold_ms=300000)
        tracker = PipelineLatencyTracker(sla_config=config)

        # Set up a breach scenario
        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 10, 0)

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TASK_EXECUTED, timestamp=time2)

        pipeline = FeedbackPipeline(latency_tracker=tracker, enabled=False)

        # Mock the SLA check method to verify it's called
        with patch.object(pipeline, "_check_and_alert_sla_breaches") as mock_check:
            pipeline._auto_flush()
            mock_check.assert_called_once()

    def test_auto_flush_handles_sla_check_error(self, caplog):
        """_auto_flush should handle SLA check errors gracefully."""
        pipeline = FeedbackPipeline(enabled=False)

        with patch.object(
            pipeline, "_check_and_alert_sla_breaches", side_effect=Exception("SLA error")
        ):
            # Should not raise exception
            pipeline._auto_flush()

        # Warning should be logged (from the outer exception handler)
        # The exact message depends on where the exception is caught


class TestSLABreachInsightStructure:
    """Tests for SLA breach insight structure."""

    def test_sla_breach_insight_has_required_fields(self):
        """SLA breach insight should have all required fields."""
        config = PipelineSLAConfig(end_to_end_threshold_ms=300000)
        tracker = PipelineLatencyTracker(sla_config=config)

        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 10, 0)

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TASK_EXECUTED, timestamp=time2)

        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(
            latency_tracker=tracker,
            memory_service=mock_memory,
            run_id="test_run_001",
            project_id="test_project",
            enabled=True,
        )

        pipeline._check_and_alert_sla_breaches()

        call_args = mock_memory.write_telemetry_insight.call_args
        insight = call_args[1]["insight"]

        # Verify required fields
        assert insight["insight_type"] == "sla_breach"
        assert "description" in insight
        assert "content" in insight
        assert "metadata" in insight
        assert "severity" in insight
        assert "confidence" in insight
        assert insight["run_id"] == "test_run_001"
        assert "suggested_action" in insight
        assert "timestamp" in insight

        # Verify metadata structure
        metadata = insight["metadata"]
        assert "level" in metadata
        assert "stage_from" in metadata
        assert "stage_to" in metadata
        assert "threshold_ms" in metadata
        assert "actual_ms" in metadata
        assert "breach_amount_ms" in metadata


class TestStageBreachDetection:
    """Tests for stage-level SLA breach detection."""

    def test_detects_stage_level_breach(self):
        """Should detect individual stage SLA breaches."""
        config = PipelineSLAConfig(
            end_to_end_threshold_ms=300000,
            stage_thresholds_ms={
                "phase_complete_to_telemetry_collected": 60000,  # 1 minute
            },
        )
        tracker = PipelineLatencyTracker(sla_config=config)

        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 3, 0)  # 3 minutes (over 1 min threshold)

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TELEMETRY_COLLECTED, timestamp=time2)

        pipeline = FeedbackPipeline(latency_tracker=tracker, enabled=True)

        alerts = pipeline._check_and_alert_sla_breaches()

        # Should have stage-level breach
        stage_alerts = [
            a
            for a in alerts
            if a.get("stage_from") == "phase_complete"
            and a.get("stage_to") == "telemetry_collected"
        ]
        assert len(stage_alerts) == 1
        assert stage_alerts[0]["threshold_ms"] == 60000


class TestStatisticsTracking:
    """Tests for SLA-related statistics tracking."""

    def test_breach_insight_increments_stats(self):
        """SLA breach insight persistence should increment insights_persisted stat."""
        config = PipelineSLAConfig(end_to_end_threshold_ms=300000)
        tracker = PipelineLatencyTracker(sla_config=config)

        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 10, 0)

        tracker.record_stage(PipelineStage.PHASE_COMPLETE, timestamp=time1)
        tracker.record_stage(PipelineStage.TASK_EXECUTED, timestamp=time2)

        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(
            latency_tracker=tracker,
            memory_service=mock_memory,
            enabled=True,
        )

        initial_stats = pipeline.get_stats()
        initial_persisted = initial_stats["insights_persisted"]

        pipeline._check_and_alert_sla_breaches()

        final_stats = pipeline.get_stats()
        assert final_stats["insights_persisted"] > initial_persisted
