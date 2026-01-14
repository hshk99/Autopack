"""Targeted unit tests for AutonomousExecutor utilities.

These focus on lightweight helpers that remain stable after the orchestration
refactor, keeping coverage on scope handling and status mapping without
exercising the full runtime loop.
"""

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
