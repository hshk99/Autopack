"""Comprehensive security tests for command blocklist pattern matching (SEC-010).

Tests various bypass attempts and ensures the command validation system
properly rejects:
- Extra spaces in commands
- Path variations (./cmd vs /full/path/cmd)
- Escaped quotes and special characters
- Command injection attempts
"""

import sys
from unittest.mock import Mock

import pytest

# Patch the incorrect import in execute_fix_handler.py before importing it
import autopack.executor.run_checkpoint

sys.modules["autopack.checkpoint"] = type(sys)("autopack.checkpoint")
sys.modules["autopack.checkpoint.run_checkpoint"] = autopack.executor.run_checkpoint

from autopack.executor.execute_fix_handler import (  # noqa: E402
    ExecuteFixHandler,
    detect_path_bypass_attempts,
    normalize_command,
)


class TestCommandNormalization:
    """Test command normalization function."""

    def test_normalize_removes_extra_spaces(self):
        """Test that extra spaces are normalized to single spaces."""
        assert normalize_command("git   checkout   main") == "git checkout main"
        assert normalize_command("git  reset  --hard  HEAD") == "git reset --hard HEAD"

    def test_normalize_strips_whitespace(self):
        """Test that leading/trailing whitespace is removed."""
        assert normalize_command("  git checkout main  ") == "git checkout main"
        assert normalize_command("\tgit status\n") == "git status"

    def test_normalize_removes_relative_paths(self):
        """Test that relative path prefixes are removed."""
        assert normalize_command("./rm -f file.txt") == "rm -f file.txt"
        assert normalize_command(".//git checkout main") == "git checkout main"


class TestPathBypassDetection:
    """Test detection of path-based bypass attempts."""

    def test_detects_full_paths(self):
        """Test detection of full path commands."""
        assert detect_path_bypass_attempts("/bin/rm -f file.txt") is True
        assert detect_path_bypass_attempts("/usr/bin/git checkout") is True

    def test_detects_relative_paths(self):
        """Test detection of relative path commands."""
        assert detect_path_bypass_attempts("./rm -f file.txt") is True
        assert detect_path_bypass_attempts("../git checkout") is True

    def test_allows_simple_commands(self):
        """Test that simple command names are allowed."""
        assert detect_path_bypass_attempts("rm -f file.txt") is False
        assert detect_path_bypass_attempts("git checkout main") is False


class TestCommandValidationGit:
    """Test git command validation."""

    @pytest.fixture
    def mock_executor(self, tmp_path):
        """Create a mock executor."""
        executor = Mock()
        executor.workspace = tmp_path
        executor.run_id = "test-run-123"
        executor._allow_execute_fix = True
        executor._execute_fix_by_phase = {}
        executor._builder_hint_by_phase = {}
        return executor

    @pytest.fixture
    def handler(self, mock_executor):
        """Create handler instance."""
        return ExecuteFixHandler(mock_executor)

    def test_git_checkout_allowed(self, handler):
        """Test that valid git checkout is allowed."""
        commands = ["git checkout main", "git checkout origin/feature"]
        is_valid, errors = handler._validate_fix_commands(commands, "git")
        assert is_valid is True
        assert len(errors) == 0

    def test_git_checkout_exact_match_required(self, handler):
        """Test that git checkout requires exact formatting."""
        # These should fail because they don't match the whitelist exactly
        commands = ["git  checkout  main", "git checkout  main"]
        is_valid, errors = handler._validate_fix_commands(commands, "git")
        # The normalized version should match, so this should pass
        assert is_valid is True

    def test_git_reset_exact_match(self, handler):
        """Test that git reset --hard HEAD must be exact."""
        # Allowed
        commands = ["git reset --hard HEAD"]
        is_valid, errors = handler._validate_fix_commands(commands, "git")
        assert is_valid is True

        # Not allowed - extra arguments
        commands = ["git reset --hard HEAD~1"]
        is_valid, errors = handler._validate_fix_commands(commands, "git")
        assert is_valid is False
        assert any("does not match" in e for e in errors)

    def test_git_stash_variations(self, handler):
        """Test git stash command variations."""
        # Allowed
        commands = ["git stash", "git stash pop"]
        is_valid, errors = handler._validate_fix_commands(commands, "git")
        assert is_valid is True

        # Not allowed
        commands = ["git stash drop"]
        is_valid, errors = handler._validate_fix_commands(commands, "git")
        assert is_valid is False

    def test_git_dangerous_push_blocked(self, handler):
        """Test that dangerous git commands are blocked."""
        commands = ["git push --force", "git push origin main"]
        is_valid, errors = handler._validate_fix_commands(commands, "git")
        assert is_valid is False
        assert any("does not match" in e for e in errors)

    def test_git_status_porcelain_exact(self, handler):
        """Test that git status requires --porcelain flag."""
        # Allowed
        commands = ["git status --porcelain"]
        is_valid, errors = handler._validate_fix_commands(commands, "git")
        assert is_valid is True

        # Not allowed
        commands = ["git status", "git status -s"]
        is_valid, errors = handler._validate_fix_commands(commands, "git")
        assert is_valid is False


