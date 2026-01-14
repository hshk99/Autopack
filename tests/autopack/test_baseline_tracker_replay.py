"""
P0.1 Reliability Test: Baseline tracker replay determinism.

Validates that given identical inputs, baseline tracker produces bit-for-bit identical outputs.
This prevents parallel-run collisions and ensures reproducible CI decisions.
"""

import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import pytest

from autopack.test_baseline_tracker import TestBaseline, TestBaselineTracker


class TestBaselineReplayDeterminism:
    """Test that baseline tracker outputs are deterministic (replay-safe)."""

    def test_baseline_to_json_is_deterministic(self):
        """Baseline serialization should be deterministic (same input → same JSON)."""
        # Create baseline with unsorted lists (simulating set conversion)
        baseline = TestBaseline(
            run_id="test-run",
            commit_sha="abc123",
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            total_tests=10,
            passing_tests=7,
            failing_tests=2,
            error_tests=1,
            skipped_tests=0,
            failing_test_ids=["test_c.py::test_3", "test_a.py::test_1", "test_b.py::test_2"],
            error_signatures={
                "test_z.py::test_error": "AssertionError: Something failed",
                "test_a.py::test_import": "ImportError: No module named 'foo'",
            },
        )

        # Serialize twice
        json1 = baseline.to_json()
        json2 = baseline.to_json()

        # Should be identical
        assert json1 == json2

        # Parse and verify structure is stable
        data1 = json.loads(json1)
        data2 = json.loads(json2)
        assert data1 == data2

    def test_diff_output_is_sorted(self):
        """Delta computation should produce sorted lists (prevents replay variability)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            tracker = TestBaselineTracker(workspace=workspace, run_id="test-run")

            # Create baseline
            baseline = TestBaseline(
                run_id="test-run",
                commit_sha="abc123",
                timestamp=datetime.now(timezone.utc),
                total_tests=5,
                passing_tests=3,
                failing_tests=2,
                error_tests=0,
                skipped_tests=0,
                failing_test_ids=["test_a.py::test_1", "test_b.py::test_2"],
                error_signatures={},
            )

            # Create current report with new failures (intentionally unsorted order)
            current_report = {
                "summary": {"total": 5, "passed": 1, "failed": 4},
                "tests": [
                    {"nodeid": "test_a.py::test_1", "outcome": "failed"},  # Pre-existing
                    {
                        "nodeid": "test_z.py::test_9",
                        "outcome": "failed",
                    },  # New (should be last alphabetically)
                    {"nodeid": "test_c.py::test_3", "outcome": "failed"},  # New (middle)
                    {"nodeid": "test_b.py::test_2", "outcome": "passed"},  # Newly passing
                    {"nodeid": "test_d.py::test_4", "outcome": "passed"},
                ],
                "collectors": [],
            }

            report_path = workspace / "current.json"
            report_path.write_text(json.dumps(current_report), encoding="utf-8")

            # Compute delta
            delta = tracker.diff(baseline, report_path)

            # Verify lists are sorted
            assert delta.newly_failing == sorted(
                delta.newly_failing
            ), f"newly_failing should be sorted, got: {delta.newly_failing}"
            assert delta.newly_passing == sorted(
                delta.newly_passing
            ), f"newly_passing should be sorted, got: {delta.newly_passing}"
            assert delta.new_collection_errors == sorted(
                delta.new_collection_errors
            ), f"new_collection_errors should be sorted, got: {delta.new_collection_errors}"

            # Verify exact expected values (sorted)
            assert delta.newly_failing == ["test_c.py::test_3", "test_z.py::test_9"]
            assert delta.newly_passing == ["test_b.py::test_2"]

    def test_run_scoped_artifacts(self):
        """Tracker should use run-scoped paths to prevent parallel-run collisions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create two trackers with different run_ids
            tracker1 = TestBaselineTracker(workspace=workspace, run_id="run-001")
            tracker2 = TestBaselineTracker(workspace=workspace, run_id="run-002")

            # Verify they use different cache directories
            assert tracker1.cache_dir != tracker2.cache_dir
            assert "run-001" in str(tracker1.cache_dir)
            assert "run-002" in str(tracker2.cache_dir)

            # Verify cache directories don't overlap
            assert not str(tracker1.cache_dir).startswith(str(tracker2.cache_dir))
            assert not str(tracker2.cache_dir).startswith(str(tracker1.cache_dir))

    def test_legacy_mode_without_run_id(self):
        """Tracker should still work without run_id (backward compatibility)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create tracker without run_id (legacy mode)
            tracker = TestBaselineTracker(workspace=workspace, run_id=None)

            # Should use global cache dir (not run-scoped)
            assert tracker.run_id is None
            assert "baselines" in str(tracker.cache_dir)
            # Should not contain a run-specific subdirectory
            assert str(tracker.cache_dir).endswith("baselines")

    def test_collection_error_blocking_detection(self):
        """Collection errors should be detected even without baseline (hard block)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            tracker = TestBaselineTracker(workspace=workspace, run_id="test-run")

            # Create report with collection error (exitcode=2, no tests)
            current_report = {
                "exitcode": 2,
                "summary": {"total": 0},
                "tests": [],
                "collectors": [
                    {
                        "nodeid": "tests/test_broken.py",
                        "outcome": "failed",
                        "longrepr": "ImportError: No module named 'nonexistent_module'\nCannot import test module",
                    }
                ],
            }

            report_path = workspace / "collection_error.json"
            report_path.write_text(json.dumps(current_report), encoding="utf-8")

            # Create minimal baseline (empty)
            baseline = TestBaseline(
                run_id="test-run",
                commit_sha="abc123",
                timestamp=datetime.now(timezone.utc),
                total_tests=0,
                passing_tests=0,
                failing_tests=0,
                error_tests=0,
                skipped_tests=0,
                failing_test_ids=[],
                error_signatures={},
            )

            # Compute delta - should detect new collection error
            delta = tracker.diff(baseline, report_path)

            assert len(delta.new_collection_errors) == 1
            assert "tests/test_broken.py" in delta.new_collection_errors[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
