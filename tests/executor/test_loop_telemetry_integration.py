"""Tests for LoopTelemetryIntegration module.

IMP-MAINT-004: Tests for the extracted telemetry integration functionality.
"""

from unittest.mock import MagicMock, patch

from autopack.executor.loop_telemetry_integration import \
    LoopTelemetryIntegration
from autopack.telemetry.analyzer import CostRecommendation


class TestLoopTelemetryIntegrationInit:
    """Test LoopTelemetryIntegration initialization."""

    def test_init_with_defaults(self):
        """Verify default initialization."""
        integration = LoopTelemetryIntegration()

        assert integration._circuit_breaker is None
        assert integration._meta_metrics_tracker is None
        assert integration._anomaly_detector is None
        assert integration._meta_metrics_enabled is True
        assert integration._task_effectiveness_enabled is True
        assert integration._task_generation_paused is False
        assert integration._total_phases_executed == 0
        assert integration._total_phases_failed == 0

    def test_init_with_components(self):
        """Verify initialization with all components."""
        mock_cb = MagicMock()
        mock_mm = MagicMock()
        mock_ad = MagicMock()
        mock_analyzer_getter = MagicMock()
        mock_alert = MagicMock()

        integration = LoopTelemetryIntegration(
            circuit_breaker=mock_cb,
            meta_metrics_tracker=mock_mm,
            anomaly_detector=mock_ad,
            meta_metrics_enabled=True,
            task_effectiveness_enabled=True,
            get_telemetry_analyzer=mock_analyzer_getter,
            emit_alert=mock_alert,
        )

        assert integration._circuit_breaker is mock_cb
        assert integration._meta_metrics_tracker is mock_mm
        assert integration._anomaly_detector is mock_ad

    def test_set_phase_stats(self):
        """Verify phase stats can be updated."""
        integration = LoopTelemetryIntegration()
        integration.set_phase_stats(executed=10, failed=2)

        assert integration._total_phases_executed == 10
        assert integration._total_phases_failed == 2


class TestBuildTelemetryDataForHealth:
    """Test building telemetry data for health analysis."""

    def test_build_telemetry_data_basic(self):
        """Verify basic telemetry data structure is built correctly."""
        integration = LoopTelemetryIntegration()
        integration.set_phase_stats(executed=5, failed=1)

        data = integration.build_telemetry_data_for_health(None)

        assert data["road_b"]["phases_analyzed"] == 5
        assert data["road_b"]["total_phases"] == 6
        assert data["road_c"]["completed_tasks"] == 5
        assert data["road_c"]["total_tasks"] == 6

    def test_build_telemetry_data_with_ranked_issues(self):
        """Verify ranked issues are incorporated into telemetry data."""
        integration = LoopTelemetryIntegration()

        ranked_issues = {
            "top_cost_sinks": [MagicMock(), MagicMock()],
            "top_failure_modes": [MagicMock()],
            "top_retry_causes": [MagicMock(), MagicMock(), MagicMock()],
        }

        data = integration.build_telemetry_data_for_health(ranked_issues)

        assert data["road_b"]["total_issues"] == 6
        assert data["road_c"]["rework_count"] == 1

    def test_build_telemetry_data_with_anomaly_detector(self):
        """Verify anomaly detector stats are included."""
        mock_anomaly_detector = MagicMock()
        mock_alert_critical = MagicMock()
        mock_alert_critical.severity.name = "CRITICAL"
        mock_alert_warning = MagicMock()
        mock_alert_warning.severity.name = "WARNING"

        # Set up the severity comparison
        from autopack.telemetry.anomaly_detector import AlertSeverity

        mock_alert_critical.severity = AlertSeverity.CRITICAL
        mock_alert_warning.severity = AlertSeverity.WARNING

        mock_anomaly_detector.get_pending_alerts.return_value = [
            mock_alert_critical,
            mock_alert_warning,
        ]

        integration = LoopTelemetryIntegration(anomaly_detector=mock_anomaly_detector)

        data = integration.build_telemetry_data_for_health(None)

        assert data["road_g"]["total_alerts"] == 2
        assert data["road_g"]["actionable_alerts"] == 1


