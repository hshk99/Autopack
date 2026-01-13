"""Contract tests for PytestRunner (PR-EXE-13).

Validates that the pytest runner correctly executes pytest, parses output,
handles timeouts, and persists CI logs.
"""

from pathlib import Path
from unittest.mock import Mock, patch
import subprocess
import pytest

from autopack.ci.pytest_runner import PytestRunner


class TestPytestRunner:
    """Test suite for PytestRunner contract."""

    @pytest.fixture
    def runner(self, tmp_path):
        """Create pytest runner instance."""
        run_id = "test-run-123"
        return PytestRunner(workspace=tmp_path, run_id=run_id, phase_finalizer=None)

    @pytest.fixture
    def ci_spec(self):
        """Create basic CI spec."""
        return {
            "paths": ["tests/"],
            "timeout": 300,
            "per_test_timeout": 60,
        }

    def test_successful_pytest_run(self, runner, tmp_path, ci_spec):
        """Test successful pytest execution."""
        # Create tests directory
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "test_example.py::test_foo PASSED\n2 passed in 1.5s"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = runner.run("phase-1", ci_spec)

        assert result.passed is True
        assert result.status == "passed"
        assert result.tests_passed == 2
        assert result.tests_failed == 0
        assert result.tests_error == 0
        assert result.tests_run == 2
        assert result.skipped is False

    def test_failed_pytest_run(self, runner, tmp_path, ci_spec):
        """Test failed pytest execution."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = "test_example.py::test_foo PASSED\ntest_example.py::test_bar FAILED\n1 passed, 1 failed in 2.0s"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = runner.run("phase-1", ci_spec)

        assert result.passed is False
        assert result.status == "failed"
        assert result.tests_passed == 1
        assert result.tests_failed == 1
        assert result.tests_run == 2
        assert result.error is not None

    def test_pytest_timeout(self, runner, tmp_path, ci_spec):
        """Test pytest timeout handling."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pytest", 300)):
            result = runner.run("phase-1", ci_spec)

        assert result.passed is False
        assert result.status == "failed"
        assert "timed out" in result.message.lower()
        assert result.error is not None

    def test_no_tests_found(self, runner, tmp_path):
        """Test handling when no test paths exist."""
        # Don't create tests directory
        ci_spec_no_paths = {
            "paths": None,  # Let runner discover
            "timeout": 300,
        }

        result = runner.run("phase-1", ci_spec_no_paths)

        assert result.skipped is True
        assert result.status == "skipped"
        assert result.passed is True
        assert result.tests_run == 0

    def test_parse_pytest_counts_passed(self, runner):
        """Test parsing pytest output for passed tests."""
        output = "====== 5 passed in 3.2s ======"
        passed, failed, error = runner._parse_pytest_counts(output)

        assert passed == 5
        assert failed == 0
        assert error == 0

    def test_parse_pytest_counts_failed(self, runner):
        """Test parsing pytest output for failed tests."""
        output = "====== 3 passed, 2 failed in 5.1s ======"
        passed, failed, error = runner._parse_pytest_counts(output)

        assert passed == 3
        assert failed == 2
        assert error == 0

    def test_parse_pytest_counts_error(self, runner):
        """Test parsing pytest output for error/collection failures."""
        output = "====== 1 error during collection ======"
        passed, failed, error = runner._parse_pytest_counts(output)

        assert passed == 0
        assert failed == 0
        assert error == 1

    def test_ci_log_persistence(self, runner, tmp_path, ci_spec):
        """Test CI log is persisted to disk."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Test output"
        mock_result.stderr = "Warning: deprecated"

        with patch("subprocess.run", return_value=mock_result):
            result = runner.run("phase-1", ci_spec)

        # Check log was persisted
        assert result.log_path is not None
        log_path = Path(result.log_path)
        assert log_path.exists()
        log_content = log_path.read_text(encoding="utf-8")
        assert "Test output" in log_content
        assert "Warning: deprecated" in log_content

    def test_json_report_path_generation(self, runner, tmp_path, ci_spec):
        """Test JSON report path is generated for structured results."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "2 passed in 1.0s"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = runner.run("phase-1", ci_spec)

            # Verify --json-report flags were added
            call_args = mock_run.call_args[0][0]
            assert "--json-report" in call_args
            assert any("--json-report-file=" in str(arg) for arg in call_args)

        assert result.report_path is not None

    def test_suspicious_zero_tests_detection(self, runner, tmp_path, ci_spec):
        """Test detection of suspicious zero test scenarios."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "no tests ran in 0.1s"  # Suspicious
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = runner.run("phase-1", ci_spec)

        assert result.tests_run == 0
        assert result.suspicious_zero_tests is True
        assert result.error is not None
