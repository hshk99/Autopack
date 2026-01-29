"""Tests for context preflight file size policies.

Tests the ContextPreflight class extracted from autonomous_executor.py
as part of PR-EXE-5 (god file refactoring).

Test Coverage:
1. File size bucket classification (table-driven)
2. Read-only decision based on total size
3. File filtering by size threshold
4. Deterministic output (same inputs → same decision)
5. Edge cases (empty files, missing files, etc.)
"""

import pytest

from autopack.executor.context_preflight import (ContextPreflight,
                                                 FileSizeBucket)


class TestFileSizeBucket:
    """Tests for file size bucket classification."""

    @pytest.mark.parametrize(
        "line_count,expected_bucket",
        [
            # SMALL bucket: ≤100 lines
            (1, FileSizeBucket.SMALL),
            (50, FileSizeBucket.SMALL),
            (100, FileSizeBucket.SMALL),
            # MEDIUM bucket: 101-500 lines
            (101, FileSizeBucket.MEDIUM),
            (250, FileSizeBucket.MEDIUM),
            (500, FileSizeBucket.MEDIUM),
            # LARGE bucket: 501-1000 lines
            (501, FileSizeBucket.LARGE),
            (750, FileSizeBucket.LARGE),
            (1000, FileSizeBucket.LARGE),
            # HUGE bucket: >1000 lines
            (1001, FileSizeBucket.HUGE),
            (5000, FileSizeBucket.HUGE),
            (50000, FileSizeBucket.HUGE),
        ],
    )
    def test_bucket_classification(self, line_count, expected_bucket):
        """Test file size bucket classification with table-driven cases.

        This test validates the bucket logic:
        - SMALL: ≤100 lines
        - MEDIUM: 101-500 lines
        - LARGE: 501-1000 lines
        - HUGE: >1000 lines
        """
        preflight = ContextPreflight()
        content = "\n" * (line_count - 1)  # line_count = newlines + 1
        bucket = preflight.check_file_size_bucket("test.py", content)
        assert bucket == expected_bucket

    def test_bucket_boundary_small_medium(self):
        """Test boundary between SMALL and MEDIUM buckets."""
        preflight = ContextPreflight()

        # 100 lines: still SMALL
        content_100 = "\n" * 99
        assert preflight.check_file_size_bucket("test.py", content_100) == FileSizeBucket.SMALL

        # 101 lines: now MEDIUM
        content_101 = "\n" * 100
        assert preflight.check_file_size_bucket("test.py", content_101) == FileSizeBucket.MEDIUM

    def test_bucket_boundary_medium_large(self):
        """Test boundary between MEDIUM and LARGE buckets."""
        preflight = ContextPreflight()

        # 500 lines: still MEDIUM
        content_500 = "\n" * 499
        assert preflight.check_file_size_bucket("test.py", content_500) == FileSizeBucket.MEDIUM

        # 501 lines: now LARGE
        content_501 = "\n" * 500
        assert preflight.check_file_size_bucket("test.py", content_501) == FileSizeBucket.LARGE

    def test_bucket_boundary_large_huge(self):
        """Test boundary between LARGE and HUGE buckets (critical for policy)."""
        preflight = ContextPreflight()

        # 1000 lines: still LARGE (allowed)
        content_1000 = "\n" * 999
        assert preflight.check_file_size_bucket("test.py", content_1000) == FileSizeBucket.LARGE

        # 1001 lines: now HUGE (read-only)
        content_1001 = "\n" * 1000
        assert preflight.check_file_size_bucket("test.py", content_1001) == FileSizeBucket.HUGE

    def test_empty_file(self):
        """Test classification of empty file."""
        preflight = ContextPreflight()
        content = ""
        bucket = preflight.check_file_size_bucket("empty.py", content)
        assert bucket == FileSizeBucket.SMALL

    def test_single_line_no_newline(self):
        """Test file with single line and no trailing newline."""
        preflight = ContextPreflight()
        content = "print('hello')"
        bucket = preflight.check_file_size_bucket("one_line.py", content)
        assert bucket == FileSizeBucket.SMALL


