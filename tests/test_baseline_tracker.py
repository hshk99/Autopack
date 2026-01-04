"""
Unit tests for TestBaselineTracker (BUILD-127 Phase 1).

Tests:
- Baseline capture and caching
- Delta computation
- Flaky test retry logic
- Severity calculation
"""
import pytest
import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from autopack.test_baseline_tracker import (
    TestBaseline,
    TestDelta,
    TestBaselineTracker
)


@pytest.fixture
def workspace(tmp_path):
    """Create temporary workspace."""
    return tmp_path


@pytest.fixture
def tracker(workspace):
    """Create tracker instance."""
    return TestBaselineTracker(workspace)


@pytest.fixture
def sample_baseline():
    """Sample baseline."""
    return TestBaseline(
        run_id="test-run",
        commit_sha="abc123",
        timestamp=datetime.now(timezone.utc),
        total_tests=100,
        passing_tests=90,
        failing_tests=8,
        error_tests=2,
        skipped_tests=0,
        failing_test_ids=[
            "tests/test_foo.py::test_failing_1",
            "tests/test_foo.py::test_failing_2"
        ],
        error_signatures={
            "tests/test_bar.py::test_error_1": "ImportError: No module named 'missing'",
            "tests/test_bar.py::test_error_2": "AttributeError: 'NoneType' object has no attribute 'value'"
        }
    )


class TestTestBaseline:
    """Test TestBaseline dataclass."""

    def test_to_json(self, sample_baseline):
        """Test JSON serialization."""
        json_str = sample_baseline.to_json()
        data = json.loads(json_str)

        assert data["run_id"] == "test-run"
        assert data["commit_sha"] == "abc123"
        assert data["total_tests"] == 100
        assert data["passing_tests"] == 90
        assert len(data["failing_test_ids"]) == 2

    def test_from_json(self, sample_baseline):
        """Test JSON deserialization."""
        json_str = sample_baseline.to_json()
        restored = TestBaseline.from_json(json_str)

        assert restored.run_id == sample_baseline.run_id
        assert restored.commit_sha == sample_baseline.commit_sha
        assert restored.total_tests == sample_baseline.total_tests
        assert restored.failing_test_ids == sample_baseline.failing_test_ids


class TestTestDelta:
    """Test TestDelta severity calculation."""

    def test_severity_none(self):
        """Test no regression."""
        delta = TestDelta()
        assert delta.calculate_severity() == "none"

    def test_severity_low(self):
        """Test low severity (1 persistent failure)."""
        delta = TestDelta(newly_failing_persistent=["test1"])
        assert delta.calculate_severity() == "low"

    def test_severity_medium(self):
        """Test medium severity (2-4 persistent failures)."""
        delta = TestDelta(newly_failing_persistent=["test1", "test2"])
        assert delta.calculate_severity() == "medium"

    def test_severity_high(self):
        """Test high severity (5-9 persistent failures)."""
        delta = TestDelta(newly_failing_persistent=["test1", "test2", "test3", "test4", "test5"])
        assert delta.calculate_severity() == "high"

    def test_severity_critical(self):
        """Test critical severity (10+ persistent failures)."""
        delta = TestDelta(newly_failing_persistent=[f"test{i}" for i in range(10)])
        assert delta.calculate_severity() == "critical"

    def test_severity_includes_collection_errors(self):
        """Test severity includes collection errors."""
        delta = TestDelta(
            newly_failing_persistent=["test1"],
            new_collection_errors_persistent=["test2", "test3", "test4"]
        )
        # Total = 4 → medium
        assert delta.calculate_severity() == "medium"


