from autopack.maintenance_auditor import (
    AuditorInput,
    DiffStats,
    TestResult,
    evaluate,
)


def test_auditor_rejects_protected_path():
    inp = AuditorInput(
        allowed_paths=["src/"],
        protected_paths=["config/"],
        diff=DiffStats(files_changed=["config/models.yaml"], lines_added=1, lines_deleted=0),
        tests=[TestResult(name="pytest -k foo", status="passed")],
        diagnostics_summary="summary",
    )
    decision = evaluate(inp)
    assert decision.verdict == "reject"
    assert any("protected path" in r for r in decision.reasons)


def test_auditor_requires_human_on_missing_tests():
    inp = AuditorInput(
        allowed_paths=["src/"],
        protected_paths=["config/"],
        diff=DiffStats(files_changed=["src/foo.py"], lines_added=10, lines_deleted=0),
        tests=[],
        diagnostics_summary="summary",
    )
    decision = evaluate(inp)
    assert decision.verdict == "require_human"
    assert any("no targeted tests" in r for r in decision.reasons)


def test_auditor_approves_safe_small_change():
    inp = AuditorInput(
        allowed_paths=["src/"],
        protected_paths=["config/"],
        diff=DiffStats(files_changed=["src/foo.py"], lines_added=5, lines_deleted=0),
        tests=[TestResult(name="pytest -k foo", status="passed")],
        diagnostics_summary="summary",
    )
    decision = evaluate(inp)
    assert decision.verdict == "approve"

