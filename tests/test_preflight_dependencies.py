from pathlib import Path

from autopack.preflight_validator import PreflightValidator


def test_preflight_validator_rejects_circular_dependencies(tmp_path: Path):
    v = PreflightValidator(tmp_path)
    plan = {
        "run_id": "r1",
        "phases": [
            {"phase_id": "a", "goal": "A", "dependencies": ["b"], "scope": {"paths": []}},
            {"phase_id": "b", "goal": "B", "dependencies": ["a"], "scope": {"paths": []}},
        ],
    }
    res = v.validate_plan(plan)
    assert res.valid is False
    assert res.error
    assert "Circular dependency" in res.error


def test_preflight_validator_rejects_missing_dependency(tmp_path: Path):
    v = PreflightValidator(tmp_path)
    plan = {
        "run_id": "r1",
        "phases": [
            {"phase_id": "a", "goal": "A", "dependencies": ["missing"], "scope": {"paths": []}},
        ],
    }
    res = v.validate_plan(plan)
    assert res.valid is False
    assert res.error
    assert "non-existent phase" in res.error
