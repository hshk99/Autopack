"""Targeted unit tests for AutonomousExecutor utilities.

These focus on lightweight helpers that remain stable after the orchestration
refactor, keeping coverage on scope handling and status mapping without
exercising the full runtime loop.
"""

import threading
from pathlib import Path
from unittest.mock import Mock, patch

from autopack.autonomous_executor import AutonomousExecutor
from autopack.executor.autonomous_loop import AutonomousLoop
from autopack.executor.error_analysis import ErrorAnalyzer


def make_executor(tmp_path: Path) -> AutonomousExecutor:
    """Create a lightweight executor without running __init__ side effects."""
    executor = AutonomousExecutor.__new__(AutonomousExecutor)
    executor.workspace = tmp_path
    executor.run_type = "project_build"
    executor._phase_error_history = {}
    # PR-EXE-10: Initialize error analyzer for _record_phase_error tests
    executor.error_analyzer = ErrorAnalyzer()
    return executor


def test_status_to_outcome_mapping(tmp_path: Path):
    executor = make_executor(tmp_path)

    assert executor._status_to_outcome("FAILED") == "auditor_reject"
    assert executor._status_to_outcome("PATCH_FAILED") == "patch_apply_error"
    assert executor._status_to_outcome("CI_FAILED") == "ci_fail"
    # Default fallback
    assert executor._status_to_outcome("UNKNOWN") == "auditor_reject"


def test_derive_allowed_paths_from_scope(tmp_path: Path):
    executor = make_executor(tmp_path)

    scope_config = {"paths": ["tests/"]}
    # Use an explicit workspace_root under the workspace to avoid absolute path issues.
    workspace_root = tmp_path / "project"
    allowed = executor._derive_allowed_paths_from_scope(scope_config, workspace_root=workspace_root)

    assert allowed == [f"{workspace_root.relative_to(tmp_path)}/"]


def test_get_next_queued_phase(tmp_path: Path):
    executor = make_executor(tmp_path)
    run_data = {
        "tiers": [
            {
                "tier_index": 0,
                "phases": [
                    {"phase_id": "p1", "phase_index": 1, "state": "COMPLETE"},
                    {"phase_id": "p2", "phase_index": 0, "state": "QUEUED"},
                ],
            }
        ]
    }

    next_phase = executor.get_next_queued_phase(run_data)
    assert next_phase["phase_id"] == "p2"


def test_record_phase_error_appends_history(tmp_path: Path):
    executor = make_executor(tmp_path)
    phase = {"phase_id": "phase-1"}

    executor._record_phase_error(
        phase, error_type="ci_fail", error_details="details", attempt_index=0
    )

    history = executor._phase_error_history["phase-1"]
    assert len(history) == 1
    assert history[0]["error_type"] == "ci_fail"


def test_autonomous_loop_default_poll_interval(tmp_path: Path):
    """Test that the default poll interval is 0.5s (reduced from 1.0s)."""
    executor = make_executor(tmp_path)
    loop = AutonomousLoop(executor)

    assert loop.poll_interval == 0.5, "Default poll interval should be 0.5s"


def test_autonomous_loop_adaptive_sleep_normal():
    """Test adaptive sleep with normal (non-idle) state."""
    executor = Mock()
    loop = AutonomousLoop(executor)

    with patch("time.sleep") as mock_sleep:
        sleep_time = loop._adaptive_sleep(is_idle=False, base_interval=0.5)
        assert sleep_time == 0.5
        mock_sleep.assert_called_once_with(0.5)


def test_autonomous_loop_adaptive_sleep_idle_backoff():
    """Test adaptive sleep with idle backoff (2x multiplier, max 5s)."""
    executor = Mock()
    loop = AutonomousLoop(executor)

    with patch("time.sleep") as mock_sleep:
        # Test with base interval 0.5s, should sleep 1.0s (0.5 * 2)
        sleep_time = loop._adaptive_sleep(is_idle=True, base_interval=0.5)
        assert sleep_time == 1.0
        mock_sleep.assert_called_once_with(1.0)


def test_autonomous_loop_adaptive_sleep_idle_cap_at_max():
    """Test that adaptive sleep caps idle backoff at max_idle_sleep (5s)."""
    executor = Mock()
    loop = AutonomousLoop(executor)
    loop.max_idle_sleep = 5.0

    with patch("time.sleep") as mock_sleep:
        # Test with base interval 3.0s, should sleep 5.0s (capped, not 6.0)
        sleep_time = loop._adaptive_sleep(is_idle=True, base_interval=3.0)
        assert sleep_time == 5.0
        mock_sleep.assert_called_once_with(5.0)


# =============================================================================
# IMP-PERF-001: Background T0 Baseline Capture Tests
# =============================================================================


def make_executor_with_baseline_support(tmp_path: Path) -> AutonomousExecutor:
    """Create executor with baseline capture infrastructure initialized."""
    executor = AutonomousExecutor.__new__(AutonomousExecutor)
    executor.workspace = tmp_path
    executor.run_id = "test-run-001"
    executor.run_type = "project_build"
    executor._phase_error_history = {}
    executor.error_analyzer = ErrorAnalyzer()
    # Initialize baseline capture infrastructure
    executor._t0_baseline = None
    executor._t0_baseline_lock = threading.Lock()
    executor._t0_baseline_ready = threading.Event()
    executor._t0_baseline_thread = None
    # Mock baseline tracker
    executor.baseline_tracker = Mock()
    return executor


