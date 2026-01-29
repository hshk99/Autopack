"""Tests for StartupPhaseLogger and startup initialization logging (IMP-OPS-012).

Tests verify that startup phases are logged with timing information,
and that failures are properly captured and reported.
"""

import logging
import time

import pytest

from autopack.api.app import StartupError, StartupPhaseLogger, StartupPhaseResult


class TestStartupPhaseResult:
    """Test suite for StartupPhaseResult dataclass."""

    def test_successful_result(self):
        """Verify successful result can be created."""
        result = StartupPhaseResult(name="test_phase", success=True, duration_seconds=0.123)
        assert result.name == "test_phase"
        assert result.success is True
        assert result.duration_seconds == 0.123
        assert result.error is None

    def test_failed_result_with_error(self):
        """Verify failed result includes error message."""
        result = StartupPhaseResult(
            name="failing_phase",
            success=False,
            duration_seconds=0.456,
            error="Something went wrong",
        )
        assert result.name == "failing_phase"
        assert result.success is False
        assert result.error == "Something went wrong"


class TestStartupError:
    """Test suite for StartupError exception."""

    def test_startup_error_message(self):
        """Verify StartupError formats message correctly."""
        error = StartupError(phase="database", message="Connection refused", cause=None)
        assert error.phase == "database"
        assert error.message == "Connection refused"
        assert "Startup phase 'database' failed" in str(error)

    def test_startup_error_with_cause(self):
        """Verify StartupError preserves original exception."""
        original = ValueError("Original error")
        error = StartupError(phase="config", message="Invalid value", cause=original)
        assert error.cause is original


