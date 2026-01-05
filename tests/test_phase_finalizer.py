"""
Unit tests for PhaseFinalizer (BUILD-127 Phase 1).

Tests:
- Gate validation logic
- Blocking conditions
- Phase validation_tests overlap
- Warning vs blocking thresholds
"""

import pytest
from unittest.mock import Mock
from datetime import datetime, timezone

from autopack.phase_finalizer import PhaseFinalizer, PhaseFinalizationDecision
from autopack.test_baseline_tracker import TestBaseline, TestDelta


@pytest.fixture
def mock_baseline_tracker():
    """Mock baseline tracker."""
    tracker = Mock()
    return tracker


@pytest.fixture
def finalizer(mock_baseline_tracker):
    """Create finalizer instance."""
    return PhaseFinalizer(mock_baseline_tracker)


@pytest.fixture
def sample_baseline():
    """Sample baseline."""
    return TestBaseline(
        run_id="test-run",
        commit_sha="abc123",
        timestamp=datetime.now(timezone.utc),
        total_tests=100,
        passing_tests=90,
        failing_tests=10,
        error_tests=0,
        skipped_tests=0,
        failing_test_ids=["tests/test_old.py::test_fail"],
        error_signatures={},
    )


class TestPhaseFinalizationDecision:
    """Test PhaseFinalizationDecision dataclass."""

    def test_can_complete_true(self):
        """Test decision allowing completion."""
        decision = PhaseFinalizationDecision(
            can_complete=True, status="COMPLETE", reason="All gates passed"
        )

        assert decision.can_complete
        assert decision.status == "COMPLETE"
        assert len(decision.blocking_issues) == 0

    def test_can_complete_false(self):
        """Test decision blocking completion."""
        decision = PhaseFinalizationDecision(
            can_complete=False,
            status="FAILED",
            reason="Test failures",
            blocking_issues=["5 test failures"],
            warnings=["Code quality low"],
        )

        assert not decision.can_complete
        assert decision.status == "FAILED"
        assert len(decision.blocking_issues) == 1
        assert len(decision.warnings) == 1


