"""
Tests for CI Runner Module

Tests for pytest execution and CI output parsing (IMP-ARCH-007).
Verifies pytest execution, output parsing, and log persistence.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch


from autopack.executor.ci_runner import (
    parse_pytest_counts,
    persist_ci_log,
    run_custom_ci,
    run_pytest_ci,
    trim_ci_output,
)


class TestParsePytestCounts:
    """Tests for parse_pytest_counts function."""

    def test_parse_all_passed(self):
        """Verify parsing of all passed tests."""
        output = "===== 5 passed in 0.01s ====="
        passed, failed, error = parse_pytest_counts(output)

        assert passed == 5
        assert failed == 0
        assert error == 0

    def test_parse_failed_and_passed(self):
        """Verify parsing of mixed passed and failed."""
        output = "===== 3 failed, 2 passed in 1.2s ====="
        passed, failed, error = parse_pytest_counts(output)

        assert passed == 2
        assert failed == 3
        assert error == 0

    def test_parse_with_errors(self):
        """Verify parsing with test errors."""
        output = "===== 1 error, 1 passed ====="
        passed, failed, error = parse_pytest_counts(output)

        assert passed == 1
        assert failed == 0
        assert error == 1

    def test_parse_collection_errors(self):
        """Verify parsing of collection errors."""
        output = "===== 2 errors during collection ====="
        passed, failed, error = parse_pytest_counts(output)

        assert passed == 0
        assert failed == 0
        assert error == 2

    def test_parse_all_failed(self):
        """Verify parsing of all failed tests."""
        output = "===== 5 failed in 0.05s ====="
        passed, failed, error = parse_pytest_counts(output)

        assert passed == 0
        assert failed == 5
        assert error == 0

    def test_parse_multiline_output(self):
        """Verify parsing of multiline output."""
        output = """
        FAILED test_module.py::test_func1 - AssertionError
        FAILED test_module.py::test_func2 - ValueError

        ===== 2 failed, 3 passed in 0.5s =====
        """
        passed, failed, error = parse_pytest_counts(output)

        assert passed == 3
        assert failed == 2
        assert error == 0

    def test_parse_empty_output(self):
        """Verify parsing of empty output."""
        output = ""
        passed, failed, error = parse_pytest_counts(output)

        assert passed == 0
        assert failed == 0
        assert error == 0

    def test_parse_no_test_marker(self):
        """Verify parsing when no tests run."""
        output = "===== no tests ran ====="
        passed, failed, error = parse_pytest_counts(output)

        assert passed == 0
        assert failed == 0
        assert error == 0

    def test_parse_case_insensitive(self):
        """Verify parsing is case-insensitive."""
        output = "===== 5 PASSED in 0.01s ====="
        passed, failed, error = parse_pytest_counts(output)

        assert passed == 5

    def test_parse_plural_and_singular_forms(self):
        """Verify parsing handles both plural and singular."""
        output1 = "===== 1 passed ====="
        passed, failed, error = parse_pytest_counts(output1)
        assert passed == 1

        output2 = "===== 1 error during collection ====="
        passed, failed, error = parse_pytest_counts(output2)
        assert error == 1

    def test_parse_complex_output(self):
        """Verify parsing of complex pytest output."""
        output = """
        tests/test_module1.py::test_func1 PASSED [10%]
        tests/test_module1.py::test_func2 FAILED [20%]
        tests/test_module2.py::test_func3 ERROR [30%]

        ===== 1 failed, 1 error, 1 passed in 2.5s =====
        """
        passed, failed, error = parse_pytest_counts(output)

        assert passed == 1
        assert failed == 1
        assert error == 1

    def test_parse_handles_whitespace(self):
        """Verify parsing handles various whitespace."""
        outputs = [
            "===== 5  passed  in 0.01s =====",
            "=====5 passed in 0.01s=====",
            "===== 5 passed in 0.01s=====",
        ]
        for output in outputs:
            passed, failed, error = parse_pytest_counts(output)
            assert passed == 5

    def test_parse_multiple_result_lines(self):
        """Verify last result line takes precedence."""
        output = """
        ===== 5 passed in 0.1s =====
        ===== 3 passed, 2 failed in 0.2s =====
        """
        passed, failed, error = parse_pytest_counts(output)

        # Should have the values from the last line
        assert passed == 3
        assert failed == 2


class TestTrimCiOutput:
    """Tests for trim_ci_output function."""

    def test_output_under_limit(self):
        """Verify output under limit is not trimmed."""
        output = "Test output" * 100  # Small output
        trimmed = trim_ci_output(output, limit=10000)

        assert trimmed == output

    def test_output_at_limit(self):
        """Verify output at exact limit is not trimmed."""
        output = "x" * 10000
        trimmed = trim_ci_output(output, limit=10000)

        assert trimmed == output

    def test_output_exceeds_limit(self):
        """Verify output exceeding limit is trimmed."""
        output = "x" * 20000
        trimmed = trim_ci_output(output, limit=10000)

        assert len(trimmed) < len(output)
        assert "... (truncated) ..." in trimmed

    def test_trimmed_preserves_first_half(self):
        """Verify trimmed output preserves first half."""
        output = "FIRST" * 2000 + "MIDDLE" * 2000 + "LAST" * 2000
        trimmed = trim_ci_output(output, limit=10000)

        assert "FIRST" in trimmed

    def test_trimmed_preserves_last_half(self):
        """Verify trimmed output preserves last half."""
        output = "FIRST" * 2000 + "MIDDLE" * 2000 + "LAST" * 2000
        trimmed = trim_ci_output(output, limit=10000)

        assert "LAST" in trimmed

    def test_trim_with_small_limit(self):
        """Verify trimming with very small limit."""
        output = "Test output" * 1000
        trimmed = trim_ci_output(output, limit=100)

        assert len(trimmed) <= len(output)
        assert "... (truncated) ..." in trimmed

    def test_trim_with_large_limit(self):
        """Verify trimming with large limit."""
        output = "Test output" * 100
        trimmed = trim_ci_output(output, limit=1000000)

        assert trimmed == output

    def test_trim_empty_output(self):
        """Verify trimming empty output."""
        output = ""
        trimmed = trim_ci_output(output, limit=10000)

        assert trimmed == ""

    def test_trim_truncation_indicator_format(self):
        """Verify truncation indicator is properly formatted."""
        output = "x" * 20000
        trimmed = trim_ci_output(output, limit=10000)

        assert "\n\n... (truncated) ...\n\n" in trimmed


class TestPersistCiLog:
    """Tests for persist_ci_log function."""

    def test_persist_creates_log_file(self):
        """Verify log file is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            log_path = persist_ci_log(
                log_name="test.log",
                content="Test content",
                phase_id="phase1",
                workspace=workspace,
                run_id="run123",
            )

            assert log_path is not None
            assert log_path.exists()
            assert log_path.read_text() == "Test content"

    def test_persist_creates_directory_structure(self):
        """Verify directory structure is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            persist_ci_log(
                log_name="test.log",
                content="Test",
                phase_id="phase1",
                workspace=workspace,
                run_id="run123",
            )

            expected_dir = workspace / ".autonomous_runs" / "run123" / "ci"
            assert expected_dir.exists()

    def test_persist_writes_content_correctly(self):
        """Verify content is written correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            content = "This is test content\nWith multiple lines\n"

            log_path = persist_ci_log(
                log_name="test.log",
                content=content,
                phase_id="phase1",
                workspace=workspace,
                run_id="run123",
            )

            assert log_path.read_text() == content

    def test_persist_overwrites_existing_file(self):
        """Verify existing file is overwritten."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create first log
            log_path1 = persist_ci_log(
                log_name="test.log",
                content="First content",
                phase_id="phase1",
                workspace=workspace,
                run_id="run123",
            )

            # Create second log with same name
            log_path2 = persist_ci_log(
                log_name="test.log",
                content="Second content",
                phase_id="phase1",
                workspace=workspace,
                run_id="run123",
            )

            assert log_path1 == log_path2
            assert log_path2.read_text() == "Second content"

    def test_persist_handles_unicode_content(self):
        """Verify unicode content is handled correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            content = "Test with unicode: 你好, مرحبا, שלום"

            log_path = persist_ci_log(
                log_name="test.log",
                content=content,
                phase_id="phase1",
                workspace=workspace,
                run_id="run123",
            )

            assert log_path.read_text(encoding="utf-8") == content

    def test_persist_returns_path(self):
        """Verify persist_ci_log returns the path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            log_path = persist_ci_log(
                log_name="test.log",
                content="Test",
                phase_id="phase1",
                workspace=workspace,
                run_id="run123",
            )

            assert isinstance(log_path, Path)
            assert log_path.name == "test.log"


class TestRunPytestCi:
    """Tests for run_pytest_ci function."""

    def test_run_pytest_ci_no_workdir(self):
        """Verify run_pytest_ci handles missing workdir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            ci_spec = {"workdir": "/nonexistent/path"}

            result = run_pytest_ci(
                phase_id="phase1",
                ci_spec=ci_spec,
                workspace=workspace,
                run_id="run123",
            )

            # Should have been handled gracefully
            assert isinstance(result, dict)
            assert "status" in result

    def test_run_pytest_ci_no_paths(self):
        """Verify run_pytest_ci handles missing pytest paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            ci_spec = {}

            result = run_pytest_ci(
                phase_id="phase1",
                ci_spec=ci_spec,
                workspace=workspace,
                run_id="run123",
            )

            assert result["status"] == "skipped"
            assert result["skipped"] is True

    @patch("subprocess.run")
    def test_run_pytest_ci_success(self, mock_run):
        """Verify successful pytest execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "tests").mkdir()
            (workspace / ".autonomous_runs" / "run123" / "ci").mkdir(parents=True)

            # Mock subprocess result
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "===== 5 passed in 0.1s ====="
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            ci_spec = {"paths": ["tests/"], "workdir": "."}

            result = run_pytest_ci(
                phase_id="phase1",
                ci_spec=ci_spec,
                workspace=workspace,
                run_id="run123",
            )

            assert result["passed"] is True
            assert result["tests_passed"] == 5

    @patch("subprocess.run")
    def test_run_pytest_ci_failure(self, mock_run):
        """Verify failed pytest execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "tests").mkdir()

            # Mock subprocess result
            mock_result = Mock()
            mock_result.returncode = 1
            mock_result.stdout = "===== 2 failed, 3 passed in 0.5s ====="
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            ci_spec = {"paths": ["tests/"], "workdir": "."}

            result = run_pytest_ci(
                phase_id="phase1",
                ci_spec=ci_spec,
                workspace=workspace,
                run_id="run123",
            )

            assert result["passed"] is False
            assert result["tests_failed"] == 2

    @patch("subprocess.run")
    def test_run_pytest_ci_timeout(self, mock_run):
        """Verify pytest timeout handling."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "tests").mkdir()

            # Mock subprocess timeout
            mock_run.side_effect = subprocess.TimeoutExpired("pytest", 300)

            ci_spec = {"paths": ["tests/"], "timeout": 300}

            result = run_pytest_ci(
                phase_id="phase1",
                ci_spec=ci_spec,
                workspace=workspace,
                run_id="run123",
            )

            assert result["passed"] is False
            assert result["error"] is not None
            # Check for timeout-related keywords
            error_lower = result["error"].lower()
            assert "timeout" in error_lower or "timed out" in error_lower

    @patch("subprocess.run")
    def test_run_pytest_ci_zero_tests(self, mock_run):
        """Verify handling of zero tests detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "tests").mkdir()

            mock_result = Mock()
            mock_result.returncode = 2
            mock_result.stdout = ""
            mock_result.stderr = "Collection error"
            mock_run.return_value = mock_result

            ci_spec = {"paths": ["tests/"], "workdir": "."}

            result = run_pytest_ci(
                phase_id="phase1",
                ci_spec=ci_spec,
                workspace=workspace,
                run_id="run123",
            )

            assert result["suspicious_zero_tests"] is True

    @patch("subprocess.run")
    def test_run_pytest_ci_custom_message(self, mock_run):
        """Verify custom success/failure messages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "tests").mkdir()

            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "===== 5 passed in 0.1s ====="
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            ci_spec = {
                "paths": ["tests/"],
                "workdir": ".",
                "success_message": "All tests passed!",
            }

            result = run_pytest_ci(
                phase_id="phase1",
                ci_spec=ci_spec,
                workspace=workspace,
                run_id="run123",
            )

            assert result["message"] == "All tests passed!"

    @patch("subprocess.run")
    def test_run_pytest_ci_environment_setup(self, mock_run):
        """Verify environment is set up correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "tests").mkdir()
            (workspace / "src").mkdir()

            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "===== 5 passed in 0.1s ====="
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            ci_spec = {"paths": ["tests/"], "env": {"CUSTOM_VAR": "value"}}

            result = run_pytest_ci(
                phase_id="phase1",
                ci_spec=ci_spec,
                workspace=workspace,
                run_id="run123",
            )

            # Verify environment was passed
            assert mock_run.called
            call_kwargs = mock_run.call_args[1]
            assert "env" in call_kwargs
            assert call_kwargs["env"]["TESTING"] == "1"


class TestRunCustomCi:
    """Tests for run_custom_ci function."""

    def test_run_custom_ci_no_command(self):
        """Verify run_custom_ci handles missing command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            ci_spec = {}

            result = run_custom_ci(
                phase_id="phase1",
                ci_spec=ci_spec,
                workspace=workspace,
                run_id="run123",
            )

            assert result["status"] == "skipped"
            assert result["skipped"] is True

    @patch("subprocess.run")
    def test_run_custom_ci_success(self, mock_run):
        """Verify successful custom command execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "Command executed successfully"
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            ci_spec = {"command": "echo test"}

            result = run_custom_ci(
                phase_id="phase1",
                ci_spec=ci_spec,
                workspace=workspace,
                run_id="run123",
            )

            assert result["passed"] is True

    @patch("subprocess.run")
    def test_run_custom_ci_failure(self, mock_run):
        """Verify failed custom command execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            mock_result = Mock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_result.stderr = "Command failed"
            mock_run.return_value = mock_result

            ci_spec = {"command": "false"}

            result = run_custom_ci(
                phase_id="phase1",
                ci_spec=ci_spec,
                workspace=workspace,
                run_id="run123",
            )

            assert result["passed"] is False


class TestCiRunnerIntegration:
    """Integration tests for CI runner."""

    def test_parse_and_trim_integration(self):
        """Verify parsing and trimming work together."""
        large_output = "x" * 5000 + "===== 10 passed in 0.5s =====" + "y" * 5000
        trimmed = trim_ci_output(large_output, limit=10000)

        # Should be able to parse trimmed output
        assert "... (truncated) ..." in trimmed
        parsed_output = trimmed.replace("... (truncated) ...", "===== 10 passed in 0.5s =====")
        passed, failed, error = parse_pytest_counts(parsed_output)
        assert passed == 10

    @patch("subprocess.run")
    def test_full_pytest_execution_flow(self, mock_run):
        """Verify full pytest execution flow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "tests").mkdir()

            # Setup mock
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "===== 100 passed in 1.5s ====="
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            ci_spec = {"paths": ["tests/"], "workdir": "."}

            result = run_pytest_ci(
                phase_id="phase1",
                ci_spec=ci_spec,
                workspace=workspace,
                run_id="run123",
            )

            # Verify results
            assert result["passed"] is True
            assert result["tests_passed"] == 100
            assert result["duration_seconds"] >= 0
            assert result["log_path"] is not None