class TestReadOnlyDecision:
    """Tests for read-only decision logic."""

    def test_all_files_within_limit(self):
        """Test decision when all files are within size limits."""
        preflight = ContextPreflight(max_lines_hard_limit=1000)
        files = {
            "small.py": "line1\nline2\nline3",  # 3 lines
            "medium.py": "\n" * 500,  # 501 lines
            "large.py": "\n" * 999,  # 1000 lines
        }

        decision = preflight.decide_read_only(files)

        assert decision.read_only is False
        assert decision.oversized_files == []
        assert "within size limits" in decision.reason.lower()
        assert decision.total_size_mb > 0

    def test_single_oversized_file(self):
        """Test decision when one file exceeds limit."""
        preflight = ContextPreflight(max_lines_hard_limit=1000)
        files = {
            "small.py": "line1\nline2",
            "huge.py": "\n" * 1500,  # 1501 lines (exceeds limit)
        }

        decision = preflight.decide_read_only(files)

        assert decision.read_only is True
        assert len(decision.oversized_files) == 1
        assert decision.oversized_files[0][0] == "huge.py"
        assert decision.oversized_files[0][1] == 1501
        assert "huge.py" in decision.reason
        assert "1000" in decision.reason

    def test_multiple_oversized_files(self):
        """Test decision when multiple files exceed limit."""
        preflight = ContextPreflight(max_lines_hard_limit=1000)
        files = {
            "huge1.py": "\n" * 2000,  # 2001 lines
            "huge2.py": "\n" * 1500,  # 1501 lines
            "small.py": "line1",
        }

        decision = preflight.decide_read_only(files)

        assert decision.read_only is True
        assert len(decision.oversized_files) == 2
        assert "huge1.py" in decision.reason
        assert "huge2.py" in decision.reason

    def test_exactly_at_limit(self):
        """Test decision when file is exactly at the limit (should pass)."""
        preflight = ContextPreflight(max_lines_hard_limit=1000)
        files = {
            "exactly_1000.py": "\n" * 999,  # Exactly 1000 lines
        }

        decision = preflight.decide_read_only(files)

        assert decision.read_only is False
        assert decision.oversized_files == []

    def test_one_line_over_limit(self):
        """Test decision when file is one line over limit (should fail)."""
        preflight = ContextPreflight(max_lines_hard_limit=1000)
        files = {
            "1001_lines.py": "\n" * 1000,  # 1001 lines
        }

        decision = preflight.decide_read_only(files)

        assert decision.read_only is True
        assert len(decision.oversized_files) == 1

    def test_total_size_calculation(self):
        """Test that total size is calculated correctly."""
        preflight = ContextPreflight()
        files = {
            "file1.py": "a" * 1024 * 1024,  # 1MB
            "file2.py": "b" * 1024 * 1024,  # 1MB
        }

        decision = preflight.decide_read_only(files)

        # Total should be ~2MB
        assert 1.9 < decision.total_size_mb < 2.1

    def test_empty_files_dict(self):
        """Test decision with no files."""
        preflight = ContextPreflight()
        files = {}

        decision = preflight.decide_read_only(files)

        assert decision.read_only is False
        assert decision.oversized_files == []
        assert decision.total_size_mb == 0

    def test_non_string_content_ignored(self):
        """Test that non-string content is safely ignored."""
        preflight = ContextPreflight()
        files = {
            "normal.py": "line1\nline2",
            "weird.py": None,  # Should be ignored
            "also_weird.py": 123,  # Should be ignored
        }

        decision = preflight.decide_read_only(files)

        assert decision.read_only is False


class TestFilterFilesBySize:
    """Tests for file filtering by size."""

    def test_filter_removes_oversized(self):
        """Test that oversized files are removed."""
        preflight = ContextPreflight()
        files = {
            "small.py": "x" * 1000,
            "large.py": "y" * 10_000_000,  # 10MB
        }

        filtered = preflight.filter_files_by_size(files, max_size_mb=1.0)

        assert "small.py" in filtered
        assert "large.py" not in filtered

    def test_filter_keeps_all_under_limit(self):
        """Test that all files under limit are kept."""
        preflight = ContextPreflight()
        files = {
            "file1.py": "x" * 1000,
            "file2.py": "y" * 2000,
            "file3.py": "z" * 3000,
        }

        filtered = preflight.filter_files_by_size(files, max_size_mb=1.0)

        assert len(filtered) == 3
        assert set(filtered.keys()) == set(files.keys())

    def test_filter_empty_dict(self):
        """Test filtering empty files dict."""
        preflight = ContextPreflight()
        files = {}

        filtered = preflight.filter_files_by_size(files, max_size_mb=1.0)

        assert filtered == {}

    def test_filter_preserves_non_string_content(self):
        """Test that non-string content is preserved."""
        preflight = ContextPreflight()
        files = {
            "normal.py": "x" * 1000,
            "weird.py": None,
        }

        filtered = preflight.filter_files_by_size(files, max_size_mb=1.0)

        assert "weird.py" in filtered
        assert filtered["weird.py"] is None