class TestUpdateCircuitBreakerHealth:
    """Test circuit breaker health updates."""

    def test_update_health_skipped_when_disabled(self):
        """Verify health update is skipped when meta-metrics disabled."""
        mock_cb = MagicMock()
        mock_mm = MagicMock()

        integration = LoopTelemetryIntegration(
            circuit_breaker=mock_cb,
            meta_metrics_tracker=mock_mm,
            meta_metrics_enabled=False,
        )

        integration.update_circuit_breaker_health({})

        mock_cb.update_health_report.assert_not_called()

    def test_update_health_skipped_when_no_circuit_breaker(self):
        """Verify health update is skipped when no circuit breaker."""
        mock_mm = MagicMock()

        integration = LoopTelemetryIntegration(
            circuit_breaker=None,
            meta_metrics_tracker=mock_mm,
            meta_metrics_enabled=True,
        )

        # Should not raise
        integration.update_circuit_breaker_health({})

    def test_update_health_calls_circuit_breaker(self):
        """Verify health report is passed to circuit breaker."""
        mock_cb = MagicMock()
        mock_mm = MagicMock()

        # Mock health report
        from autopack.telemetry.meta_metrics import FeedbackLoopHealth

        mock_health_report = MagicMock()
        mock_health_report.overall_status = FeedbackLoopHealth.HEALTHY
        mock_health_report.overall_score = 0.9
        mock_mm.analyze_feedback_loop_health.return_value = mock_health_report

        integration = LoopTelemetryIntegration(
            circuit_breaker=mock_cb,
            meta_metrics_tracker=mock_mm,
            meta_metrics_enabled=True,
        )

        integration.update_circuit_breaker_health({})

        mock_cb.update_health_report.assert_called_once_with(mock_health_report)


class TestUpdateTaskEffectiveness:
    """Test task effectiveness tracking updates."""

    def test_update_task_effectiveness_records_to_tracker(self):
        """Verify task outcomes are recorded to effectiveness tracker."""
        mock_tracker = MagicMock()
        mock_report = MagicMock()
        mock_report.effectiveness_score = 0.85
        mock_report.get_effectiveness_grade.return_value = "A"
        mock_tracker.record_task_outcome.return_value = mock_report

        integration = LoopTelemetryIntegration(task_effectiveness_enabled=True)
        integration.set_task_effectiveness_tracker(mock_tracker)

        integration.update_task_effectiveness(
            phase_id="phase-123",
            phase_type="BUILD",
            success=True,
            execution_time_seconds=30.5,
            tokens_used=5000,
        )

        mock_tracker.record_task_outcome.assert_called_once_with(
            task_id="phase-123",
            success=True,
            execution_time_seconds=30.5,
            tokens_used=5000,
            category="BUILD",
            notes="Phase execution outcome from autonomous loop",
        )
        mock_tracker.feed_back_to_priority_engine.assert_called_once_with(mock_report)

    def test_update_task_effectiveness_skipped_when_disabled(self):
        """Verify effectiveness update is skipped when disabled."""
        mock_tracker = MagicMock()

        integration = LoopTelemetryIntegration(task_effectiveness_enabled=False)
        integration.set_task_effectiveness_tracker(mock_tracker)

        integration.update_task_effectiveness(
            phase_id="phase-123",
            phase_type="BUILD",
            success=True,
            execution_time_seconds=30.5,
        )

        # Anomaly detector should still be called even when effectiveness disabled
        mock_tracker.record_task_outcome.assert_not_called()

    def test_update_task_effectiveness_handles_generated_tasks(self):
        """Verify generated task execution is verified."""
        mock_tracker = MagicMock()
        mock_report = MagicMock()
        mock_report.effectiveness_score = 0.85
        mock_report.get_effectiveness_grade.return_value = "A"
        mock_tracker.record_task_outcome.return_value = mock_report
        mock_tracker.record_execution.return_value = True

        integration = LoopTelemetryIntegration(task_effectiveness_enabled=True)
        integration.set_task_effectiveness_tracker(mock_tracker)

        integration.update_task_effectiveness(
            phase_id="generated-task-execution-task-456",
            phase_type="IMPROVE",
            success=True,
            execution_time_seconds=60.0,
        )

        mock_tracker.record_execution.assert_called_once_with("task-456", True)


