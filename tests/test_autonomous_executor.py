"""Targeted unit tests for AutonomousExecutor utilities.

These focus on lightweight helpers that remain stable after the orchestration
refactor, keeping coverage on scope handling and status mapping without
exercising the full runtime loop.
"""

from pathlib import Path


from autopack.autonomous_executor import AutonomousExecutor


def make_executor(tmp_path: Path) -> AutonomousExecutor:
    """Create a lightweight executor without running __init__ side effects."""
    executor = AutonomousExecutor.__new__(AutonomousExecutor)
    executor.workspace = tmp_path
    executor.run_type = "project_build"
    executor._phase_error_history = {}
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
