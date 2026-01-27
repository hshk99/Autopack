"""Tests for FlakyTestDetector in autopack.analytics module."""

import json
from pathlib import Path

import pytest

from autopack.analytics.flaky_test_detector import FlakyTestDetector


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for state files."""
    return tmp_path


@pytest.fixture
def sample_ci_retry_state() -> dict:
    """Sample ci_retry_state.json data with flaky and consistent failures."""
    return {
        "retries": [
            # Flaky test - fails then succeeds (high flakiness)
            {
                "test_name": "test_auth_login",
                "outcome": "failed",
                "attempt": 1,
                "workflow": "ci",
                "failure_reason": "timeout",
            },
            {
                "test_name": "test_auth_login",
                "outcome": "failed",
                "attempt": 2,
                "workflow": "ci",
                "failure_reason": "timeout",
            },
            {
                "test_name": "test_auth_login",
                "outcome": "success",
                "attempt": 3,
                "workflow": "ci",
            },
            # Another flaky test with mixed outcomes
            {
                "test_name": "test_api_rate_limit",
                "outcome": "failed",
                "attempt": 1,
                "workflow": "integration",
                "failure_reason": "connection_refused",
            },
            {
                "test_name": "test_api_rate_limit",
                "outcome": "success",
                "attempt": 2,
                "workflow": "integration",
            },
            {
                "test_name": "test_api_rate_limit",
                "outcome": "failed",
                "attempt": 3,
                "workflow": "integration",
                "failure_reason": "connection_timeout",
            },
            {
                "test_name": "test_api_rate_limit",
                "outcome": "success",
                "attempt": 4,
                "workflow": "integration",
            },
            # Consistent failure (not flaky, just broken)
            {
                "test_name": "test_db_connection",
                "outcome": "failed",
                "attempt": 1,
                "workflow": "unit",
                "failure_reason": "connection_refused",
            },
            {
                "test_name": "test_db_connection",
                "outcome": "failed",
                "attempt": 2,
                "workflow": "unit",
                "failure_reason": "connection_refused",
            },
            {
                "test_name": "test_db_connection",
                "outcome": "failed",
                "attempt": 3,
                "workflow": "unit",
                "failure_reason": "connection_refused",
            },
            # Stable test (all pass)
            {
                "test_name": "test_simple_math",
                "outcome": "success",
                "attempt": 1,
                "workflow": "unit",
            },
            {
                "test_name": "test_simple_math",
                "outcome": "success",
                "attempt": 1,
                "workflow": "unit",
            },
            {
                "test_name": "test_simple_math",
                "outcome": "success",
                "attempt": 1,
                "workflow": "unit",
            },
        ]
    }


@pytest.fixture
def populated_ci_state_file(
    temp_state_dir: Path,
    sample_ci_retry_state: dict,
) -> Path:
    """Create CI state file in temp directory."""
    ci_state_path = temp_state_dir / "ci_retry_state.json"
    ci_state_path.write_text(json.dumps(sample_ci_retry_state))
    return ci_state_path


class TestFlakyTestDetectorInit:
    """Tests for FlakyTestDetector initialization."""

    def test_init_with_file_path(self, temp_state_dir: Path) -> None:
        """Test detector initializes with file path."""
        file_path = temp_state_dir / "ci_retry_state.json"
        detector = FlakyTestDetector(file_path)
        assert detector.ci_state_path == file_path

    def test_init_with_directory_path(self, temp_state_dir: Path) -> None:
        """Test detector initializes with directory path."""
        detector = FlakyTestDetector(temp_state_dir)
        assert detector.ci_state_path == temp_state_dir / "ci_retry_state.json"

    def test_init_with_string_path(self, temp_state_dir: Path) -> None:
        """Test detector accepts string paths."""
        detector = FlakyTestDetector(str(temp_state_dir))
        assert detector.ci_state_path == Path(str(temp_state_dir)) / "ci_retry_state.json"


class TestAnalyzeFailurePatterns:
    """Tests for analyze_failure_patterns() method."""

    def test_empty_file(self, temp_state_dir: Path) -> None:
        """Test analysis with no CI retry data."""
        detector = FlakyTestDetector(temp_state_dir)
        result = detector.analyze_failure_patterns()
        assert result == []

    def test_detects_flaky_tests(self, populated_ci_state_file: Path) -> None:
        """Test flaky test detection returns tests with scores."""
        detector = FlakyTestDetector(populated_ci_state_file)
        result = detector.analyze_failure_patterns()

        # Should return list of (test_id, score) tuples
        assert isinstance(result, list)
        assert len(result) > 0

        # Check structure
        for test_id, score in result:
            assert isinstance(test_id, str)
            assert isinstance(score, float)
            assert 0.0 <= score <= 1.0

    def test_flaky_tests_sorted_by_score(self, populated_ci_state_file: Path) -> None:
        """Test that results are sorted by flakiness score descending."""
        detector = FlakyTestDetector(populated_ci_state_file)
        result = detector.analyze_failure_patterns()

        if len(result) > 1:
            scores = [score for _, score in result]
            assert scores == sorted(scores, reverse=True)

    def test_excludes_consistent_failures(self, populated_ci_state_file: Path) -> None:
        """Test that consistently failing tests have low flakiness scores."""
        detector = FlakyTestDetector(populated_ci_state_file)
        result = detector.analyze_failure_patterns()

        # test_db_connection always fails - should not be highly flaky
        db_test_scores = [score for test_id, score in result if test_id == "test_db_connection"]
        # Either not in list or has low score
        assert len(db_test_scores) == 0 or db_test_scores[0] < 0.3

    def test_excludes_stable_tests(self, populated_ci_state_file: Path) -> None:
        """Test that stable tests are not flagged as flaky."""
        detector = FlakyTestDetector(populated_ci_state_file)
        result = detector.analyze_failure_patterns()

        # test_simple_math always passes - should not be in flaky list
        stable_tests = [test_id for test_id, _ in result if test_id == "test_simple_math"]
        assert len(stable_tests) == 0


class TestShouldAutoRetry:
    """Tests for should_auto_retry() method."""

    def test_unknown_test_returns_false(self, temp_state_dir: Path) -> None:
        """Test that unknown tests recommend investigation."""
        detector = FlakyTestDetector(temp_state_dir)
        assert detector.should_auto_retry("unknown_test") is False

    def test_flaky_test_returns_true(self, populated_ci_state_file: Path) -> None:
        """Test that flaky tests recommend auto-retry."""
        detector = FlakyTestDetector(populated_ci_state_file)

        # test_api_rate_limit has 50% failure rate - highly flaky
        result = detector.should_auto_retry("test_api_rate_limit")
        # Should recommend retry due to mixed outcomes and connection-related pattern
        assert result is True

    def test_consistent_failure_returns_false(self, populated_ci_state_file: Path) -> None:
        """Test that consistently failing tests recommend investigation."""
        detector = FlakyTestDetector(populated_ci_state_file)

        # test_db_connection always fails - not flaky, needs investigation
        result = detector.should_auto_retry("test_db_connection")
        assert result is False

    def test_stable_test_returns_false(self, populated_ci_state_file: Path) -> None:
        """Test that stable tests recommend investigation if they suddenly fail."""
        detector = FlakyTestDetector(populated_ci_state_file)

        # test_simple_math always passes - if it fails, investigate
        result = detector.should_auto_retry("test_simple_math")
        assert result is False

    def test_timeout_pattern_triggers_retry(self, temp_state_dir: Path) -> None:
        """Test that timeout-related failures trigger auto-retry."""
        ci_state = {
            "retries": [
                {"test_name": "test_slow", "outcome": "failed", "failure_reason": "timeout"},
                {"test_name": "test_slow", "outcome": "success", "attempt": 2},
                {"test_name": "test_slow", "outcome": "failed", "failure_reason": "timeout"},
            ]
        }
        ci_path = temp_state_dir / "ci_retry_state.json"
        ci_path.write_text(json.dumps(ci_state))

        detector = FlakyTestDetector(ci_path)
        result = detector.should_auto_retry("test_slow")
        # Should recommend retry due to timeout pattern
        assert result is True


class TestGetRetryRecommendation:
    """Tests for get_retry_recommendation() method."""

    def test_empty_list(self, populated_ci_state_file: Path) -> None:
        """Test recommendation with empty test list."""
        detector = FlakyTestDetector(populated_ci_state_file)
        result = detector.get_retry_recommendation([])

        assert result["should_retry"] is False
        assert result["retry_tests"] == []
        assert result["investigate_tests"] == []

    def test_returns_correct_structure(self, populated_ci_state_file: Path) -> None:
        """Test that recommendation has expected structure."""
        detector = FlakyTestDetector(populated_ci_state_file)
        result = detector.get_retry_recommendation(["test_auth_login", "test_db_connection"])

        assert "should_retry" in result
        assert "retry_tests" in result
        assert "investigate_tests" in result
        assert "details" in result
        assert isinstance(result["should_retry"], bool)
        assert isinstance(result["retry_tests"], list)
        assert isinstance(result["investigate_tests"], list)
        assert isinstance(result["details"], dict)

    def test_separates_retry_and_investigate(self, populated_ci_state_file: Path) -> None:
        """Test that tests are correctly categorized."""
        detector = FlakyTestDetector(populated_ci_state_file)
        result = detector.get_retry_recommendation(["test_api_rate_limit", "test_db_connection"])

        # test_api_rate_limit is flaky (connection-related pattern)
        # test_db_connection always fails
        all_tests = set(result["retry_tests"]) | set(result["investigate_tests"])
        assert "test_api_rate_limit" in all_tests
        assert "test_db_connection" in all_tests

    def test_details_include_scores(self, populated_ci_state_file: Path) -> None:
        """Test that details include flakiness scores."""
        detector = FlakyTestDetector(populated_ci_state_file)
        result = detector.get_retry_recommendation(["test_auth_login"])

        assert "test_auth_login" in result["details"]
        details = result["details"]["test_auth_login"]
        assert "flakiness_score" in details
        assert "patterns" in details
        assert "should_retry" in details


class TestGetFlakyTestReport:
    """Tests for get_flaky_test_report() method."""

    def test_empty_data(self, temp_state_dir: Path) -> None:
        """Test report generation with no data."""
        detector = FlakyTestDetector(temp_state_dir)
        result = detector.get_flaky_test_report()

        assert "timestamp" in result
        assert "summary" in result
        assert "flaky_tests" in result
        assert result["flaky_tests"] == []

    def test_report_structure(self, populated_ci_state_file: Path) -> None:
        """Test that report has expected structure."""
        detector = FlakyTestDetector(populated_ci_state_file)
        result = detector.get_flaky_test_report()

        assert "timestamp" in result
        assert "summary" in result
        assert "flaky_tests" in result
        assert "recommendations" in result
        assert "auto_retry_candidates" in result

    def test_summary_statistics(self, populated_ci_state_file: Path) -> None:
        """Test summary contains expected statistics."""
        detector = FlakyTestDetector(populated_ci_state_file)
        result = detector.get_flaky_test_report()

        summary = result["summary"]
        assert "total_tests_analyzed" in summary
        assert "flaky_tests_detected" in summary
        assert "high_severity_count" in summary
        assert "auto_retry_candidates" in summary
        assert "average_flakiness" in summary

    def test_flaky_test_entry_structure(self, populated_ci_state_file: Path) -> None:
        """Test that flaky test entries have expected fields."""
        detector = FlakyTestDetector(populated_ci_state_file)
        result = detector.get_flaky_test_report()

        if result["flaky_tests"]:
            test = result["flaky_tests"][0]
            assert "test_id" in test
            assert "flakiness_score" in test
            assert "failure_rate" in test
            assert "total_runs" in test
            assert "patterns" in test
            assert "recommendation" in test
            assert "severity" in test

    def test_recommendations_sorted_by_priority(self, populated_ci_state_file: Path) -> None:
        """Test that recommendations are sorted by severity."""
        detector = FlakyTestDetector(populated_ci_state_file)
        result = detector.get_flaky_test_report()

        # Recommendations should be for highest flakiness tests
        if len(result["recommendations"]) > 1:
            scores = [r["flakiness_score"] for r in result["recommendations"]]
            assert scores == sorted(scores, reverse=True)


class TestRecordFailure:
    """Tests for record_failure() method."""

    def test_creates_file_if_not_exists(self, temp_state_dir: Path) -> None:
        """Test that record_failure creates the CI state file."""
        ci_path = temp_state_dir / "ci_retry_state.json"
        detector = FlakyTestDetector(ci_path)

        detector.record_failure("test_new", "failed", workflow="ci")

        assert ci_path.exists()
        with open(ci_path) as f:
            data = json.load(f)
        assert "retries" in data
        assert len(data["retries"]) == 1
        assert data["retries"][0]["test_name"] == "test_new"

    def test_appends_to_existing_file(self, populated_ci_state_file: Path) -> None:
        """Test that record_failure appends to existing data."""
        detector = FlakyTestDetector(populated_ci_state_file)

        # Get initial count
        with open(populated_ci_state_file) as f:
            initial_data = json.load(f)
        initial_count = len(initial_data["retries"])

        detector.record_failure("test_new", "success")

        with open(populated_ci_state_file) as f:
            data = json.load(f)
        assert len(data["retries"]) == initial_count + 1

    def test_records_all_fields(self, temp_state_dir: Path) -> None:
        """Test that all fields are recorded correctly."""
        ci_path = temp_state_dir / "ci_retry_state.json"
        detector = FlakyTestDetector(ci_path)

        detector.record_failure(
            "test_example",
            "failed",
            workflow="integration",
            failure_reason="connection_timeout",
            attempt=2,
            run_id="12345",
        )

        with open(ci_path) as f:
            data = json.load(f)

        record = data["retries"][0]
        assert record["test_name"] == "test_example"
        assert record["outcome"] == "failed"
        assert record["workflow"] == "integration"
        assert record["failure_reason"] == "connection_timeout"
        assert record["attempt"] == 2
        assert record["run_id"] == "12345"
        assert "timestamp" in record

    def test_clears_cache_after_record(self, populated_ci_state_file: Path) -> None:
        """Test that cache is cleared after recording."""
        detector = FlakyTestDetector(populated_ci_state_file)

        # Load data to populate cache
        detector.analyze_failure_patterns()
        assert detector._test_stats is not None

        # Record should clear cache
        detector.record_failure("test_new", "failed")
        assert detector._test_stats is None


class TestCacheHandling:
    """Tests for data caching behavior."""

    def test_cache_prevents_multiple_reads(self, populated_ci_state_file: Path) -> None:
        """Test that data is cached after first read."""
        detector = FlakyTestDetector(populated_ci_state_file)

        # First call loads data
        result1 = detector.analyze_failure_patterns()
        # Second call should use cached data
        result2 = detector.analyze_failure_patterns()

        assert result1 == result2
        assert detector._ci_data is not None

    def test_clear_cache(self, populated_ci_state_file: Path) -> None:
        """Test that clear_cache resets cached data."""
        detector = FlakyTestDetector(populated_ci_state_file)

        # Load data
        detector.analyze_failure_patterns()
        assert detector._ci_data is not None
        assert detector._test_stats is not None

        # Clear cache
        detector.clear_cache()

        assert detector._ci_data is None
        assert detector._test_stats is None


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_invalid_json(self, temp_state_dir: Path) -> None:
        """Test handling of invalid JSON files."""
        ci_path = temp_state_dir / "ci_retry_state.json"
        ci_path.write_text("{ invalid json }")

        detector = FlakyTestDetector(ci_path)
        result = detector.analyze_failure_patterns()

        # Should return empty list, not crash
        assert result == []

    def test_handles_empty_retries(self, temp_state_dir: Path) -> None:
        """Test handling of empty retries array."""
        ci_path = temp_state_dir / "ci_retry_state.json"
        ci_path.write_text(json.dumps({"retries": []}))

        detector = FlakyTestDetector(ci_path)
        result = detector.analyze_failure_patterns()

        assert result == []

    def test_handles_malformed_entries(self, temp_state_dir: Path) -> None:
        """Test handling of malformed entries in arrays."""
        ci_path = temp_state_dir / "ci_retry_state.json"
        ci_path.write_text(
            json.dumps({"retries": ["not a dict", 123, None, {"test_name": "valid"}]})
        )

        detector = FlakyTestDetector(ci_path)
        result = detector.analyze_failure_patterns()

        # Should not crash, should skip invalid entries
        assert isinstance(result, list)

    def test_handles_missing_test_name(self, temp_state_dir: Path) -> None:
        """Test handling of entries without test_name."""
        ci_path = temp_state_dir / "ci_retry_state.json"
        ci_path.write_text(
            json.dumps(
                {
                    "retries": [
                        {"outcome": "failed"},  # No test_name
                        {"test_name": "valid", "outcome": "failed"},
                        {"test_name": "valid", "outcome": "success"},
                        {"test_name": "valid", "outcome": "failed"},
                    ]
                }
            )
        )

        detector = FlakyTestDetector(ci_path)
        result = detector.analyze_failure_patterns()

        # Should process valid entries
        assert isinstance(result, list)

    def test_below_threshold_not_reported(self, temp_state_dir: Path) -> None:
        """Test that tests below MIN_RUNS_FOR_ANALYSIS are not reported."""
        ci_path = temp_state_dir / "ci_retry_state.json"
        ci_path.write_text(
            json.dumps(
                {
                    "retries": [
                        {"test_name": "test_few_runs", "outcome": "failed"},
                        {"test_name": "test_few_runs", "outcome": "success"},
                        # Only 2 runs - below threshold of 3
                    ]
                }
            )
        )

        detector = FlakyTestDetector(ci_path)
        result = detector.analyze_failure_patterns()

        # test_few_runs should not appear (below threshold)
        test_ids = [test_id for test_id, _ in result]
        assert "test_few_runs" not in test_ids


class TestPatternDetection:
    """Tests for failure pattern detection."""

    def test_detects_timeout_pattern(self, temp_state_dir: Path) -> None:
        """Test detection of timeout-related patterns."""
        ci_path = temp_state_dir / "ci_retry_state.json"
        ci_path.write_text(
            json.dumps(
                {
                    "retries": [
                        {
                            "test_name": "test_slow",
                            "outcome": "failed",
                            "failure_reason": "timeout",
                        },
                        {"test_name": "test_slow", "outcome": "success"},
                        {
                            "test_name": "test_slow",
                            "outcome": "failed",
                            "failure_reason": "timeout",
                        },
                    ]
                }
            )
        )

        detector = FlakyTestDetector(ci_path)
        report = detector.get_flaky_test_report()

        # Find test_slow in flaky tests
        slow_tests = [t for t in report["flaky_tests"] if t["test_id"] == "test_slow"]
        if slow_tests:
            assert "timeout-related" in slow_tests[0]["patterns"]

    def test_detects_connection_pattern(self, temp_state_dir: Path) -> None:
        """Test detection of connection-related patterns."""
        ci_path = temp_state_dir / "ci_retry_state.json"
        ci_path.write_text(
            json.dumps(
                {
                    "retries": [
                        {
                            "test_name": "test_network",
                            "outcome": "failed",
                            "failure_reason": "connection_refused",
                        },
                        {"test_name": "test_network", "outcome": "success"},
                        {
                            "test_name": "test_network",
                            "outcome": "failed",
                            "failure_reason": "network_error",
                        },
                    ]
                }
            )
        )

        detector = FlakyTestDetector(ci_path)
        report = detector.get_flaky_test_report()

        # Find test_network in flaky tests
        network_tests = [t for t in report["flaky_tests"] if t["test_id"] == "test_network"]
        if network_tests:
            assert "connection-related" in network_tests[0]["patterns"]

    def test_detects_multi_workflow_pattern(self, temp_state_dir: Path) -> None:
        """Test detection of multi-workflow patterns."""
        ci_path = temp_state_dir / "ci_retry_state.json"
        ci_path.write_text(
            json.dumps(
                {
                    "retries": [
                        {"test_name": "test_multi", "outcome": "failed", "workflow": "ci"},
                        {
                            "test_name": "test_multi",
                            "outcome": "success",
                            "workflow": "integration",
                        },
                        {"test_name": "test_multi", "outcome": "failed", "workflow": "nightly"},
                    ]
                }
            )
        )

        detector = FlakyTestDetector(ci_path)
        report = detector.get_flaky_test_report()

        # Find test_multi in flaky tests
        multi_tests = [t for t in report["flaky_tests"] if t["test_id"] == "test_multi"]
        if multi_tests:
            assert "multi-workflow" in multi_tests[0]["patterns"]
