"""Tests for TelemetryTaskDaemon (IMP-LOOP-030).

Tests cover:
- Daemon initialization and configuration
- Start/stop lifecycle
- Single cycle execution (run_once)
- Multi-cycle execution in background thread
- Integration with TelemetryAnalyzer and TaskGenerator
- Statistics tracking and cycle history
- Configuration updates
"""

import threading
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

from autopack.roadc.task_daemon import (DEFAULT_INTERVAL_SECONDS,
                                        DEFAULT_MAX_TASKS_PER_CYCLE,
                                        DEFAULT_MIN_CONFIDENCE,
                                        DaemonCycleResult, DaemonStats,
                                        TelemetryTaskDaemon,
                                        create_task_daemon)


class TestDaemonCycleResult:
    """Tests for DaemonCycleResult dataclass."""

    def test_cycle_result_creation(self):
        """DaemonCycleResult should store all cycle metrics."""
        result = DaemonCycleResult(
            cycle_number=1,
            timestamp=datetime.now(timezone.utc),
            insights_found=10,
            tasks_generated=3,
            tasks_persisted=2,
            tasks_queued=3,
            cycle_duration_ms=150.5,
        )
        assert result.cycle_number == 1
        assert result.insights_found == 10
        assert result.tasks_generated == 3
        assert result.tasks_persisted == 2
        assert result.tasks_queued == 3
        assert result.cycle_duration_ms == 150.5
        assert result.error is None
        assert result.skipped_reason is None

    def test_cycle_result_with_error(self):
        """DaemonCycleResult should store error information."""
        result = DaemonCycleResult(
            cycle_number=2,
            timestamp=datetime.now(timezone.utc),
            insights_found=0,
            tasks_generated=0,
            tasks_persisted=0,
            tasks_queued=0,
            cycle_duration_ms=50.0,
            error="Database connection failed",
        )
        assert result.error == "Database connection failed"

    def test_cycle_result_with_skip_reason(self):
        """DaemonCycleResult should store skip reason."""
        result = DaemonCycleResult(
            cycle_number=3,
            timestamp=datetime.now(timezone.utc),
            insights_found=5,
            tasks_generated=0,
            tasks_persisted=0,
            tasks_queued=0,
            cycle_duration_ms=75.0,
            skipped_reason="No high-ROI patterns detected",
        )
        assert result.skipped_reason == "No high-ROI patterns detected"


class TestDaemonStats:
    """Tests for DaemonStats dataclass."""

    def test_daemon_stats_defaults(self):
        """DaemonStats should have sensible defaults."""
        stats = DaemonStats()
        assert stats.total_cycles == 0
        assert stats.successful_cycles == 0
        assert stats.failed_cycles == 0
        assert stats.total_insights_processed == 0
        assert stats.total_tasks_generated == 0
        assert stats.avg_cycle_duration_ms == 0.0
        assert stats.last_successful_cycle is None
        assert stats.last_error is None
        assert stats.cycle_history == []


class TestTelemetryTaskDaemonInit:
    """Tests for TelemetryTaskDaemon initialization."""

    def test_daemon_default_configuration(self):
        """Daemon should initialize with default configuration."""
        daemon = TelemetryTaskDaemon()
        assert daemon._interval == DEFAULT_INTERVAL_SECONDS
        assert daemon._min_confidence == DEFAULT_MIN_CONFIDENCE
        assert daemon._max_tasks_per_cycle == DEFAULT_MAX_TASKS_PER_CYCLE
        assert daemon._project_id == "default"
        assert daemon._auto_persist is True
        assert daemon._auto_queue is True
        assert not daemon.is_running

    def test_daemon_custom_configuration(self):
        """Daemon should accept custom configuration."""
        daemon = TelemetryTaskDaemon(
            interval_seconds=60,
            min_confidence=0.8,
            max_tasks_per_cycle=10,
            project_id="test-project",
            auto_persist=False,
            auto_queue=False,
        )
        assert daemon._interval == 60
        assert daemon._min_confidence == 0.8
        assert daemon._max_tasks_per_cycle == 10
        assert daemon._project_id == "test-project"
        assert daemon._auto_persist is False
        assert daemon._auto_queue is False

    def test_daemon_with_db_session(self):
        """Daemon should accept database session."""
        mock_session = Mock()
        daemon = TelemetryTaskDaemon(db_session=mock_session)
        assert daemon._db_session is mock_session

    def test_daemon_with_memory_service(self):
        """Daemon should accept memory service."""
        mock_memory = Mock()
        daemon = TelemetryTaskDaemon(memory_service=mock_memory)
        assert daemon._memory_service is mock_memory


