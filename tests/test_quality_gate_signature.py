"""
Test QualityGate.assess_phase signature compatibility.

Ensures that assess_phase() can be called with minimal args (backwards compatibility).
"""
import pytest
from pathlib import Path
from autopack.quality_gate import QualityGate


def test_assess_phase_minimal_args():
    """Test that assess_phase works with minimal arguments."""
    qg = QualityGate(repo_root=Path.cwd())

    # Minimal call - should not raise TypeError
    report = qg.assess_phase(
        phase_id="test-phase",
        phase_spec={"name": "Test Phase"},
        auditor_result={"approved": True, "issues_found": []},
    )

    # Should return a valid QualityReport
    assert report is not None
    assert report.quality_level in ["PASS", "WARNING", "BLOCKED"]


def test_assess_phase_with_optional_args():
    """Test that assess_phase works with all optional args."""
    qg = QualityGate(repo_root=Path.cwd())

    # Full call with all arguments
    report = qg.assess_phase(
        phase_id="test-phase",
        phase_spec={"name": "Test Phase"},
        auditor_result={"approved": True, "issues_found": []},
        ci_result={"success": True},
        coverage_delta=2.5,
        patch_content="diff --git a/test.py",
        files_changed=["test.py"],
    )

    assert report is not None
    assert report.quality_level == "PASS"


def test_assess_phase_missing_ci_result():
    """Test that assess_phase handles missing ci_result gracefully."""
    qg = QualityGate(repo_root=Path.cwd())

    # Call without ci_result (common in llm_service.py)
    report = qg.assess_phase(
        phase_id="test-phase",
        phase_spec={"name": "Test Phase"},
        auditor_result={"approved": True, "issues_found": []},
        coverage_delta=0.0,
    )

    assert report is not None
    # Should not crash with "missing patch_content" error


def test_assess_phase_ci_failure():
    """Test that assess_phase correctly blocks on CI failure."""
    qg = QualityGate(repo_root=Path.cwd())

    report = qg.assess_phase(
        phase_id="test-phase",
        phase_spec={"name": "Test Phase"},
        auditor_result={"approved": True, "issues_found": []},
        ci_result={"success": False},
    )

    assert report.quality_level == "BLOCKED"
    assert "CI tests failed" in report.issues
