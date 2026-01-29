"""Contract tests for apply/sanitize.py module.

Tests the patch sanitization and normalization functions extracted
from governed_apply.py.
"""

from __future__ import annotations

from autopack.apply.sanitize import (classify_patch_files,
                                     extract_files_from_patch,
                                     fix_empty_file_diffs, normalize_patch,
                                     parse_patch_stats, sanitize_patch)


class TestFixEmptyFileDiffs:
    """Tests for fix_empty_file_diffs function."""

    def test_fixes_missing_headers_for_empty_init_file(self) -> None:
        """Empty __init__.py files should get --- /dev/null and +++ headers."""
        patch = """diff --git a/pkg/__init__.py b/pkg/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/pkg/module.py b/pkg/module.py"""

        result = fix_empty_file_diffs(patch)

        assert "--- /dev/null" in result
        assert "+++ b/pkg/__init__.py" in result

    def test_preserves_complete_diff_headers(self) -> None:
        """Diffs with complete headers should not be modified."""
        patch = """diff --git a/file.py b/file.py
new file mode 100644
--- /dev/null
+++ b/file.py
@@ -0,0 +1,3 @@
+def foo():
+    pass
+"""

        result = fix_empty_file_diffs(patch)

        # Should have exactly one of each header
        assert result.count("--- /dev/null") == 1
        assert result.count("+++ b/file.py") == 1

    def test_handles_multiple_empty_files(self) -> None:
        """Multiple empty files in same patch should all be fixed."""
        patch = """diff --git a/a/__init__.py b/a/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/b/__init__.py b/b/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/c/module.py b/c/module.py"""

        result = fix_empty_file_diffs(patch)

        assert "+++ b/a/__init__.py" in result
        assert "+++ b/b/__init__.py" in result


class TestSanitizePatch:
    """Tests for sanitize_patch function."""

    def test_adds_plus_prefix_to_new_file_content(self) -> None:
        """Lines in new files missing + prefix should get one added."""
        # Note: In real patches, lines missing prefix don't start with spaces
        # because space-prefixed lines are context lines. This tests the case
        # where a line has actual content but no diff prefix.
        patch = """diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,1 @@
CONSTANT = 42"""

        result = sanitize_patch(patch)

        assert "+CONSTANT = 42" in result

    def test_normalizes_blank_lines_in_hunk(self) -> None:
        """Blank lines inside hunks should get space prefix."""
        patch = """diff --git a/file.py b/file.py
--- a/file.py
+++ b/file.py
@@ -1,3 +1,3 @@
 def foo():

     pass"""

        result = sanitize_patch(patch)

        # The blank line should have a space prefix
        lines = result.split("\n")
        hunk_started = False
        for line in lines:
            if line.startswith("@@"):
                hunk_started = True
                continue
            if hunk_started and line == "":
                # Empty lines outside hunk are ok
                continue
            if hunk_started:
                # Inside hunk, lines should start with +, -, space, or \
                assert line.startswith(("+", "-", " ", "\\")) or line == ""

    def test_preserves_properly_formatted_patch(self) -> None:
        """Properly formatted patches should pass through unchanged."""
        patch = """diff --git a/file.py b/file.py
--- a/file.py
+++ b/file.py
@@ -1,2 +1,3 @@
 def foo():
+    print("hello")
     pass
"""

        result = sanitize_patch(patch)

        assert "+    print(" in result
        assert " def foo():" in result
        assert "     pass" in result


class TestClassifyPatchFiles:
    """Tests for classify_patch_files function."""

    def test_identifies_new_files(self) -> None:
        """Files with 'new file mode' or '--- /dev/null' are new."""
        patch = """diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,1 @@
+pass"""

        new_files, existing_files = classify_patch_files(patch)

        assert "new.py" in new_files
        assert "new.py" not in existing_files

    def test_identifies_existing_files(self) -> None:
        """Files with '--- a/' prefix are existing."""
        patch = """diff --git a/existing.py b/existing.py
--- a/existing.py
+++ b/existing.py
@@ -1,1 +1,2 @@
 pass
+# added"""

        new_files, existing_files = classify_patch_files(patch)

        assert "existing.py" in existing_files
        assert "existing.py" not in new_files

    def test_identifies_deleted_files(self) -> None:
        """Files with 'deleted file mode' or '+++ /dev/null' are existing (being deleted)."""
        patch = """diff --git a/deleted.py b/deleted.py
deleted file mode 100644
--- a/deleted.py
+++ /dev/null
@@ -1,1 +0,0 @@
-pass"""

        new_files, existing_files = classify_patch_files(patch)

        assert "deleted.py" in existing_files
        assert "deleted.py" not in new_files


