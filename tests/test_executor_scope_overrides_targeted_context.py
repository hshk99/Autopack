from types import MethodType


def test_scope_overrides_targeted_context():
    """
    Regression: If a phase has scope.paths, Autopack must use scoped context even if the
    phase matches a targeted-context pattern (e.g., frontend/docker by name/category).
    """
    from autopack.autonomous_executor import AutonomousExecutor

    ex = AutonomousExecutor.__new__(AutonomousExecutor)
    ex.workspace = "."
    ex.run_type = "project_build"

    calls = {"scoped": 0, "frontend": 0}

    def _scoped(self, phase, scope):
        calls["scoped"] += 1
        return {"existing_files": {"fileorganizer/frontend/package.json": "{}"}}

    def _frontend(self, phase):
        calls["frontend"] += 1
        return {"existing_files": {"package.json": "{}"}}

    ex._load_scoped_context = MethodType(_scoped, ex)
    ex._load_targeted_context_for_frontend = MethodType(_frontend, ex)

    phase = {
        "phase_id": "p1",
        "name": "frontend build",
        "task_category": "frontend",
        "scope": {"paths": ["fileorganizer/frontend/package.json"]},
    }

    result = ex._load_repository_context(phase)
    assert calls["scoped"] == 1
    assert calls["frontend"] == 0
    assert "fileorganizer/frontend/package.json" in result["existing_files"]