class TestRecordPhaseToAnomalyDetector:
    """Test phase outcome recording to anomaly detector."""

    def test_record_phase_to_anomaly_detector(self):
        """Verify phase outcomes are recorded to anomaly detector."""
        mock_detector = MagicMock()
        mock_detector.record_phase_outcome.return_value = []

        integration = LoopTelemetryIntegration(anomaly_detector=mock_detector)

        integration.record_phase_to_anomaly_detector(
            phase_id="phase-123",
            phase_type="BUILD",
            success=True,
            tokens_used=5000,
            duration_seconds=30.5,
        )

        mock_detector.record_phase_outcome.assert_called_once_with(
            phase_id="phase-123",
            phase_type="BUILD",
            success=True,
            tokens_used=5000,
            duration_seconds=30.5,
        )

    def test_record_phase_skipped_when_no_detector(self):
        """Verify recording is skipped when no detector."""
        integration = LoopTelemetryIntegration(anomaly_detector=None)

        # Should not raise
        integration.record_phase_to_anomaly_detector(
            phase_id="phase-123",
            phase_type="BUILD",
            success=True,
            tokens_used=5000,
            duration_seconds=30.5,
        )


class TestGetTelemetryAdjustments:
    """Test telemetry-driven phase adjustments."""

    def test_get_adjustments_returns_empty_for_no_phase_type(self):
        """Verify empty adjustments for None phase type."""
        integration = LoopTelemetryIntegration()

        adjustments = integration.get_telemetry_adjustments(None)

        assert adjustments == {}

    def test_get_adjustments_returns_empty_when_no_analyzer(self):
        """Verify empty adjustments when no analyzer available."""
        integration = LoopTelemetryIntegration(get_telemetry_analyzer=lambda: None)

        adjustments = integration.get_telemetry_adjustments("BUILD")

        assert adjustments == {}

    def test_critical_context_reduction(self):
        """Verify CRITICAL reduce_context_size triggers 30% reduction."""
        mock_analyzer = MagicMock()
        mock_analyzer.get_recommendations_for_phase.return_value = [
            {
                "severity": "CRITICAL",
                "action": "reduce_context_size",
                "reason": "High token usage",
                "metric_value": 150000,
            }
        ]

        integration = LoopTelemetryIntegration(get_telemetry_analyzer=lambda: mock_analyzer)

        adjustments = integration.get_telemetry_adjustments("BUILD")

        assert adjustments.get("context_reduction_factor") == 0.7

    def test_critical_timeout_increase(self):
        """Verify CRITICAL increase_timeout triggers 50% increase."""
        mock_analyzer = MagicMock()
        mock_analyzer.get_recommendations_for_phase.return_value = [
            {
                "severity": "CRITICAL",
                "action": "increase_timeout",
                "reason": "Frequent timeouts",
                "metric_value": 5,
            }
        ]

        integration = LoopTelemetryIntegration(get_telemetry_analyzer=lambda: mock_analyzer)

        adjustments = integration.get_telemetry_adjustments("TEST")

        assert adjustments.get("timeout_increase_factor") == 1.5

    def test_critical_model_downgrade(self):
        """Verify CRITICAL switch_to_smaller_model triggers downgrade."""
        mock_analyzer = MagicMock()
        mock_analyzer.get_recommendations_for_phase.return_value = [
            {
                "severity": "CRITICAL",
                "action": "switch_to_smaller_model",
                "reason": "High failure rate",
                "metric_value": 0.6,
            }
        ]

        integration = LoopTelemetryIntegration(get_telemetry_analyzer=lambda: mock_analyzer)

        with patch("autopack.executor.loop_telemetry_integration.settings") as mock_settings:
            mock_settings.default_model = "claude-opus"
            adjustments = integration.get_telemetry_adjustments("ANALYZE")

        assert adjustments.get("model_downgrade") == "sonnet"

    def test_high_severity_no_adjustments(self):
        """Verify HIGH severity does not trigger adjustments."""
        mock_analyzer = MagicMock()
        mock_analyzer.get_recommendations_for_phase.return_value = [
            {
                "severity": "HIGH",
                "action": "reduce_context_size",
                "reason": "Elevated token usage",
                "metric_value": 75000,
            }
        ]

        integration = LoopTelemetryIntegration(get_telemetry_analyzer=lambda: mock_analyzer)

        adjustments = integration.get_telemetry_adjustments("BUILD")

        assert adjustments == {}


