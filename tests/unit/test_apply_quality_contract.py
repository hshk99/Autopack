"""Contract tests for apply/quality.py module.

Tests the patch quality validation functions extracted from governed_apply.py.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from autopack.apply.quality import (
    check_file_truncation,
    check_merge_conflict_markers,
    check_structural_similarity,
    check_symbol_preservation,
    check_yaml_truncation,
    detect_truncated_content,
    extract_python_symbols,
    validate_patch_quality,
    validate_python_syntax,
)


class TestExtractPythonSymbols:
    """Tests for extract_python_symbols function."""

    def test_extracts_function_names(self) -> None:
        """Should extract function definitions."""
        source = """
def foo():
    pass

def bar():
    pass
"""
        symbols = extract_python_symbols(source)

        assert "foo" in symbols
        assert "bar" in symbols

    def test_extracts_class_names(self) -> None:
        """Should extract class definitions."""
        source = """
class MyClass:
    pass

class AnotherClass:
    pass
"""
        symbols = extract_python_symbols(source)

        assert "MyClass" in symbols
        assert "AnotherClass" in symbols

    def test_extracts_async_function_names(self) -> None:
        """Should extract async function definitions."""
        source = """
async def async_foo():
    pass
"""
        symbols = extract_python_symbols(source)

        assert "async_foo" in symbols

    def test_extracts_uppercase_constants(self) -> None:
        """Should extract uppercase constants."""
        source = """
MY_CONSTANT = 42
ANOTHER_ONE = "test"
"""
        symbols = extract_python_symbols(source)

        assert "MY_CONSTANT" in symbols
        assert "ANOTHER_ONE" in symbols

    def test_ignores_lowercase_variables(self) -> None:
        """Should ignore lowercase variables."""
        source = """
my_var = 42
"""
        symbols = extract_python_symbols(source)

        assert "my_var" not in symbols

    def test_returns_empty_set_for_invalid_syntax(self) -> None:
        """Should return empty set for invalid Python."""
        source = "def broken("

        symbols = extract_python_symbols(source)

        assert symbols == set()


class TestCheckSymbolPreservation:
    """Tests for check_symbol_preservation function."""

    def test_accepts_no_symbol_loss(self) -> None:
        """Should accept when no symbols are lost."""
        old = """
def foo():
    pass
"""
        new = """
def foo():
    return 42
"""
        is_valid, error = check_symbol_preservation(old, new, max_lost_ratio=0.3)

        assert is_valid
        assert error == ""

    def test_accepts_minor_symbol_loss(self) -> None:
        """Should accept when symbol loss is below threshold."""
        old = """
def foo():
    pass

def bar():
    pass

def baz():
    pass

def qux():
    pass
"""
        new = """
def foo():
    pass

def bar():
    pass

def baz():
    pass
"""
        is_valid, error = check_symbol_preservation(old, new, max_lost_ratio=0.3)

        assert is_valid

    def test_rejects_major_symbol_loss(self) -> None:
        """Should reject when too many symbols are lost."""
        old = """
def foo():
    pass

def bar():
    pass

def baz():
    pass
"""
        new = """
def foo():
    pass
"""
        is_valid, error = check_symbol_preservation(old, new, max_lost_ratio=0.3)

        assert not is_valid
        assert "symbol_preservation_violation" in error
        assert "bar" in error or "baz" in error


class TestCheckStructuralSimilarity:
    """Tests for check_structural_similarity function."""

    def test_accepts_similar_content(self) -> None:
        """Should accept when content is similar enough."""
        old = "line1\nline2\nline3\nline4\nline5"
        new = "line1\nline2\nline3\nline4\nline5_modified"

        is_valid, error = check_structural_similarity(old, new, min_ratio=0.6)

        assert is_valid
        assert error == ""

    def test_rejects_drastically_different_content(self) -> None:
        """Should reject when content is too different."""
        old = "aaaaaaaaaa\nbbbbbbbbbb\ncccccccccc"
        new = "xxxxxxxxxx\nyyyyyyyyyy\nzzzzzzzzzz"

        is_valid, error = check_structural_similarity(old, new, min_ratio=0.6)

        assert not is_valid
        assert "structural_similarity_violation" in error


class TestValidatePatchQuality:
    """Tests for validate_patch_quality function."""

    def test_accepts_valid_patch(self) -> None:
        """Should accept a well-formed patch."""
        patch = """diff --git a/file.py b/file.py
index 1234567..abcdefg 100644
--- a/file.py
+++ b/file.py
@@ -1,2 +1,3 @@
 def foo():
+    print("hello")
     pass
"""
        errors = validate_patch_quality(patch)

        assert errors == []

    def test_detects_truncation_ellipsis(self) -> None:
        """Should detect truncation markers."""
        patch = """diff --git a/file.py b/file.py
index 1234567..abcdefg 100644
--- a/file.py
+++ b/file.py
@@ -1,2 +1,3 @@
+...
"""
        errors = validate_patch_quality(patch)

        assert any("truncation" in e.lower() or "ellipsis" in e.lower() for e in errors)

    def test_detects_malformed_hunk_header(self) -> None:
        """Should detect malformed hunk headers."""
        patch = """diff --git a/file.py b/file.py
