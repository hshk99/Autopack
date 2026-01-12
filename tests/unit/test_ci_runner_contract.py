"""Contract tests for CI runner module.

These tests verify the ci_runner module behavior contract for PR-EXE-3.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
import subprocess

from autopack.executor.ci_runner import (
    CIResult,
    CISpec,
    create_skipped_result,
    trim_ci_output,
    persist_ci_log,
    parse_pytest_counts,
    discover_pytest_paths,
    run_pytest,
    run_custom_ci,
    run_ci_checks,
)


class TestCIResult:
    """Contract tests for CIResult dataclass."""

    def test_to_dict_returns_all_fields(self):
        """Contract: to_dict returns all expected fields."""
        result = CIResult(
            status="passed",
            message="All tests passed",
            passed=True,
            tests_run=10,
            tests_passed=10,
            tests_failed=0,
            tests_error=0,
            duration_seconds=5.5,
            output="output here",
            error=None,
            report_path="/path/to/report.json",
            log_path="/path/to/log.txt",
            skipped=False,
            suspicious_zero_tests=False,
            collector_error_digest=None,
        )

        data = result.to_dict()

        assert data["status"] == "passed"
        assert data["message"] == "All tests passed"
        assert data["passed"] is True
        assert data["tests_run"] == 10
        assert data["tests_passed"] == 10
        assert data["tests_failed"] == 0
        assert data["tests_error"] == 0
        assert data["duration_seconds"] == 5.5
        assert data["output"] == "output here"
        assert data["error"] is None
        assert data["report_path"] == "/path/to/report.json"
        assert data["log_path"] == "/path/to/log.txt"
        assert data["skipped"] is False
        assert data["suspicious_zero_tests"] is False
        assert data["collector_error_digest"] is None

    def test_defaults_for_minimal_result(self):
        """Contract: Minimal result has sensible defaults."""
        result = CIResult(
            status="failed",
            message="Test failed",
            passed=False,
        )

        assert result.tests_run == 0
        assert result.tests_passed == 0
        assert result.duration_seconds == 0.0
        assert result.output == ""
        assert result.skipped is False


class TestCISpec:
    """Contract tests for CISpec dataclass."""

    def test_from_dict_defaults_to_pytest(self):
        """Contract: Empty spec defaults to pytest type."""
        spec = CISpec.from_dict({}, "phase-1")

        assert spec.ci_type == "pytest"
        assert spec.timeout_seconds == 300
        assert spec.per_test_timeout == 60

    def test_from_dict_detects_custom_from_command(self):
        """Contract: Spec with command but no type is custom."""
        spec = CISpec.from_dict({"command": "npm test"}, "phase-1")

        assert spec.ci_type == "custom"
        assert spec.command == "npm test"
        assert spec.timeout_seconds == 600

    def test_from_dict_respects_explicit_type(self):
        """Contract: Explicit type is respected."""
        spec = CISpec.from_dict({"type": "custom", "command": "make test"}, "phase-1")

        assert spec.ci_type == "custom"

    def test_from_dict_extracts_all_fields(self):
        """Contract: All fields are extracted from dict."""
        spec = CISpec.from_dict(
            {
                "type": "pytest",
                "skip": True,
                "reason": "Not needed",
                "paths": ["tests/unit/"],
                "args": ["-x", "--cov"],
                "workdir": "src",
                "timeout_seconds": 120,
                "per_test_timeout": 30,
                "env": {"DEBUG": "1"},
                "json_report_name": "custom_report.json",
                "log_name": "custom.log",
                "success_message": "All good!",
                "failure_message": "Tests failed!",
            },
            "phase-1",
        )

        assert spec.skip is True
        assert spec.skip_reason == "Not needed"
        assert spec.paths == ["tests/unit/"]
        assert spec.args == ["-x", "--cov"]
        assert spec.workdir == "src"
        assert spec.timeout_seconds == 120
        assert spec.per_test_timeout == 30
        assert spec.env == {"DEBUG": "1"}
        assert spec.json_report_name == "custom_report.json"
        assert spec.log_name == "custom.log"
        assert spec.success_message == "All good!"
        assert spec.failure_message == "Tests failed!"


class TestCreateSkippedResult:
    """Contract tests for create_skipped_result function."""

    def test_returns_skipped_result(self):
        """Contract: Returns a properly configured skipped result."""
        result = create_skipped_result("Custom reason")

        assert result.status == "skipped"
        assert result.message == "Custom reason"
        assert result.passed is True
        assert result.skipped is True
        assert result.tests_run == 0

    def test_default_reason(self):
        """Contract: Has sensible default reason."""
        result = create_skipped_result()

        assert "CI skipped" in result.message


class TestTrimCIOutput:
    """Contract tests for trim_ci_output function."""

    def test_short_output_unchanged(self):
        """Contract: Output under limit is unchanged."""
        output = "Short output"
        result = trim_ci_output(output, limit=100)

        assert result == output

    def test_long_output_truncated(self):
        """Contract: Output over limit is truncated with marker."""
        output = "x" * 20000
        result = trim_ci_output(output, limit=10000)

        assert len(result) < len(output)
        assert "... (truncated) ..." in result

    def test_truncation_preserves_start_and_end(self):
        """Contract: Truncation keeps start and end of output."""
        output = "START" + "x" * 20000 + "END"
        result = trim_ci_output(output, limit=10000)

        assert result.startswith("START")
        assert result.endswith("END")


class TestParsePytestCounts:
    """Contract tests for parse_pytest_counts function."""

    def test_parses_passed_only(self):
        """Contract: Parses output with only passed tests."""
        output = "10 passed in 5.2s"
        passed, failed, error = parse_pytest_counts(output)

        assert passed == 10
        assert failed == 0
        assert error == 0

    def test_parses_mixed_results(self):
        """Contract: Parses output with passed, failed, and errors."""
        output = "8 passed, 2 failed, 1 error in 10.5s"
        passed, failed, error = parse_pytest_counts(output)

        assert passed == 8
        assert failed == 2
        assert error == 1

    def test_parses_collection_errors(self):
        """Contract: Parses collection errors separately."""
        output = "3 errors during collection"
        passed, failed, error = parse_pytest_counts(output)

        assert passed == 0
        assert failed == 0
        assert error == 3

    def test_handles_no_tests(self):
        """Contract: Returns zeros when no test counts found."""
        output = "no tests ran"
        passed, failed, error = parse_pytest_counts(output)

        assert passed == 0
        assert failed == 0
        assert error == 0


class TestDiscoverPytestPaths:
    """Contract tests for discover_pytest_paths function."""

    def test_finds_tests_directory(self, tmp_path):
        """Contract: Discovers tests/ directory when it exists."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        result = discover_pytest_paths(tmp_path)

        assert result == ["tests/"]

    def test_returns_none_when_no_tests(self, tmp_path):
        """Contract: Returns None when no test paths found."""
        result = discover_pytest_paths(tmp_path)

        assert result is None

    def test_file_organizer_custom_paths(self, tmp_path):
        """Contract: Uses custom paths for file-organizer-app-v1."""
        tests_dir = tmp_path / "fileorganizer" / "backend" / "tests"
        tests_dir.mkdir(parents=True)

        result = discover_pytest_paths(tmp_path, "file-organizer-app-v1")

        assert result == ["fileorganizer/backend/tests/"]