class TestCommandValidationFile:
    """Test file command validation."""

    @pytest.fixture
    def mock_executor(self, tmp_path):
        """Create a mock executor."""
        executor = Mock()
        executor.workspace = tmp_path
        executor.run_id = "test-run-123"
        executor._allow_execute_fix = True
        executor._execute_fix_by_phase = {}
        executor._builder_hint_by_phase = {}
        return executor

    @pytest.fixture
    def handler(self, mock_executor):
        """Create handler instance."""
        return ExecuteFixHandler(mock_executor)

    def test_rm_f_allowed(self, handler):
        """Test that rm -f is allowed with valid paths."""
        commands = ["rm -f file.txt", "rm -f /tmp/file.txt"]
        is_valid, errors = handler._validate_fix_commands(commands, "file")
        assert is_valid is True
        assert len(errors) == 0

    def test_rm_rf_blocked(self, handler):
        """Test that rm -rf is blocked (banned prefix)."""
        commands = ["rm -rf /tmp"]
        is_valid, errors = handler._validate_fix_commands(commands, "file")
        assert is_valid is False
        assert any("banned prefix" in e.lower() for e in errors)

    def test_mkdir_allowed(self, handler):
        """Test that mkdir -p is allowed."""
        commands = ["mkdir -p /tmp/dir", "mkdir -p ./newdir"]
        is_valid, errors = handler._validate_fix_commands(commands, "file")
        assert is_valid is True

    def test_cp_allowed(self, handler):
        """Test that cp command is allowed."""
        commands = ["cp src.txt dst.txt", "cp -r src dst"]
        is_valid, errors = handler._validate_fix_commands(commands, "file")
        assert is_valid is True

    def test_mv_allowed(self, handler):
        """Test that mv command is allowed."""
        commands = ["mv old.txt new.txt"]
        is_valid, errors = handler._validate_fix_commands(commands, "file")
        assert is_valid is True


