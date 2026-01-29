"""Tests for intention effectiveness tracking (IMP-INTENT-002)."""

from unittest.mock import MagicMock, patch

from autopack.telemetry.intention_effectiveness import (
    IntentionEffectivenessTracker, IntentionOutcome)


class TestIntentionEffectivenessTracker:
    """Test intention effectiveness tracking and analysis."""

    def test_calculate_goal_drift_identical(self):
        """Test goal drift calculation when goals are identical."""
        tracker = IntentionEffectivenessTracker()
        drift = tracker.calculate_goal_drift("build a parser", "build a parser")
        assert drift == 0.0

    def test_calculate_goal_drift_completely_different(self):
        """Test goal drift calculation when goals are completely different."""
        tracker = IntentionEffectivenessTracker()
        drift = tracker.calculate_goal_drift("build a parser", "delete all files")
        assert drift > 0.5

    def test_calculate_goal_drift_partial_overlap(self):
        """Test goal drift with partial keyword overlap."""
        tracker = IntentionEffectivenessTracker()
        drift = tracker.calculate_goal_drift("build a parser", "build a compiler")
        # Should have some overlap but not perfect
        assert 0 < drift < 1.0

    def test_calculate_goal_drift_empty_goal(self):
        """Test goal drift with empty initial goal."""
        tracker = IntentionEffectivenessTracker()
        drift = tracker.calculate_goal_drift("", "some output")
        assert drift == 1.0

    def test_calculate_goal_drift_empty_output(self):
        """Test goal drift with empty final output."""
        tracker = IntentionEffectivenessTracker()
        drift = tracker.calculate_goal_drift("build something", "")
        assert drift == 1.0

    def test_calculate_goal_drift_case_insensitive(self):
        """Test that goal drift calculation is case insensitive."""
        tracker = IntentionEffectivenessTracker()
        drift1 = tracker.calculate_goal_drift("Build a Parser", "build a parser")
        drift2 = tracker.calculate_goal_drift("build a parser", "BUILD A PARSER")
        assert drift1 == 0.0
        assert drift2 == 0.0

    @patch("autopack.telemetry.intention_effectiveness.SessionLocal")
    def test_effectiveness_report_structure(self, mock_session_local):
        """Test that effectiveness report has correct structure."""
        # Mock the database session
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mock_session_local.return_value = mock_session

        tracker = IntentionEffectivenessTracker()
        report = tracker.get_effectiveness_report(days=7)

        assert "period_days" in report
        assert report["period_days"] == 7

        assert "with_intentions" in report
        assert "without_intentions" in report
        assert "effectiveness_delta" in report

        # Check with_intentions structure
        with_int = report["with_intentions"]
        assert "run_count" in with_int
        assert "success_rate" in with_int
        assert "avg_goal_drift" in with_int
        assert "avg_completion_time" in with_int
        assert "avg_error_count" in with_int

        # Check without_intentions structure
        without_int = report["without_intentions"]
        assert "run_count" in without_int
        assert "success_rate" in without_int
        assert "avg_goal_drift" in without_int
        assert "avg_completion_time" in without_int
        assert "avg_error_count" in without_int

        # Check effectiveness_delta structure
        delta = report["effectiveness_delta"]
        assert "success_rate_improvement" in delta
        assert "goal_drift_reduction" in delta
        assert "time_reduction_pct" in delta

    @patch("autopack.telemetry.intention_effectiveness.SessionLocal")
    def test_effectiveness_report_empty_database(self, mock_session_local):
        """Test effectiveness report with no data."""
        # Mock the database session
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mock_session_local.return_value = mock_session

        tracker = IntentionEffectivenessTracker()
        report = tracker.get_effectiveness_report(days=7)

        # Should return zeros when no data
        assert report["with_intentions"]["run_count"] == 0
        assert report["without_intentions"]["run_count"] == 0
        assert report["with_intentions"]["success_rate"] == 0.0
        assert report["without_intentions"]["success_rate"] == 0.0

    def test_intention_outcome_creation(self):
        """Test IntentionOutcome dataclass creation."""
        outcome = IntentionOutcome(
            run_id="run_123",
            phase_id="phase_1",
            had_intentions=True,
            intention_source="memory",
            intention_chars=150,
            goal_drift_score=0.1,
            success=True,
            completion_time_sec=45.5,
            error_count=0,
            retry_count=0,
        )

        assert outcome.run_id == "run_123"
        assert outcome.phase_id == "phase_1"
        assert outcome.had_intentions is True
        assert outcome.intention_source == "memory"
        assert outcome.intention_chars == 150
        assert outcome.goal_drift_score == 0.1
        assert outcome.success is True
        assert outcome.completion_time_sec == 45.5
        assert outcome.error_count == 0
        assert outcome.retry_count == 0

    def test_intention_outcome_with_failures(self):
        """Test IntentionOutcome with failed phase."""
        outcome = IntentionOutcome(
            run_id="run_456",
            phase_id="phase_2",
            had_intentions=False,
            intention_source=None,
            intention_chars=0,
            goal_drift_score=0.8,
            success=False,
            completion_time_sec=120.0,
            error_count=3,
            retry_count=2,
        )

        assert outcome.had_intentions is False
        assert outcome.success is False
        assert outcome.error_count == 3
        assert outcome.retry_count == 2
        assert outcome.goal_drift_score == 0.8
