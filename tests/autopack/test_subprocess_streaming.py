"""Tests for subprocess streaming utilities (Phase A2)."""

import sys

from autopack.subprocess_streaming import (read_last_n_lines,
                                           run_with_streaming,
                                           run_with_streaming_legacy_compat)


def test_run_with_streaming_success(tmp_path):
    """Test successful command execution with streaming."""
    log_path = tmp_path / "test.log"

    result = run_with_streaming(
        command=[sys.executable, "-c", "print('Hello, World!')"],
        log_path=log_path,
        timeout=5,
    )

    assert result.returncode == 0
    assert result.log_path == log_path
    assert log_path.exists()
    assert "Hello, World!" in result.tail
    assert not result.timeout_occurred


def test_run_with_streaming_failure(tmp_path):
    """Test failed command execution with streaming."""
    log_path = tmp_path / "test_fail.log"

    result = run_with_streaming(
        command=[sys.executable, "-c", "import sys; sys.exit(1)"],
        log_path=log_path,
        timeout=5,
    )

    assert result.returncode == 1
    assert result.log_path == log_path
    assert log_path.exists()
    assert not result.timeout_occurred


def test_run_with_streaming_timeout(tmp_path):
    """Test command timeout handling."""
    log_path = tmp_path / "test_timeout.log"

    result = run_with_streaming(
        command=[sys.executable, "-c", "import time; time.sleep(10)"],
        log_path=log_path,
        timeout=1,  # Short timeout
    )

    assert result.returncode == -1
    assert result.timeout_occurred
    assert log_path.exists()
    assert "[TIMEOUT]" in result.tail


def test_run_with_streaming_large_output(tmp_path):
    """Test streaming with large output - verify memory efficiency."""
    log_path = tmp_path / "test_large.log"

    # Generate 1000 lines of output
    python_code = """
for i in range(1000):
    print(f'Line {i:04d}: ' + 'x' * 100)
"""

    result = run_with_streaming(
        command=[sys.executable, "-c", python_code],
        log_path=log_path,
        timeout=10,
        tail_lines=10,  # Only return last 10 lines
    )

    assert result.returncode == 0
    assert log_path.exists()

    # Verify log has all 1000 lines
    with open(log_path, "r") as f:
        all_lines = f.readlines()
    assert len(all_lines) == 1000

    # Verify tail has only last 10 lines
    tail_line_count = len([line for line in result.tail.split("\n") if line.strip()])
    assert tail_line_count <= 10

    # Verify last line content
    assert "Line 0999" in result.tail


def test_run_with_streaming_stderr_merged(tmp_path):
    """Test that stderr is merged into stdout in log file."""
    log_path = tmp_path / "test_stderr.log"

    python_code = """
import sys
print('stdout message', file=sys.stdout)
print('stderr message', file=sys.stderr)
"""

    result = run_with_streaming(
        command=[sys.executable, "-c", python_code],
        log_path=log_path,
        timeout=5,
    )

    assert result.returncode == 0

    # Both stdout and stderr should be in the log file
    log_content = log_path.read_text()
    assert "stdout message" in log_content
    assert "stderr message" in log_content


def test_read_last_n_lines(tmp_path):
    """Test reading last N lines from file."""
    test_file = tmp_path / "lines.txt"
    test_file.write_text("\n".join([f"Line {i}" for i in range(100)]))

    # Read last 10 lines
    tail = read_last_n_lines(test_file, n=10)
    lines = [line.strip() for line in tail.split("\n") if line.strip()]

    assert len(lines) == 10
    assert lines[0] == "Line 90"
    assert lines[-1] == "Line 99"


def test_read_last_n_lines_fewer_than_requested(tmp_path):
    """Test reading last N lines when file has fewer lines."""
    test_file = tmp_path / "short.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3")

    tail = read_last_n_lines(test_file, n=10)
    lines = [line.strip() for line in tail.split("\n") if line.strip()]

    assert len(lines) == 3


def test_legacy_compat_wrapper(tmp_path):
    """Test legacy-compatible wrapper returns expected dict structure."""
    log_path = tmp_path / "test_legacy.log"

    result = run_with_streaming_legacy_compat(
        command=[sys.executable, "-c", "print('test output')"],
        log_path=log_path,
        timeout=5,
    )

    # Verify dict structure matches subprocess.run expectations
    assert isinstance(result, dict)
    assert "returncode" in result
    assert "stdout" in result
    assert "stderr" in result
    assert "log_path" in result

    assert result["returncode"] == 0
    assert "test output" in result["stdout"]
    assert result["stderr"] == ""  # Merged into stdout
    assert result["log_path"] == str(log_path)


def test_creates_log_directory_if_missing(tmp_path):
    """Test that log directory is created if it doesn't exist."""
    log_path = tmp_path / "nested" / "dir" / "test.log"
    assert not log_path.parent.exists()

    result = run_with_streaming(
        command=[sys.executable, "-c", "print('test')"],
        log_path=log_path,
        timeout=5,
    )

    assert result.returncode == 0
    assert log_path.parent.exists()
    assert log_path.exists()


def test_run_with_cwd(tmp_path):
    """Test running command with custom working directory."""
    log_path = tmp_path / "cwd_test.log"
    work_dir = tmp_path / "workdir"
    work_dir.mkdir()

    result = run_with_streaming(
        command=[sys.executable, "-c", "import os; print(os.getcwd())"],
        log_path=log_path,
        cwd=work_dir,
        timeout=5,
    )

    assert result.returncode == 0
    assert str(work_dir) in result.tail


def test_run_with_custom_env(tmp_path):
    """Test running command with custom environment variables."""
    log_path = tmp_path / "env_test.log"

    import os

    custom_env = os.environ.copy()
    custom_env["TEST_VAR"] = "custom_value"

    result = run_with_streaming(
        command=[sys.executable, "-c", "import os; print(os.getenv('TEST_VAR'))"],
        log_path=log_path,
        env=custom_env,
        timeout=5,
    )

    assert result.returncode == 0
    assert "custom_value" in result.tail
