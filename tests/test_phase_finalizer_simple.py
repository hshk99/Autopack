"""
Simplified unit tests for PhaseFinalizer (BUILD-127 Phase 1).
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from autopack.phase_finalizer import PhaseFinalizer, PhaseFinalizationDecision
from autopack.test_baseline_tracker import TestBaseline, TestDelta


def test_finalization_decision_can_complete():
    """Test decision allowing completion."""
    decision = PhaseFinalizationDecision(
        can_complete=True,
        status="COMPLETE",
        reason="All gates passed"
    )
    
    assert decision.can_complete
    assert decision.status == "COMPLETE"


def test_finalization_decision_blocked():
    """Test decision blocking completion."""
    decision = PhaseFinalizationDecision(
        can_complete=False,
        status="FAILED",
        reason="Test failures",
        blocking_issues=["5 test failures"]
    )
    
    assert not decision.can_complete
    assert len(decision.blocking_issues) == 1


def test_finalizer_all_gates_pass(tmp_path):
    """Test completion when all gates pass."""
    tracker = Mock()
    finalizer = PhaseFinalizer(tracker)
    
    # Mock CI delta - no regressions
    delta = TestDelta(regression_severity="none")
    tracker.compute_full_delta.return_value = delta
    (tmp_path / "file1.py").write_text("# ok\n", encoding="utf-8")
    
    decision = finalizer.assess_completion(
        phase_id="test-phase",
        phase_spec={"validation": {"tests": []}},
        ci_result=None,
        baseline=None,
        quality_report={"quality_level": "high", "is_blocked": False},
        auditor_result={},
        deliverables=["file1.py"],
        applied_files=["file1.py"],
        workspace=tmp_path
    )
    
    assert decision.can_complete


def test_finalizer_high_regression_blocks(tmp_path):
    """Test CI high regression blocks completion."""
    tracker = Mock()
    finalizer = PhaseFinalizer(tracker)

    # Mock CI delta - high regression
    delta = TestDelta(
        newly_failing_persistent=["test1", "test2", "test3", "test4", "test5"],
        regression_severity="high"
    )
    tracker.compute_full_delta.return_value = delta
    (tmp_path / "file1.py").write_text("# ok\n", encoding="utf-8")

    report_path = tmp_path / "report.json"
    report_path.write_text("{}", encoding="utf-8")

    baseline = Mock()

    decision = finalizer.assess_completion(
        phase_id="test-phase",
        phase_spec={"validation": {"tests": []}},
        ci_result={"report_path": str(report_path)},
        baseline=baseline,
        quality_report={"quality_level": "high", "is_blocked": False},
        auditor_result={},
        deliverables=["file1.py"],
        applied_files=["file1.py"],
        workspace=tmp_path
    )

    assert not decision.can_complete
    assert decision.status == "FAILED"


def test_finalizer_noop_patch_blocks_when_deliverables_missing(tmp_path):
    """Test no-op patch blocks when deliverables are missing."""
    tracker = Mock()
    finalizer = PhaseFinalizer(tracker)

    # No deliverables exist yet
    decision = finalizer.assess_completion(
        phase_id="test-phase",
        phase_spec={},
        ci_result=None,
        baseline=None,
        quality_report={"quality_level": "high", "is_blocked": False},
        auditor_result={},
        deliverables=["file1.py"],
        applied_files=[],
        workspace=tmp_path,
        apply_stats={"mode": "patch", "patch_nonempty": False, "patch_bytes": 0}
    )

    assert not decision.can_complete
    assert "No-op detected" in decision.reason
    assert "missing" in decision.reason.lower()


def test_finalizer_noop_patch_allowed_when_deliverables_exist(tmp_path):
    """Test no-op patch allowed when deliverables already exist (idempotent phase)."""
    tracker = Mock()
    finalizer = PhaseFinalizer(tracker)

    # Create deliverable that already exists
    (tmp_path / "file1.py").write_text("# existing\n", encoding="utf-8")

    decision = finalizer.assess_completion(
        phase_id="test-phase",
        phase_spec={},
        ci_result=None,
        baseline=None,
        quality_report={"quality_level": "high", "is_blocked": False},
        auditor_result={},
        deliverables=["file1.py"],
        applied_files=[],
        workspace=tmp_path,
        apply_stats={"mode": "patch", "patch_nonempty": False, "patch_bytes": 0}
    )

    assert decision.can_complete
    assert len(decision.warnings) > 0
    assert "no changes" in decision.warnings[0].lower()


def test_finalizer_noop_structured_edit_blocks_when_deliverables_missing(tmp_path):
    """Test no-op structured_edit blocks when deliverables are missing."""
    tracker = Mock()
    finalizer = PhaseFinalizer(tracker)

    decision = finalizer.assess_completion(
        phase_id="test-phase",
        phase_spec={},
        ci_result=None,
        baseline=None,
        quality_report={"quality_level": "high", "is_blocked": False},
        auditor_result={},
        deliverables=["file1.py"],
        applied_files=[],
        workspace=tmp_path,
        apply_stats={
            "mode": "structured_edit",
            "operations_planned": 5,
            "operations_applied": 0,
            "operations_failed": 0
        }
    )

    assert not decision.can_complete
    assert "No-op detected" in decision.reason


def test_finalizer_noop_allowed_with_allow_noop_flag(tmp_path):
    """Test no-op allowed when phase_spec has allow_noop=true."""
    tracker = Mock()
    finalizer = PhaseFinalizer(tracker)

    decision = finalizer.assess_completion(
        phase_id="test-phase",
        phase_spec={"allow_noop": True},
        ci_result=None,
        baseline=None,
        quality_report={"quality_level": "high", "is_blocked": False},
        auditor_result={},
        deliverables=["file1.py"],
        applied_files=[],
        workspace=tmp_path,
        apply_stats={"mode": "patch", "patch_nonempty": False, "patch_bytes": 0}
    )

    assert decision.can_complete
    assert len(decision.warnings) > 0
    assert "allow_noop=true" in decision.warnings[0]


def test_finalizer_detect_noop_patch_mode():
    """Test _detect_noop method for patch mode."""
    tracker = Mock()
    finalizer = PhaseFinalizer(tracker)

    # Empty patch is a no-op
    assert finalizer._detect_noop({"mode": "patch", "patch_nonempty": False})

    # Non-empty patch is not a no-op
    assert not finalizer._detect_noop({"mode": "patch", "patch_nonempty": True, "patch_bytes": 100})


def test_finalizer_detect_noop_structured_edit_mode():
    """Test _detect_noop method for structured_edit mode."""
    tracker = Mock()
    finalizer = PhaseFinalizer(tracker)

    # Zero operations applied is a no-op
    assert finalizer._detect_noop({
        "mode": "structured_edit",
        "operations_planned": 5,
        "operations_applied": 0
    })

    # Some operations applied is not a no-op
    assert not finalizer._detect_noop({
        "mode": "structured_edit",
        "operations_planned": 5,
        "operations_applied": 3
    })
