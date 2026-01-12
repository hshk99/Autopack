"""Contract tests for diff_generator module.

This test suite validates the public API contract of the diff_generator module
extracted from anthropic_clients.py (PR-LLM-4).

Tests cover:
- Valid unified diff format generation
- Correct file path headers
- Context lines parameter
- New/deleted file handling
- Stats extraction
- Format validation
- Deterministic behavior
"""

import pytest
from autopack.patching.diff_generator import (
    extract_diff_stats,
    generate_diff_from_full_file,
    generate_unified_diff,
    validate_diff_format,
)


class TestGenerateUnifiedDiff:
    """Test generate_unified_diff function."""

    def test_generates_valid_unified_diff_format(self):
        """Generated diff should be valid unified diff format."""
        old_content = "line1\nline2\nline3\n"
        new_content = "line1\nline2_modified\nline3\n"

        diff = generate_unified_diff(old_content, new_content, "test.txt")

        assert diff.startswith("diff --git a/test.txt b/test.txt")
        assert "--- a/test.txt" in diff
        assert "+++ b/test.txt" in diff
        assert "@@" in diff
        assert validate_diff_format(diff)

    def test_includes_correct_file_paths_in_headers(self):
        """Diff headers should include correct a/ and b/ prefixes."""
        old_content = "old"
        new_content = "new"
        filepath = "src/module/file.py"

        diff = generate_unified_diff(old_content, new_content, filepath)

        assert f"diff --git a/{filepath} b/{filepath}" in diff
        assert f"--- a/{filepath}" in diff
        assert f"+++ b/{filepath}" in diff

    def test_respects_context_lines_parameter(self):
        """Context lines parameter should control amount of context shown."""
        old_content = "\n".join([f"line{i}" for i in range(1, 21)])
        new_content = "\n".join([f"line{i}" if i != 10 else "CHANGED" for i in range(1, 21)])

        # Test with 0 context lines
        diff_0 = generate_unified_diff(old_content, new_content, "test.txt", context_lines=0)
        assert "line8" not in diff_0  # Context lines shouldn't appear

        # Test with 3 context lines (default)
        diff_3 = generate_unified_diff(old_content, new_content, "test.txt", context_lines=3)
        assert "line7" in diff_3  # Should show 3 lines before
        assert "line13" in diff_3  # Should show 3 lines after

        # Test with 5 context lines
        diff_5 = generate_unified_diff(old_content, new_content, "test.txt", context_lines=5)
        assert "line5" in diff_5  # Should show 5 lines before
        assert "line15" in diff_5  # Should show 5 lines after

    def test_handles_new_file_creation(self):
        """Empty old_content should generate new file diff."""
        old_content = ""
        new_content = "new file content\n"

        diff = generate_unified_diff(old_content, new_content, "newfile.txt")

        assert "new file mode 100644" in diff
        assert "--- /dev/null" in diff
        assert "+++ b/newfile.txt" in diff
        assert validate_diff_format(diff)

    def test_handles_file_deletion(self):
        """Empty new_content should generate deleted file diff."""
        old_content = "old file content\n"
        new_content = ""

        diff = generate_unified_diff(old_content, new_content, "deleted.txt")

        assert "deleted file mode 100644" in diff
        assert "--- a/deleted.txt" in diff
        assert "+++ /dev/null" in diff
        assert validate_diff_format(diff)

    def test_handles_no_changes(self):
        """Identical content should return empty string."""
        content = "same content\n"

        diff = generate_unified_diff(content, content, "test.txt")

        assert diff == ""

    def test_single_line_change_with_context(self):
        """Single line modification should show proper context."""
        old_content = "line1\nline2\nline3\nline4\nline5\n"
        new_content = "line1\nline2\nMODIFIED\nline4\nline5\n"

        diff = generate_unified_diff(old_content, new_content, "test.txt")

        assert "-line3" in diff
        assert "+MODIFIED" in diff
        assert " line2" in diff  # Context line
        assert " line4" in diff  # Context line

    def test_multiple_hunks_for_distant_changes(self):
        """Changes far apart should generate multiple hunks."""
        old_content = "\n".join([f"line{i}" for i in range(1, 101)])
        new_content = "\n".join(
            ["CHANGE1" if i == 10 else "CHANGE2" if i == 90 else f"line{i}" for i in range(1, 101)]
        )

        diff = generate_unified_diff(old_content, new_content, "test.txt", context_lines=3)

        # Should have at least 2 hunks (git may split further based on heuristics)
        hunk_count = diff.count("@@")
        assert hunk_count >= 2

    def test_multiline_addition(self):
        """Adding multiple lines should be reflected in diff."""
        old_content = "line1\nline2\n"
        new_content = "line1\nadded_line_a\nadded_line_b\nline2\n"

        diff = generate_unified_diff(old_content, new_content, "test.txt")

        assert "+added_line_a" in diff
        assert "+added_line_b" in diff

    def test_multiline_deletion(self):
        """Removing multiple lines should be reflected in diff."""
        old_content = "line1\nremove_a\nremove_b\nline2\n"
        new_content = "line1\nline2\n"

        diff = generate_unified_diff(old_content, new_content, "test.txt")

        assert "-remove_a" in diff
        assert "-remove_b" in diff

    def test_whitespace_only_change(self):
        """Whitespace changes should be detected."""
        old_content = "line1\nline2\nline3\n"
        new_content = "line1\nline2 \nline3\n"  # Added trailing space

        diff = generate_unified_diff(old_content, new_content, "test.txt")

        # Should show line2 changed (though trailing space may not be visible)
        assert "-line2" in diff
        assert "+line2" in diff

    def test_empty_lines_handling(self):
        """Empty lines in content should be preserved."""
        old_content = "line1\n\nline3\n"
        new_content = "line1\n\n\nline3\n"  # Added empty line

        diff = generate_unified_diff(old_content, new_content, "test.txt")

        assert diff != ""
        assert validate_diff_format(diff)

    def test_deterministic_output(self):
        """Same inputs should always produce same output."""
        old_content = "a\nb\nc\n"
        new_content = "a\nX\nc\n"

        diff1 = generate_unified_diff(old_content, new_content, "test.txt")
        diff2 = generate_unified_diff(old_content, new_content, "test.txt")

        assert diff1 == diff2


