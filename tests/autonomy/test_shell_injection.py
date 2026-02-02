"""Test shell injection protection (IMP-SEC-002).

Verifies that shell=True is replaced with shlex.split() + shell=False
to prevent command injection attacks.
"""

import shlex
from unittest.mock import MagicMock, patch

from autopack.autonomy.action_executor import SafeActionExecutor
from autopack.maintenance_runner import run_tests


class TestShellInjectionBlocked:
    """Verify shell injection is blocked via shlex.split()."""

    def test_shlex_split_handles_semicolon_injection(self):
        """Verify shlex.split parses injection attempts as literal arguments."""
        # Attempt injection with semicolon
        malicious_command = "echo hello; rm -rf /"

        # shlex.split treats the entire string as arguments to echo
        args = shlex.split(malicious_command)

        # The semicolon becomes a literal argument, not a command separator
        assert args == ["echo", "hello;", "rm", "-rf", "/"]
        # "rm" is NOT executed as a separate command - it's an argument to echo

    def test_shlex_split_handles_pipe_injection(self):
        """Verify shlex.split parses pipe injection as literal argument."""
        malicious_command = "cat file.txt | rm -rf /"
        args = shlex.split(malicious_command)

        # Pipe becomes literal argument
        assert args == ["cat", "file.txt", "|", "rm", "-rf", "/"]

    def test_shlex_split_handles_backtick_injection(self):
        """Verify shlex.split parses backtick injection as literal argument."""
        malicious_command = "echo `rm -rf /`"
        args = shlex.split(malicious_command)

        # Backticks become literal argument
        assert args == ["echo", "`rm", "-rf", "/`"]

    def test_shlex_split_handles_dollar_paren_injection(self):
        """Verify shlex.split parses $() injection as literal argument."""
        malicious_command = "echo $(rm -rf /)"
        args = shlex.split(malicious_command)

        # $() becomes literal argument
        assert args == ["echo", "$(rm", "-rf", "/)"]

    def test_shlex_split_handles_ampersand_injection(self):
        """Verify shlex.split parses && injection as literal argument."""
        malicious_command = "echo hello && rm -rf /"
        args = shlex.split(malicious_command)

        # && becomes literal argument
        assert args == ["echo", "hello", "&&", "rm", "-rf", "/"]

    def test_shlex_split_preserves_quoted_arguments(self):
        """Verify shlex.split correctly handles quoted strings."""
        command = "echo \"hello world\" 'single quoted'"
        args = shlex.split(command)

        # Quoted strings are preserved as single arguments
        assert args == ["echo", "hello world", "single quoted"]


class TestSafeActionExecutorNoShellTrue:
    """Verify SafeActionExecutor uses shlex.split() instead of shell=True."""

    @patch("autopack.autonomy.action_executor.subprocess.Popen")
    def test_execute_command_uses_shlex_split(self, mock_popen, tmp_path):
        """Verify execute_command uses shlex.split() with shell=False."""
        # Mock subprocess.Popen to return a mock process
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("output", "")
        mock_proc.returncode = 0
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        executor = SafeActionExecutor(
            workspace_root=tmp_path,
            command_timeout=30,
            dry_run=False,
        )

        # Mock classify_action to return SAFE
        with patch("autopack.autonomy.action_executor.classify_action") as mock_classify:
            from autopack.autonomy.action_allowlist import ActionClassification

            mock_classify.return_value = ActionClassification.SAFE

            executor.execute_command("echo hello world")

            # Verify subprocess.Popen was called with shlex.split() args
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args

            # First positional arg should be the parsed command list
            assert call_args[0][0] == ["echo", "hello", "world"]

            # shell should be False
            assert call_args[1]["shell"] is False

    @patch("autopack.autonomy.action_executor.subprocess.Popen")
    def test_injection_attempt_becomes_literal_args(self, mock_popen, tmp_path):
        """Verify injection attempts become literal arguments."""
        # Mock subprocess.Popen to return a mock process
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("output", "")
        mock_proc.returncode = 0
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        executor = SafeActionExecutor(
            workspace_root=tmp_path,
            command_timeout=30,
            dry_run=False,
        )

        with patch("autopack.autonomy.action_executor.classify_action") as mock_classify:
            from autopack.autonomy.action_allowlist import ActionClassification

            mock_classify.return_value = ActionClassification.SAFE

            # Attempt injection
            executor.execute_command("echo hello; rm -rf /")

            # The command should be parsed as arguments, not executed with shell
            call_args = mock_popen.call_args
            assert call_args[0][0] == ["echo", "hello;", "rm", "-rf", "/"]
            assert call_args[1]["shell"] is False


class TestMaintenanceRunnerNoShellTrue:
    """Verify maintenance_runner uses shlex.split() instead of shell=True."""

    @patch("autopack.maintenance_runner.subprocess.run")
    def test_run_tests_uses_shlex_split(self, mock_run, tmp_path):
        """Verify run_tests uses shlex.split() with shell=False."""
        mock_run.return_value = MagicMock(returncode=0, stdout="output", stderr="")

        run_tests(["pytest tests/ -v"], workspace=tmp_path, timeout=60)

        # Verify subprocess.run was called with a list (not string)
        mock_run.assert_called_once()
        call_args = mock_run.call_args

        # First positional arg should be the parsed command list
        assert call_args[0][0] == ["pytest", "tests/", "-v"]

        # shell should be False
        assert call_args[1]["shell"] is False

    @patch("autopack.maintenance_runner.subprocess.run")
    def test_injection_blocked_in_test_commands(self, mock_run, tmp_path):
        """Verify injection in test commands becomes literal args."""
        mock_run.return_value = MagicMock(returncode=0, stdout="output", stderr="")

        # Attempt injection via test command
        run_tests(["pytest; rm -rf /"], workspace=tmp_path, timeout=60)

        call_args = mock_run.call_args
        # Semicolon becomes literal argument
        assert call_args[0][0] == ["pytest;", "rm", "-rf", "/"]
        assert call_args[1]["shell"] is False
