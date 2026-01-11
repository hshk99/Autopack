from __future__ import annotations

from autopack.executor.context_loading import load_repository_context


class FakeExecutor:
    def __init__(self) -> None:
        self.scoped_called = False
        self.frontend_called = False

    def _load_scoped_context(self, phase: dict, scope_config: dict) -> dict:
        self.scoped_called = True
        return {"existing_files": {"_sentinel": "scoped"}}

    def _load_targeted_context_for_templates(self, phase: dict) -> dict:
        raise AssertionError("templates loader should not be called when scope.paths exists")

    def _load_targeted_context_for_frontend(self, phase: dict) -> dict:
        self.frontend_called = True
        raise AssertionError("frontend loader should not be called when scope.paths exists")

    def _load_targeted_context_for_docker(self, phase: dict) -> dict:
        raise AssertionError("docker loader should not be called when scope.paths exists")

    def _load_repository_context_heuristic(self, phase: dict) -> dict:
        raise AssertionError("heuristic loader should not be called when scope.paths exists")


def test_scope_precedence_over_targeted_loaders() -> None:
    ex = FakeExecutor()
    phase = {
        "phase_id": "any",
        "name": "Frontend phase",
        "description": "",
        "task_category": "frontend",
        "scope": {"paths": ["src/autopack/something.py"]},
    }
    ctx = load_repository_context(ex, phase)
    assert ex.scoped_called is True
    assert ex.frontend_called is False
    assert ctx["existing_files"]["_sentinel"] == "scoped"
