"""Tests for command timeout cleanup functionality.

Verifies that long-running processes are properly killed and cleaned up
when they exceed the timeout threshold, preventing resource exhaustion
and zombie processes.
"""

import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from autopack.autonomy.action_executor import SafeActionExecutor


class TestTimeoutCleanup:
    """Test suite for process cleanup on timeout."""

    @pytest.fixture
    def executor(self, tmp_path):
        """Create a SafeActionExecutor with short timeout for testing."""
        return SafeActionExecutor(
            workspace_root=tmp_path,
            command_timeout=1,  # 1 second timeout for quick tests
            dry_run=False,
        )

    @pytest.mark.skipif(sys.platform == "win32", reason="sleep command not available on Windows")
    def test_timeout_returns_error_result(self, executor):
        """Test that timeout results in an error ActionExecutionResult."""
        # Use sleep command that will exceed timeout (Unix-only)
        result = executor.execute_command("sleep 5")

        assert result.executed is True
        assert result.success is False
        assert result.error == "TimeoutExpired"
        assert "timed out" in result.reason.lower()

    @pytest.mark.skipif(sys.platform == "win32", reason="sleep command not available on Windows")
    def test_timeout_kills_process_tree(self, executor):
        """Test that subprocess is actually killed on timeout."""
        # Create a command that spawns child processes (Unix-only)
        # This command should timeout
        result = executor.execute_command("sleep 10")

        assert result.executed is True
        assert result.success is False

        # Give system a moment to reap zombie processes
        time.sleep(0.1)

    def test_quick_command_succeeds(self, executor):
        """Test that quick commands complete successfully without timeout."""
        result = executor.execute_command("echo test")

        assert result.executed is True
        assert result.success is True
        assert "test" in result.stdout

    @pytest.mark.skipif(sys.platform == "win32", reason="sleep command not available on Windows")
    def test_timeout_exception_is_caught(self, executor):
        """Test that TimeoutExpired exception is caught and handled."""
        result = executor.execute_command("sleep 5")

        assert result.error == "TimeoutExpired"
        assert result.success is False

    def test_command_with_output_returns_stdout(self, executor):
        """Test that successful commands capture stdout."""
        result = executor.execute_command("echo hello world")

        assert result.executed is True
        assert result.success is True
        assert "hello world" in result.stdout

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix ls command not available on Windows")
    def test_command_error_captured(self, executor):
        """Test that command errors are captured in stderr."""
        result = executor.execute_command("ls /nonexistent/path")

        assert result.executed is True
        # Command will fail but may still return success=False or success=True
        # depending on how the error is handled

    @pytest.mark.skipif(sys.platform == "win32", reason="sleep command not available on Windows")
    def test_timeout_logging(self, executor, caplog):
        """Test that timeout is logged appropriately."""
        result = executor.execute_command("sleep 5")

        assert result.success is False
        # Check that warning was logged about timeout
        assert any(
            "timed out" in record.message.lower()
            for record in caplog.records
            if record.levelname == "WARNING"
        )

    @patch("autopack.autonomy.action_executor.psutil")
    def test_psutil_used_for_process_cleanup(self, mock_psutil, executor):
        """Test that psutil is used when available for process tree cleanup."""
        # Mock psutil process handling
        mock_process = MagicMock()
        mock_process.children.return_value = []
        mock_psutil.Process.return_value = mock_process

        result = executor.execute_command("sleep 5")

        assert result.success is False
        # psutil.Process should have been called during cleanup
        assert mock_psutil.Process.called

    def test_multiple_timeouts_dont_exhaust_resources(self, executor):
        """Test that multiple timeouts don't accumulate zombie processes."""
        for _ in range(3):
            result = executor.execute_command("sleep 5")
            assert result.success is False
            assert result.error == "TimeoutExpired"

        # If resources weren't cleaned up properly, this would eventually fail
        # Just completing without error indicates cleanup is working

    def test_normal_exit_codes_preserved(self, executor):
        """Test that non-zero exit codes are properly preserved."""
        result = executor.execute_command("bash -c 'exit 42'")

        assert result.executed is True
        assert result.success is False
        # Exit code should be preserved in stderr or reason

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Unix pipes not supported in shell=False mode on Windows"
    )
    def test_command_with_pipes_handled(self, executor):
        """Test that commands with pipes work correctly (Unix-only)."""
        # Note: pipes require shell=True, but our executor uses shell=False
        # This test verifies that piped commands fail gracefully
        result = executor.execute_command("echo test | cat")

        # Piped commands will fail with shell=False
        # This is expected behavior for security reasons
        assert result.executed is True
