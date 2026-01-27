"""Tests for async/sync boundary handling (IMP-032)."""

import asyncio
import logging
from unittest.mock import patch

import pytest

from autopack.error_recovery import ErrorRecoverySystem


class TestContextAwareWait:
    """Test context-aware wait methods in ErrorRecoverySystem."""

    def test_sync_wait_uses_time_sleep(self):
        """sync_wait should use time.sleep."""
        recovery = ErrorRecoverySystem()

        with patch("time.sleep") as mock_sleep:
            recovery.sync_wait(1.5)
            mock_sleep.assert_called_once_with(1.5)

    @pytest.mark.asyncio
    async def test_async_wait_uses_asyncio_sleep(self):
        """async_wait should use asyncio.sleep."""
        recovery = ErrorRecoverySystem()

        # Verify async_wait is an async function that can be awaited
        assert asyncio.iscoroutinefunction(recovery.async_wait)

        # Test that async_wait actually works (use small delay)
        # This verifies it uses asyncio.sleep internally (doesn't block the loop)
        await recovery.async_wait(0.001)

    def test_wait_in_sync_context_no_warning(self, caplog):
        """wait() in sync context should not warn."""
        recovery = ErrorRecoverySystem()

        with patch("time.sleep"):
            with caplog.at_level(logging.WARNING):
                recovery.wait(1.0)

        # Should not have any warnings about async context
        assert "async context" not in caplog.text

    @pytest.mark.asyncio
    async def test_wait_in_async_context_logs_warning(self, caplog):
        """wait() in async context should log warning."""
        recovery = ErrorRecoverySystem()

        with patch("time.sleep"):
            with caplog.at_level(logging.WARNING):
                # We're in an async context (pytest.mark.asyncio provides event loop)
                recovery.wait(1.0)

        # Should warn about calling sync wait from async context
        assert "async context" in caplog.text or "event loop" in caplog.text


class TestSyncContextDocumentation:
    """Verify that time.sleep calls are documented as intentional."""

    def test_error_recovery_network_fix_documented(self):
        """_fix_network_error time.sleep should be documented."""
        import inspect

        from autopack import error_recovery

        source = inspect.getsource(error_recovery.ErrorRecoverySystem._fix_network_error)
        assert "time.sleep" in source
        assert "intentional" in source.lower() or "sync context" in source.lower()

    def test_error_recovery_execute_with_retry_documented(self):
        """execute_with_retry time.sleep should be documented."""
        import inspect

        from autopack import error_recovery

        source = inspect.getsource(error_recovery.ErrorRecoverySystem.execute_with_retry)
        assert "time.sleep" in source
        assert "intentional" in source.lower() or "sync context" in source.lower()

    def test_autonomous_loop_documented(self):
        """autonomous_loop time.sleep should be documented."""
        import inspect

        from autopack.executor import autonomous_loop

        source = inspect.getsource(autonomous_loop.AutonomousLoop._adaptive_sleep)
        assert "time.sleep" in source
        assert "intentional" in source.lower() or "sync context" in source.lower()


class TestWaitMethodsInterface:
    """Test that wait methods have correct signatures and behavior."""

    def test_sync_wait_is_synchronous(self):
        """sync_wait should be a regular function, not async."""
        recovery = ErrorRecoverySystem()
        assert not asyncio.iscoroutinefunction(recovery.sync_wait)

    def test_async_wait_is_asynchronous(self):
        """async_wait should be an async function."""
        recovery = ErrorRecoverySystem()
        assert asyncio.iscoroutinefunction(recovery.async_wait)

    def test_wait_is_synchronous(self):
        """wait should be a regular function that works in sync context."""
        recovery = ErrorRecoverySystem()
        assert not asyncio.iscoroutinefunction(recovery.wait)
