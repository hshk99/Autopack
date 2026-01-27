"""Tests for APIServerLifecycle (IMP-QUAL-003).

Tests verify that file handles are properly closed using try/finally pattern
to prevent resource leaks when starting the API server.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestAPIServerLifecycleFileHandleCleanup:
    """Test suite for file handle cleanup in APIServerLifecycle."""

    @pytest.fixture
    def mock_executor(self, tmp_path):
        """Create a mock executor with minimal required attributes."""
        executor = MagicMock()
        executor.api_url = "http://localhost:8000"
        executor.workspace = str(tmp_path)
        executor.run_id = "test-run-123"
        executor.api_client = MagicMock()
        return executor

    def test_file_handle_closed_on_subprocess_success(self, mock_executor, tmp_path):
        """Verify file handle is closed after subprocess successfully inherits it."""
        from autopack.api.server_lifecycle import APIServerLifecycle

        lifecycle = APIServerLifecycle(mock_executor)

        # Create diagnostics directory
        log_dir = tmp_path / ".autonomous_runs" / "test-run-123" / "diagnostics"
        log_dir.mkdir(parents=True, exist_ok=True)

        mock_process = MagicMock()
        mock_process.poll.return_value = None

        # Track if close was called on the file handle
        close_called = []
        original_open = open

        def tracking_open(*args, **kwargs):
            f = original_open(*args, **kwargs)
            original_close = f.close

            def tracked_close():
                close_called.append(True)
                return original_close()

            f.close = tracked_close
            return f

        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch("builtins.open", tracking_open),
        ):
            # Mock health check to succeed immediately
            mock_executor.api_client.check_health.return_value = {"status": "healthy"}

            lifecycle.start_server("127.0.0.1", 8000)

        # File handle should have been closed in the finally block
        assert len(close_called) >= 1, "File handle close() was not called"
        assert lifecycle.log_file_handle is None, "log_file_handle should be None after cleanup"

    def test_file_handle_closed_on_subprocess_failure(self, mock_executor, tmp_path):
        """Verify file handle is closed even when subprocess creation fails."""
        from autopack.api.server_lifecycle import APIServerLifecycle

        lifecycle = APIServerLifecycle(mock_executor)

        # Create diagnostics directory
        log_dir = tmp_path / ".autonomous_runs" / "test-run-123" / "diagnostics"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Track if close was called on the file handle
        close_called = []
        original_open = open

        def tracking_open(*args, **kwargs):
            f = original_open(*args, **kwargs)
            original_close = f.close

            def tracked_close():
                close_called.append(True)
                return original_close()

            f.close = tracked_close
            return f

        with (
            patch("subprocess.Popen", side_effect=OSError("Subprocess creation failed")),
            patch("builtins.open", tracking_open),
        ):
            result = lifecycle.start_server("127.0.0.1", 8000)

        # File handle should have been closed in the finally block even on failure
        assert len(close_called) >= 1, "File handle close() was not called on failure"
        assert lifecycle.log_file_handle is None, "log_file_handle should be None after cleanup"
        assert result is False, "start_server should return False on failure"

    def test_file_handle_not_leaked_when_open_fails(self, mock_executor, tmp_path):
        """Verify no leak when file open itself fails."""
        from autopack.api.server_lifecycle import APIServerLifecycle

        lifecycle = APIServerLifecycle(mock_executor)

        mock_process = MagicMock()
        mock_process.poll.return_value = None

        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch("builtins.open", side_effect=PermissionError("Cannot open file")),
        ):
            mock_executor.api_client.check_health.return_value = {"status": "healthy"}
            lifecycle.start_server("127.0.0.1", 8000)

        # Should not crash and log_file_handle should be None
        assert lifecycle.log_file_handle is None

    def test_log_file_handle_reset_to_none_in_finally(self, mock_executor, tmp_path):
        """Verify log_file_handle is always set to None in finally block."""
        from autopack.api.server_lifecycle import APIServerLifecycle

        lifecycle = APIServerLifecycle(mock_executor)

        # Create diagnostics directory
        log_dir = tmp_path / ".autonomous_runs" / "test-run-123" / "diagnostics"
        log_dir.mkdir(parents=True, exist_ok=True)

        mock_process = MagicMock()
        mock_process.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            mock_executor.api_client.check_health.return_value = {"status": "healthy"}
            lifecycle.start_server("127.0.0.1", 8000)

        # Verify cleanup happened
        assert lifecycle.log_file_handle is None, (
            "log_file_handle should be None after start_server completes"
        )
