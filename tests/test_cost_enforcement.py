"""Tests for cost enforcement in autonomous execution (IMP-COST-005).

Verifies that telemetry cost recommendations are properly enforced,
pausing execution when cost limits are approached.
"""

from unittest.mock import MagicMock, patch

import pytest

from autopack.executor.autonomous_loop import AutonomousLoop
from autopack.telemetry.analyzer import CostRecommendation, TelemetryAnalyzer


class TestCostRecommendationDataclass:
    """Test the CostRecommendation dataclass."""

    def test_cost_recommendation_fields(self):
        """Verify CostRecommendation has all required fields."""
        rec = CostRecommendation(
            should_pause=True,
            reason="Test reason",
            current_spend=1000.0,
            budget_remaining_pct=5.0,
            severity="critical",
        )
        assert rec.should_pause is True
        assert rec.reason == "Test reason"
        assert rec.current_spend == 1000.0
        assert rec.budget_remaining_pct == 5.0
        assert rec.severity == "critical"


class TestTelemetryAnalyzerCostRecommendations:
    """Test the get_cost_recommendations method on TelemetryAnalyzer."""

    def test_no_pause_when_usage_below_warning_threshold(self):
        """Should not recommend pause when usage is below warning threshold."""
        mock_session = MagicMock()
        analyzer = TelemetryAnalyzer(mock_session)

        # 50% usage - well below warning threshold
        rec = analyzer.get_cost_recommendations(
            tokens_used=500_000,
            token_cap=1_000_000,
        )

        assert rec.should_pause is False
        assert rec.severity == "info"
        assert rec.budget_remaining_pct == pytest.approx(50.0)

    def test_warning_when_usage_above_warning_threshold(self):
        """Should issue warning when usage exceeds warning threshold (80%)."""
        mock_session = MagicMock()
        analyzer = TelemetryAnalyzer(mock_session)

        # 85% usage - above warning, below critical
        rec = analyzer.get_cost_recommendations(
            tokens_used=850_000,
            token_cap=1_000_000,
        )

        assert rec.should_pause is False
        assert rec.severity == "warning"
        assert rec.budget_remaining_pct == pytest.approx(15.0)
        assert "85.0%" in rec.reason

    def test_pause_when_usage_above_critical_threshold(self):
        """Should recommend pause when usage exceeds critical threshold (95%)."""
        mock_session = MagicMock()
        analyzer = TelemetryAnalyzer(mock_session)

        # 96% usage - above critical threshold
        rec = analyzer.get_cost_recommendations(
            tokens_used=960_000,
            token_cap=1_000_000,
        )

        assert rec.should_pause is True
        assert rec.severity == "critical"
        assert rec.budget_remaining_pct == pytest.approx(4.0)

    def test_pause_at_exactly_critical_threshold(self):
        """Should recommend pause when usage is exactly at critical threshold."""
        mock_session = MagicMock()
        analyzer = TelemetryAnalyzer(mock_session)

        # Exactly 95% usage
        rec = analyzer.get_cost_recommendations(
            tokens_used=950_000,
            token_cap=1_000_000,
        )

        assert rec.should_pause is True
        assert rec.severity == "critical"

    def test_no_pause_when_no_token_cap(self):
        """Should not recommend pause when token cap is zero or negative."""
        mock_session = MagicMock()
        analyzer = TelemetryAnalyzer(mock_session)

        # No token cap
        rec = analyzer.get_cost_recommendations(
            tokens_used=1_000_000,
            token_cap=0,
        )

        assert rec.should_pause is False
        assert rec.budget_remaining_pct == 100.0

    def test_custom_thresholds(self):
        """Should respect custom warning and critical thresholds."""
        mock_session = MagicMock()
        analyzer = TelemetryAnalyzer(mock_session)

        # 70% usage with custom 60% warning threshold
        rec = analyzer.get_cost_recommendations(
            tokens_used=700_000,
            token_cap=1_000_000,
            warning_threshold_pct=0.60,
            critical_threshold_pct=0.80,
        )

        assert rec.should_pause is False
        assert rec.severity == "warning"  # Above custom warning (60%)

        # 85% usage with custom 80% critical threshold
        rec = analyzer.get_cost_recommendations(
            tokens_used=850_000,
            token_cap=1_000_000,
            warning_threshold_pct=0.60,
            critical_threshold_pct=0.80,
        )

        assert rec.should_pause is True  # Above custom critical (80%)


