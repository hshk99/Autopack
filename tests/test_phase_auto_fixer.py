from autopack.phase_auto_fixer import (
    normalize_deliverables,
    derive_scope_paths_from_deliverables,
    auto_fix_phase_scope,
)


def test_normalize_deliverables_strips_annotations_and_normalizes_slashes():
    raw = [
        "src/autopack/research/evaluation/gold_set.json (non-empty valid JSON)",
        "`tests\\\\test_example.py`",
        "  ./docs/readme.md  ",
    ]
    out = normalize_deliverables(raw)
    assert out == [
        "src/autopack/research/evaluation/gold_set.json",
        "tests/test_example.py",
        "docs/readme.md",
    ]


def test_derive_scope_paths_from_deliverables():
    deliverables = [
        "src/autopack/research/evaluation/gold_set.json",
        "tests/test_example.py",
        "docs/research/",
    ]
    paths = derive_scope_paths_from_deliverables(deliverables)
    assert "src/autopack/research/evaluation/" in paths
    assert "tests/" in paths
    assert "docs/research/" in paths


def test_auto_fix_adds_ci_and_marks_applied():
    phase = {
        "phase_id": "p1",
        "name": "Test phase",
        "description": "Run tests",
        "complexity": "medium",
        "scope": {
            "deliverables": ["tests/test_example.py (10+ tests)"],
            "paths": [],
        },
        "state": "QUEUED",
    }
    r = auto_fix_phase_scope(phase)
    assert r.changed is True
    assert r.new_scope.get("_autofix_v1_applied") is True
    assert "ci" in r.new_scope
    assert r.new_scope["ci"]["timeout_seconds"] >= 900
    assert any(p.endswith("/") for p in r.new_scope.get("paths", []))


def test_auto_fix_escalates_ci_on_prior_timeout():
    phase = {
        "phase_id": "p2",
        "name": "Integration phase",
        "description": "Some long test suite",
        "complexity": "low",
        "scope": {
            "deliverables": ["tests/test_something.py"],
            "paths": ["tests/"],
            "last_failure_reason": "exit code 143 timeout",
        },
        "state": "QUEUED",
    }
    r = auto_fix_phase_scope(phase)
    assert r.new_scope["ci"]["timeout_seconds"] >= 1200
    assert r.new_scope["ci"]["per_test_timeout"] >= 90
