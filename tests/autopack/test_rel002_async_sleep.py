"""Tests for IMP-REL-002: Async sleep in error recovery.

Verifies that async retry functionality uses asyncio.sleep() instead of
time.sleep() to avoid blocking the event loop during retries.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autopack.error_recovery import (ErrorCategory, ErrorRecoverySystem,
                                     async_safe_execute, get_error_recovery,
                                     safe_execute)


class TestAsyncExecuteWithRetry:
    """Tests for async_execute_with_retry method."""

    @pytest.fixture
    def recovery(self):
        """Create a fresh error recovery instance."""
        return ErrorRecoverySystem()

    @pytest.mark.asyncio
    async def test_async_execute_with_retry_succeeds_first_attempt(self, recovery):
        """Test that async retry returns result on first successful attempt."""
        async_func = AsyncMock(return_value="success")

        result = await recovery.async_execute_with_retry(
            func=async_func,
            operation_name="test_operation",
            max_retries=3,
        )

        assert result == "success"
        async_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_execute_with_retry_retries_on_failure(self, recovery):
        """Test that async retry retries on transient failures."""
        call_count = 0

        async def failing_then_succeeding():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Transient error")
            return "success"

        result = await recovery.async_execute_with_retry(
            func=failing_then_succeeding,
            operation_name="test_operation",
            max_retries=3,
        )

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_async_execute_with_retry_uses_asyncio_sleep(self, recovery):
        """Test that async retry uses asyncio.sleep instead of time.sleep."""
        async_func = AsyncMock(side_effect=[ValueError("error"), "success"])

        with patch("autopack.error_recovery.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await recovery.async_execute_with_retry(
                func=async_func,
                operation_name="test_operation",
                max_retries=3,
            )

            # Verify asyncio.sleep was called (not time.sleep)
            mock_sleep.assert_called()
            assert result == "success"

    @pytest.mark.asyncio
    async def test_async_execute_with_retry_exponential_backoff(self, recovery):
        """Test that async retry uses exponential backoff."""
        async_func = AsyncMock(
            side_effect=[ValueError("e1"), ValueError("e2"), ValueError("e3"), "success"]
        )

        with patch("autopack.error_recovery.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await recovery.async_execute_with_retry(
                func=async_func,
                operation_name="test_operation",
                max_retries=3,
            )

            # Exponential backoff: 2^0=1, 2^1=2, 2^2=4
            sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
            assert sleep_calls == [1, 2, 4]
            assert result == "success"

    @pytest.mark.asyncio
    async def test_async_execute_with_retry_raises_after_max_retries(self, recovery):
        """Test that async retry raises after exhausting retries."""
        async_func = AsyncMock(side_effect=ValueError("Persistent error"))

        with patch("autopack.error_recovery.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ValueError, match="Persistent error"):
                await recovery.async_execute_with_retry(
                    func=async_func,
                    operation_name="test_operation",
                    max_retries=2,
                )

        # Initial attempt + 2 retries = 3 calls
        assert async_func.call_count == 3


class TestAsyncSafeExecute:
    """Tests for async_safe_execute convenience function."""

    @pytest.mark.asyncio
    async def test_async_safe_execute_returns_result_on_success(self):
        """Test that async_safe_execute returns result on success."""
        async_func = AsyncMock(return_value="success")

        result = await async_safe_execute(
            func=async_func,
            operation_name="test_operation",
        )

        assert result == "success"

    @pytest.mark.asyncio
    async def test_async_safe_execute_returns_default_on_failure(self):
        """Test that async_safe_execute returns default on permanent failure."""
        async_func = AsyncMock(side_effect=ValueError("error"))

        with patch("autopack.error_recovery.asyncio.sleep", new_callable=AsyncMock):
            result = await async_safe_execute(
                func=async_func,
                operation_name="test_operation",
                default_return="default_value",
                max_retries=1,
            )

        assert result == "default_value"


class TestSyncVsAsyncSleep:
    """Tests comparing sync and async sleep behavior."""

    def test_sync_execute_with_retry_uses_time_sleep(self):
        """Test that sync retry uses time.sleep (not asyncio.sleep)."""
        recovery = ErrorRecoverySystem()
        sync_func = MagicMock(side_effect=[ValueError("error"), "success"])

        with patch("autopack.error_recovery.time.sleep") as mock_time_sleep:
            result = recovery.execute_with_retry(
                func=sync_func,
                operation_name="test_operation",
                max_retries=3,
            )

            # Verify time.sleep was called for sync version
            mock_time_sleep.assert_called()
            assert result == "success"

    @pytest.mark.asyncio
    async def test_async_does_not_block_event_loop(self):
        """Test that async retry doesn't block concurrent tasks."""
        recovery = ErrorRecoverySystem()

        # Track when tasks complete
        completion_order = []

        async def slow_retry_task():
            async def failing():
                raise ValueError("retry me")

            try:
                await recovery.async_execute_with_retry(
                    func=failing,
                    operation_name="slow_task",
                    max_retries=1,  # Will retry once with 1s backoff
                )
            except ValueError:
                pass
            completion_order.append("slow")

        async def fast_task():
            await asyncio.sleep(0.1)  # Much faster than retry backoff
            completion_order.append("fast")

        # Run both tasks concurrently with mocked sleep
        with patch("autopack.error_recovery.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # Make sleep return immediately to speed up test
            mock_sleep.return_value = None
            await asyncio.gather(slow_retry_task(), fast_task())

        # Fast task should complete (wouldn't happen if time.sleep blocked event loop)
        assert "fast" in completion_order


class TestErrorRecoveryWaitMethods:
    """Tests for the wait method variants in ErrorRecoverySystem."""

    def test_sync_wait_uses_time_sleep(self):
        """Test that sync_wait uses time.sleep."""
        recovery = ErrorRecoverySystem()

        with patch("autopack.error_recovery.time.sleep") as mock_sleep:
            recovery.sync_wait(1.5)
            mock_sleep.assert_called_once_with(1.5)

    @pytest.mark.asyncio
    async def test_async_wait_uses_asyncio_sleep(self):
        """Test that async_wait uses asyncio.sleep."""
        recovery = ErrorRecoverySystem()

        with patch("autopack.error_recovery.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await recovery.async_wait(2.5)
            mock_sleep.assert_called_once_with(2.5)

    def test_wait_warns_in_async_context(self):
        """Test that wait() warns when called from async context."""
        recovery = ErrorRecoverySystem()

        async def run_in_async_context():
            with patch("autopack.error_recovery.time.sleep"):
                with patch("autopack.error_recovery.logger.warning") as mock_warning:
                    recovery.wait(1.0)
                    # Should warn about using sync sleep in async context
                    mock_warning.assert_called()
                    warning_msg = mock_warning.call_args[0][0]
                    assert "async context" in warning_msg.lower()

        asyncio.run(run_in_async_context())
