"""Contract tests for CustomRunner (PR-EXE-13).

Validates that the custom CI runner correctly executes custom commands,
handles timeouts, and persists logs.
"""

from pathlib import Path
from unittest.mock import Mock, patch
import subprocess
import pytest

from autopack.ci.custom_runner import CustomRunner, CustomCIResult


class TestCustomRunner:
    """Test suite for CustomRunner contract."""

    @pytest.fixture
    def runner(self, tmp_path):
        """Create custom runner instance."""
        run_id = "test-run-123"
        return CustomRunner(workspace=tmp_path, run_id=run_id)

    def test_successful_custom_command(self, runner, tmp_path):
        """Test successful custom command execution."""
        ci_spec = {
            "command": "echo 'Tests passed'",
            "timeout": 300,
        }

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Tests passed"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = runner.run("phase-1", ci_spec)

        assert result.passed is True
        assert result.status == "passed"
        assert result.message == "CI command succeeded"
        assert result.skipped is False

    def test_failed_custom_command(self, runner, tmp_path):
        """Test failed custom command execution."""
        ci_spec = {
            "command": "exit 1",
            "timeout": 300,
        }

        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error occurred"

        with patch("subprocess.run", return_value=mock_result):
            result = runner.run("phase-1", ci_spec)

        assert result.passed is False
        assert result.status == "failed"
        assert "failed" in result.message.lower()
        assert result.error is not None
        assert "Exit code 1" in result.error

    def test_command_timeout(self, runner, tmp_path):
        """Test custom command timeout handling."""
        ci_spec = {
            "command": "sleep 1000",
            "timeout": 5,
        }

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("sleep", 5)):
            result = runner.run("phase-1", ci_spec)

        assert result.passed is False
        assert result.status == "failed"
        assert "timed out" in result.message.lower()
        assert result.error is not None

    def test_missing_command_skips(self, runner, tmp_path):
        """Test missing command results in skip."""
        ci_spec = {
            "timeout": 300,
            # No command specified
        }

        result = runner.run("phase-1", ci_spec)

        assert result.skipped is True
        assert result.status == "skipped"
        assert result.passed is True
        assert "not configured" in result.message.lower()

    def test_ci_log_persistence(self, runner, tmp_path):
        """Test CI log is persisted to disk."""
        ci_spec = {
            "command": "echo 'Test output'",
            "timeout": 300,
        }

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Test output"
        mock_result.stderr = "Warning message"

        with patch("subprocess.run", return_value=mock_result):
            result = runner.run("phase-1", ci_spec)

        # Check log was persisted
        assert result.report_path is not None
        log_path = Path(result.report_path)
        assert log_path.exists()
        log_content = log_path.read_text(encoding="utf-8")
        assert "Test output" in log_content
        assert "Warning message" in log_content

    def test_custom_success_message(self, runner, tmp_path):
        """Test custom success message is used."""
        ci_spec = {
            "command": "echo 'ok'",
            "success_message": "All checks passed!",
            "timeout": 300,
        }

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "ok"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = runner.run("phase-1", ci_spec)

        assert result.passed is True
        assert result.message == "All checks passed!"