class TestTelemetryTaskDaemonStartStop:
    """Tests for daemon start/stop lifecycle."""

    def test_daemon_start_sets_running_flag(self):
        """Starting daemon should set is_running to True."""
        daemon = TelemetryTaskDaemon(interval_seconds=1)

        with patch.object(daemon, "_initialize_components", return_value=True):
            result = daemon.start()
            assert result is True
            assert daemon.is_running is True

            # Clean up
            daemon.stop()
            assert daemon.is_running is False

    def test_daemon_start_fails_if_already_running(self):
        """Starting daemon when already running should return False."""
        daemon = TelemetryTaskDaemon(interval_seconds=1)

        with patch.object(daemon, "_initialize_components", return_value=True):
            daemon.start()
            result = daemon.start()  # Second start
            assert result is False

            daemon.stop()

    def test_daemon_start_fails_on_init_error(self):
        """Starting daemon should fail if component initialization fails."""
        daemon = TelemetryTaskDaemon()

        with patch.object(daemon, "_initialize_components", return_value=False):
            result = daemon.start()
            assert result is False
            assert daemon.is_running is False

    def test_daemon_stop_when_not_running(self):
        """Stopping daemon when not running should return True."""
        daemon = TelemetryTaskDaemon()
        result = daemon.stop()
        assert result is True

    def test_daemon_stop_gracefully(self):
        """Daemon should stop gracefully within timeout."""
        daemon = TelemetryTaskDaemon(interval_seconds=1)

        with patch.object(daemon, "_initialize_components", return_value=True):
            with patch.object(daemon, "_execute_cycle") as mock_cycle:
                mock_cycle.return_value = DaemonCycleResult(
                    cycle_number=1,
                    timestamp=datetime.now(timezone.utc),
                    insights_found=0,
                    tasks_generated=0,
                    tasks_persisted=0,
                    tasks_queued=0,
                    cycle_duration_ms=10.0,
                    skipped_reason="No insights",
                )

                daemon.start()
                time.sleep(0.1)  # Let daemon start

                result = daemon.stop(timeout=5.0)
                assert result is True
                assert daemon.is_running is False


class TestTelemetryTaskDaemonRunOnce:
    """Tests for single cycle execution (run_once)."""

    def test_run_once_returns_cycle_result(self):
        """run_once should return a DaemonCycleResult."""
        daemon = TelemetryTaskDaemon()

        with patch.object(daemon, "_initialize_components", return_value=True):
            with patch.object(daemon, "_execute_cycle") as mock_cycle:
                expected = DaemonCycleResult(
                    cycle_number=1,
                    timestamp=datetime.now(timezone.utc),
                    insights_found=5,
                    tasks_generated=2,
                    tasks_persisted=2,
                    tasks_queued=2,
                    cycle_duration_ms=100.0,
                )
                mock_cycle.return_value = expected

                result = daemon.run_once()
                assert result == expected

    def test_run_once_fails_on_init_error(self):
        """run_once should return error result if initialization fails."""
        daemon = TelemetryTaskDaemon()

        with patch.object(daemon, "_initialize_components", return_value=False):
            result = daemon.run_once()
            assert result.error == "Failed to initialize components"
            assert result.tasks_generated == 0


class TestTelemetryTaskDaemonExecuteCycle:
    """Tests for _execute_cycle method."""

    @pytest.fixture
    def daemon_with_mocks(self):
        """Create daemon with mocked components."""
        daemon = TelemetryTaskDaemon()

        # Mock task generator
        mock_generator = Mock()
        mock_result = Mock()
        mock_result.insights_processed = 10
        mock_result.tasks_generated = []  # No tasks by default
        mock_generator.generate_tasks.return_value = mock_result
        mock_generator.emit_tasks_for_execution.return_value = {
            "persisted": 0,
            "queued": 0,
        }

        daemon._task_generator = mock_generator

        return daemon

    def test_execute_cycle_with_no_tasks(self, daemon_with_mocks):
        """Cycle should complete with skip reason when no tasks generated."""
        result = daemon_with_mocks._execute_cycle()

        assert result.insights_found == 10
        assert result.tasks_generated == 0
        assert result.skipped_reason == "No high-ROI patterns detected"

    def test_execute_cycle_with_tasks(self, daemon_with_mocks):
        """Cycle should emit tasks when generated."""
        # Setup mock to return tasks
        mock_task = Mock()
        daemon_with_mocks._task_generator.generate_tasks.return_value.tasks_generated = [
            mock_task,
            mock_task,
        ]
        daemon_with_mocks._task_generator.emit_tasks_for_execution.return_value = {
            "persisted": 2,
            "queued": 2,
        }

        result = daemon_with_mocks._execute_cycle()

        assert result.tasks_generated == 2
        assert result.tasks_persisted == 2
        assert result.tasks_queued == 2
        assert result.skipped_reason is None
        assert result.error is None

    def test_execute_cycle_increments_cycle_number(self, daemon_with_mocks):
        """Each cycle should increment the cycle number."""
        result1 = daemon_with_mocks._execute_cycle()
        result2 = daemon_with_mocks._execute_cycle()
        result3 = daemon_with_mocks._execute_cycle()

        assert result1.cycle_number == 1
        assert result2.cycle_number == 2
        assert result3.cycle_number == 3

    def test_execute_cycle_handles_exception(self, daemon_with_mocks):
        """Cycle should catch and report exceptions."""
        daemon_with_mocks._task_generator.generate_tasks.side_effect = RuntimeError("Test error")

        result = daemon_with_mocks._execute_cycle()

        assert result.error == "Test error"
        assert result.tasks_generated == 0