class TestStartupPhaseLogger:
    """Test suite for StartupPhaseLogger class."""

    def test_initialization(self):
        """Verify logger initializes with empty phases list."""
        logger = StartupPhaseLogger()
        assert logger.phases == []

    def test_begin_startup_logs_message(self, caplog):
        """Verify begin_startup logs initialization message."""
        startup_logger = StartupPhaseLogger()

        with caplog.at_level(logging.INFO):
            startup_logger.begin_startup()

        assert any(
            "Beginning application initialization sequence" in record.message
            for record in caplog.records
        )

    def test_run_phase_success(self, caplog):
        """Verify successful phase is logged with timing."""
        startup_logger = StartupPhaseLogger()
        startup_logger.begin_startup()

        def successful_phase():
            time.sleep(0.01)

        with caplog.at_level(logging.INFO):
            startup_logger.run_phase("test_phase", successful_phase)

        assert len(startup_logger.phases) == 1
        result = startup_logger.phases[0]
        assert result.name == "test_phase"
        assert result.success is True
        assert result.duration_seconds >= 0.01
        assert result.error is None

        # Verify logging
        assert any("Starting phase: test_phase" in record.message for record in caplog.records)
        assert any("Phase 'test_phase' completed" in record.message for record in caplog.records)

    def test_run_phase_failure(self, caplog):
        """Verify failed phase raises StartupError with context."""
        startup_logger = StartupPhaseLogger()
        startup_logger.begin_startup()

        def failing_phase():
            raise ValueError("Test error message")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(StartupError) as exc_info:
                startup_logger.run_phase("failing_phase", failing_phase)

        assert exc_info.value.phase == "failing_phase"
        assert "Test error message" in exc_info.value.message

        # Verify error is recorded
        assert len(startup_logger.phases) == 1
        result = startup_logger.phases[0]
        assert result.name == "failing_phase"
        assert result.success is False
        assert "Test error message" in result.error

        # Verify error logging
        assert any("Phase 'failing_phase' FAILED" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_run_phase_async_success(self, caplog):
        """Verify async phase execution with timing."""
        startup_logger = StartupPhaseLogger()
        startup_logger.begin_startup()

        async def async_phase():
            import asyncio

            await asyncio.sleep(0.01)

        with caplog.at_level(logging.INFO):
            await startup_logger.run_phase_async("async_phase", async_phase)

        assert len(startup_logger.phases) == 1
        result = startup_logger.phases[0]
        assert result.name == "async_phase"
        assert result.success is True
        assert result.duration_seconds >= 0.01

    @pytest.mark.asyncio
    async def test_run_phase_async_with_sync_func(self, caplog):
        """Verify run_phase_async handles sync functions."""
        startup_logger = StartupPhaseLogger()
        startup_logger.begin_startup()

        def sync_phase():
            time.sleep(0.01)

        with caplog.at_level(logging.INFO):
            await startup_logger.run_phase_async("sync_phase", sync_phase)

        assert len(startup_logger.phases) == 1
        result = startup_logger.phases[0]
        assert result.name == "sync_phase"
        assert result.success is True

    @pytest.mark.asyncio
    async def test_run_phase_async_failure(self, caplog):
        """Verify async phase failure handling."""
        startup_logger = StartupPhaseLogger()
        startup_logger.begin_startup()

        async def failing_async_phase():
            raise RuntimeError("Async error")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(StartupError) as exc_info:
                await startup_logger.run_phase_async("failing_async", failing_async_phase)

        assert exc_info.value.phase == "failing_async"
        assert "Async error" in exc_info.value.message

    def test_complete_startup_logs_summary(self, caplog):
        """Verify complete_startup logs summary with timings."""
        startup_logger = StartupPhaseLogger()
        startup_logger.begin_startup()

        def phase1():
            time.sleep(0.01)

        def phase2():
            time.sleep(0.02)

        startup_logger.run_phase("phase1", phase1)
        startup_logger.run_phase("phase2", phase2)

        with caplog.at_level(logging.INFO):
            startup_logger.complete_startup()

        # Verify summary log
        assert any(
            "All 2 startup phases completed successfully" in record.message
            for record in caplog.records
        )
        assert any(
            "phase1=" in record.message and "phase2=" in record.message for record in caplog.records
        )

    def test_get_phase_timings(self):
        """Verify get_phase_timings returns timing dictionary."""
        startup_logger = StartupPhaseLogger()
        startup_logger.begin_startup()

        startup_logger.run_phase("fast_phase", lambda: None)
        startup_logger.run_phase("another_phase", lambda: None)

        timings = startup_logger.get_phase_timings()

        assert "fast_phase" in timings
        assert "another_phase" in timings
        assert isinstance(timings["fast_phase"], float)
        assert isinstance(timings["another_phase"], float)

    def test_multiple_phases_tracking(self):
        """Verify multiple phases are tracked in order."""
        startup_logger = StartupPhaseLogger()
        startup_logger.begin_startup()

        startup_logger.run_phase("phase_a", lambda: None)
        startup_logger.run_phase("phase_b", lambda: None)
        startup_logger.run_phase("phase_c", lambda: None)

        assert len(startup_logger.phases) == 3
        assert startup_logger.phases[0].name == "phase_a"
        assert startup_logger.phases[1].name == "phase_b"
        assert startup_logger.phases[2].name == "phase_c"

    def test_phase_failure_preserves_prior_phases(self):
        """Verify that prior successful phases are preserved after failure."""
        startup_logger = StartupPhaseLogger()
        startup_logger.begin_startup()

        startup_logger.run_phase("successful_phase", lambda: None)

        with pytest.raises(StartupError):
            startup_logger.run_phase(
                "failing_phase", lambda: (_ for _ in ()).throw(ValueError("Error"))
            )

        # First phase should still be recorded
        assert len(startup_logger.phases) == 2
        assert startup_logger.phases[0].success is True
        assert startup_logger.phases[1].success is False


class TestStartupLoggingIntegration:
    """Integration tests for startup logging in app lifespan."""

    def test_startup_error_is_importable(self):
        """Verify StartupError can be imported from app module."""
        from autopack.api.app import StartupError

        error = StartupError("test", "message")
        assert isinstance(error, Exception)

    def test_startup_phase_logger_is_importable(self):
        """Verify StartupPhaseLogger can be imported from app module."""
        from autopack.api.app import StartupPhaseLogger

        logger = StartupPhaseLogger()
        assert hasattr(logger, "run_phase")
        assert hasattr(logger, "begin_startup")
        assert hasattr(logger, "complete_startup")
