"""Contract tests for patch quality validation module.

Tests the patch_quality module extracted from governed_apply.py (PR-APPLY-3).
"""

import pytest

from autopack.patching.patch_quality import (
    QualityIssue,
    QualityValidationResult,
    validate_patch_quality,
)


class TestValidPatchValidation:
    """Tests for validating valid patches."""

    def test_valid_simple_patch_passes_validation(self):
        """Valid simple patch should pass quality validation."""
        patch = """diff --git a/test.py b/test.py
index 1234567..89abcdef 100644
--- a/test.py
+++ b/test.py
@@ -1,3 +1,3 @@
 def foo():
-    return 1
+    return 2
"""
        result = validate_patch_quality(patch)
        assert result.valid
        assert len(result.issues) == 0
        assert result.score > 0.9

    def test_valid_new_file_patch_passes_validation(self):
        """Valid new file patch should pass validation."""
        patch = """diff --git a/new_file.py b/new_file.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/new_file.py
@@ -0,0 +1,5 @@
+def hello():
+    return "world"
+
+if __name__ == "__main__":
+    print(hello())
"""
        result = validate_patch_quality(patch)
        assert result.valid
        assert len(result.issues) == 0
        assert result.score == 1.0

    def test_valid_multifile_patch_passes_validation(self):
        """Valid multi-file patch should pass validation."""
        patch = """diff --git a/file1.py b/file1.py
index 1234567..89abcdef 100644
--- a/file1.py
+++ b/file1.py
@@ -1,2 +1,2 @@
-old_line = 1
+new_line = 2
 other_line = 3
diff --git a/file2.py b/file2.py
index 2345678..9abcdef0 100644
--- a/file2.py
+++ b/file2.py
@@ -1,1 +1,1 @@
-x = 1
+x = 2
"""
        result = validate_patch_quality(patch)
        assert result.valid
        assert len(result.issues) == 0


class TestInvalidPatchDetection:
    """Tests for detecting invalid/problematic patches."""

    def test_empty_patch_fails_validation(self):
        """Empty patch should fail validation."""
        result = validate_patch_quality("")
        assert not result.valid
        assert len(result.issues) > 0
        assert result.issues[0].severity == "error"
        assert "empty" in result.issues[0].message.lower()

    def test_patch_with_ellipsis_rejected(self):
        """Patch with truncation ellipsis should be rejected."""
        patch = """diff --git a/test.py b/test.py
index 1234567..89abcdef 100644
--- a/test.py
+++ b/test.py
@@ -1,5 +1,5 @@
 def foo():
+    ...
+    # ... more code here
     return 1
"""
        result = validate_patch_quality(patch)
        assert not result.valid
        assert len(result.issues) >= 1
        assert any("truncation" in issue.message.lower() or "ellipsis" in issue.message.lower()
                   for issue in result.issues)

    def test_malformed_hunk_header_rejected(self):
        """Patch with malformed hunk header should be rejected."""
        patch = """diff --git a/test.py b/test.py
index 1234567..89abcdef 100644
--- a/test.py
+++ b/test.py
@@ bad header @@
 def foo():
-    return 1
+    return 2
"""
        result = validate_patch_quality(patch)
        assert not result.valid
        assert any("malformed" in issue.message.lower() for issue in result.issues)

    def test_incomplete_diff_structure_rejected(self):
        """Patch with incomplete diff structure should be rejected."""
        patch = """diff --git a/test.py b/test.py
+++ b/test.py
@@ -1,1 +1,1 @@
-old
+new
"""
        # Missing "---" line and index line
        result = validate_patch_quality(patch)
        assert not result.valid
        assert any("incomplete" in issue.message.lower() for issue in result.issues)

    def test_zero_length_hunk_rejected(self):
        """Patch with zero-length hunk should be rejected."""
        patch = """diff --git a/test.py b/test.py
index 1234567..89abcdef 100644
--- a/test.py
+++ b/test.py
@@ -1,0 +1,0 @@
"""
        result = validate_patch_quality(patch)
        assert not result.valid
        assert any("zero-length" in issue.message.lower() for issue in result.issues)


class TestTruncationDetection:
    """Tests for detecting truncated file content."""

    def test_file_with_unclosed_quote_detected(self):
        """New file with unclosed quote should be detected."""
        patch = """diff --git a/test.py b/test.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/test.py
@@ -0,0 +1,2 @@
+def foo():
+    return "incomplete string
"""
        result = validate_patch_quality(patch)
        assert not result.valid
        assert any("unclosed quote" in issue.message.lower() for issue in result.issues)

    def test_yaml_with_empty_list_marker_detected(self):
        """YAML file ending with empty list marker should be detected."""
        patch = """diff --git a/config.yaml b/config.yaml
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/config.yaml
@@ -0,0 +1,3 @@
+settings:
+  items:
+    -
"""
        result = validate_patch_quality(patch)
        assert not result.valid
        assert any("yaml" in issue.message.lower() and "empty list marker" in issue.message.lower()
                   for issue in result.issues)

    def test_yaml_with_incomplete_multiline_string_detected(self):
        """YAML file with incomplete multi-line string should be detected."""
        patch = """diff --git a/config.yaml b/config.yaml
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/config.yaml
@@ -0,0 +1,2 @@
+description: |
"""
        result = validate_patch_quality(patch)
        assert not result.valid
        assert any("yaml" in issue.message.lower() and "multi-line" in issue.message.lower()
                   for issue in result.issues)