class TestPersistCILog:
    """Contract tests for persist_ci_log function."""

    def test_writes_log_file(self, tmp_path):
        """Contract: Writes log content to file."""
        result = persist_ci_log(
            workspace=tmp_path,
            run_id="run-123",
            log_name="test.log",
            content="Log content here",
            phase_id="phase-1",
        )

        assert result is not None
        assert result.exists()
        assert result.read_text() == "Log content here"

    def test_creates_directory_structure(self, tmp_path):
        """Contract: Creates necessary directories."""
        result = persist_ci_log(
            workspace=tmp_path,
            run_id="run-123",
            log_name="test.log",
            content="content",
            phase_id="phase-1",
        )

        expected_dir = tmp_path / ".autonomous_runs" / "run-123" / "ci"
        assert expected_dir.exists()

    def test_returns_none_on_failure(self, tmp_path):
        """Contract: Returns None when write fails."""
        # Make workspace read-only (this may not work on all platforms)
        with patch("pathlib.Path.write_text", side_effect=PermissionError("Access denied")):
            result = persist_ci_log(
                workspace=tmp_path,
                run_id="run-123",
                log_name="test.log",
                content="content",
                phase_id="phase-1",
            )

            assert result is None


class TestRunPytest:
    """Contract tests for run_pytest function."""

    def test_returns_skipped_when_no_paths(self, tmp_path):
        """Contract: Returns skipped result when no test paths found."""
        spec = CISpec.from_dict({}, "phase-1")

        result = run_pytest(
            phase_id="phase-1",
            spec=spec,
            workspace=tmp_path,
            run_id="run-123",
        )

        assert result.skipped is True
        assert "No pytest paths found" in result.message

    def test_returns_timeout_result(self, tmp_path):
        """Contract: Returns failed result on timeout."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        spec = CISpec.from_dict({"timeout_seconds": 1}, "phase-1")

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 1)):
            result = run_pytest(
                phase_id="phase-1",
                spec=spec,
                workspace=tmp_path,
                run_id="run-123",
            )

        assert result.passed is False
        assert "timed out" in result.message.lower()

    def test_parses_test_counts(self, tmp_path):
        """Contract: Parses test counts from pytest output."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        spec = CISpec.from_dict({}, "phase-1")

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "5 passed in 2.0s"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = run_pytest(
                phase_id="phase-1",
                spec=spec,
                workspace=tmp_path,
                run_id="run-123",
            )

        assert result.passed is True
        assert result.tests_passed == 5