class TestTestBaselineTracker:
    """Test TestBaselineTracker."""

    def test_init(self, workspace):
        """Test tracker initialization."""
        tracker = TestBaselineTracker(workspace)
        assert tracker.workspace == workspace
        assert tracker.cache_dir.exists()

    @patch('subprocess.run')
    def test_capture_baseline_success(self, mock_run, tracker, workspace):
        """Test baseline capture with mocked pytest."""
        # Mock pytest output
        report_data = {
            "summary": {
                "total": 100,
                "passed": 90,
                "failed": 8,
                "error": 2,
                "skipped": 0
            },
            "tests": [
                {"nodeid": "tests/test_foo.py::test_failing_1", "outcome": "failed"},
                {"nodeid": "tests/test_bar.py::test_error_1", "outcome": "error",
                 "call": {"longrepr": "ImportError: No module named 'missing'"}}
            ]
        }

        # Create report file
        report_file = workspace / ".autonomous_runs" / "baseline.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(json.dumps(report_data))

        mock_run.return_value = Mock(returncode=0)

        baseline = tracker.capture_baseline(
            run_id="test-run",
            commit_sha="abc123"
        )

        assert baseline.total_tests == 100
        assert baseline.passing_tests == 90
        assert baseline.failing_tests == 8
        assert baseline.error_tests == 2
        assert len(baseline.failing_test_ids) == 2

    def test_capture_baseline_uses_cache(self, tracker, workspace, sample_baseline):
        """Test baseline cache reuse."""
        # Write cache
        cache_file = tracker.cache_dir / "abc123.json"
        cache_file.write_text(sample_baseline.to_json())

        # Should use cache (no subprocess call)
        baseline = tracker.capture_baseline(
            run_id="test-run",
            commit_sha="abc123"
        )

        assert baseline.run_id == "test-run"
        assert baseline.total_tests == 100

    def test_diff_newly_failing(self, tracker, workspace, sample_baseline):
        """Test delta computation - newly failing tests."""
        # Current report with new failure
        current_data = {
            "tests": [
                {"nodeid": "tests/test_foo.py::test_failing_1", "outcome": "failed"},
                {"nodeid": "tests/test_foo.py::test_failing_2", "outcome": "failed"},
                {"nodeid": "tests/test_new.py::test_new_fail", "outcome": "failed"}  # NEW
            ]
        }

        current_path = workspace / "current.json"
        current_path.write_text(json.dumps(current_data))

        delta = tracker.diff(sample_baseline, current_path)

        assert "tests/test_new.py::test_new_fail" in delta.newly_failing
        assert len(delta.newly_failing) == 1

    def test_diff_newly_passing(self, tracker, workspace, sample_baseline):
        """Test delta computation - newly passing tests."""
        # Current report with previously failing test now passing
        current_data = {
            "tests": [
                {"nodeid": "tests/test_foo.py::test_failing_1", "outcome": "passed"},  # NOW PASSING
                {"nodeid": "tests/test_foo.py::test_failing_2", "outcome": "failed"}
            ]
        }

        current_path = workspace / "current.json"
        current_path.write_text(json.dumps(current_data))

        delta = tracker.diff(sample_baseline, current_path)

        assert "tests/test_foo.py::test_failing_1" in delta.newly_passing

    @patch('subprocess.run')
    def test_retry_newly_failing_all_pass(self, mock_run, tracker, workspace):
        """Test retry - all tests pass on retry."""
        retry_data = {
            "tests": [
                {"nodeid": "tests/test_flaky.py::test1", "outcome": "passed"},
                {"nodeid": "tests/test_flaky.py::test2", "outcome": "passed"}
            ]
        }

        retry_path = workspace / ".autonomous_runs" / "retry.json"
        retry_path.parent.mkdir(parents=True, exist_ok=True)
        retry_path.write_text(json.dumps(retry_data))

        mock_run.return_value = Mock(returncode=0)

        outcomes = tracker.retry_newly_failing(
            ["tests/test_flaky.py::test1", "tests/test_flaky.py::test2"],
            workspace
        )

        assert outcomes["tests/test_flaky.py::test1"] == "passed"
        assert outcomes["tests/test_flaky.py::test2"] == "passed"

    @patch('subprocess.run')
    def test_retry_newly_failing_some_persist(self, mock_run, tracker, workspace):
        """Test retry - some tests still fail."""
        retry_data = {
            "tests": [
                {"nodeid": "tests/test_mixed.py::test1", "outcome": "passed"},
                {"nodeid": "tests/test_mixed.py::test2", "outcome": "failed"}
            ]
        }

        retry_path = workspace / ".autonomous_runs" / "retry.json"
        retry_path.parent.mkdir(parents=True, exist_ok=True)
        retry_path.write_text(json.dumps(retry_data))

        mock_run.return_value = Mock(returncode=0)

        outcomes = tracker.retry_newly_failing(
            ["tests/test_mixed.py::test1", "tests/test_mixed.py::test2"],
            workspace
        )

        assert outcomes["tests/test_mixed.py::test1"] == "passed"
        assert outcomes["tests/test_mixed.py::test2"] == "failed"

    @patch('subprocess.run')
    def test_compute_full_delta_with_flaky(self, mock_run, tracker, workspace, sample_baseline):
        """Test full delta computation with flaky detection."""
        # Current report
        current_data = {
            "tests": [
                {"nodeid": "tests/test_foo.py::test_failing_1", "outcome": "failed"},
                {"nodeid": "tests/test_foo.py::test_failing_2", "outcome": "failed"},
                {"nodeid": "tests/test_flaky.py::test1", "outcome": "failed"}  # Will pass on retry
            ]
        }

        current_path = workspace / ".autonomous_runs" / "current.json"
        current_path.parent.mkdir(parents=True, exist_ok=True)
        current_path.write_text(json.dumps(current_data))

        # Retry report - flaky test passes
        retry_data = {
            "tests": [
                {"nodeid": "tests/test_flaky.py::test1", "outcome": "passed"}
            ]
        }

        retry_path = workspace / ".autonomous_runs" / "retry.json"
        retry_path.write_text(json.dumps(retry_data))

        mock_run.return_value = Mock(returncode=0)

        delta = tracker.compute_full_delta(sample_baseline, current_path, workspace)

        # Flaky test should be in flaky_suspects (not persistent)
        assert "tests/test_flaky.py::test1" in delta.flaky_suspects
        assert "tests/test_flaky.py::test1" not in delta.newly_failing_persistent

    def test_extract_error_signature(self, tracker):
        """Test error signature extraction."""
        test_data = {
            "call": {
                "longrepr": "ImportError: No module named 'missing'\n  File '/path/to/file.py', line 10\n    import missing"
            }
        }

        signature = tracker._extract_error_signature(test_data)
        assert "ImportError" in signature
        assert len(signature) <= 200

    def test_extract_error_signature_truncates(self, tracker):
        """Test error signature truncation."""
        long_error = "Error: " + "x" * 300
        test_data = {
            "call": {
                "longrepr": long_error
            }
        }

        signature = tracker._extract_error_signature(test_data)
        assert len(signature) == 200