class TestGenerateDiffFromFullFile:
    """Test generate_diff_from_full_file function."""

    def test_reads_existing_file_and_generates_diff(self, tmp_path):
        """Should read existing file and generate diff against new content."""
        test_file = tmp_path / "existing.txt"
        test_file.write_text("old content\n")

        new_content = "new content\n"
        diff = generate_diff_from_full_file(str(test_file), new_content)

        assert "-old content" in diff
        assert "+new content" in diff
        assert validate_diff_format(diff)

    def test_handles_nonexistent_file_as_new_file(self, tmp_path):
        """Non-existent file should be treated as new file."""
        test_file = tmp_path / "nonexistent.txt"
        new_content = "new file\n"

        diff = generate_diff_from_full_file(str(test_file), new_content)

        assert "new file mode 100644" in diff
        assert validate_diff_format(diff)


class TestValidateDiffFormat:
    """Test validate_diff_format function."""

    def test_validates_correct_unified_diff(self):
        """Well-formed diff should pass validation."""
        diff = """diff --git a/test.txt b/test.txt
index 1111111..2222222 100644
--- a/test.txt
+++ b/test.txt
@@ -1,3 +1,3 @@
 line1
-line2
+line2_modified
 line3"""

        assert validate_diff_format(diff)

    def test_rejects_empty_string(self):
        """Empty string should fail validation."""
        assert not validate_diff_format("")

    def test_rejects_missing_diff_header(self):
        """Diff without 'diff --git' header should fail."""
        diff = """--- a/test.txt
+++ b/test.txt
@@ -1 +1 @@
-old
+new"""

        assert not validate_diff_format(diff)

    def test_rejects_missing_file_markers(self):
        """Diff without --- and +++ should fail."""
        diff = """diff --git a/test.txt b/test.txt
@@ -1 +1 @@
-old
+new"""

        assert not validate_diff_format(diff)

    def test_rejects_missing_hunk_header(self):
        """Diff without @@ hunk header should fail (unless new/deleted file)."""
        diff = """diff --git a/test.txt b/test.txt
index 1111111..2222222 100644
--- a/test.txt
+++ b/test.txt
-old
+new"""

        assert not validate_diff_format(diff)

    def test_accepts_new_file_mode_without_hunk(self):
        """New file mode is valid even without traditional hunk."""
        diff = """diff --git a/test.txt b/test.txt
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/test.txt"""

        assert validate_diff_format(diff)

    def test_accepts_deleted_file_mode_without_hunk(self):
        """Deleted file mode is valid even without traditional hunk."""
        diff = """diff --git a/test.txt b/test.txt
deleted file mode 100644
index 1111111..0000000
--- a/test.txt
+++ /dev/null"""

        assert validate_diff_format(diff)