def test_get_t0_baseline_returns_none_when_not_ready(tmp_path: Path):
    """IMP-PERF-001: get_t0_baseline returns None immediately with timeout=0."""
    executor = make_executor_with_baseline_support(tmp_path)
    # Event not set, baseline not ready
    result = executor.get_t0_baseline(timeout=0)
    assert result is None


def test_get_t0_baseline_returns_baseline_when_ready(tmp_path: Path):
    """IMP-PERF-001: get_t0_baseline returns baseline when capture complete."""
    executor = make_executor_with_baseline_support(tmp_path)

    # Simulate completed baseline capture
    mock_baseline = Mock()
    mock_baseline.total_tests = 100
    mock_baseline.passing_tests = 95
    executor._t0_baseline = mock_baseline
    executor._t0_baseline_ready.set()

    result = executor.get_t0_baseline(timeout=0)
    assert result is mock_baseline
    assert result.total_tests == 100


def test_get_t0_baseline_waits_for_ready(tmp_path: Path):
    """IMP-PERF-001: get_t0_baseline waits for background thread completion."""
    executor = make_executor_with_baseline_support(tmp_path)

    mock_baseline = Mock()
    mock_baseline.total_tests = 50

    def set_baseline_after_delay():
        import time

        time.sleep(0.1)
        with executor._t0_baseline_lock:
            executor._t0_baseline = mock_baseline
        executor._t0_baseline_ready.set()

    # Start a thread that will set the baseline after a short delay
    thread = threading.Thread(target=set_baseline_after_delay)
    thread.start()

    # This should wait and get the baseline
    result = executor.get_t0_baseline(timeout=2.0)
    thread.join()

    assert result is mock_baseline


def test_get_t0_baseline_timeout_returns_none(tmp_path: Path):
    """IMP-PERF-001: get_t0_baseline returns None on timeout."""
    executor = make_executor_with_baseline_support(tmp_path)
    # Event never set - will timeout
    result = executor.get_t0_baseline(timeout=0.1)
    assert result is None


def test_t0_baseline_property_backward_compatible(tmp_path: Path):
    """IMP-PERF-001: t0_baseline property maintains backward compatibility."""
    executor = make_executor_with_baseline_support(tmp_path)

    mock_baseline = Mock()
    mock_baseline.total_tests = 75
    executor._t0_baseline = mock_baseline
    executor._t0_baseline_ready.set()

    # Access via property (backward compatible)
    result = executor.t0_baseline
    assert result is mock_baseline


def test_start_background_baseline_capture_creates_thread(tmp_path: Path):
    """IMP-PERF-001: _start_background_baseline_capture creates daemon thread."""
    executor = make_executor_with_baseline_support(tmp_path)

    # Mock subprocess to simulate git command
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "abc123def456\n"

    mock_baseline = Mock()
    mock_baseline.total_tests = 10
    mock_baseline.passing_tests = 10
    mock_baseline.failing_tests = 0
    mock_baseline.error_tests = 0
    executor.baseline_tracker.capture_baseline.return_value = mock_baseline

    with patch("subprocess.run", return_value=mock_result):
        executor._start_background_baseline_capture()

        # Wait for thread to complete
        executor._t0_baseline_thread.join(timeout=5.0)

    # Verify thread was started and completed
    assert executor._t0_baseline_ready.is_set()
    assert executor._t0_baseline is not None
    assert executor._t0_baseline.total_tests == 10


def test_start_background_baseline_capture_handles_git_failure(tmp_path: Path):
    """IMP-PERF-001: Background capture handles git command failure gracefully."""
    executor = make_executor_with_baseline_support(tmp_path)

    mock_result = Mock()
    mock_result.returncode = 1  # Git command failed
    mock_result.stdout = ""

    with patch("subprocess.run", return_value=mock_result):
        executor._start_background_baseline_capture()
        executor._t0_baseline_thread.join(timeout=5.0)

    # Should still set ready event even on failure
    assert executor._t0_baseline_ready.is_set()
    assert executor._t0_baseline is None


def test_start_background_baseline_capture_handles_exception(tmp_path: Path):
    """IMP-PERF-001: Background capture handles exceptions gracefully."""
    executor = make_executor_with_baseline_support(tmp_path)

    with patch("subprocess.run", side_effect=Exception("Network error")):
        executor._start_background_baseline_capture()
        executor._t0_baseline_thread.join(timeout=5.0)

    # Should still set ready event even on exception
    assert executor._t0_baseline_ready.is_set()
    assert executor._t0_baseline is None


def test_background_baseline_thread_is_daemon(tmp_path: Path):
    """IMP-PERF-001: Background thread is daemon to not block process exit."""
    executor = make_executor_with_baseline_support(tmp_path)

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "abc123\n"

    mock_baseline = Mock()
    mock_baseline.total_tests = 5
    mock_baseline.passing_tests = 5
    mock_baseline.failing_tests = 0
    mock_baseline.error_tests = 0
    executor.baseline_tracker.capture_baseline.return_value = mock_baseline

    with patch("subprocess.run", return_value=mock_result):
        executor._start_background_baseline_capture()
        # Check daemon status before join
        assert executor._t0_baseline_thread.daemon is True
        executor._t0_baseline_thread.join(timeout=5.0)