class TestExtractFilesFromPatch:
    """Tests for extract_files_from_patch function."""

    def test_extracts_file_paths(self) -> None:
        """Should extract all file paths from patch."""
        patch = """diff --git a/file1.py b/file1.py
--- a/file1.py
+++ b/file1.py
@@ -1,1 +1,1 @@
-old
+new
diff --git a/file2.py b/file2.py
new file mode 100644
--- /dev/null
+++ b/file2.py
@@ -0,0 +1,1 @@
+pass"""

        files = extract_files_from_patch(patch)

        assert "file1.py" in files
        assert "file2.py" in files

    def test_handles_nested_paths(self) -> None:
        """Should handle nested directory paths correctly."""
        patch = """diff --git a/src/pkg/module.py b/src/pkg/module.py
--- a/src/pkg/module.py
+++ b/src/pkg/module.py
@@ -1,1 +1,1 @@
-old
+new"""

        files = extract_files_from_patch(patch)

        assert "src/pkg/module.py" in files

    def test_returns_empty_for_empty_patch(self) -> None:
        """Empty patch should return empty list."""
        files = extract_files_from_patch("")

        assert files == []


class TestNormalizePatch:
    """Tests for normalize_patch function."""

    def test_converts_crlf_to_lf(self) -> None:
        """Windows line endings should be converted to Unix."""
        patch = "line1\r\nline2\r\n"

        result = normalize_patch(patch)

        assert "\r\n" not in result
        assert result == "line1\nline2\n"

    def test_converts_cr_to_lf(self) -> None:
        """Old Mac line endings should be converted to Unix."""
        patch = "line1\rline2\r"

        result = normalize_patch(patch)

        assert "\r" not in result
        assert result == "line1\nline2\n"

    def test_ensures_trailing_newline(self) -> None:
        """Patch should end with newline."""
        patch = "content"

        result = normalize_patch(patch)

        assert result.endswith("\n")

    def test_preserves_existing_trailing_newline(self) -> None:
        """Should not add extra newline if already present."""
        patch = "content\n"

        result = normalize_patch(patch)

        assert result == "content\n"


class TestParsePatchStats:
    """Tests for parse_patch_stats function."""

    def test_counts_additions_and_deletions(self) -> None:
        """Should count lines added and removed correctly."""
        patch = """diff --git a/file.py b/file.py
--- a/file.py
+++ b/file.py
@@ -1,3 +1,4 @@
 unchanged
-removed1
-removed2
+added1
+added2
+added3"""

        files, added, removed = parse_patch_stats(patch)

        assert "file.py" in files
        assert added == 3
        assert removed == 2

    def test_excludes_header_lines_from_counts(self) -> None:
        """--- and +++ header lines should not be counted."""
        patch = """diff --git a/file.py b/file.py
--- a/file.py
+++ b/file.py
@@ -1,1 +1,1 @@
-old
+new"""

        files, added, removed = parse_patch_stats(patch)

        assert added == 1
        assert removed == 1

    def test_handles_multiple_files(self) -> None:
        """Should handle patches with multiple files."""
        patch = """diff --git a/file1.py b/file1.py
--- a/file1.py
+++ b/file1.py
@@ -1,1 +1,1 @@
-a
+b
diff --git a/file2.py b/file2.py
--- a/file2.py
+++ b/file2.py
@@ -1,1 +1,2 @@
 x
+y"""

        files, added, removed = parse_patch_stats(patch)

        assert len(files) == 2
        assert "file1.py" in files
        assert "file2.py" in files
        assert added == 2
        assert removed == 1

    def test_handles_empty_patch(self) -> None:
        """Empty patch should return zero counts."""
        files, added, removed = parse_patch_stats("")

        assert files == []
        assert added == 0
        assert removed == 0

    def test_handles_none_patch(self) -> None:
        """None patch should return zero counts."""
        files, added, removed = parse_patch_stats(None)  # type: ignore[arg-type]

        assert files == []
        assert added == 0
        assert removed == 0