class TestAutonomousLoopCostCheck:
    """Test cost recommendation checking in AutonomousLoop."""

    def test_check_cost_recommendations_returns_recommendation(self):
        """Verify _check_cost_recommendations returns CostRecommendation."""
        mock_executor = MagicMock()
        mock_executor._run_tokens_used = 500_000
        mock_executor.db_session = MagicMock()

        loop = AutonomousLoop(mock_executor)

        mock_analyzer = MagicMock()
        mock_analyzer.get_cost_recommendations.return_value = CostRecommendation(
            should_pause=False,
            reason="Test",
            current_spend=500_000.0,
            budget_remaining_pct=50.0,
            severity="info",
        )

        with patch.object(loop, "_get_telemetry_analyzer", return_value=mock_analyzer):
            with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
                mock_settings.run_token_cap = 1_000_000
                rec = loop._check_cost_recommendations()

        assert isinstance(rec, CostRecommendation)
        assert rec.should_pause is False

    def test_check_cost_recommendations_calls_analyzer(self):
        """Verify _check_cost_recommendations queries the telemetry analyzer."""
        mock_executor = MagicMock()
        mock_executor._run_tokens_used = 800_000
        mock_executor.db_session = MagicMock()

        loop = AutonomousLoop(mock_executor)

        mock_analyzer = MagicMock()
        mock_analyzer.get_cost_recommendations.return_value = CostRecommendation(
            should_pause=False,
            reason="Test",
            current_spend=800_000.0,
            budget_remaining_pct=20.0,
            severity="warning",
        )

        with patch.object(loop, "_get_telemetry_analyzer", return_value=mock_analyzer):
            with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
                mock_settings.run_token_cap = 1_000_000
                loop._check_cost_recommendations()

        mock_analyzer.get_cost_recommendations.assert_called_once_with(800_000, 1_000_000)

    def test_check_cost_recommendations_handles_no_analyzer(self):
        """Verify graceful handling when telemetry analyzer is unavailable."""
        mock_executor = MagicMock()
        mock_executor._run_tokens_used = 950_000
        mock_executor.db_session = None

        loop = AutonomousLoop(mock_executor)

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.run_token_cap = 1_000_000
            rec = loop._check_cost_recommendations()

        # Should still return a recommendation based on basic check
        assert isinstance(rec, CostRecommendation)
        assert rec.should_pause is True  # 95% usage triggers pause


class TestAutonomousLoopCostPause:
    """Test cost pause handling in AutonomousLoop."""

    def test_pause_for_cost_limit_logs_warning(self):
        """Verify _pause_for_cost_limit logs appropriate warning."""
        mock_executor = MagicMock()
        mock_executor._get_project_slug.return_value = "test-project"

        loop = AutonomousLoop(mock_executor)

        recommendation = CostRecommendation(
            should_pause=True,
            reason="Token usage at 96% of budget",
            current_spend=960_000.0,
            budget_remaining_pct=4.0,
            severity="critical",
        )

        with patch("autopack.executor.autonomous_loop.logger") as mock_logger:
            with patch("autopack.executor.autonomous_loop.log_build_event"):
                loop._pause_for_cost_limit(recommendation)

        # Verify warning was logged
        mock_logger.warning.assert_called()
        call_args = mock_logger.warning.call_args[0][0]
        assert "IMP-COST-005" in call_args
        assert "Cost pause triggered" in call_args

    def test_pause_for_cost_limit_logs_build_event(self):
        """Verify _pause_for_cost_limit logs to build event."""
        mock_executor = MagicMock()
        mock_executor._get_project_slug.return_value = "test-project"

        loop = AutonomousLoop(mock_executor)

        recommendation = CostRecommendation(
            should_pause=True,
            reason="Token usage at 96% of budget",
            current_spend=960_000.0,
            budget_remaining_pct=4.0,
            severity="critical",
        )

        # Patch at source module since it's imported dynamically inside the method
        with patch("autopack.archive_consolidator.log_build_event") as mock_log_event:
            loop._pause_for_cost_limit(recommendation)

        mock_log_event.assert_called_once()
        call_kwargs = mock_log_event.call_args[1]
        assert call_kwargs["event_type"] == "COST_PAUSE"
        assert "test-project" == call_kwargs["project_slug"]


class TestCostEnforcementIntegration:
    """Integration tests for cost enforcement in execution loop."""

    def test_cost_pause_stops_execution_loop(self):
        """Verify that cost pause recommendation stops the execution loop."""
        mock_executor = MagicMock()
        mock_executor._run_tokens_used = 960_000
        mock_executor.db_session = MagicMock()
        mock_executor.run_id = "test-run"
        mock_executor._phase_failure_counts = {}
        mock_executor._get_project_slug.return_value = "test-project"
        mock_executor.get_run_status.return_value = {"phases": []}
        mock_executor.get_next_queued_phase.return_value = None

        loop = AutonomousLoop(mock_executor)

        # Mock the cost check to return a pause recommendation
        pause_rec = CostRecommendation(
            should_pause=True,
            reason="Token usage at 96% of budget",
            current_spend=960_000.0,
            budget_remaining_pct=4.0,
            severity="critical",
        )

        with patch.object(loop, "_check_cost_recommendations", return_value=pause_rec):
            with patch.object(loop, "_pause_for_cost_limit") as mock_pause:
                with patch.object(loop, "_log_db_pool_health"):
                    with patch(
                        "autopack.executor.autonomous_loop.is_budget_exhausted",
                        return_value=False,
                    ):
                        stats = loop._execute_loop(
                            poll_interval=0.1,
                            max_iterations=10,
                            stop_on_first_failure=False,
                        )

        # Verify pause was called
        mock_pause.assert_called_once_with(pause_rec)

        # Verify loop stopped with cost_limit_reached reason
        assert stats["stop_reason"] == "cost_limit_reached"
