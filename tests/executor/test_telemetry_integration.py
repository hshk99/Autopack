"""Tests for telemetry integration into executor decision loop.

IMP-TEL-002: Wire telemetry analysis into executor decision points.
"""

from unittest.mock import MagicMock, patch

from autopack.executor.autonomous_loop import AutonomousLoop


class TestTelemetryRecommendationsAppliedBeforePhase:
    """Test that telemetry recommendations are queried and applied before phase execution."""

    def test_telemetry_recommendations_applied_before_phase(self):
        """Verify telemetry analyzer is consulted before executing a phase."""
        # Setup mock executor
        mock_executor = MagicMock()
        mock_executor.db_session = MagicMock()

        # Create loop instance
        loop = AutonomousLoop(mock_executor)

        # Mock the analyzer to return a HIGH recommendation (logged only)
        mock_analyzer = MagicMock()
        mock_analyzer.get_recommendations_for_phase.return_value = [
            {
                "severity": "HIGH",
                "action": "optimize_prompt",
                "reason": "Elevated failure rate for phase type 'BUILD'",
                "metric_value": 0.35,
            }
        ]

        with patch.object(loop, "_get_telemetry_analyzer", return_value=mock_analyzer):
            adjustments = loop._get_telemetry_adjustments("BUILD")

        # Verify analyzer was consulted
        mock_analyzer.get_recommendations_for_phase.assert_called_once_with("BUILD")

        # HIGH recommendations should not trigger adjustments (logged only)
        assert adjustments == {}

    def test_no_adjustments_when_no_phase_type(self):
        """Verify no adjustments are made when phase_type is None."""
        mock_executor = MagicMock()
        loop = AutonomousLoop(mock_executor)

        adjustments = loop._get_telemetry_adjustments(None)

        assert adjustments == {}

    def test_no_adjustments_when_no_analyzer(self):
        """Verify graceful handling when telemetry analyzer is unavailable."""
        mock_executor = MagicMock()
        mock_executor.db_session = None  # No database session

        loop = AutonomousLoop(mock_executor)
        adjustments = loop._get_telemetry_adjustments("BUILD")

        assert adjustments == {}


class TestCriticalTelemetryTriggersModelDowngrade:
    """Test that CRITICAL telemetry recommendations trigger model downgrade."""

    def test_critical_telemetry_triggers_model_downgrade(self):
        """Verify CRITICAL switch_to_smaller_model recommendation triggers downgrade."""
        mock_executor = MagicMock()
        mock_executor.db_session = MagicMock()

        loop = AutonomousLoop(mock_executor)

        mock_analyzer = MagicMock()
        mock_analyzer.get_recommendations_for_phase.return_value = [
            {
                "severity": "CRITICAL",
                "action": "switch_to_smaller_model",
                "reason": "High failure rate (60%) for phase type 'ANALYZE'",
                "metric_value": 0.6,
            }
        ]

        with patch.object(loop, "_get_telemetry_analyzer", return_value=mock_analyzer):
            with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
                mock_settings.default_model = "claude-opus"
                adjustments = loop._get_telemetry_adjustments("ANALYZE")

        # Should recommend downgrade from opus to sonnet
        assert adjustments.get("model_downgrade") == "sonnet"

    def test_critical_context_reduction(self):
        """Verify CRITICAL reduce_context_size recommendation triggers 30% reduction."""
        mock_executor = MagicMock()
        mock_executor.db_session = MagicMock()

        loop = AutonomousLoop(mock_executor)

        mock_analyzer = MagicMock()
        mock_analyzer.get_recommendations_for_phase.return_value = [
            {
                "severity": "CRITICAL",
                "action": "reduce_context_size",
                "reason": "Very high average token usage (150,000) for phase type 'BUILD'",
                "metric_value": 150000,
            }
        ]

        with patch.object(loop, "_get_telemetry_analyzer", return_value=mock_analyzer):
            adjustments = loop._get_telemetry_adjustments("BUILD")

        assert adjustments.get("context_reduction_factor") == 0.7

    def test_critical_timeout_increase(self):
        """Verify CRITICAL increase_timeout recommendation triggers 50% increase."""
        mock_executor = MagicMock()
        mock_executor.db_session = MagicMock()

        loop = AutonomousLoop(mock_executor)

        mock_analyzer = MagicMock()
        mock_analyzer.get_recommendations_for_phase.return_value = [
            {
                "severity": "CRITICAL",
                "action": "increase_timeout",
                "reason": "Frequent timeouts (5) for phase type 'TEST'",
                "metric_value": 5,
            }
        ]

        with patch.object(loop, "_get_telemetry_analyzer", return_value=mock_analyzer):
            adjustments = loop._get_telemetry_adjustments("TEST")

        assert adjustments.get("timeout_increase_factor") == 1.5


class TestHighSeverityRecommendationsLoggedOnly:
    """Test that HIGH severity recommendations are logged but don't trigger mitigations."""

    def test_high_severity_recommendations_logged_only(self):
        """Verify HIGH severity recommendations do not trigger adjustments."""
        mock_executor = MagicMock()
        mock_executor.db_session = MagicMock()

        loop = AutonomousLoop(mock_executor)

        mock_analyzer = MagicMock()
        mock_analyzer.get_recommendations_for_phase.return_value = [
            {
                "severity": "HIGH",
                "action": "reduce_context_size",
                "reason": "High average token usage (75,000) for phase type 'BUILD'",
                "metric_value": 75000,
            },
            {
                "severity": "HIGH",
                "action": "increase_timeout",
                "reason": "Timeout detected (2) for phase type 'BUILD'",
                "metric_value": 2,
            },
        ]

        with patch.object(loop, "_get_telemetry_analyzer", return_value=mock_analyzer):
            # IMP-MAINT-004: Logger is now in loop_telemetry_integration module
            with patch("autopack.executor.loop_telemetry_integration.logger") as mock_logger:
                adjustments = loop._get_telemetry_adjustments("BUILD")

        # No adjustments should be made for HIGH severity
        assert adjustments == {}

        # But recommendations should be logged
        assert mock_logger.info.call_count >= 2

    def test_mixed_severity_only_critical_applied(self):
        """Verify only CRITICAL recommendations trigger adjustments when mixed."""
        mock_executor = MagicMock()
        mock_executor.db_session = MagicMock()

        loop = AutonomousLoop(mock_executor)

        mock_analyzer = MagicMock()
        mock_analyzer.get_recommendations_for_phase.return_value = [
            {
                "severity": "HIGH",
                "action": "optimize_prompt",
                "reason": "Elevated failure rate",
                "metric_value": 0.35,
            },
            {
                "severity": "CRITICAL",
                "action": "increase_timeout",
                "reason": "Frequent timeouts (4)",
                "metric_value": 4,
            },
        ]

        with patch.object(loop, "_get_telemetry_analyzer", return_value=mock_analyzer):
            adjustments = loop._get_telemetry_adjustments("BUILD")

        # Only the CRITICAL timeout adjustment should be applied
        assert adjustments.get("timeout_increase_factor") == 1.5
        assert "context_reduction_factor" not in adjustments
        assert "model_downgrade" not in adjustments