class TestTelemetryTaskDaemonStats:
    """Tests for statistics tracking."""

    def test_stats_updated_after_successful_cycle(self):
        """Statistics should be updated after successful cycle."""
        daemon = TelemetryTaskDaemon()
        initial_stats = daemon.stats

        assert initial_stats.total_cycles == 0

        # Simulate cycle result
        result = DaemonCycleResult(
            cycle_number=1,
            timestamp=datetime.now(timezone.utc),
            insights_found=5,
            tasks_generated=2,
            tasks_persisted=2,
            tasks_queued=2,
            cycle_duration_ms=100.0,
        )
        daemon._update_stats(result)

        updated_stats = daemon.stats
        assert updated_stats.total_cycles == 1
        assert updated_stats.successful_cycles == 1
        assert updated_stats.failed_cycles == 0
        assert updated_stats.total_insights_processed == 5
        assert updated_stats.total_tasks_generated == 2

    def test_stats_updated_after_failed_cycle(self):
        """Statistics should track failed cycles."""
        daemon = TelemetryTaskDaemon()

        result = DaemonCycleResult(
            cycle_number=1,
            timestamp=datetime.now(timezone.utc),
            insights_found=0,
            tasks_generated=0,
            tasks_persisted=0,
            tasks_queued=0,
            cycle_duration_ms=50.0,
            error="Database error",
        )
        daemon._update_stats(result)

        stats = daemon.stats
        assert stats.total_cycles == 1
        assert stats.successful_cycles == 0
        assert stats.failed_cycles == 1
        assert stats.last_error == "Database error"

    def test_stats_rolling_average_duration(self):
        """Average cycle duration should be calculated correctly."""
        daemon = TelemetryTaskDaemon()

        # Add cycles with different durations
        for i, duration in enumerate([100.0, 200.0, 300.0], start=1):
            result = DaemonCycleResult(
                cycle_number=i,
                timestamp=datetime.now(timezone.utc),
                insights_found=0,
                tasks_generated=0,
                tasks_persisted=0,
                tasks_queued=0,
                cycle_duration_ms=duration,
                skipped_reason="No insights",
            )
            daemon._update_stats(result)

        stats = daemon.stats
        assert stats.avg_cycle_duration_ms == 200.0  # (100 + 200 + 300) / 3

    def test_cycle_history_bounded(self):
        """Cycle history should be bounded to MAX_CYCLE_HISTORY."""
        daemon = TelemetryTaskDaemon()

        # Add more cycles than the limit
        for i in range(TelemetryTaskDaemon.MAX_CYCLE_HISTORY + 20):
            result = DaemonCycleResult(
                cycle_number=i,
                timestamp=datetime.now(timezone.utc),
                insights_found=0,
                tasks_generated=0,
                tasks_persisted=0,
                tasks_queued=0,
                cycle_duration_ms=10.0,
                skipped_reason="No insights",
            )
            daemon._update_stats(result)

        assert len(daemon.stats.cycle_history) == TelemetryTaskDaemon.MAX_CYCLE_HISTORY

    def test_get_recent_cycles(self):
        """get_recent_cycles should return last N cycles."""
        daemon = TelemetryTaskDaemon()

        # Add 5 cycles
        for i in range(5):
            result = DaemonCycleResult(
                cycle_number=i + 1,
                timestamp=datetime.now(timezone.utc),
                insights_found=i,
                tasks_generated=0,
                tasks_persisted=0,
                tasks_queued=0,
                cycle_duration_ms=10.0,
                skipped_reason="No insights",
            )
            daemon._update_stats(result)

        recent = daemon.get_recent_cycles(count=3)
        assert len(recent) == 3
        assert recent[0].cycle_number == 3
        assert recent[1].cycle_number == 4
        assert recent[2].cycle_number == 5


