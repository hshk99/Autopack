"""Tests for BackgroundTaskSupervisor (IMP-OPS-001).

Tests verify that background tasks are automatically restarted on failure
with exponential backoff and proper logging.
"""

import asyncio
import logging
from unittest.mock import patch

import pytest

from autopack.api.app import BackgroundTaskSupervisor


class TestBackgroundTaskSupervisor:
    """Test suite for BackgroundTaskSupervisor class."""

    def test_initialization(self):
        """Verify supervisor initializes with default max_restarts."""
        supervisor = BackgroundTaskSupervisor()
        assert supervisor._max_restarts == 5
        assert supervisor._restart_counts == {}
        assert supervisor._tasks == {}

    def test_custom_max_restarts(self):
        """Verify supervisor accepts custom max_restarts value."""
        supervisor = BackgroundTaskSupervisor(max_restarts=10)
        assert supervisor._max_restarts == 10

    def test_get_status_returns_restart_counts(self):
        """Verify get_status returns restart counts dictionary."""
        supervisor = BackgroundTaskSupervisor()
        supervisor._restart_counts = {"task1": 2, "task2": 0}
        status = supervisor.get_status()
        assert status == {"task1": 2, "task2": 0}

    def test_reset_restart_count(self):
        """Verify reset_restart_count clears count for specific task."""
        supervisor = BackgroundTaskSupervisor()
        supervisor._restart_counts = {"task1": 3}
        supervisor.reset_restart_count("task1")
        assert supervisor._restart_counts["task1"] == 0

    def test_reset_restart_count_for_nonexistent_task(self):
        """Verify reset_restart_count handles non-existent tasks gracefully."""
        supervisor = BackgroundTaskSupervisor()
        supervisor._restart_counts = {}
        # Should not raise exception
        supervisor.reset_restart_count("nonexistent")
        assert supervisor._restart_counts == {}

    @pytest.mark.asyncio
    async def test_task_completes_normally(self):
        """Verify that normally completing tasks exit supervision loop."""
        supervisor = BackgroundTaskSupervisor(max_restarts=3)

        async def successful_task():
            """Task that completes normally."""
            await asyncio.sleep(0.01)
            return "success"

        # Task should complete without restart
        await supervisor.supervise("test_task", successful_task)
        assert supervisor._restart_counts.get("test_task", 0) == 0

    @pytest.mark.asyncio
    async def test_task_restart_on_failure(self):
        """Verify that failing tasks are restarted with backoff."""
        supervisor = BackgroundTaskSupervisor(max_restarts=3)
        attempt_count = 0

        async def failing_task():
            """Task that fails on first attempt then succeeds."""
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count == 1:
                raise ValueError("Test error")
            await asyncio.sleep(0.01)

        with patch("asyncio.sleep") as mock_sleep:
            await supervisor.supervise("test_task", failing_task)

            # Verify sleep was called for backoff
            assert mock_sleep.call_count > 0

        # Verify restart happened
        assert attempt_count == 2
        assert supervisor._restart_counts["test_task"] == 1

    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """Verify restart delay uses exponential backoff (2^attempt, capped at 60s)."""
        supervisor = BackgroundTaskSupervisor(max_restarts=5)
        attempt_count = 0
        sleep_durations = []

        async def failing_task():
            """Task that fails multiple times."""
            nonlocal attempt_count
            attempt_count += 1
            raise ValueError(f"Attempt {attempt_count}")

        # Capture sleep durations
        original_sleep = asyncio.sleep

        async def mock_sleep(duration):
            sleep_durations.append(duration)
            await original_sleep(0.001)  # Short sleep for test speed

        with patch("asyncio.sleep", side_effect=mock_sleep):
            await supervisor.supervise("test_task", failing_task)

        # Verify exponential backoff: 2s, 4s, 8s, 16s, 32s (max_restarts=5)
        expected_backoffs = [2, 4, 8, 16, 32]
        assert sleep_durations == expected_backoffs

    @pytest.mark.asyncio
    async def test_max_restarts_limit(self):
        """Verify that tasks stop restarting after max_restarts."""
        supervisor = BackgroundTaskSupervisor(max_restarts=2)
        attempt_count = 0

        async def always_failing_task():
            """Task that always fails."""
            nonlocal attempt_count
            attempt_count += 1
            raise ValueError("Always fails")

        with patch("asyncio.sleep", return_value=asyncio.sleep(0.001)):
            await supervisor.supervise("test_task", always_failing_task)

        # Should have attempted max_restarts times (loop condition: restart_count < max_restarts)
        assert attempt_count == 2
        assert supervisor._restart_counts["test_task"] == 2

    @pytest.mark.asyncio
    async def test_cancelled_error_propagates(self):
        """Verify that CancelledError is not caught (graceful shutdown)."""
        supervisor = BackgroundTaskSupervisor()

        async def cancellable_task():
            """Task that gets cancelled."""
            await asyncio.sleep(10)  # Long sleep

        # Create task and cancel it
        task = asyncio.create_task(supervisor.supervise("test_task", cancellable_task))
        await asyncio.sleep(0.01)  # Let task start
        task.cancel()

        # Should raise CancelledError
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_logging_on_task_start(self, caplog):
        """Verify that task start is logged."""
        supervisor = BackgroundTaskSupervisor()

        async def simple_task():
            await asyncio.sleep(0.01)

        with caplog.at_level(logging.INFO):
            await supervisor.supervise("test_task", simple_task)

        # Verify start log
        assert any("Starting task: test_task" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_logging_on_task_failure(self, caplog):
        """Verify that task failures are logged with details."""
        supervisor = BackgroundTaskSupervisor(max_restarts=1)
        attempt_count = 0

        async def failing_task():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count == 1:
                raise ValueError("Test error")

        with caplog.at_level(logging.ERROR):
            with patch("asyncio.sleep", return_value=asyncio.sleep(0.001)):
                await supervisor.supervise("test_task", failing_task)

        # Verify error log
        assert any(
            "Task failed (attempt 1/1): test_task" in record.message for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_logging_on_max_restarts_exceeded(self, caplog):
        """Verify that exceeding max_restarts logs critical message."""
        supervisor = BackgroundTaskSupervisor(max_restarts=2)

        async def always_failing_task():
            raise ValueError("Always fails")

        with caplog.at_level(logging.CRITICAL):
            with patch("asyncio.sleep", return_value=asyncio.sleep(0.001)):
                await supervisor.supervise("test_task", always_failing_task)

        # Verify critical log
        assert any(
            "Task test_task exceeded max restarts" in record.message for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_task_normal_completion_logs(self, caplog):
        """Verify that normally completing tasks log completion."""
        supervisor = BackgroundTaskSupervisor()

        async def simple_task():
            await asyncio.sleep(0.01)

        with caplog.at_level(logging.INFO):
            await supervisor.supervise("test_task", simple_task)

        # Verify completion log
        assert any(
            "Task completed normally: test_task" in record.message for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_concurrent_supervision(self):
        """Verify that multiple tasks can be supervised concurrently."""
        supervisor = BackgroundTaskSupervisor()

        async def task_a():
            await asyncio.sleep(0.02)
            return "a"

        async def task_b():
            await asyncio.sleep(0.02)
            return "b"

        # Run tasks concurrently
        results = await asyncio.gather(
            supervisor.supervise("task_a", task_a),
            supervisor.supervise("task_b", task_b),
        )

        # Both should complete without restarts
        assert results == [None, None]
        # Tasks that complete normally don't get added to restart_counts
        assert supervisor._restart_counts == {}

    @pytest.mark.asyncio
    async def test_backoff_capped_at_60_seconds(self):
        """Verify that exponential backoff is capped at 60 seconds."""
        supervisor = BackgroundTaskSupervisor(max_restarts=10)
        sleep_durations = []

        async def always_failing_task():
            raise ValueError("Always fails")

        # Capture sleep durations
        original_sleep = asyncio.sleep

        async def mock_sleep(duration):
            sleep_durations.append(duration)
            await original_sleep(0.001)

        with patch("asyncio.sleep", side_effect=mock_sleep):
            await supervisor.supervise("test_task", always_failing_task)

        # Verify backoff is capped at 60s after 5th attempt
        # 2, 4, 8, 16, 32, 60, 60, 60, 60, 60
        assert all(duration <= 60 for duration in sleep_durations)
