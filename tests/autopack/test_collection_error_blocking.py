"""
P0.1 Reliability Test: Collection error hard blocking.

Validates that collection/import errors (pytest exitcode=2, failed collectors)
ALWAYS cause phase failure, regardless of baseline state.

This prevents silent acceptance of broken test suites.
"""
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import pytest

from autopack.test_baseline_tracker import TestBaseline, TestBaselineTracker
from autopack.phase_finalizer import PhaseFinalizer


class TestCollectionErrorBlocking:
    """Test that collection errors are hard blocks."""

    def test_collection_error_blocks_even_without_baseline(self):
        """Collection errors should block completion even when baseline is unavailable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            tracker = TestBaselineTracker(workspace=workspace, run_id="test-run")
            finalizer = PhaseFinalizer(baseline_tracker=tracker)

            # Create CI result with collection error
            ci_report = {
                "exitcode": 2,
                "summary": {"total": 0},
                "tests": [],
                "collectors": [
                    {
                        "nodeid": "tests/test_broken.py",
                        "outcome": "failed",
                        "longrepr": "ImportError: No module named 'broken_dep'"
                    }
                ]
            }

            report_path = workspace / "ci_result.json"
            report_path.write_text(json.dumps(ci_report), encoding='utf-8')

            ci_result = {
                "report_path": str(report_path),
                "passed": False,
                "suspicious_zero_tests": True
            }

            # Assess completion without baseline (simulates first run)
            decision = finalizer.assess_completion(
                phase_id="test-phase",
                phase_spec={},
                ci_result=ci_result,
                baseline=None,  # No baseline available
                quality_report=None,
                auditor_result=None,
                deliverables=[],
                applied_files=[],
                workspace=workspace
            )

            # Should be blocked
            assert not decision.can_complete
            assert decision.status == "FAILED"
            assert any("collection" in issue.lower() or "import" in issue.lower()
                      for issue in decision.blocking_issues), \
                f"Expected collection/import error in blocking_issues, got: {decision.blocking_issues}"

    def test_persistent_collection_error_blocks_after_retry(self):
        """Persistent collection errors (failed twice) should block completion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            tracker = TestBaselineTracker(workspace=workspace, run_id="test-run")
            finalizer = PhaseFinalizer(baseline_tracker=tracker)

            # Create baseline with no errors
            baseline = TestBaseline(
                run_id="test-run",
                commit_sha="abc123",
                timestamp=datetime.now(timezone.utc),
                total_tests=5,
                passing_tests=5,
                failing_tests=0,
                error_tests=0,
                skipped_tests=0,
                failing_test_ids=[],
                error_signatures={}
            )

            # Create current report with NEW collection error
            ci_report = {
                "exitcode": 2,
                "summary": {"total": 0},
                "tests": [],
                "collectors": [
                    {
                        "nodeid": "tests/test_new_broken.py",
                        "outcome": "failed",
                        "longrepr": "SyntaxError: invalid syntax"
                    }
                ]
            }

            report_path = workspace / "ci_result.json"
            report_path.write_text(json.dumps(ci_report), encoding='utf-8')

            # Create retry report (collection error persists)
            retry_report = {
                "exitcode": 2,
                "summary": {"total": 0},
                "tests": [],
                "collectors": [
                    {
                        "nodeid": "tests/test_new_broken.py",
                        "outcome": "failed",
                        "longrepr": "SyntaxError: invalid syntax"
                    }
                ]
            }

            retry_path = workspace / ".autonomous_runs" / "test-run" / "ci" / "retry.json"
            retry_path.parent.mkdir(parents=True, exist_ok=True)
            retry_path.write_text(json.dumps(retry_report), encoding='utf-8')

            ci_result = {
                "report_path": str(report_path),
                "passed": False,
                "suspicious_zero_tests": True
            }

            # Assess completion
            decision = finalizer.assess_completion(
                phase_id="test-phase",
                phase_spec={},
                ci_result=ci_result,
                baseline=baseline,
                quality_report=None,
                auditor_result=None,
                deliverables=[],
                applied_files=[],
                workspace=workspace
            )

            # Should be blocked due to persistent collection error
            assert not decision.can_complete
            assert decision.status == "FAILED"
            assert any("collection" in issue.lower() for issue in decision.blocking_issues), \
                f"Expected collection error in blocking_issues, got: {decision.blocking_issues}"

    def test_zero_tests_blocks_when_suspicious(self):
        """Zero tests detected with non-zero exitcode should block (collection failure)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            tracker = TestBaselineTracker(workspace=workspace, run_id="test-run")
            finalizer = PhaseFinalizer(baseline_tracker=tracker)

            # Create report with zero tests but non-zero exitcode (collection failure signal)
            ci_report = {
                "exitcode": 2,
                "summary": {"total": 0},
                "tests": [],
                "collectors": []  # Empty collectors but exitcode indicates failure
            }

            report_path = workspace / "ci_result.json"
            report_path.write_text(json.dumps(ci_report), encoding='utf-8')

            ci_result = {
                "report_path": str(report_path),
                "passed": False,
                "suspicious_zero_tests": True  # Executor flagged this as suspicious
            }

            # Assess completion
            decision = finalizer.assess_completion(
                phase_id="test-phase",
                phase_spec={},
                ci_result=ci_result,
                baseline=None,
                quality_report=None,
                auditor_result=None,
                deliverables=[],
                applied_files=[],
                workspace=workspace
            )

            # Should be blocked
            assert not decision.can_complete
            assert decision.status == "FAILED"
            assert any("0 tests" in issue or "collection" in issue.lower() or
                      ("total_tests=0" in issue and "exitcode" in issue)
                      for issue in decision.blocking_issues), \
                f"Expected zero-test blocking issue, got: {decision.blocking_issues}"

    def test_legitimate_zero_tests_allowed(self):
        """Zero tests with exitcode=0 and no suspicious flag should be allowed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            tracker = TestBaselineTracker(workspace=workspace, run_id="test-run")
            finalizer = PhaseFinalizer(baseline_tracker=tracker)

            # Create report with zero tests but successful run (e.g., no tests matched filter)
            ci_report = {
                "exitcode": 0,
                "summary": {"total": 0},
                "tests": [],
                "collectors": []
            }

            report_path = workspace / "ci_result.json"
            report_path.write_text(json.dumps(ci_report), encoding='utf-8')

            ci_result = {
                "report_path": str(report_path),
                "passed": True,
                "suspicious_zero_tests": False  # Not flagged as suspicious
            }

            # Assess completion
            decision = finalizer.assess_completion(
                phase_id="test-phase",
                phase_spec={},
                ci_result=ci_result,
                baseline=None,
                quality_report=None,
                auditor_result=None,
                deliverables=[],
                applied_files=[],
                workspace=workspace
            )

            # Should NOT be blocked (legitimate empty test run)
            assert decision.can_complete
            assert decision.status == "COMPLETE"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
