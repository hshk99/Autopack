"""Tests for task generation success metrics (IMP-LOOP-004)."""

from unittest.mock import MagicMock, patch

import pytest

from autopack.models import TaskGenerationEvent
from autopack.roadc.task_generator import (AutonomousTaskGenerator,
                                           _emit_task_generation_event)
from autopack.telemetry.analyzer import (RankedIssue, TaskGenerationStats,
                                         TelemetryAnalyzer)


class TestTaskGenerationEvent:
    """Tests for TaskGenerationEvent model."""

    def test_event_fields(self):
        """Test TaskGenerationEvent has all required fields."""
        event = TaskGenerationEvent(
            run_id="test-run-123",
            success=True,
            insights_processed=10,
            patterns_detected=5,
            tasks_generated=3,
            tasks_persisted=3,
            generation_time_ms=150.5,
            telemetry_source="direct",
            min_confidence=0.7,
            max_tasks=10,
        )

        assert event.run_id == "test-run-123"
        assert event.success is True
        assert event.insights_processed == 10
        assert event.patterns_detected == 5
        assert event.tasks_generated == 3
        assert event.tasks_persisted == 3
        assert event.generation_time_ms == 150.5
        assert event.telemetry_source == "direct"
        assert event.min_confidence == 0.7
        assert event.max_tasks == 10

    def test_event_error_fields(self):
        """Test TaskGenerationEvent error fields."""
        event = TaskGenerationEvent(
            success=False,
            error_message="Connection timeout",
            error_type="TimeoutError",
        )

        assert event.success is False
        assert event.error_message == "Connection timeout"
        assert event.error_type == "TimeoutError"


class TestEmitTaskGenerationEvent:
    """Tests for _emit_task_generation_event function."""

    @patch("autopack.database.SessionLocal")
    @patch("autopack.models.TaskGenerationEvent")
    def test_emit_success_event(self, mock_event_class, mock_session_local):
        """Test emitting a successful generation event."""
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session

        _emit_task_generation_event(
            success=True,
            insights_processed=10,
            patterns_detected=5,
            tasks_generated=3,
            generation_time_ms=100.0,
            run_id="test-run",
            telemetry_source="direct",
        )

        mock_event_class.assert_called_once()
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    @patch("autopack.database.SessionLocal")
    @patch("autopack.models.TaskGenerationEvent")
    def test_emit_failure_event(self, mock_event_class, mock_session_local):
        """Test emitting a failed generation event."""
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session

        _emit_task_generation_event(
            success=False,
            error_message="Test error",
            error_type="ValueError",
        )

        mock_event_class.assert_called_once()
        call_kwargs = mock_event_class.call_args.kwargs
        assert call_kwargs["success"] is False
        assert call_kwargs["error_message"] == "Test error"
        assert call_kwargs["error_type"] == "ValueError"

    @patch("autopack.database.SessionLocal")
    def test_emit_handles_db_error(self, mock_session_local):
        """Test that emit handles database errors gracefully."""
        mock_session = MagicMock()
        mock_session.commit.side_effect = Exception("DB error")
        mock_session_local.return_value = mock_session

        # Should not raise, just log warning
        _emit_task_generation_event(success=True, tasks_generated=1)

        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()