class TestCostRecommendations:
    """Test cost recommendation checking."""

    def test_check_cost_basic_recommendation_under_budget(self):
        """Verify basic recommendation when under budget."""
        integration = LoopTelemetryIntegration(get_telemetry_analyzer=lambda: None)

        recommendation = integration.check_cost_recommendations(tokens_used=50000, token_cap=100000)

        assert recommendation.should_pause is False
        assert recommendation.budget_remaining_pct == 50.0

    def test_check_cost_basic_recommendation_at_budget_limit(self):
        """Verify pause recommendation when at 95% budget."""
        integration = LoopTelemetryIntegration(get_telemetry_analyzer=lambda: None)

        recommendation = integration.check_cost_recommendations(tokens_used=96000, token_cap=100000)

        assert recommendation.should_pause is True
        assert recommendation.severity == "critical"

    def test_check_cost_no_token_cap(self):
        """Verify no pause when no token cap configured."""
        integration = LoopTelemetryIntegration(get_telemetry_analyzer=lambda: None)

        recommendation = integration.check_cost_recommendations(tokens_used=1000000, token_cap=0)

        assert recommendation.should_pause is False
        assert recommendation.budget_remaining_pct == 100.0

    def test_check_cost_uses_analyzer_when_available(self):
        """Verify analyzer is used when available."""
        mock_analyzer = MagicMock()
        expected_recommendation = CostRecommendation(
            should_pause=True,
            reason="Budget critical",
            current_spend=95000.0,
            budget_remaining_pct=5.0,
            severity="critical",
        )
        mock_analyzer.get_cost_recommendations.return_value = expected_recommendation

        integration = LoopTelemetryIntegration(get_telemetry_analyzer=lambda: mock_analyzer)

        recommendation = integration.check_cost_recommendations(tokens_used=95000, token_cap=100000)

        assert recommendation is expected_recommendation
        mock_analyzer.get_cost_recommendations.assert_called_once_with(95000, 100000)


class TestPauseForCostLimit:
    """Test cost pause handling."""

    def test_pause_for_cost_limit_logs_warning(self):
        """Verify cost pause is logged."""
        integration = LoopTelemetryIntegration()

        recommendation = CostRecommendation(
            should_pause=True,
            reason="Budget exhausted",
            current_spend=100000.0,
            budget_remaining_pct=0.0,
            severity="critical",
        )

        with patch("autopack.executor.loop_telemetry_integration.logger") as mock_logger:
            with patch("autopack.archive_consolidator.log_build_event"):
                integration.pause_for_cost_limit(recommendation, "test-project")

        mock_logger.warning.assert_called()

    def test_pause_for_cost_limit_logs_build_event(self):
        """Verify cost pause logs build event."""
        integration = LoopTelemetryIntegration()

        recommendation = CostRecommendation(
            should_pause=True,
            reason="Budget exhausted",
            current_spend=100000.0,
            budget_remaining_pct=0.0,
            severity="critical",
        )

        with patch("autopack.archive_consolidator.log_build_event") as mock_log_event:
            integration.pause_for_cost_limit(recommendation, "test-project")

        mock_log_event.assert_called_once()
        call_kwargs = mock_log_event.call_args[1]
        assert call_kwargs["event_type"] == "COST_PAUSE"
        assert call_kwargs["project_slug"] == "test-project"


class TestTaskGenerationPause:
    """Test task generation pause functionality."""

    def test_task_generation_pause_property(self):
        """Verify task generation pause state can be read and set."""
        integration = LoopTelemetryIntegration()

        assert integration.task_generation_paused is False

        integration.task_generation_paused = True
        assert integration.task_generation_paused is True

        integration.task_generation_paused = False
        assert integration.task_generation_paused is False