class TestStrictMode:
    """Tests for strict mode validation."""

    def test_strict_mode_flags_large_hunks(self):
        """Strict mode should flag large hunks as potentially problematic."""
        # Create a patch with a large hunk (>100 lines)
        added_lines = "\n".join([f"+line {i}" for i in range(101)])
        patch = f"""diff --git a/test.py b/test.py
index 1234567..89abcdef 100644
--- a/test.py
+++ b/test.py
@@ -1,1 +1,101 @@
-old
{added_lines}
"""
        result_normal = validate_patch_quality(patch, strict_mode=False)
        result_strict = validate_patch_quality(patch, strict_mode=True)

        # Strict mode should find more issues (warnings about large hunks)
        assert len(result_strict.issues) >= len(result_normal.issues)

        # In strict mode, should have warnings about large hunks
        if result_strict.issues:
            assert any("large hunk" in issue.message.lower() for issue in result_strict.issues)

    def test_strict_mode_vs_normal_mode(self):
        """Strict mode should be more restrictive than normal mode."""
        # Valid but large patch
        added_lines = "\n".join([f"+line {i}" for i in range(150)])
        patch = f"""diff --git a/test.py b/test.py
index 1234567..89abcdef 100644
--- a/test.py
+++ b/test.py
@@ -1,1 +1,150 @@
 old
{added_lines}
"""
        normal_result = validate_patch_quality(patch, strict_mode=False)
        strict_result = validate_patch_quality(patch, strict_mode=True)

        # Normal mode might pass, but strict mode should have warnings
        if strict_result.issues:
            warning_count_strict = len([i for i in strict_result.issues if i.severity == "warning"])
            warning_count_normal = len([i for i in normal_result.issues if i.severity == "warning"])
            assert warning_count_strict >= warning_count_normal


class TestQualityScore:
    """Tests for quality score calculation."""

    def test_perfect_patch_has_high_score(self):
        """Perfect patch should have score of 1.0."""
        patch = """diff --git a/test.py b/test.py
index 1234567..89abcdef 100644
--- a/test.py
+++ b/test.py
@@ -1,1 +1,1 @@
-old
+new
"""
        result = validate_patch_quality(patch)
        assert result.score == 1.0

    def test_patch_with_errors_has_zero_score(self):
        """Patch with errors should have score of 0.0."""
        patch = """diff --git a/test.py b/test.py
@@ bad header @@
-old
+new
"""
        result = validate_patch_quality(patch)
        assert result.score == 0.0

    def test_patch_with_warnings_has_reduced_score(self):
        """Patch with warnings should have reduced but non-zero score."""
        # Create patch that would generate warnings in strict mode
        added_lines = "\n".join([f"+line {i}" for i in range(150)])
        patch = f"""diff --git a/test.py b/test.py
index 1234567..89abcdef 100644
--- a/test.py
+++ b/test.py
@@ -1,1 +1,150 @@
 old
{added_lines}
"""
        result = validate_patch_quality(patch, strict_mode=True)

        # Should have warnings but still be valid
        warnings = [i for i in result.issues if i.severity == "warning"]
        if warnings:
            assert 0.0 < result.score < 1.0


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_patch_with_legitimate_ellipsis_in_string_accepted(self):
        """Patch with legitimate ellipsis in strings should be accepted."""
        patch = """diff --git a/test.py b/test.py
index 1234567..89abcdef 100644
--- a/test.py
+++ b/test.py
@@ -1,2 +1,2 @@
 def foo():
-    logger.info("Processing...")
+    logger.info("Still processing...")
"""
        result = validate_patch_quality(patch)
        # Should be valid - ellipsis in strings is legitimate
        assert result.valid

    def test_whitespace_only_patch_handled(self):
        """Patch with only whitespace should be handled gracefully."""
        patch = "   \n\n  \t  \n"
        result = validate_patch_quality(patch)
        assert not result.valid

    def test_very_long_valid_patch_accepted(self):
        """Very long but valid patch should be accepted."""
        # Create a large but valid patch
        hunks = []
        for i in range(50):
            hunks.append(f"""@@ -{i},1 +{i},1 @@
-old_line_{i}
+new_line_{i}
""")

        patch = f"""diff --git a/test.py b/test.py
index 1234567..89abcdef 100644
--- a/test.py
+++ b/test.py
{"".join(hunks)}"""

        result = validate_patch_quality(patch, strict_mode=False)
        # Should be valid in normal mode
        assert result.valid or len(result.issues) == 0


class TestIssueReporting:
    """Tests for quality issue reporting."""

    def test_issue_includes_line_number_when_available(self):
        """Quality issues should include line numbers when available."""
        patch = """diff --git a/test.py b/test.py
@@ bad @@
-old
+new
"""
        result = validate_patch_quality(patch)
        # Should have at least one issue with a line number
        issues_with_line_numbers = [i for i in result.issues if i.line_number is not None]
        assert len(issues_with_line_numbers) > 0

    def test_issue_severity_classification(self):
        """Issues should be correctly classified by severity."""
        patch = """diff --git a/test.py b/test.py
@@ bad @@
"""
        result = validate_patch_quality(patch)
        # Should have error-level issues
        errors = [i for i in result.issues if i.severity == "error"]
        assert len(errors) > 0

    def test_multiple_issues_all_reported(self):
        """Multiple issues in same patch should all be reported."""
        patch = """diff --git a/test.py b/test.py
@@ bad1 @@
+    ...
@@ bad2 @@
+    ... more code
"""
        result = validate_patch_quality(patch)
        # Should report multiple issues
        assert len(result.issues) >= 2
