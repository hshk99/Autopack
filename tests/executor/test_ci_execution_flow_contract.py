"""Contract tests for CIExecutionFlow module.

Validates that CIExecutionFlow correctly:
1. Routes to pytest or custom CI based on spec
2. Handles AUTOPACK_SKIP_CI for telemetry runs
3. Parses pytest JSON reports and test counts
4. Executes custom CI commands with shell support
5. Trims output and persists logs
6. Handles errors (timeouts, collection errors)
"""

from pathlib import Path
from unittest.mock import Mock, patch

from autopack.executor.ci_execution_flow import CIExecutionFlow


def make_ci_flow(tmp_path: Path) -> CIExecutionFlow:
    """Create a CIExecutionFlow with mocked executor."""
    executor = Mock()
    executor.workspace = str(tmp_path)
    executor.run_id = "test-run-123"
    executor.phase_finalizer = Mock()
    executor._get_project_slug = Mock(return_value=None)
    return CIExecutionFlow(executor)


def test_execute_ci_checks_routes_to_pytest(tmp_path: Path):
    """Test that execute_ci_checks routes to pytest when ci_mode is pytest."""
    ci_flow = make_ci_flow(tmp_path)
    phase = {"phase_id": "phase-1", "ci": {"mode": "pytest"}}

    with patch.object(ci_flow, "_run_pytest_ci", return_value={"passed": 10, "failed": 0}):
        result = ci_flow.execute_ci_checks("phase-1", phase)

    assert result is not None
    assert result["passed"] == 10
    assert result["failed"] == 0


def test_execute_ci_checks_routes_to_custom(tmp_path: Path):
    """Test that execute_ci_checks routes to custom CI when ci_mode is custom."""
    ci_flow = make_ci_flow(tmp_path)
    phase = {"phase_id": "phase-1", "ci": {"mode": "custom", "command": "npm test"}}

    with patch.object(ci_flow, "_run_custom_ci", return_value={"exit_code": 0}):
        result = ci_flow.execute_ci_checks("phase-1", phase)

    assert result is not None
    assert result["exit_code"] == 0


def test_execute_ci_checks_skips_when_env_set(tmp_path: Path, monkeypatch):
    """Test that execute_ci_checks skips when AUTOPACK_SKIP_CI is set for telemetry run."""
    monkeypatch.setenv("AUTOPACK_SKIP_CI", "1")
    ci_flow = make_ci_flow(tmp_path)
    # Use telemetry run_id to honor AUTOPACK_SKIP_CI flag
    ci_flow.run_id = "telemetry-collection-test-123"
    phase = {"phase_id": "phase-1", "ci": {"mode": "pytest"}}

    result = ci_flow.execute_ci_checks("phase-1", phase)

    # Should return None for telemetry runs with AUTOPACK_SKIP_CI
    assert result is None


def test_execute_ci_checks_skips_when_ci_spec_skip_set(tmp_path: Path):
    """Test that execute_ci_checks skips when ci.skip is set in spec."""
    ci_flow = make_ci_flow(tmp_path)
    phase = {"phase_id": "phase-1", "ci": {"skip": True, "reason": "Not needed for this phase"}}

    result = ci_flow.execute_ci_checks("phase-1", phase)

    assert result is not None
    assert result["skipped"] is True
    assert "Not needed for this phase" in result["message"]


def test_execute_ci_checks_returns_skipped_when_no_ci_spec(tmp_path: Path):
    """Test that execute_ci_checks returns skipped result when no pytest paths found."""
    ci_flow = make_ci_flow(tmp_path)
    phase = {"phase_id": "phase-1"}

    result = ci_flow.execute_ci_checks("phase-1", phase)

    # When no CI spec provided, it defaults to pytest but finds no paths
    assert result is not None
    assert result["status"] == "skipped"
    assert result["passed"] is True


def test_run_pytest_ci_parses_json_report(tmp_path: Path):
    """Test that _run_pytest_ci parses pytest output correctly."""
    ci_flow = make_ci_flow(tmp_path)

    # Create tests directory
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(exist_ok=True)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=1, stdout="2 passed, 1 failed in 1.5s", stderr="")
        result = ci_flow._run_pytest_ci("phase-1", {"paths": ["tests/"]})

    assert result is not None
    assert result["tests_passed"] == 2
    assert result["tests_failed"] == 1
    assert result["passed"] is False


def test_run_pytest_ci_handles_collection_error(tmp_path: Path):
    """Test that _run_pytest_ci handles collection errors gracefully."""
    ci_flow = make_ci_flow(tmp_path)

    # Create tests directory
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(exist_ok=True)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(
            returncode=2, stdout="", stderr="ERROR collecting tests\n1 error during collection"
        )
        result = ci_flow._run_pytest_ci("phase-1", {"paths": ["tests/"]})

    assert result is not None
    assert result["error"] is not None
    assert "collection" in result["error"].lower() or result["tests_error"] > 0


def test_run_pytest_ci_handles_timeout(tmp_path: Path):
    """Test that _run_pytest_ci handles subprocess timeout."""
    import subprocess

    ci_flow = make_ci_flow(tmp_path)

    # Create tests directory
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(exist_ok=True)

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pytest", 5)):
        result = ci_flow._run_pytest_ci("phase-1", {"paths": ["tests/"], "timeout_seconds": 5})

    assert result is not None
    assert result["error"] is not None
    assert "timed out" in result["error"].lower()