class TestRunCustomCI:
    """Contract tests for run_custom_ci function."""

    def test_returns_skipped_when_no_command(self, tmp_path):
        """Contract: Returns skipped result when no command configured."""
        spec = CISpec.from_dict({"type": "custom"}, "phase-1")

        result = run_custom_ci(
            phase_id="phase-1",
            spec=spec,
            workspace=tmp_path,
            run_id="run-123",
        )

        assert result.skipped is True
        assert "not configured" in result.message.lower()

    def test_returns_passed_on_zero_exit(self, tmp_path):
        """Contract: Returns passed result on exit code 0."""
        spec = CISpec.from_dict({"command": "echo hello"}, "phase-1")

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "hello"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = run_custom_ci(
                phase_id="phase-1",
                spec=spec,
                workspace=tmp_path,
                run_id="run-123",
            )

        assert result.passed is True
        assert result.status == "passed"

    def test_returns_failed_on_nonzero_exit(self, tmp_path):
        """Contract: Returns failed result on non-zero exit code."""
        spec = CISpec.from_dict({"command": "exit 1"}, "phase-1")

        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"

        with patch("subprocess.run", return_value=mock_result):
            result = run_custom_ci(
                phase_id="phase-1",
                spec=spec,
                workspace=tmp_path,
                run_id="run-123",
            )

        assert result.passed is False
        assert result.status == "failed"


class TestRunCIChecks:
    """Contract tests for run_ci_checks function."""

    def test_respects_skip_flag(self, tmp_path):
        """Contract: Respects skip flag in CI spec."""
        phase = {"ci": {"skip": True, "reason": "Test reason"}}

        result = run_ci_checks(
            phase_id="phase-1",
            phase=phase,
            workspace=tmp_path,
            run_id="run-123",
        )

        assert result.skipped is True
        assert "Test reason" in result.message

    def test_routes_to_custom_ci(self, tmp_path):
        """Contract: Routes to custom CI when type is custom."""
        phase = {"ci": {"type": "custom", "command": "echo test"}}

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "test"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = run_ci_checks(
                phase_id="phase-1",
                phase=phase,
                workspace=tmp_path,
                run_id="run-123",
            )

        assert result.passed is True

    def test_routes_to_pytest_by_default(self, tmp_path):
        """Contract: Routes to pytest when no type specified."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        phase = {}

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "1 passed"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = run_ci_checks(
                phase_id="phase-1",
                phase=phase,
                workspace=tmp_path,
                run_id="run-123",
            )

        assert result is not None

    def test_returns_none_for_telemetry_skip(self, tmp_path):
        """Contract: Returns None when AUTOPACK_SKIP_CI=1 for telemetry runs."""
        phase = {}

        with patch.dict("os.environ", {"AUTOPACK_SKIP_CI": "1"}):
            result = run_ci_checks(
                phase_id="phase-1",
                phase=phase,
                workspace=tmp_path,
                run_id="telemetry-collection-123",
                is_telemetry_run=True,
            )

        assert result is None

    def test_ignores_skip_for_non_telemetry(self, tmp_path):
        """Contract: Ignores AUTOPACK_SKIP_CI for non-telemetry runs."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        phase = {}

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "1 passed"
        mock_result.stderr = ""

        with patch.dict("os.environ", {"AUTOPACK_SKIP_CI": "1"}):
            with patch("subprocess.run", return_value=mock_result):
                result = run_ci_checks(
                    phase_id="phase-1",
                    phase=phase,
                    workspace=tmp_path,
                    run_id="regular-run-123",
                    is_telemetry_run=False,
                )

        # Should run CI despite env var
        assert result is not None

    def test_extracts_ci_from_scope(self, tmp_path):
        """Contract: Extracts CI spec from phase scope when not at top level."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        phase = {"scope": {"ci": {"skip": True, "reason": "From scope"}}}

        result = run_ci_checks(
            phase_id="phase-1",
            phase=phase,
            workspace=tmp_path,
            run_id="run-123",
        )

        assert result.skipped is True
        assert "From scope" in result.message