class TestIntegration:
    """Integration tests."""

    @patch('subprocess.run')
    def test_end_to_end_baseline_and_delta(self, mock_run, tracker, workspace):
        """Test full workflow: capture baseline, compute delta with retry."""
        # Baseline capture
        baseline_data = {
            "summary": {"total": 10, "passed": 9, "failed": 1, "error": 0, "skipped": 0},
            "tests": [
                {"nodeid": "tests/test_old.py::test_failing", "outcome": "failed"}
            ]
        }

        baseline_path = workspace / ".autonomous_runs" / "baseline.json"
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(baseline_data))

        mock_run.return_value = Mock(returncode=0)

        baseline = tracker.capture_baseline("run1", "commit1")

        # Current report - 2 new failures
        current_data = {
            "tests": [
                {"nodeid": "tests/test_old.py::test_failing", "outcome": "failed"},
                {"nodeid": "tests/test_new.py::test_fail1", "outcome": "failed"},
                {"nodeid": "tests/test_new.py::test_fail2", "outcome": "failed"}
            ]
        }

        current_path = workspace / ".autonomous_runs" / "current.json"
        current_path.write_text(json.dumps(current_data))

        # Retry - one passes (flaky), one fails (persistent)
        retry_data = {
            "tests": [
                {"nodeid": "tests/test_new.py::test_fail1", "outcome": "passed"},
                {"nodeid": "tests/test_new.py::test_fail2", "outcome": "failed"}
            ]
        }

        retry_path = workspace / ".autonomous_runs" / "retry.json"
        retry_path.write_text(json.dumps(retry_data))

        delta = tracker.compute_full_delta(baseline, current_path, workspace)

        # Assertions
        assert "tests/test_new.py::test_fail1" in delta.flaky_suspects
        assert "tests/test_new.py::test_fail2" in delta.newly_failing_persistent
        assert delta.regression_severity == "low"  # 1 persistent failure
