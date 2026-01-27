from __future__ import annotations

from autopack.executor.phase_dispatch import (
    SPECIAL_PHASE_METHODS,
    resolve_special_phase_method,
)


def test_phase_dispatch_registry_has_expected_special_phases() -> None:
    expected = {
        "research-tracer-bullet",
        "research-gatherers-web-compilation",
        "diagnostics-handoff-bundle",
        "diagnostics-cursor-prompt",
        "diagnostics-second-opinion-triage",
        "diagnostics-deep-retrieval",
        "diagnostics-iteration-loop",
    }
    assert expected.issubset(set(SPECIAL_PHASE_METHODS.keys()))


def test_resolve_special_phase_method_returns_none_for_unknown() -> None:
    assert resolve_special_phase_method("not-a-phase") is None


def test_resolve_special_phase_method_returns_method_name() -> None:
    assert (
        resolve_special_phase_method("research-tracer-bullet")
        == "_execute_research_tracer_bullet_batched"
    )