class TestDeterministicBehavior:
    """Tests for deterministic behavior."""

    def test_same_input_same_output_bucket(self):
        """Test that same input produces same bucket classification."""
        preflight = ContextPreflight()
        content = "\n" * 250  # 251 lines (MEDIUM)

        bucket1 = preflight.check_file_size_bucket("test.py", content)
        bucket2 = preflight.check_file_size_bucket("test.py", content)
        bucket3 = preflight.check_file_size_bucket("test.py", content)

        assert bucket1 == bucket2 == bucket3 == FileSizeBucket.MEDIUM

    def test_same_input_same_decision(self):
        """Test that same files produce same read-only decision."""
        preflight = ContextPreflight(max_lines_hard_limit=1000)
        files = {
            "file1.py": "\n" * 500,
            "file2.py": "\n" * 1500,
        }

        decision1 = preflight.decide_read_only(files)
        decision2 = preflight.decide_read_only(files)

        assert decision1.read_only == decision2.read_only
        assert decision1.oversized_files == decision2.oversized_files
        assert decision1.total_size_mb == decision2.total_size_mb

    def test_different_order_same_decision(self):
        """Test that file order doesn't affect decision."""
        preflight = ContextPreflight(max_lines_hard_limit=1000)

        files1 = {
            "a.py": "\n" * 1500,
            "b.py": "\n" * 500,
        }

        files2 = {
            "b.py": "\n" * 500,
            "a.py": "\n" * 1500,
        }

        decision1 = preflight.decide_read_only(files1)
        decision2 = preflight.decide_read_only(files2)

        assert decision1.read_only == decision2.read_only
        assert set(f[0] for f in decision1.oversized_files) == set(
            f[0] for f in decision2.oversized_files
        )


class TestContextValidation:
    """Tests for overall context validation."""

    def test_validate_success(self):
        """Test validation passes for good context."""
        preflight = ContextPreflight(max_files=40, max_total_size_mb=5.0, max_lines_hard_limit=1000)
        files = {
            "file1.py": "\n" * 500,
            "file2.py": "\n" * 300,
        }

        is_valid, message = preflight.validate_context_size(files, phase_id="test_phase")

        assert is_valid is True
        assert "validated" in message.lower()

    def test_validate_fails_oversized_file(self):
        """Test validation fails for oversized file."""
        preflight = ContextPreflight(max_lines_hard_limit=1000)
        files = {
            "huge.py": "\n" * 1500,
        }

        is_valid, message = preflight.validate_context_size(files)

        assert is_valid is False
        assert "huge.py" in message

    def test_validate_fails_total_size(self):
        """Test validation fails for excessive total size."""
        preflight = ContextPreflight(max_total_size_mb=1.0)
        files = {
            "file1.py": "x" * 600_000,  # ~0.6MB
            "file2.py": "y" * 600_000,  # ~0.6MB (total > 1MB)
        }

        is_valid, message = preflight.validate_context_size(files)

        assert is_valid is False
        assert "total context size" in message.lower()

    def test_file_count_warning(self):
        """Test warning for large file count."""
        preflight = ContextPreflight(max_files=10)

        warning = preflight.get_file_count_warning(15)

        assert warning is not None
        assert "15" in warning
        assert "10" in warning

    def test_no_warning_under_limit(self):
        """Test no warning when under file count limit."""
        preflight = ContextPreflight(max_files=10)

        warning = preflight.get_file_count_warning(5)

        assert warning is None


class TestCustomConfiguration:
    """Tests for custom configuration values."""

    def test_custom_hard_limit(self):
        """Test custom hard limit is respected."""
        preflight = ContextPreflight(max_lines_hard_limit=500)
        files = {
            "file.py": "\n" * 600,  # 601 lines
        }

        decision = preflight.decide_read_only(files)

        assert decision.read_only is True

    def test_custom_max_files(self):
        """Test custom max files limit."""
        preflight = ContextPreflight(max_files=5)

        warning = preflight.get_file_count_warning(6)

        assert warning is not None
        assert "5" in warning

    def test_custom_size_limits(self):
        """Test custom size limits."""
        preflight = ContextPreflight(max_total_size_mb=10.0, read_only_threshold_mb=5.0)

        assert preflight.max_total_size_mb == 10.0
        assert preflight.read_only_threshold_mb == 5.0
