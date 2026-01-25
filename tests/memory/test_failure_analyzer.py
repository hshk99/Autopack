"""Tests for failure pattern analyzer."""

import os
import tempfile

import pytest

from memory.failure_analyzer import FailureAnalyzer
from memory.metrics_db import MetricsDatabase


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    # Use a file in temp dir with manual cleanup to avoid Windows locking issues
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = MetricsDatabase(db_path=db_path)
    yield db
    # Clean up
    try:
        os.unlink(db_path)
    except PermissionError:
        pass  # Windows may hold the file


@pytest.fixture
def analyzer(temp_db):
    """Create a FailureAnalyzer instance with temp database."""
    return FailureAnalyzer(metrics_db=temp_db)


class TestFailureAnalyzer:
    """Tests for FailureAnalyzer class."""

    def test_categorize_failure_ci_test_failure(self, analyzer):
        """Test categorization of CI test failures."""
        assert analyzer.categorize_failure("Test suite failed with 3 errors") == "ci_test_failure"
        assert analyzer.categorize_failure("pytest test failure in module") == "ci_test_failure"

    def test_categorize_failure_ci_build_failure(self, analyzer):
        """Test categorization of CI build failures."""
        assert analyzer.categorize_failure("Build failed: compilation error") == "ci_build_failure"

    def test_categorize_failure_merge_conflict(self, analyzer):
        """Test categorization of merge conflicts."""
        assert analyzer.categorize_failure("Merge conflict detected") == "merge_conflict"
        assert analyzer.categorize_failure("CONFLICT in src/main.py") == "merge_conflict"

    def test_categorize_failure_stagnation(self, analyzer):
        """Test categorization of stagnation/timeout."""
        assert analyzer.categorize_failure("Stagnation detected in phase") == "stagnation"
        assert analyzer.categorize_failure("Operation timeout after 30s") == "stagnation"

    def test_categorize_failure_connection_error(self, analyzer):
        """Test categorization of connection errors."""
        assert analyzer.categorize_failure("Connection refused to API") == "connection_error"
        assert analyzer.categorize_failure("Network error: unreachable") == "connection_error"

    def test_categorize_failure_permission_denied(self, analyzer):
        """Test categorization of permission errors."""
        assert analyzer.categorize_failure("Permission denied: write access") == "permission_denied"
        assert analyzer.categorize_failure("Access denied to resource") == "permission_denied"

    def test_categorize_failure_rate_limit(self, analyzer):
        """Test categorization of rate limit errors."""
        assert analyzer.categorize_failure("Rate limit exceeded") == "rate_limit"
        assert analyzer.categorize_failure("Too many requests, retry later") == "rate_limit"

    def test_categorize_failure_lint_failure(self, analyzer):
        """Test categorization of lint failures."""
        assert analyzer.categorize_failure("Lint check failed") == "lint_failure"
        assert analyzer.categorize_failure("Black formatting error") == "lint_failure"
        assert analyzer.categorize_failure("isort import sorting failed") == "lint_failure"

    def test_categorize_failure_type_error(self, analyzer):
        """Test categorization of type errors."""
        assert analyzer.categorize_failure("Type error: expected int") == "type_error"

    def test_categorize_failure_unknown(self, analyzer):
        """Test categorization of unknown errors."""
        assert analyzer.categorize_failure("Something unexpected happened") == "unknown"

    def test_compute_pattern_hash_normalizes_numbers(self, analyzer):
        """Test that pattern hash normalizes numbers."""
        hash1 = analyzer.compute_pattern_hash("Error in line 42")
        hash2 = analyzer.compute_pattern_hash("Error in line 99")
        assert hash1 == hash2

    def test_compute_pattern_hash_normalizes_git_hashes(self, analyzer):
        """Test that pattern hash normalizes git hashes."""
        # Git hashes are exactly 40 hex characters
        hash1 = analyzer.compute_pattern_hash(
            "Commit 1234567890abcdef1234567890abcdef12345678 failed"
        )
        hash2 = analyzer.compute_pattern_hash(
            "Commit abcdef1234567890abcdef1234567890abcdef12 failed"
        )
        assert hash1 == hash2

    def test_compute_pattern_hash_normalizes_windows_paths(self, analyzer):
        """Test that pattern hash normalizes Windows paths."""
        # The backslash escaping makes these different in raw strings
        hash1 = analyzer.compute_pattern_hash("Error in C:\\Users\\test\\file.py")
        hash2 = analyzer.compute_pattern_hash("Error in C:\\Users\\other\\file.py")
        assert hash1 == hash2

    def test_compute_pattern_hash_normalizes_unix_paths(self, analyzer):
        """Test that pattern hash normalizes Unix paths."""
        hash1 = analyzer.compute_pattern_hash("Error in /home/user/test.py")
        hash2 = analyzer.compute_pattern_hash("Error in /var/log/app.log")
        assert hash1 == hash2

    def test_compute_pattern_hash_different_errors_different_hash(self, analyzer):
        """Test that different error types produce different hashes."""
        hash1 = analyzer.compute_pattern_hash("Test suite failed")
        hash2 = analyzer.compute_pattern_hash("Build compilation error")
        assert hash1 != hash2

    def test_record_failure_returns_pattern_hash(self, analyzer):
        """Test that record_failure returns a pattern hash."""
        pattern_hash = analyzer.record_failure("phase-1", "Test failed with error")
        assert pattern_hash is not None
        assert len(pattern_hash) == 12

    def test_record_failure_increments_occurrence_count(self, analyzer):
        """Test that repeated failures increment the count."""
        error = "Test suite failed"
        analyzer.record_failure("phase-1", error)
        analyzer.record_failure("phase-2", error)
        analyzer.record_failure("phase-3", error)

        stats = analyzer.get_failure_statistics()
        total = stats["by_category"].get("ci_test_failure", 0)
        assert total == 3

    def test_record_failure_with_resolution(self, analyzer):
        """Test recording failure with resolution."""
        error = "Lint check failed"
        analyzer.record_failure("phase-1", error, resolved_by="Run black formatter")

        suggestion = analyzer.get_resolution_suggestion(error)
        assert suggestion == "Run black formatter"

    def test_get_resolution_suggestion_no_match(self, analyzer):
        """Test that unknown errors return no suggestion."""
        suggestion = analyzer.get_resolution_suggestion("Never seen this error before")
        assert suggestion is None

    def test_get_resolution_suggestion_matches_similar(self, analyzer):
        """Test that similar errors match the same resolution."""
        analyzer.record_failure("phase-1", "Error in line 10", resolved_by="Fix the bug")

        suggestion = analyzer.get_resolution_suggestion("Error in line 99")
        assert suggestion == "Fix the bug"

    def test_get_failure_statistics_empty(self, analyzer):
        """Test statistics on empty database."""
        stats = analyzer.get_failure_statistics()
        assert stats["by_category"] == {}
        assert stats["top_patterns"] == []
        assert stats["total_unique_patterns"] == 0

    def test_get_failure_statistics_with_data(self, analyzer):
        """Test statistics with recorded failures."""
        analyzer.record_failure("phase-1", "Test failed")
        analyzer.record_failure("phase-2", "Test failed")
        analyzer.record_failure("phase-3", "Build failed")

        stats = analyzer.get_failure_statistics()
        assert "ci_test_failure" in stats["by_category"]
        assert stats["by_category"]["ci_test_failure"] == 2
        assert stats["by_category"]["ci_build_failure"] == 1
        assert len(stats["top_patterns"]) == 2

    def test_detect_new_patterns_empty(self, analyzer):
        """Test detecting new patterns on empty database."""
        patterns = analyzer.detect_new_patterns(since_hours=24)
        assert patterns == []

    def test_detect_new_patterns_with_data(self, analyzer):
        """Test detecting new patterns with recent data."""
        analyzer.record_failure("phase-1", "New error occurred")

        patterns = analyzer.detect_new_patterns(since_hours=24)
        assert len(patterns) == 1
        assert patterns[0]["failure_type"] == "unknown"


class TestFailureCategories:
    """Tests for failure categories constant."""

    def test_all_categories_defined(self, analyzer):
        """Test that all expected categories are defined."""
        expected = [
            "ci_test_failure",
            "ci_build_failure",
            "merge_conflict",
            "stagnation",
            "connection_error",
            "permission_denied",
            "rate_limit",
            "lint_failure",
            "type_error",
            "unknown",
        ]
        assert analyzer.FAILURE_CATEGORIES == expected
