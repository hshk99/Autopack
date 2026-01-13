"""Contract tests for ExecuteFixHandler (PR-EXE-13).

Validates that the execute fix handler correctly executes automated fixes,
validates commands, and handles security constraints.
"""

from unittest.mock import Mock, patch
import pytest
import sys

# Patch the incorrect import in execute_fix_handler.py before importing it
# The source file incorrectly imports from autopack.checkpoint instead of autopack.executor
import autopack.executor.run_checkpoint
sys.modules['autopack.checkpoint'] = type(sys)('autopack.checkpoint')
sys.modules['autopack.checkpoint.run_checkpoint'] = autopack.executor.run_checkpoint

from autopack.executor.execute_fix_handler import ExecuteFixHandler  # noqa: E402


class MockDoctorResponse:
    """Mock Doctor response for testing."""

    def __init__(self, fix_commands=None, fix_type="file", verify_command=None, builder_hint=None):
        self.fix_commands = fix_commands or []
        self.fix_type = fix_type
        self.verify_command = verify_command
        self.builder_hint = builder_hint


class TestExecuteFixHandler:
    """Test suite for ExecuteFixHandler contract."""

    @pytest.fixture
    def mock_executor(self, tmp_path):
        """Create a mock executor."""
        executor = Mock()
        executor.workspace = tmp_path
        executor.run_id = "test-run-123"
        executor.run_type = "project_build"
        executor._allow_execute_fix = True
        executor._execute_fix_by_phase = {}
        executor._builder_hint_by_phase = {}
        executor._update_phase_status = Mock()
        return executor

    @pytest.fixture
    def handler(self, mock_executor):
        """Create handler instance."""
        return ExecuteFixHandler(mock_executor)

    def test_successful_fix_execution(self, handler, mock_executor):
        """Test successful fix execution."""
        phase = {"phase_id": "phase-1"}
        response = MockDoctorResponse(
            fix_commands=["rm -f temp.txt"],
            fix_type="file"
        )

        mock_subprocess_result = Mock()
        mock_subprocess_result.returncode = 0
        mock_subprocess_result.stdout = "Clean working directory"
        mock_subprocess_result.stderr = ""

        with patch("subprocess.run", return_value=mock_subprocess_result):
            with patch("autopack.executor.execute_fix_handler.create_execute_fix_checkpoint"):
                result = handler.execute_fix(phase, response)

        assert result.action_taken == "execute_fix_success"
        assert result.should_continue_retry is True
        assert mock_executor._execute_fix_by_phase["phase-1"] == 1

    def test_failed_fix_execution(self, handler, mock_executor):
        """Test failed fix execution."""
        phase = {"phase_id": "phase-1"}
        response = MockDoctorResponse(
            fix_commands=["rm -f temp2.txt"],
            fix_type="file"
        )

        mock_subprocess_result = Mock()
        mock_subprocess_result.returncode = 1
        mock_subprocess_result.stdout = ""
        mock_subprocess_result.stderr = "Error"

        with patch("subprocess.run", return_value=mock_subprocess_result):
            with patch("autopack.executor.execute_fix_handler.create_execute_fix_checkpoint"):
                result = handler.execute_fix(phase, response)

        assert result.action_taken == "execute_fix_failed"
        assert result.should_continue_retry is False
        mock_executor._update_phase_status.assert_called_once_with("phase-1", "FAILED")

    def test_disabled_execute_fix(self, handler, mock_executor):
        """Test behavior when execute_fix is disabled."""
        mock_executor._allow_execute_fix = False
        phase = {"phase_id": "phase-1"}
        response = MockDoctorResponse(
            fix_commands=["rm -f temp3.txt"],
            fix_type="file"
        )

        result = handler.execute_fix(phase, response)

        assert result.action_taken == "execute_fix_disabled"
        assert result.should_continue_retry is True

    def test_command_validation_git_allowed(self, handler):
        """Test validation allows whitelisted git commands."""
        commands = [
            "git checkout main",
            "git reset --hard HEAD",
            "git status --porcelain",
        ]

        is_valid, errors = handler._validate_fix_commands(commands, "git")

        assert is_valid is True
        assert len(errors) == 0

    def test_command_validation_git_disallowed(self, handler):
        """Test validation blocks non-whitelisted git commands."""
        commands = ["git push --force"]

        is_valid, errors = handler._validate_fix_commands(commands, "git")

        assert is_valid is False
        assert len(errors) > 0

    def test_command_validation_banned_metacharacters(self, handler):
        """Test validation blocks banned metacharacters."""
        commands = ["git status && rm -rf /"]

        is_valid, errors = handler._validate_fix_commands(commands, "git")

        assert is_valid is False
        assert any("metacharacter" in error.lower() for error in errors)

    def test_command_validation_banned_prefixes(self, handler):
        """Test validation blocks banned command prefixes."""
        commands = ["sudo git status"]

        is_valid, errors = handler._validate_fix_commands(commands, "git")

        assert is_valid is False
        assert any("banned prefix" in error.lower() for error in errors)

    def test_git_blocked_for_project_build(self, handler, mock_executor):
        """Test git execute_fix is blocked for project_build runs."""
        mock_executor.run_type = "project_build"
        phase = {"phase_id": "phase-1"}
        response = MockDoctorResponse(
            fix_commands=["git reset --hard HEAD"],
            fix_type="git"
        )

        result = handler.execute_fix(phase, response)

        assert result.action_taken == "execute_fix_blocked_git_project_build"
        assert result.should_continue_retry is True

    def test_verify_command_success(self, handler, mock_executor):
        """Test successful verify command execution."""
        phase = {"phase_id": "phase-1"}
        response = MockDoctorResponse(
            fix_commands=["rm -f verify.txt"],
            fix_type="file",
            verify_command="rm -f verify2.txt"
        )

        mock_subprocess_result = Mock()
        mock_subprocess_result.returncode = 0
        mock_subprocess_result.stdout = "OK"
        mock_subprocess_result.stderr = ""

        with patch("subprocess.run", return_value=mock_subprocess_result):
            with patch("autopack.executor.execute_fix_handler.create_execute_fix_checkpoint"):
                result = handler.execute_fix(phase, response)

        assert result.action_taken == "execute_fix_success"
        assert result.should_continue_retry is True

    def test_per_phase_limit(self, handler, mock_executor):
        """Test execute_fix respects per-phase limit."""
        mock_executor._execute_fix_by_phase["phase-1"] = 1  # Already at limit

        phase = {"phase_id": "phase-1"}
        response = MockDoctorResponse(
            fix_commands=["rm -f limit.txt"],
            fix_type="file"
        )

        result = handler.execute_fix(phase, response)

        assert result.action_taken == "execute_fix_limit"
        assert result.should_continue_retry is False
        mock_executor._update_phase_status.assert_called_once_with("phase-1", "FAILED")