class TestAutonomousTaskGeneratorMetrics:
    """Tests for metrics integration in AutonomousTaskGenerator."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create a mock memory service."""
        mock = MagicMock()
        mock.retrieve_insights.return_value = [
            {"id": "insight-1", "issue_type": "cost_sink", "severity": "high", "content": "Test"},
            {"id": "insight-2", "issue_type": "cost_sink", "severity": "high", "content": "Test2"},
        ]
        return mock

    @pytest.fixture
    def mock_regression_protector(self):
        """Create a mock regression protector."""
        mock = MagicMock()
        mock.check_protection.return_value = MagicMock(is_protected=True)
        # Mock filter_patterns_with_risk_assessment to return patterns unchanged with empty risk dict
        mock.filter_patterns_with_risk_assessment.side_effect = lambda patterns: (patterns, {})
        return mock

    @patch("autopack.roadc.task_generator._emit_task_generation_event")
    def test_generate_tasks_emits_success_metrics(
        self, mock_emit, mock_memory_service, mock_regression_protector
    ):
        """Test that generate_tasks emits success metrics."""
        generator = AutonomousTaskGenerator(
            memory_service=mock_memory_service,
            regression_protector=mock_regression_protector,
        )

        generator.generate_tasks(
            max_tasks=5,
            min_confidence=0.5,
            run_id="test-run-123",
        )

        # Verify emit was called with success=True
        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args.kwargs
        assert call_kwargs["success"] is True
        assert call_kwargs["run_id"] == "test-run-123"
        assert call_kwargs["telemetry_source"] == "memory"
        assert call_kwargs["max_tasks"] == 5
        assert call_kwargs["min_confidence"] == 0.5
        assert call_kwargs["insights_processed"] >= 0

    @patch("autopack.roadc.task_generator._emit_task_generation_event")
    def test_generate_tasks_emits_failure_metrics_on_error(
        self, mock_emit, mock_regression_protector
    ):
        """Test that generate_tasks emits failure metrics on error."""
        # Create memory service that raises an error
        mock_memory = MagicMock()
        mock_memory.retrieve_insights.side_effect = ValueError("Test error")

        generator = AutonomousTaskGenerator(
            memory_service=mock_memory,
            regression_protector=mock_regression_protector,
        )

        with pytest.raises(ValueError):
            generator.generate_tasks(run_id="error-run")

        # Verify emit was called with success=False
        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args.kwargs
        assert call_kwargs["success"] is False
        assert call_kwargs["error_message"] == "Test error"
        assert call_kwargs["error_type"] == "ValueError"
        assert call_kwargs["run_id"] == "error-run"

    @patch("autopack.roadc.task_generator._emit_task_generation_event")
    def test_generate_tasks_with_telemetry_insights(
        self, mock_emit, mock_memory_service, mock_regression_protector
    ):
        """Test that telemetry_source is 'direct' when using telemetry_insights."""
        generator = AutonomousTaskGenerator(
            memory_service=mock_memory_service,
            regression_protector=mock_regression_protector,
        )

        telemetry_data = {
            "top_cost_sinks": [
                RankedIssue(
                    rank=1,
                    issue_type="cost_sink",
                    phase_id="phase-1",
                    phase_type="implementation",
                    metric_value=100000,
                    details={"avg_tokens": 50000, "count": 5},
                )
            ],
            "top_failure_modes": [],
            "top_retry_causes": [],
        }

        generator.generate_tasks(
            telemetry_insights=telemetry_data,
            run_id="direct-run",
        )

        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args.kwargs
        assert call_kwargs["telemetry_source"] == "direct"