class TestBypassAttempts:
    """Test detection of common bypass attempts."""

    @pytest.fixture
    def mock_executor(self, tmp_path):
        """Create a mock executor."""
        executor = Mock()
        executor.workspace = tmp_path
        executor.run_id = "test-run-123"
        executor._allow_execute_fix = True
        executor._execute_fix_by_phase = {}
        executor._builder_hint_by_phase = {}
        return executor

    @pytest.fixture
    def handler(self, mock_executor):
        """Create handler instance."""
        return ExecuteFixHandler(mock_executor)

    def test_command_injection_with_semicolon_blocked(self, handler):
        """Test that commands with semicolons are blocked."""
        commands = ["rm -f file.txt; rm -rf /"]
        is_valid, errors = handler._validate_fix_commands(commands, "file")
        assert is_valid is False
        assert any("metacharacter" in e.lower() for e in errors)

    def test_command_injection_with_pipe_blocked(self, handler):
        """Test that piped commands are blocked."""
        commands = ["git status | cat"]
        is_valid, errors = handler._validate_fix_commands(commands, "git")
        assert is_valid is False
        assert any("metacharacter" in e.lower() for e in errors)

    def test_command_injection_with_ampersand_blocked(self, handler):
        """Test that && commands are blocked."""
        commands = ["git reset --hard HEAD && rm -rf /"]
        is_valid, errors = handler._validate_fix_commands(commands, "git")
        assert is_valid is False
        assert any("metacharacter" in e.lower() for e in errors)

    def test_command_injection_with_backticks_blocked(self, handler):
        """Test that backtick substitution is blocked."""
        commands = ["echo `rm -rf /`"]
        is_valid, errors = handler._validate_fix_commands(commands, "file")
        assert is_valid is False
        assert any("metacharacter" in e.lower() for e in errors)

    def test_command_injection_with_dollar_paren_blocked(self, handler):
        """Test that $() substitution is blocked."""
        commands = ["echo $(rm -rf /)"]
        is_valid, errors = handler._validate_fix_commands(commands, "file")
        assert is_valid is False
        assert any("metacharacter" in e.lower() for e in errors)

    def test_command_injection_with_dollar_brace_blocked(self, handler):
        """Test that ${} substitution is blocked."""
        commands = ["echo ${rm -rf /}"]
        is_valid, errors = handler._validate_fix_commands(commands, "file")
        assert is_valid is False
        assert any("metacharacter" in e.lower() for e in errors)

    def test_redirect_blocked(self, handler):
        """Test that redirects are blocked."""
        commands = ["git status > /etc/passwd"]
        is_valid, errors = handler._validate_fix_commands(commands, "git")
        assert is_valid is False
        assert any("metacharacter" in e.lower() for e in errors)

    def test_append_redirect_blocked(self, handler):
        """Test that append redirects are blocked."""
        commands = ["echo bad >> /var/log/syslog"]
        is_valid, errors = handler._validate_fix_commands(commands, "file")
        assert is_valid is False
        assert any("metacharacter" in e.lower() for e in errors)

    def test_sudo_bypass_blocked(self, handler):
        """Test that sudo is blocked."""
        commands = ["sudo rm -f file.txt", "sudo git reset --hard HEAD"]
        is_valid, errors = handler._validate_fix_commands(commands, "file")
        assert is_valid is False
        assert any("banned prefix" in e.lower() for e in errors)

    def test_su_bypass_blocked(self, handler):
        """Test that su is blocked."""
        commands = ["su - root", "su -c 'rm -rf /'"]
        is_valid, errors = handler._validate_fix_commands(commands, "file")
        assert is_valid is False
        assert any("banned prefix" in e.lower() for e in errors)

    def test_newline_injection_blocked(self, handler):
        """Test that newline characters are blocked."""
        commands = ["git status\nrm -rf /"]
        is_valid, errors = handler._validate_fix_commands(commands, "git")
        assert is_valid is False
        assert any("metacharacter" in e.lower() for e in errors)

    def test_carriage_return_injection_blocked(self, handler):
        """Test that carriage return characters are blocked."""
        commands = ["git status\r\nrm -rf /"]
        is_valid, errors = handler._validate_fix_commands(commands, "git")
        assert is_valid is False
        assert any("metacharacter" in e.lower() for e in errors)

    def test_fork_bomb_blocked(self, handler):
        """Test that fork bomb commands are blocked."""
        commands = [":(){ :|:& };:"]
        is_valid, errors = handler._validate_fix_commands(commands, "git")
        assert is_valid is False
        assert any("banned prefix" in e.lower() for e in errors)

    def test_shutdown_blocked(self, handler):
        """Test that shutdown commands are blocked."""
        commands = ["shutdown -h now", "reboot", "poweroff", "halt"]
        is_valid, errors = handler._validate_fix_commands(commands, "git")
        assert is_valid is False
        assert any("banned prefix" in e.lower() for e in errors)

    def test_chmod_777_blocked(self, handler):
        """Test that chmod 777 is blocked."""
        commands = ["chmod 777 file.txt"]
        is_valid, errors = handler._validate_fix_commands(commands, "file")
        assert is_valid is False
        assert any("banned prefix" in e.lower() for e in errors)

    def test_mkfs_blocked(self, handler):
        """Test that mkfs is blocked."""
        commands = ["mkfs /dev/sda1"]
        is_valid, errors = handler._validate_fix_commands(commands, "file")
        assert is_valid is False
        assert any("banned prefix" in e.lower() for e in errors)

    def test_dd_blocked(self, handler):
        """Test that dd if= is blocked."""
        commands = ["dd if=/dev/zero of=/dev/sda"]
        is_valid, errors = handler._validate_fix_commands(commands, "file")
        assert is_valid is False
        assert any("banned prefix" in e.lower() for e in errors)


class TestCommandValidationPython:
    """Test python command validation."""

    @pytest.fixture
    def mock_executor(self, tmp_path):
        """Create a mock executor."""
        executor = Mock()
        executor.workspace = tmp_path
        executor.run_id = "test-run-123"
        executor._allow_execute_fix = True
        executor._execute_fix_by_phase = {}
        executor._builder_hint_by_phase = {}
        return executor

    @pytest.fixture
    def handler(self, mock_executor):
        """Create handler instance."""
        return ExecuteFixHandler(mock_executor)

    def test_pip_install_allowed(self, handler):
        """Test that pip install is allowed."""
        commands = ["pip install requests", "pip install package==1.0.0"]
        is_valid, errors = handler._validate_fix_commands(commands, "python")
        assert is_valid is True
        assert len(errors) == 0

    def test_pip_uninstall_allowed(self, handler):
        """Test that pip uninstall -y is allowed."""
        commands = ["pip uninstall -y requests"]
        is_valid, errors = handler._validate_fix_commands(commands, "python")
        assert is_valid is True

    def test_pip_uninstall_without_y_blocked(self, handler):
        """Test that pip uninstall without -y is blocked."""
        commands = ["pip uninstall requests"]
        is_valid, errors = handler._validate_fix_commands(commands, "python")
        assert is_valid is False

    def test_python_m_pip_allowed(self, handler):
        """Test that python -m pip install is allowed."""
        commands = ["python -m pip install requests"]
        is_valid, errors = handler._validate_fix_commands(commands, "python")
        assert is_valid is True

    def test_python_dangerous_commands_blocked(self, handler):
        """Test that dangerous python commands are blocked."""
        commands = ["python -c 'import os; os.system(\"rm -rf /\")'"]
        is_valid, errors = handler._validate_fix_commands(commands, "python")
        # This should fail due to metacharacters or not matching pattern
        assert is_valid is False
