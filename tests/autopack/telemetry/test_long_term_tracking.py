"""Tests for long-term impact tracking (IMP-LOOP-033).

Tests the ScheduledCheck, FollowupCheckResult, RegressionPreventionReport dataclasses
and related methods for tracking 7/30/90 day follow-up effectiveness checks.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from autopack.task_generation.task_effectiveness_tracker import (
    FollowupCheckResult, ScheduledCheck, TaskEffectivenessTracker)
from autopack.telemetry.analyzer import (RegressionPreventionReport,
                                         TelemetryAnalyzer)


class TestScheduledCheck:
    """Tests for ScheduledCheck dataclass."""

    def test_creation(self):
        """Test basic creation of ScheduledCheck."""
        check_date = datetime.now() + timedelta(days=7)
        check = ScheduledCheck(
            task_id="IMP-LOOP-033",
            check_date=check_date,
            interval_days=7,
        )

        assert check.task_id == "IMP-LOOP-033"
        assert check.check_date == check_date
        assert check.interval_days == 7
        assert check.executed is False
        assert check.executed_at is None
        assert check.result is None

    def test_is_due_not_yet(self):
        """Test is_due returns False for future checks."""
        future_date = datetime.now() + timedelta(days=7)
        check = ScheduledCheck(
            task_id="IMP-LOOP-033",
            check_date=future_date,
            interval_days=7,
        )

        assert check.is_due() is False

    def test_is_due_past_date(self):
        """Test is_due returns True for past check dates."""
        past_date = datetime.now() - timedelta(days=1)
        check = ScheduledCheck(
            task_id="IMP-LOOP-033",
            check_date=past_date,
            interval_days=7,
        )

        assert check.is_due() is True

    def test_is_due_already_executed(self):
        """Test is_due returns False if already executed."""
        past_date = datetime.now() - timedelta(days=1)
        check = ScheduledCheck(
            task_id="IMP-LOOP-033",
            check_date=past_date,
            interval_days=7,
            executed=True,
        )

        assert check.is_due() is False

    def test_to_dict(self):
        """Test serialization to dictionary."""
        check_date = datetime.now()
        check = ScheduledCheck(
            task_id="IMP-LOOP-033",
            check_date=check_date,
            interval_days=7,
        )

        result = check.to_dict()

        assert result["task_id"] == "IMP-LOOP-033"
        assert result["interval_days"] == 7
        assert result["executed"] is False
        assert "check_date" in result


class TestFollowupCheckResult:
    """Tests for FollowupCheckResult dataclass."""

    def test_creation(self):
        """Test basic creation of FollowupCheckResult."""
        result = FollowupCheckResult(
            task_id="IMP-LOOP-033",
            interval_days=7,
            check_date=datetime.now(),
            related_test_count=100,
            failures_since_task=5,
            success_rate_since_task=0.95,
            regressions_prevented=10,
            effectiveness_maintained=True,
        )

        assert result.task_id == "IMP-LOOP-033"
        assert result.interval_days == 7
        assert result.related_test_count == 100
        assert result.failures_since_task == 5
        assert result.success_rate_since_task == 0.95
        assert result.regressions_prevented == 10
        assert result.effectiveness_maintained is True

    def test_to_dict(self):
        """Test serialization to dictionary."""
        result = FollowupCheckResult(
            task_id="IMP-LOOP-033",
            interval_days=30,
            check_date=datetime.now(),
        )

        dict_result = result.to_dict()

        assert dict_result["task_id"] == "IMP-LOOP-033"
        assert dict_result["interval_days"] == 30
        assert "check_date" in dict_result


class TestRegressionPreventionReport:
    """Tests for RegressionPreventionReport dataclass."""

    def test_creation(self):
        """Test basic creation of RegressionPreventionReport."""
        since_date = datetime.now() - timedelta(days=30)
        report = RegressionPreventionReport(
            task_id="IMP-LOOP-033",
            since_date=since_date,
            related_test_count=50,
            failures_before=20,
            failures_after=5,
            regressions_prevented=15,
            confidence=0.85,
            measurement_window_days=30,
        )

        assert report.task_id == "IMP-LOOP-033"
        assert report.related_test_count == 50
        assert report.failures_before == 20
        assert report.failures_after == 5
        assert report.regressions_prevented == 15
        assert report.confidence == 0.85
        assert report.measurement_window_days == 30


class TestTaskEffectivenessTrackerScheduling:
    """Tests for TaskEffectivenessTracker scheduling methods."""

    @pytest.fixture
    def tracker(self):
        """Create a TaskEffectivenessTracker instance."""
        return TaskEffectivenessTracker()

    def test_schedule_followup_check_default_intervals(self, tracker):
        """Test scheduling with default 7/30/90 day intervals."""
        checks = tracker.schedule_followup_check("IMP-LOOP-033")

        assert len(checks) == 3
        intervals = [c.interval_days for c in checks]
        assert 7 in intervals
        assert 30 in intervals
        assert 90 in intervals

    def test_schedule_followup_check_custom_intervals(self, tracker):
        """Test scheduling with custom intervals."""
        checks = tracker.schedule_followup_check("IMP-LOOP-033", days=[14, 60])

        assert len(checks) == 2
        intervals = [c.interval_days for c in checks]
        assert 14 in intervals
        assert 60 in intervals

    def test_schedule_followup_check_no_duplicates(self, tracker):
        """Test that duplicate scheduling is prevented."""
        checks1 = tracker.schedule_followup_check("IMP-LOOP-033", days=[7])
        checks2 = tracker.schedule_followup_check("IMP-LOOP-033", days=[7])

        assert len(checks1) == 1
        assert len(checks2) == 0  # Duplicate prevented

    def test_schedule_followup_check_different_tasks(self, tracker):
        """Test scheduling for different tasks."""
        checks1 = tracker.schedule_followup_check("IMP-LOOP-033", days=[7])
        checks2 = tracker.schedule_followup_check("IMP-MEM-020", days=[7])

        assert len(checks1) == 1
        assert len(checks2) == 1
        assert checks1[0].task_id == "IMP-LOOP-033"
        assert checks2[0].task_id == "IMP-MEM-020"

    def test_get_due_checks(self, tracker):
        """Test getting due checks."""
        # Schedule a check for the past (should be due)
        past_check = ScheduledCheck(
            task_id="IMP-LOOP-033",
            check_date=datetime.now() - timedelta(days=1),
            interval_days=7,
        )
        tracker._scheduled_checks.append(past_check)

        # Schedule a check for the future (should not be due)
        tracker.schedule_followup_check("IMP-MEM-020", days=[30])

        due = tracker.get_due_checks()

        assert len(due) == 1
        assert due[0].task_id == "IMP-LOOP-033"

    def test_execute_followup_check(self, tracker):
        """Test executing a follow-up check."""
        check = ScheduledCheck(
            task_id="IMP-LOOP-033",
            check_date=datetime.now(),
            interval_days=7,
        )
        tracker._scheduled_checks.append(check)

        result = tracker.execute_followup_check(
            scheduled_check=check,
            related_test_count=100,
            failures_since_task=5,
            success_rate_since_task=0.95,
        )

        assert result.task_id == "IMP-LOOP-033"
        assert result.interval_days == 7
        assert result.related_test_count == 100
        assert result.failures_since_task == 5
        assert result.success_rate_since_task == 0.95
        assert result.effectiveness_maintained is True
        assert check.executed is True
        assert check.executed_at is not None

    def test_execute_followup_check_effectiveness_not_maintained(self, tracker):
        """Test executing a check where effectiveness dropped below threshold."""
        check = ScheduledCheck(
            task_id="IMP-LOOP-033",
            check_date=datetime.now(),
            interval_days=7,
        )
        tracker._scheduled_checks.append(check)

        result = tracker.execute_followup_check(
            scheduled_check=check,
            related_test_count=100,
            failures_since_task=50,
            success_rate_since_task=0.50,  # Below 0.7 threshold
        )

        assert result.effectiveness_maintained is False

    def test_get_followup_results_for_task(self, tracker):
        """Test getting follow-up results for a specific task."""
        # Create some results
        result1 = FollowupCheckResult(
            task_id="IMP-LOOP-033",
            interval_days=7,
            check_date=datetime.now(),
        )
        result2 = FollowupCheckResult(
            task_id="IMP-LOOP-033",
            interval_days=30,
            check_date=datetime.now(),
        )
        result3 = FollowupCheckResult(
            task_id="IMP-MEM-020",
            interval_days=7,
            check_date=datetime.now(),
        )
        tracker._followup_results.extend([result1, result2, result3])

        results = tracker.get_followup_results_for_task("IMP-LOOP-033")

        assert len(results) == 2
        assert all(r.task_id == "IMP-LOOP-033" for r in results)

    def test_get_long_term_impact_summary(self, tracker):
        """Test getting the long-term impact summary."""
        # Schedule some checks
        tracker.schedule_followup_check("IMP-LOOP-033", days=[7, 30, 90])

        # Create a past check that's due
        past_check = ScheduledCheck(
            task_id="IMP-MEM-020",
            check_date=datetime.now() - timedelta(days=1),
            interval_days=7,
        )
        tracker._scheduled_checks.append(past_check)

        # Add some results
        result = FollowupCheckResult(
            task_id="IMP-TEST-001",
            interval_days=7,
            check_date=datetime.now(),
            success_rate_since_task=0.9,
            effectiveness_maintained=True,
            regressions_prevented=5,
        )
        tracker._followup_results.append(result)

        summary = tracker.get_long_term_impact_summary()

        assert summary["total_scheduled"] == 4  # 3 + 1
        assert summary["pending_checks"] == 4
        assert summary["due_checks"] == 1
        assert summary["total_results"] == 1
        assert summary["avg_success_rate"] == 0.9
        assert summary["effectiveness_maintained_rate"] == 1.0
        assert summary["total_regressions_prevented"] == 5
        assert 7 in summary["by_interval"]
        assert 30 in summary["by_interval"]
        assert 90 in summary["by_interval"]


class TestTelemetryAnalyzerRegressionPrevention:
    """Tests for TelemetryAnalyzer regression prevention methods."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock()

    @pytest.fixture
    def analyzer(self, mock_db):
        """Create a TelemetryAnalyzer with mock DB."""
        return TelemetryAnalyzer(db_session=mock_db)

    def test_measure_regression_prevention_basic(self, analyzer, mock_db):
        """Test basic regression prevention measurement."""
        # The method calls _count_failures_in_window and _count_runs_in_window
        # which each call db.execute. We need to mock the return values properly.
        #
        # Order of calls in measure_regression_prevention:
        # 1. _count_failures_in_window (before) -> accesses failure_count
        # 2. _count_failures_in_window (after) -> accesses failure_count
        # 3. _count_runs_in_window (before) -> accesses run_count
        # 4. _count_runs_in_window (after) -> accesses run_count

        def create_mock_result(value, attr_name):
            """Create a mock result that returns value for the given attribute."""
            mock_result = MagicMock()
            mock_row = MagicMock()
            setattr(mock_row, attr_name, value)
            mock_result.fetchone.return_value = mock_row
            return mock_result

        # Set up the side_effect for sequential calls in correct order
        mock_db.execute.side_effect = [
            create_mock_result(20, "failure_count"),  # failures before
            create_mock_result(10, "failure_count"),  # failures after
            create_mock_result(100, "run_count"),  # runs before
            create_mock_result(100, "run_count"),  # runs after
        ]

        since_date = datetime.now(timezone.utc) - timedelta(days=30)
        report = analyzer.measure_regression_prevention(
            task_id="IMP-LOOP-033",
            since_date=since_date,
        )

        assert report.task_id == "IMP-LOOP-033"
        assert report.since_date == since_date
        assert report.failures_before == 20
        assert report.failures_after == 10
        assert isinstance(report.confidence, float)
        assert report.confidence > 0  # Should have some confidence with 100 samples

    def test_measure_regression_prevention_with_related_phases(self, analyzer, mock_db):
        """Test regression prevention with specific phase types."""
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.failure_count = 5
        mock_row.run_count = 50
        mock_result.fetchone.return_value = mock_row

        mock_db.execute.return_value = mock_result

        since_date = datetime.now(timezone.utc) - timedelta(days=30)
        report = analyzer.measure_regression_prevention(
            task_id="IMP-LOOP-033",
            since_date=since_date,
            related_phase_types=["task_generation", "feedback_pipeline"],
        )

        assert report.task_id == "IMP-LOOP-033"
        # Verify the query was executed with phase type filtering
        assert mock_db.execute.called

    def test_detect_related_phase_types_loop(self, analyzer):
        """Test detection of related phase types for LOOP tasks."""
        phase_types = analyzer._detect_related_phase_types("IMP-LOOP-033")

        assert "task_generation" in phase_types
        assert "feedback_pipeline" in phase_types
        assert "autonomous_loop" in phase_types

    def test_detect_related_phase_types_mem(self, analyzer):
        """Test detection of related phase types for MEM tasks."""
        phase_types = analyzer._detect_related_phase_types("IMP-MEM-020")

        assert "memory" in phase_types
        assert "context_injection" in phase_types
        assert "learning" in phase_types

    def test_detect_related_phase_types_unknown(self, analyzer):
        """Test detection returns empty list for unknown categories."""
        phase_types = analyzer._detect_related_phase_types("IMP-UNKNOWN-001")

        assert phase_types == []

    def test_calculate_confidence_low_samples(self, analyzer):
        """Test confidence calculation with low sample count."""
        confidence = analyzer._calculate_confidence(3, 100)
        assert confidence == 0.0  # Below minimum threshold

    def test_calculate_confidence_high_samples(self, analyzer):
        """Test confidence calculation with high sample count."""
        confidence = analyzer._calculate_confidence(100, 100)
        assert confidence > 0.5  # Should have reasonable confidence

    def test_get_long_term_impact_report_batch(self, analyzer, mock_db):
        """Test batch generation of long-term impact reports."""
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.failure_count = 5
        mock_row.run_count = 50
        mock_result.fetchone.return_value = mock_row
        mock_db.execute.return_value = mock_result

        task_ids = ["IMP-LOOP-033", "IMP-MEM-020"]
        since_dates = {
            "IMP-LOOP-033": datetime.now(timezone.utc) - timedelta(days=30),
            "IMP-MEM-020": datetime.now(timezone.utc) - timedelta(days=15),
        }

        reports = analyzer.get_long_term_impact_report(
            task_ids=task_ids,
            since_dates=since_dates,
        )

        assert len(reports) == 2
        assert "IMP-LOOP-033" in reports
        assert "IMP-MEM-020" in reports

    def test_get_long_term_impact_report_missing_date(self, analyzer, mock_db):
        """Test batch report skips tasks without completion dates."""
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.failure_count = 5
        mock_row.run_count = 50
        mock_result.fetchone.return_value = mock_row
        mock_db.execute.return_value = mock_result

        task_ids = ["IMP-LOOP-033", "IMP-MEM-020"]
        since_dates = {
            "IMP-LOOP-033": datetime.now(timezone.utc) - timedelta(days=30),
            # IMP-MEM-020 missing
        }

        reports = analyzer.get_long_term_impact_report(
            task_ids=task_ids,
            since_dates=since_dates,
        )

        assert len(reports) == 1
        assert "IMP-LOOP-033" in reports
        assert "IMP-MEM-020" not in reports


