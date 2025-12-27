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