class TestTelemetryTaskDaemonConfiguration:
    """Tests for configuration updates."""

    def test_update_interval(self):
        """Configuration update should change interval."""
        daemon = TelemetryTaskDaemon(interval_seconds=300)
        assert daemon._interval == 300

        daemon.update_configuration(interval_seconds=60)
        assert daemon._interval == 60

    def test_update_min_confidence(self):
        """Configuration update should change min_confidence."""
        daemon = TelemetryTaskDaemon(min_confidence=0.7)
        assert daemon._min_confidence == 0.7

        daemon.update_configuration(min_confidence=0.9)
        assert daemon._min_confidence == 0.9

    def test_update_max_tasks_per_cycle(self):
        """Configuration update should change max_tasks_per_cycle."""
        daemon = TelemetryTaskDaemon(max_tasks_per_cycle=5)
        assert daemon._max_tasks_per_cycle == 5

        daemon.update_configuration(max_tasks_per_cycle=10)
        assert daemon._max_tasks_per_cycle == 10

    def test_update_multiple_settings(self):
        """Multiple settings can be updated at once."""
        daemon = TelemetryTaskDaemon()

        daemon.update_configuration(
            interval_seconds=120,
            min_confidence=0.8,
            max_tasks_per_cycle=3,
        )

        assert daemon._interval == 120
        assert daemon._min_confidence == 0.8
        assert daemon._max_tasks_per_cycle == 3

    def test_update_with_none_preserves_values(self):
        """Passing None should preserve existing values."""
        daemon = TelemetryTaskDaemon(
            interval_seconds=100,
            min_confidence=0.5,
        )

        daemon.update_configuration(interval_seconds=200, min_confidence=None)

        assert daemon._interval == 200
        assert daemon._min_confidence == 0.5  # Unchanged


class TestCreateTaskDaemon:
    """Tests for create_task_daemon factory function."""

    def test_factory_creates_daemon(self):
        """Factory should create a TelemetryTaskDaemon instance."""
        daemon = create_task_daemon()
        assert isinstance(daemon, TelemetryTaskDaemon)

    def test_factory_passes_db_session(self):
        """Factory should pass db_session to daemon."""
        mock_session = Mock()
        daemon = create_task_daemon(db_session=mock_session)
        assert daemon._db_session is mock_session

    def test_factory_passes_kwargs(self):
        """Factory should pass additional kwargs to daemon."""
        daemon = create_task_daemon(
            interval_seconds=120,
            min_confidence=0.9,
            project_id="factory-test",
        )
        assert daemon._interval == 120
        assert daemon._min_confidence == 0.9
        assert daemon._project_id == "factory-test"


class TestTelemetryTaskDaemonIntegration:
    """Integration tests for daemon with mocked dependencies."""

    def test_daemon_runs_multiple_cycles(self):
        """Daemon should run multiple cycles in background."""
        daemon = TelemetryTaskDaemon(interval_seconds=0.1)  # Fast interval for testing
        cycle_count = 0
        cycle_lock = threading.Lock()

        def mock_execute_cycle():
            nonlocal cycle_count
            with cycle_lock:
                cycle_count += 1
            return DaemonCycleResult(
                cycle_number=cycle_count,
                timestamp=datetime.now(timezone.utc),
                insights_found=1,
                tasks_generated=0,
                tasks_persisted=0,
                tasks_queued=0,
                cycle_duration_ms=10.0,
                skipped_reason="Test",
            )

        with patch.object(daemon, "_initialize_components", return_value=True):
            with patch.object(daemon, "_execute_cycle", side_effect=mock_execute_cycle):
                daemon.start()
                time.sleep(0.5)  # Let daemon run several cycles
                daemon.stop()

        # Should have run multiple cycles
        assert cycle_count >= 3

    def test_daemon_stops_on_signal(self):
        """Daemon should stop when stop signal is set."""
        daemon = TelemetryTaskDaemon(interval_seconds=10)  # Long interval

        cycle_started = threading.Event()

        def slow_execute_cycle():
            cycle_started.set()
            time.sleep(5)  # Long cycle
            return DaemonCycleResult(
                cycle_number=1,
                timestamp=datetime.now(timezone.utc),
                insights_found=0,
                tasks_generated=0,
                tasks_persisted=0,
                tasks_queued=0,
                cycle_duration_ms=5000.0,
                skipped_reason="Test",
            )

        with patch.object(daemon, "_initialize_components", return_value=True):
            with patch.object(daemon, "_execute_cycle", side_effect=slow_execute_cycle):
                daemon.start()

                # Wait for cycle to start then stop
                cycle_started.wait(timeout=1.0)
                start_time = time.time()
                daemon.stop(timeout=2.0)
                stop_time = time.time()

        # Should have stopped within reasonable time (not waiting for full cycle)
        assert stop_time - start_time < 3.0