class TestLongTermTrackingIntegration:
    """Integration tests for long-term tracking functionality."""

    def test_full_scheduling_and_execution_flow(self):
        """Test complete flow from scheduling to execution."""
        tracker = TaskEffectivenessTracker()

        # Schedule follow-up checks
        checks = tracker.schedule_followup_check("IMP-LOOP-033", days=[7])
        assert len(checks) == 1

        # Simulate time passing - modify the check date
        checks[0].check_date = datetime.now() - timedelta(days=1)

        # Get due checks
        due = tracker.get_due_checks()
        assert len(due) == 1

        # Execute the check
        result = tracker.execute_followup_check(
            scheduled_check=due[0],
            related_test_count=100,
            failures_since_task=5,
            success_rate_since_task=0.95,
        )

        # Verify result
        assert result.effectiveness_maintained is True
        assert result.task_id == "IMP-LOOP-033"

        # Verify check is marked as executed
        assert due[0].executed is True

        # Get summary
        summary = tracker.get_long_term_impact_summary()
        assert summary["executed_checks"] == 1
        assert summary["total_results"] == 1

    def test_multiple_interval_tracking(self):
        """Test tracking across multiple intervals."""
        tracker = TaskEffectivenessTracker()

        # Schedule all intervals
        tracker.schedule_followup_check("IMP-LOOP-033", days=[7, 30, 90])

        summary = tracker.get_long_term_impact_summary()

        assert summary["total_scheduled"] == 3
        assert summary["by_interval"][7]["scheduled"] == 1
        assert summary["by_interval"][30]["scheduled"] == 1
        assert summary["by_interval"][90]["scheduled"] == 1