def test_run_custom_ci_executes_command(tmp_path: Path):
    """Test that _run_custom_ci executes custom command."""
    ci_flow = make_ci_flow(tmp_path)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="Tests passed", stderr="")
        result = ci_flow._run_custom_ci("phase-1", {"command": "npm test"})

    assert result is not None
    assert result["status"] == "passed"
    assert result["passed"] is True
    assert "Tests passed" in result["output"]


def test_run_custom_ci_uses_shell_for_string_commands(tmp_path: Path):
    """Test that _run_custom_ci uses shell=True for string commands by default."""
    ci_flow = make_ci_flow(tmp_path)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        ci_flow._run_custom_ci("phase-1", {"command": "npm test && npm run lint"})

    # Verify shell=True was used (default for string commands)
    call_kwargs = mock_run.call_args[1]
    assert call_kwargs.get("shell") is True


def test_trim_ci_output_limits_to_10kb(tmp_path: Path):
    """Test that _trim_ci_output limits output to 10KB."""
    ci_flow = make_ci_flow(tmp_path)

    # Create output larger than 10KB
    large_output = "x" * 20000
    trimmed = ci_flow._trim_ci_output(large_output)

    assert len(trimmed) <= 10240  # 10KB = 10240 bytes
    assert "[trimmed]" in trimmed or len(trimmed) < len(large_output)


def test_persist_ci_log_writes_to_ci_dir(tmp_path: Path):
    """Test that _persist_ci_log writes log to CI directory."""
    ci_flow = make_ci_flow(tmp_path)
    phase_id = "phase-1"
    log_name = "pytest_phase-1.log"
    output = "Test output\nLine 2\nLine 3"

    log_path = ci_flow._persist_ci_log(log_name, output, phase_id)

    # Check that log file was created
    assert log_path is not None
    assert log_path.exists()
    assert "Test output" in log_path.read_text()


def test_persist_ci_log_handles_errors_gracefully(tmp_path: Path):
    """Test that _persist_ci_log handles write errors gracefully."""
    from unittest.mock import patch

    ci_flow = make_ci_flow(tmp_path)

    # Mock mkdir to raise PermissionError to simulate write failure
    with patch.object(Path, "mkdir", side_effect=PermissionError("Permission denied")):
        # Should not raise exception, returns None on error
        result = ci_flow._persist_ci_log("test.log", "output", "phase-1")

    # Should return None when write fails (non-blocking error handling)
    assert result is None


def test_parse_pytest_counts_extracts_counts(tmp_path: Path):
    """Test that _parse_pytest_counts extracts test counts from output."""
    ci_flow = make_ci_flow(tmp_path)

    output = """
    ============================= test session starts ==============================
    collected 15 items

    tests/test_foo.py::test_one PASSED                                       [  6%]
    tests/test_foo.py::test_two FAILED                                       [ 13%]
    tests/test_bar.py::test_three ERROR                                      [ 20%]

    =========================== short test summary info ============================
    12 passed, 2 failed, 1 error in 5.2s
    """

    passed, failed, error = ci_flow._parse_pytest_counts(output)

    assert passed == 12
    assert failed == 2
    assert error == 1


def test_parse_pytest_counts_handles_no_matches(tmp_path: Path):
    """Test that _parse_pytest_counts returns zeros when no matches found."""
    ci_flow = make_ci_flow(tmp_path)

    output = "No test output here"
    passed, failed, error = ci_flow._parse_pytest_counts(output)

    assert passed == 0
    assert failed == 0
    assert error == 0


def test_run_pytest_ci_includes_json_report_path(tmp_path: Path):
    """Test that _run_pytest_ci includes JSON report path in result."""
    ci_flow = make_ci_flow(tmp_path)

    # Create tests directory
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(exist_ok=True)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="100 passed", stderr="")
        result = ci_flow._run_pytest_ci("phase-1", {"paths": ["tests/"]})

    # Check that result includes report_path
    assert result is not None
    assert "report_path" in result


def test_execute_ci_checks_handles_phase_without_phase_id(tmp_path: Path):
    """Test that execute_ci_checks handles phases without explicit phase_id."""
    ci_flow = make_ci_flow(tmp_path)
    phase = {"ci": {"mode": "pytest"}}

    with patch.object(ci_flow, "_run_pytest_ci", return_value={"passed": 5}):
        result = ci_flow.execute_ci_checks("derived-phase-id", phase)

    assert result is not None


def test_run_custom_ci_handles_nonzero_exit_code(tmp_path: Path):
    """Test that _run_custom_ci properly reports non-zero exit codes."""
    ci_flow = make_ci_flow(tmp_path)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="Tests failed")
        result = ci_flow._run_custom_ci("phase-1", {"command": "npm test"})

    assert result is not None
    assert result["status"] == "failed"
    assert result["passed"] is False
    assert result["error"] is not None


def test_run_pytest_ci_uses_correct_timeout(tmp_path: Path):
    """Test that _run_pytest_ci uses specified timeout."""
    ci_flow = make_ci_flow(tmp_path)

    # Create tests directory
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(exist_ok=True)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="10 passed", stderr="")
        ci_flow._run_pytest_ci("phase-1", {"paths": ["tests/"], "timeout_seconds": 120})

    # Verify timeout was passed
    call_kwargs = mock_run.call_args[1]
    assert call_kwargs.get("timeout") == 120