index 1234567..abcdefg 100644
--- a/file.py
+++ b/file.py
@@ this is not valid @@
+content
"""
        errors = validate_patch_quality(patch)

        assert any("malformed" in e.lower() for e in errors)

    def test_detects_incomplete_diff_structure(self) -> None:
        """Should detect missing diff components."""
        patch = """diff --git a/file.py b/file.py
+content
"""
        errors = validate_patch_quality(patch)

        assert any("incomplete" in e.lower() for e in errors)

    def test_ignores_ellipsis_in_strings(self) -> None:
        """Should not flag ellipsis inside strings."""
        patch = """diff --git a/file.py b/file.py
index 1234567..abcdefg 100644
--- a/file.py
+++ b/file.py
@@ -1,1 +1,2 @@
 def foo():
+    print("Loading...")
"""
        errors = validate_patch_quality(patch)

        # Should not flag the "..." in the string
        assert not any("truncation" in e.lower() for e in errors)


class TestDetectTruncatedContent:
    """Tests for detect_truncated_content function."""

    def test_detects_unclosed_quote(self) -> None:
        """Should detect unclosed quotes at end of new file."""
        patch = """diff --git a/file.py b/file.py
new file mode 100644
--- /dev/null
+++ b/file.py
@@ -0,0 +1,2 @@
+def foo():
+    return "unclosed"""

        errors = detect_truncated_content(patch)

        assert any("unclosed quote" in e.lower() for e in errors)

    def test_accepts_complete_new_file(self) -> None:
        """Should accept properly terminated new files."""
        patch = """diff --git a/file.py b/file.py
new file mode 100644
--- /dev/null
+++ b/file.py
@@ -0,0 +1,3 @@
+def foo():
+    return "complete"
+"""
        errors = detect_truncated_content(patch)

        assert errors == []


class TestCheckFileTruncation:
    """Tests for check_file_truncation function."""

    def test_detects_unclosed_double_quote(self) -> None:
        """Should detect unclosed double quotes."""
        lines = ['return "unclosed']

        errors = check_file_truncation("test.py", lines)

        assert any("unclosed quote" in e.lower() for e in errors)

    def test_accepts_matched_quotes(self) -> None:
        """Should accept properly matched quotes."""
        lines = ['return "complete"']

        errors = check_file_truncation("test.py", lines)

        assert errors == []


class TestCheckYamlTruncation:
    """Tests for check_yaml_truncation function."""

    def test_detects_empty_list_marker(self) -> None:
        """Should detect file ending with empty list marker."""
        lines = ["items:", "-"]

        errors = check_yaml_truncation("test.yaml", lines)

        assert any("empty list marker" in e.lower() for e in errors)

    def test_detects_incomplete_list_item(self) -> None:
        """Should detect incomplete list item."""
        lines = ["items:", "- "]

        errors = check_yaml_truncation("test.yaml", lines)

        assert any("incomplete list item" in e.lower() for e in errors)

    def test_accepts_complete_yaml(self) -> None:
        """Should accept complete YAML."""
        lines = ["name: test", "version: 1.0"]

        errors = check_yaml_truncation("test.yaml", lines)

        # May have structural errors from yaml parser, but not truncation-specific
        assert not any("empty list marker" in e.lower() for e in errors)
        assert not any("incomplete list item" in e.lower() for e in errors)


class TestValidatePythonSyntax:
    """Tests for validate_python_syntax function."""

    def test_accepts_valid_python(self) -> None:
        """Should accept valid Python syntax."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("def foo():\n    pass\n")
            path = Path(f.name)

        try:
            is_valid, error = validate_python_syntax(path)

            assert is_valid
            assert error is None
        finally:
            path.unlink()

    def test_rejects_invalid_python(self) -> None:
        """Should reject invalid Python syntax."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("def broken(\n")
            path = Path(f.name)

        try:
            is_valid, error = validate_python_syntax(path)

            assert not is_valid
            assert error is not None
        finally:
            path.unlink()

    def test_skips_non_python_files(self) -> None:
        """Should skip non-Python files."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("not python")
            path = Path(f.name)

        try:
            is_valid, error = validate_python_syntax(path)

            assert is_valid
            assert error is None
        finally:
            path.unlink()


class TestCheckMergeConflictMarkers:
    """Tests for check_merge_conflict_markers function."""

    def test_detects_conflict_start_marker(self) -> None:
        """Should detect <<<<<<< marker."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("<<<<<<< HEAD\nconflict\n")
            path = Path(f.name)

        try:
            has_conflicts, error = check_merge_conflict_markers(path)

            assert has_conflicts
            assert "<<<<<<<" in error
        finally:
            path.unlink()

    def test_detects_conflict_end_marker(self) -> None:
        """Should detect >>>>>>> marker."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(">>>>>>> branch\n")
            path = Path(f.name)

        try:
            has_conflicts, error = check_merge_conflict_markers(path)

            assert has_conflicts
            assert ">>>>>>>" in error
        finally:
            path.unlink()

    def test_accepts_clean_file(self) -> None:
        """Should accept files without conflict markers."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("def foo():\n    pass\n")
            path = Path(f.name)

        try:
            has_conflicts, error = check_merge_conflict_markers(path)

            assert not has_conflicts
            assert error is None
        finally:
            path.unlink()

    def test_ignores_equals_separator(self) -> None:
        """Should not flag ======= which is common in code comments."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("# =============================\n")
            path = Path(f.name)

        try:
            has_conflicts, error = check_merge_conflict_markers(path)

            assert not has_conflicts
        finally:
            path.unlink()
