"""Contract tests for apply/engine.py module.

Tests the core patch application engine functions extracted from governed_apply.py.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from autopack.apply.engine import (
    PatchApplyError,
    apply_patch_directly,
    check_existing_files_for_new_patches,
    check_git_apply,
    is_ndjson_synthetic_patch,
    run_git_apply,
    validate_patch_context,
)


class TestPatchApplyError:
    """Tests for PatchApplyError exception."""

    def test_can_raise_with_message(self) -> None:
        """Should be raisable with a message."""
        try:
            raise PatchApplyError("Test error message")
        except PatchApplyError as e:
            assert "Test error message" in str(e)


class TestValidatePatchContext:
    """Tests for validate_patch_context function."""

    def test_validates_matching_context(self) -> None:
        """Should accept patches with matching context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            # Create a file with known content
            test_file = workspace / "test.py"
            test_file.write_text("def foo():\n    pass\n")

            patch = """diff --git a/test.py b/test.py
--- a/test.py
+++ b/test.py
@@ -1,2 +1,3 @@
 def foo():
+    print("hello")
     pass
"""
            errors = validate_patch_context(patch, workspace)

            assert errors == []

    def test_detects_context_mismatch(self) -> None:
        """Should detect when context doesn't match file content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            # Create a file with different content than the patch expects
            test_file = workspace / "test.py"
            test_file.write_text("def bar():\n    pass\n")

            patch = """diff --git a/test.py b/test.py
--- a/test.py
+++ b/test.py
@@ -1,2 +1,3 @@
 def foo():
+    print("hello")
     pass
"""
            errors = validate_patch_context(patch, workspace)

            assert len(errors) > 0
            assert any("mismatch" in e.lower() for e in errors)

    def test_skips_new_files(self) -> None:
        """Should skip validation for new files (no existing file to compare)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            patch = """diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+def foo():
+    pass
"""
            errors = validate_patch_context(patch, workspace)

            assert errors == []


class TestCheckExistingFilesForNewPatches:
    """Tests for check_existing_files_for_new_patches function."""

    def test_allows_new_file_when_not_exists(self) -> None:
        """Should allow creating new files that don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            patch = """diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,1 @@
+pass
"""
            # Should not raise
            check_existing_files_for_new_patches(patch, workspace)

    def test_raises_when_file_exists(self) -> None:
        """Should raise when trying to create file that already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            # Create existing file
            existing = workspace / "existing.py"
            existing.write_text("original content")

            patch = """diff --git a/existing.py b/existing.py
new file mode 100644
--- /dev/null
+++ b/existing.py
@@ -0,0 +1,1 @@
+new content
"""
            try:
                check_existing_files_for_new_patches(patch, workspace)
                assert False, "Should have raised PatchApplyError"
            except PatchApplyError as e:
                assert "existing file as new" in str(e).lower()


class TestApplyPatchDirectly:
    """Tests for apply_patch_directly function."""

    def test_writes_new_file(self) -> None:
        """Should write new files directly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            patch = """diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+def foo():
+    pass
"""
            success, files = apply_patch_directly(patch, workspace)

            assert success
            assert "new.py" in files
            assert (workspace / "new.py").exists()
            content = (workspace / "new.py").read_text()
            assert "def foo():" in content

    def test_creates_parent_directories(self) -> None:
        """Should create parent directories for new files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            patch = """diff --git a/pkg/sub/module.py b/pkg/sub/module.py
new file mode 100644
--- /dev/null
+++ b/pkg/sub/module.py
@@ -0,0 +1,1 @@
+pass
"""
            success, files = apply_patch_directly(patch, workspace)

            assert success
            assert (workspace / "pkg" / "sub" / "module.py").exists()

    def test_skips_existing_file_patches(self) -> None:
        """Should skip patches for existing files (not new file mode)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            patch = """diff --git a/existing.py b/existing.py
--- a/existing.py
+++ b/existing.py
@@ -1,1 +1,2 @@
 original
+added
"""
            success, files = apply_patch_directly(patch, workspace)

            # Should return False because no new files were written
            assert not success
            assert files == []


class TestIsNdjsonSyntheticPatch:
    """Tests for is_ndjson_synthetic_patch function."""

    def test_detects_ndjson_header(self) -> None:
        """Should detect NDJSON synthetic patch header."""
        patch = """# NDJSON Operations Applied (3 files)
diff --git a/file1.py b/file1.py
+++ b/file1.py
"""
        assert is_ndjson_synthetic_patch(patch)

    def test_detects_with_leading_whitespace(self) -> None:
        """Should detect even with leading whitespace."""
        patch = """  # NDJSON Operations Applied (3 files)
diff --git a/file1.py b/file1.py
"""
        assert is_ndjson_synthetic_patch(patch)

    def test_rejects_normal_patch(self) -> None:
        """Should reject normal patches."""
        patch = """diff --git a/file.py b/file.py
--- a/file.py
+++ b/file.py
@@ -1,1 +1,2 @@
 original
+added
"""
        assert not is_ndjson_synthetic_patch(patch)

    def test_rejects_empty_patch(self) -> None:
        """Should reject empty patches."""
        assert not is_ndjson_synthetic_patch("")
        assert not is_ndjson_synthetic_patch("   ")


class TestCheckGitApply:
    """Tests for check_git_apply function."""

    def test_returns_mode_error_for_unknown_mode(self) -> None:
        """Should return error for unknown mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            patch_file = workspace / "test.diff"
            patch_file.write_text("")

            success, error = check_git_apply(workspace, patch_file, "unknown_mode")

            assert not success
            assert "Unknown mode" in error


class TestRunGitApply:
    """Tests for run_git_apply function."""

    def test_returns_mode_error_for_unknown_mode(self) -> None:
        """Should return error for unknown mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            patch_file = workspace / "test.diff"
            patch_file.write_text("")

            success, error = run_git_apply(workspace, patch_file, "unknown_mode")

            assert not success
            assert "Unknown mode" in error


class TestApplyPatchIntegration:
    """Integration tests for apply_patch function."""

    def test_handles_empty_patch(self) -> None:
        """Should accept empty patches."""
        from autopack.apply.engine import apply_patch

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            success, error = apply_patch("", workspace)

            assert success
            assert error is None

    def test_handles_whitespace_only_patch(self) -> None:
        """Should accept whitespace-only patches."""
        from autopack.apply.engine import apply_patch

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            success, error = apply_patch("   \n  \n", workspace)

            assert success
            assert error is None