class TestExtractDiffStats:
    """Test extract_diff_stats function."""

    def test_extracts_insertions_count(self):
        """Should count + lines correctly."""
        diff = """diff --git a/test.txt b/test.txt
--- a/test.txt
+++ b/test.txt
@@ -1,2 +1,4 @@
 line1
+added1
+added2
 line2"""

        stats = extract_diff_stats(diff)
        assert stats.insertions == 2

    def test_extracts_deletions_count(self):
        """Should count - lines correctly."""
        diff = """diff --git a/test.txt b/test.txt
--- a/test.txt
+++ b/test.txt
@@ -1,4 +1,2 @@
 line1
-removed1
-removed2
 line2"""

        stats = extract_diff_stats(diff)
        assert stats.deletions == 2

    def test_calculates_modifications(self):
        """Modifications should be min of insertions and deletions."""
        diff = """diff --git a/test.txt b/test.txt
--- a/test.txt
+++ b/test.txt
@@ -1,3 +1,3 @@
 line1
-old2
-old3
+new2
+new3
+added4"""

        stats = extract_diff_stats(diff)
        assert stats.insertions == 3
        assert stats.deletions == 2
        assert stats.modifications == 2  # min(3, 2)

    def test_counts_files_changed(self):
        """Should count number of distinct files in diff."""
        diff = """diff --git a/file1.txt b/file1.txt
--- a/file1.txt
+++ b/file1.txt
@@ -1 +1 @@
-old1
+new1
diff --git a/file2.txt b/file2.txt
--- a/file2.txt
+++ b/file2.txt
@@ -1 +1 @@
-old2
+new2"""

        stats = extract_diff_stats(diff)
        assert stats.files_changed == 2

    def test_handles_empty_diff(self):
        """Empty diff should return zero stats."""
        stats = extract_diff_stats("")

        assert stats.insertions == 0
        assert stats.deletions == 0
        assert stats.modifications == 0
        assert stats.files_changed == 0

    def test_ignores_file_marker_lines(self):
        """Should not count --- and +++ as deletions/insertions."""
        diff = """diff --git a/test.txt b/test.txt
--- a/test.txt
+++ b/test.txt
@@ -1 +1 @@
-old
+new"""

        stats = extract_diff_stats(diff)
        assert stats.insertions == 1
        assert stats.deletions == 1


# Table-driven test scenarios
@pytest.mark.parametrize(
    "scenario,old,new,expected_markers",
    [
        ("simple_addition", "a\nb\n", "a\nb\nc\n", ["+c"]),
        ("simple_deletion", "a\nb\nc\n", "a\nb\n", ["-c"]),
        ("simple_modification", "a\nb\n", "a\nX\n", ["-b", "+X"]),
        ("multiple_additions", "a\n", "a\nb\nc\n", ["+b", "+c"]),
        ("multiple_deletions", "a\nb\nc\n", "a\n", ["-b", "-c"]),
        ("mixed_changes", "a\nb\nc\n", "X\nb\nY\n", ["-a", "+X", "-c", "+Y"]),
        ("add_at_start", "b\n", "a\nb\n", ["+a"]),
        ("add_at_end", "a\n", "a\nb\n", ["+b"]),
        ("delete_at_start", "a\nb\n", "b\n", ["-a"]),
        ("delete_at_end", "a\nb\n", "a\n", ["-b"]),
        ("replace_all", "a\nb\n", "X\nY\n", ["-a", "-b", "+X", "+Y"]),
        ("add_middle", "a\nc\n", "a\nb\nc\n", ["+b"]),
        ("delete_middle", "a\nb\nc\n", "a\nc\n", ["-b"]),
        ("no_trailing_newline", "a\nb", "a\nX", ["-b", "+X"]),
    ],
)
def test_diff_scenarios(scenario, old, new, expected_markers):
    """Test various diff scenarios with expected markers."""
    diff = generate_unified_diff(old, new, "test.txt")

    for marker in expected_markers:
        assert marker in diff, f"Expected '{marker}' in diff for scenario '{scenario}'"