class TestPhaseFinalizer:
    """Test PhaseFinalizer."""

    def test_assess_completion_all_gates_pass(self, finalizer, mock_baseline_tracker, tmp_path):
        """Test completion when all gates pass."""
        # Mock CI delta - no regressions
        delta = TestDelta(regression_severity="none")
        mock_baseline_tracker.compute_full_delta.return_value = delta

        # Deliverables exist in workspace
        (tmp_path / "file1.py").write_text("# ok\n", encoding="utf-8")

        phase_spec = {"validation": {"tests": []}}

        report_path = tmp_path / "report.json"
        report_path.write_text("{}", encoding="utf-8")

        decision = finalizer.assess_completion(
            phase_id="test-phase",
            phase_spec=phase_spec,
            ci_result={"report_path": str(report_path)},
            baseline=Mock(),
            quality_report={"quality_level": "high", "is_blocked": False},
            auditor_result={},
            deliverables=["file1.py"],
            applied_files=["file1.py"],
            workspace=tmp_path,
        )

        assert decision.can_complete
        assert decision.status == "COMPLETE"
        assert len(decision.blocking_issues) == 0

    def test_assess_completion_ci_persistent_failures_block(
        self, finalizer, mock_baseline_tracker, sample_baseline, tmp_path
    ):
        """Test CI persistent failures block completion."""
        # Mock CI delta - persistent failures
        delta = TestDelta(
            newly_failing_persistent=["tests/test_new.py::test_fail"], regression_severity="high"
        )
        mock_baseline_tracker.compute_full_delta.return_value = delta

        (tmp_path / "file1.py").write_text("# ok\n", encoding="utf-8")

        phase_spec = {"validation": {"tests": []}}

        # Create dummy report file
        report_path = tmp_path / "report.json"
        report_path.write_text("{}", encoding="utf-8")

        decision = finalizer.assess_completion(
            phase_id="test-phase",
            phase_spec=phase_spec,
            ci_result={"report_path": str(report_path)},
            baseline=sample_baseline,
            quality_report={"quality_level": "medium", "is_blocked": False},
            auditor_result={},
            deliverables=["file1.py"],
            applied_files=["file1.py"],
            workspace=tmp_path,
        )

        assert not decision.can_complete
        assert decision.status == "FAILED"
        assert any("HIGH regression" in issue for issue in decision.blocking_issues)

    def test_assess_completion_phase_validation_tests_block(
        self, finalizer, mock_baseline_tracker, sample_baseline, tmp_path
    ):
        """Test phase validation_tests failures block even on medium severity."""
        # Mock CI delta - medium severity, but overlaps with phase validation_tests
        delta = TestDelta(
            newly_failing_persistent=["tests/test_critical.py::test_important"],
            regression_severity="low",  # Would normally not block
        )
        mock_baseline_tracker.compute_full_delta.return_value = delta

        (tmp_path / "file1.py").write_text("# ok\n", encoding="utf-8")

        # Phase specifies this test as critical
        phase_spec = {"validation": {"tests": ["tests/test_critical.py::test_important"]}}

        report_path = tmp_path / "report.json"
        report_path.write_text("{}", encoding="utf-8")

        decision = finalizer.assess_completion(
            phase_id="test-phase",
            phase_spec=phase_spec,
            ci_result={"report_path": str(report_path)},
            baseline=sample_baseline,
            quality_report={"quality_level": "high", "is_blocked": False},
            auditor_result={},
            deliverables=["file1.py"],
            applied_files=["file1.py"],
            workspace=tmp_path,
        )

        assert not decision.can_complete
        assert decision.status == "FAILED"
        assert any("Phase validation tests failed" in issue for issue in decision.blocking_issues)

    def test_assess_completion_collection_errors_block(
        self, finalizer, mock_baseline_tracker, sample_baseline, tmp_path
    ):
        """Test persistent collection errors block completion."""
        delta = TestDelta(
            new_collection_errors_persistent=["tests/test_broken.py::test_import_fail"],
            regression_severity="low",
        )
        mock_baseline_tracker.compute_full_delta.return_value = delta

        (tmp_path / "file1.py").write_text("# ok\n", encoding="utf-8")

        phase_spec = {"validation": {"tests": []}}

        report_path = tmp_path / "report.json"
        report_path.write_text("{}", encoding="utf-8")

        decision = finalizer.assess_completion(
            phase_id="test-phase",
            phase_spec=phase_spec,
            ci_result={"report_path": str(report_path)},
            baseline=sample_baseline,
            quality_report={"quality_level": "high", "is_blocked": False},
            auditor_result={},
            deliverables=["file1.py"],
            applied_files=["file1.py"],
            workspace=tmp_path,
        )

        assert not decision.can_complete
        assert any("collection errors" in issue for issue in decision.blocking_issues)

    def test_assess_completion_failed_collectors_block_without_baseline(
        self, finalizer, mock_baseline_tracker, tmp_path
    ):
        """
        pytest-json-report encodes collection/import errors as failed collectors (exitcode=2),
        often with tests=[] and summary.total=0. This must block deterministically even without
        a baseline (baseline capture can fail/time out).
        """
        (tmp_path / "file1.py").write_text("# ok\n", encoding="utf-8")

        report_path = tmp_path / "pytest_report.json"
        report_path.write_text(
            """
{
  "exitcode": 2,
  "summary": { "total": 0, "collected": 10 },
  "tests": [],
  "collectors": [
    {
      "nodeid": "tests/some_module/test_broken_import.py",
      "outcome": "failed",
      "result": [],
      "longrepr": "ImportError while importing test module 'tests/some_module/test_broken_import.py'\\nE   ImportError: cannot import name 'X'"
    }
  ]
}
            """.strip(),
            encoding="utf-8",
        )

        decision = finalizer.assess_completion(
            phase_id="test-phase",
            phase_spec={"validation": {"tests": []}},
            ci_result={
                "report_path": str(report_path),
                "passed": False,
                "suspicious_zero_tests": True,
            },
            baseline=None,
            quality_report={"quality_level": "high", "is_blocked": False},
            auditor_result={},
            deliverables=["file1.py"],
            applied_files=["file1.py"],
            workspace=tmp_path,
        )

        assert not decision.can_complete
        assert decision.status == "FAILED"
        assert any("CI collection/import error" in issue for issue in decision.blocking_issues)
        # With baseline=None, we should not attempt delta computation.
        assert not mock_baseline_tracker.compute_full_delta.called

    def test_assess_completion_flaky_tests_warn_only(
        self, finalizer, mock_baseline_tracker, sample_baseline, tmp_path
    ):
        """Test flaky tests generate warnings, not blocks."""
        delta = TestDelta(
            flaky_suspects=["tests/test_flaky.py::test_intermittent"], regression_severity="none"
        )
        mock_baseline_tracker.compute_full_delta.return_value = delta
        (tmp_path / "file1.py").write_text("# ok\n", encoding="utf-8")

        phase_spec = {"validation": {"tests": []}}

        report_path = tmp_path / "report.json"
        report_path.write_text("{}", encoding="utf-8")

        decision = finalizer.assess_completion(
            phase_id="test-phase",
            phase_spec=phase_spec,
            ci_result={"report_path": str(report_path)},
            baseline=sample_baseline,
            quality_report={"quality_level": "high", "is_blocked": False},
            auditor_result={},
            deliverables=["file1.py"],
            applied_files=["file1.py"],
            workspace=tmp_path,
        )

        assert decision.can_complete  # Should NOT block
        assert any("Flaky tests" in w for w in decision.warnings)

    def test_assess_completion_quality_gate_blocked(
        self, finalizer, mock_baseline_tracker, tmp_path
    ):
        """Test quality gate blocks completion."""
        delta = TestDelta(regression_severity="none")
        mock_baseline_tracker.compute_full_delta.return_value = delta
        (tmp_path / "file1.py").write_text("# ok\n", encoding="utf-8")

        phase_spec = {"validation": {"tests": []}}

        decision = finalizer.assess_completion(
            phase_id="test-phase",
            phase_spec=phase_spec,
            ci_result=None,
            baseline=None,
            quality_report={"quality_level": "low", "is_blocked": True},
            auditor_result={},
            deliverables=["file1.py"],
            applied_files=["file1.py"],
            workspace=tmp_path,
        )

        assert not decision.can_complete
        assert any("Quality gate blocked" in issue for issue in decision.blocking_issues)

    def test_assess_completion_missing_deliverables_block(
        self, finalizer, mock_baseline_tracker, tmp_path
    ):
        """Test missing deliverables block completion."""
        delta = TestDelta(regression_severity="none")
        mock_baseline_tracker.compute_full_delta.return_value = delta

        phase_spec = {"validation": {"tests": []}}

        decision = finalizer.assess_completion(
            phase_id="test-phase",
            phase_spec=phase_spec,
            ci_result=None,
            baseline=None,
            quality_report={"quality_level": "high", "is_blocked": False},
            auditor_result={},
            deliverables=["file1.py", "tests/test_missing.py"],
            applied_files=["file1.py"],
            workspace=tmp_path,
        )

        assert not decision.can_complete
        assert any("Missing required deliverables" in issue for issue in decision.blocking_issues)

    def test_assess_completion_medium_regression_blocks(
        self, finalizer, mock_baseline_tracker, sample_baseline, tmp_path
    ):
        """Test medium regression blocks completion (delta-based strict gating)."""
        delta = TestDelta(
            newly_failing_persistent=["test1.py::test1", "test2.py::test2"],
            regression_severity="medium",
        )
        mock_baseline_tracker.compute_full_delta.return_value = delta
        (tmp_path / "file1.py").write_text("# ok\n", encoding="utf-8")

        # No phase validation_tests specified
        phase_spec = {"validation": {"tests": []}}

        report_path = tmp_path / "report.json"
        report_path.write_text("{}", encoding="utf-8")

        decision = finalizer.assess_completion(
            phase_id="test-phase",
            phase_spec=phase_spec,
            ci_result={"report_path": str(report_path)},
            baseline=sample_baseline,
            quality_report={"quality_level": "high", "is_blocked": False},
            auditor_result={},
            deliverables=["file1.py"],
            applied_files=["file1.py"],
            workspace=tmp_path,
        )

        assert not decision.can_complete
        assert any("MEDIUM regression" in issue for issue in decision.blocking_issues)

    def test_should_block_on_ci(self, finalizer):
        """Test should_block_on_ci logic."""
        # Collection errors → block
        delta1 = TestDelta(new_collection_errors_persistent=["test1"])
        assert finalizer.should_block_on_ci(delta1, set())

        # Phase validation tests failed → block
        delta2 = TestDelta(newly_failing_persistent=["tests/test_critical.py::test1"])
        phase_tests = {"tests/test_critical.py::test1"}
        assert finalizer.should_block_on_ci(delta2, phase_tests)

        # High severity → block
        delta3 = TestDelta(regression_severity="high")
        assert finalizer.should_block_on_ci(delta3, set())

        # Medium severity, no phase tests → block
        delta4 = TestDelta(regression_severity="medium")
        assert finalizer.should_block_on_ci(delta4, set())

    def test_assess_completion_ci_report_not_json_does_not_crash(
        self,
        finalizer,
        mock_baseline_tracker,
        sample_baseline,
        tmp_path,
    ):
        """
        Regression test: PhaseFinalizer must not crash if ci_result.report_path points to a non-JSON file.

        This can happen if a CI adapter only persisted a text log or produced an empty/truncated file.
        In that case, delta computation should fail gracefully and completion should proceed based on
        other gates (quality/deliverables).
        """
        bad_report = tmp_path / "pytest.log"
        bad_report.write_text("not json", encoding="utf-8")

        # If compute_full_delta is called, it will attempt json.loads and would raise.
        # Our PhaseFinalizer wraps delta computation, so this shouldn't propagate.
        def _boom(*args, **kwargs):
            raise ValueError("boom")

        mock_baseline_tracker.compute_full_delta.side_effect = _boom

        decision = finalizer.assess_completion(
            phase_id="test-phase",
            phase_spec={"validation": {"tests": []}},
            ci_result={"report_path": str(bad_report)},
            baseline=sample_baseline,
            quality_report={"quality_level": "high", "is_blocked": False},
            auditor_result={},
            deliverables=[],  # keep gates minimal
            applied_files=[],
            workspace=tmp_path,
        )

        assert decision.can_complete
        assert decision.status == "COMPLETE"