class TestTelemetryAnalyzerTaskGenerationStats:
    """Tests for TelemetryAnalyzer.get_task_generation_stats()."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        return MagicMock()

    def test_get_task_generation_stats_returns_stats(self, mock_db_session):
        """Test that get_task_generation_stats returns proper stats."""
        # Mock the overall stats query
        mock_overall_row = MagicMock()
        mock_overall_row.total_runs = 10
        mock_overall_row.successful_runs = 8
        mock_overall_row.failed_runs = 2
        mock_overall_row.total_tasks_generated = 25
        mock_overall_row.total_insights_processed = 100
        mock_overall_row.total_patterns_detected = 30
        mock_overall_row.avg_generation_time_ms = 150.5

        # Mock the error types query
        mock_error_row = MagicMock()
        mock_error_row.error_type = "ValueError"
        mock_error_row.count = 2

        mock_db_session.execute.side_effect = [
            MagicMock(fetchone=lambda: mock_overall_row),
            MagicMock(__iter__=lambda self: iter([mock_error_row])),
        ]

        analyzer = TelemetryAnalyzer(db_session=mock_db_session)
        stats = analyzer.get_task_generation_stats(window_days=7)

        assert isinstance(stats, TaskGenerationStats)
        assert stats.total_runs == 10
        assert stats.successful_runs == 8
        assert stats.failed_runs == 2
        assert stats.success_rate == 0.8
        assert stats.total_tasks_generated == 25
        assert stats.total_insights_processed == 100
        assert stats.total_patterns_detected == 30
        assert stats.avg_generation_time_ms == 150.5
        assert stats.avg_tasks_per_run == 25 / 8  # total_tasks / successful_runs
        assert stats.common_error_types == {"ValueError": 2}

    def test_get_task_generation_stats_empty_data(self, mock_db_session):
        """Test stats with no data returns zeros."""
        mock_empty_row = MagicMock()
        mock_empty_row.total_runs = 0
        mock_empty_row.successful_runs = None
        mock_empty_row.failed_runs = None
        mock_empty_row.total_tasks_generated = None
        mock_empty_row.total_insights_processed = None
        mock_empty_row.total_patterns_detected = None
        mock_empty_row.avg_generation_time_ms = None

        mock_db_session.execute.side_effect = [
            MagicMock(fetchone=lambda: mock_empty_row),
            MagicMock(__iter__=lambda self: iter([])),
        ]

        analyzer = TelemetryAnalyzer(db_session=mock_db_session)
        stats = analyzer.get_task_generation_stats()

        assert stats.total_runs == 0
        assert stats.success_rate == 0.0
        assert stats.avg_tasks_per_run == 0.0
        assert stats.common_error_types == {}


class TestTaskGenerationStats:
    """Tests for TaskGenerationStats dataclass."""

    def test_stats_dataclass_fields(self):
        """Test TaskGenerationStats has all expected fields."""
        stats = TaskGenerationStats(
            total_runs=10,
            successful_runs=8,
            failed_runs=2,
            success_rate=0.8,
            total_tasks_generated=25,
            total_insights_processed=100,
            total_patterns_detected=30,
            avg_generation_time_ms=150.5,
            avg_tasks_per_run=3.125,
            common_error_types={"ValueError": 2},
        )

        assert stats.total_runs == 10
        assert stats.successful_runs == 8
        assert stats.failed_runs == 2
        assert stats.success_rate == 0.8
        assert stats.total_tasks_generated == 25
        assert stats.total_insights_processed == 100
        assert stats.total_patterns_detected == 30
        assert stats.avg_generation_time_ms == 150.5
        assert stats.avg_tasks_per_run == 3.125
        assert stats.common_error_types == {"ValueError": 2}


class TestWriteTaskGenerationReport:
    """Tests for TelemetryAnalyzer.write_task_generation_report()."""

    @pytest.fixture
    def sample_stats(self):
        """Create sample stats for testing."""
        return TaskGenerationStats(
            total_runs=10,
            successful_runs=8,
            failed_runs=2,
            success_rate=0.8,
            total_tasks_generated=25,
            total_insights_processed=100,
            total_patterns_detected=30,
            avg_generation_time_ms=150.5,
            avg_tasks_per_run=3.125,
            common_error_types={"ValueError": 2, "TimeoutError": 1},
        )

    def test_write_report_creates_file(self, tmp_path, sample_stats):
        """Test that write_task_generation_report creates a markdown file."""
        mock_session = MagicMock()
        analyzer = TelemetryAnalyzer(db_session=mock_session)

        output_path = tmp_path / "reports" / "task_generation_report.md"
        analyzer.write_task_generation_report(sample_stats, output_path)

        assert output_path.exists()
        content = output_path.read_text()

        assert "# Task Generation Metrics Report" in content
        assert "Total Runs | 10" in content
        assert "Successful Runs | 8" in content
        assert "Failed Runs | 2" in content
        assert "Success Rate | 80.0%" in content
        assert "Total Tasks Generated | 25" in content
        assert "ValueError | 2" in content
        assert "TimeoutError | 1" in content

    def test_write_report_no_errors(self, tmp_path):
        """Test report with no errors shows appropriate message."""
        mock_session = MagicMock()
        analyzer = TelemetryAnalyzer(db_session=mock_session)

        stats = TaskGenerationStats(
            total_runs=5,
            successful_runs=5,
            failed_runs=0,
            success_rate=1.0,
            total_tasks_generated=10,
            total_insights_processed=50,
            total_patterns_detected=15,
            avg_generation_time_ms=100.0,
            avg_tasks_per_run=2.0,
            common_error_types={},
        )

        output_path = tmp_path / "clean_report.md"
        analyzer.write_task_generation_report(stats, output_path)

        content = output_path.read_text()
        assert "No errors recorded in analysis window" in content
