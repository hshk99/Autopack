"""IMP-SAFETY-008: Test Layer 2 scope validation at patch application.

Validates that GovernedApplyPath correctly blocks patches that attempt to
modify files outside the configured scope paths, even when the Builder
generates out-of-scope changes.

This is the second validation layer (post-Builder, at patch application).
Layer 1 (pre-Builder) is in ScopeContextValidator.
"""

from pathlib import Path

from autopack.governed_apply import GovernedApplyPath


class TestLayer2ScopeValidation:
    """Test suite for Layer 2 scope enforcement at patch application."""

    def test_patch_blocked_when_file_outside_scope(self, tmp_path: Path):
        """Patch that touches files outside scope should be rejected."""
        # Setup: create files in workspace
        src_file = tmp_path / "src" / "main.py"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("# main.py\n", encoding="utf-8")

        # Create governed apply with restricted scope
        apply_path = GovernedApplyPath(
            workspace=tmp_path,
            run_type="project_build",
            scope_paths=["src/main.py"],  # Only this file is in scope
        )

        # Patch tries to modify a file outside scope
        patch_content = """diff --git a/tests/test_main.py b/tests/test_main.py
new file mode 100644
--- /dev/null
+++ b/tests/test_main.py
@@ -0,0 +1,3 @@
+# test file
+def test_main():
+    pass
"""

        success, error = apply_path.apply_patch(patch_content, full_file_mode=True)

        assert success is False
        assert error is not None
        assert "Outside scope" in error or "scope" in error.lower()

    def test_patch_allowed_when_file_in_scope(self, tmp_path: Path):
        """Patch that only touches files within scope should succeed."""
        # Setup: create files in workspace
        src_dir = tmp_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)

        # Create governed apply with scope including new files under src/
        apply_path = GovernedApplyPath(
            workspace=tmp_path,
            run_type="project_build",
            scope_paths=["src/"],  # All files under src/ are in scope
        )

        # Patch creates a new file within scope (proper git diff format)
        patch_content = """diff --git a/src/utils.py b/src/utils.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/src/utils.py
@@ -0,0 +1,3 @@
+# utils module
+def helper():
+    return True
"""

        success, error = apply_path.apply_patch(patch_content, full_file_mode=True)

        assert success is True
        assert error is None
        # Verify file was created
        assert (tmp_path / "src" / "utils.py").exists()

    def test_scope_validation_with_multiple_files(self, tmp_path: Path):
        """Patch with multiple files - all must be in scope."""
        # Setup
        src_dir = tmp_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)

        apply_path = GovernedApplyPath(
            workspace=tmp_path,
            run_type="project_build",
            scope_paths=["src/main.py", "src/config.py"],  # Only specific files
        )

        # Patch touches in-scope and out-of-scope files
        patch_content = """diff --git a/src/main.py b/src/main.py
new file mode 100644
--- /dev/null
+++ b/src/main.py
@@ -0,0 +1 @@
+# main
diff --git a/src/secret.py b/src/secret.py
new file mode 100644
--- /dev/null
+++ b/src/secret.py
@@ -0,0 +1 @@
+# out of scope file
"""

        success, error = apply_path.apply_patch(patch_content, full_file_mode=True)

        assert success is False
        assert error is not None
        assert "scope" in error.lower()

    def test_no_scope_means_no_restriction(self, tmp_path: Path):
        """When scope_paths is empty, no scope restrictions apply."""
        # Setup
        src_dir = tmp_path / "anywhere"
        src_dir.mkdir(parents=True, exist_ok=True)

        apply_path = GovernedApplyPath(
            workspace=tmp_path,
            run_type="project_build",
            scope_paths=[],  # No scope restriction
        )

        # Patch can create files anywhere (proper git diff format)
        patch_content = """diff --git a/anywhere/file.py b/anywhere/file.py
new file mode 100644
index 0000000..abcdef0
--- /dev/null
+++ b/anywhere/file.py
@@ -0,0 +1 @@
+# this should work
"""

        success, error = apply_path.apply_patch(patch_content, full_file_mode=True)

        assert success is True
        assert error is None

    def test_directory_scope_allows_nested_files(self, tmp_path: Path):
        """Directory scope should allow all files within that directory."""
        # Setup
        src_dir = tmp_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)

        apply_path = GovernedApplyPath(
            workspace=tmp_path,
            run_type="project_build",
            scope_paths=["src/"],  # Directory scope
        )

        # Patch creates nested file within scope (proper git diff format)
        patch_content = """diff --git a/src/subdir/nested/deep.py b/src/subdir/nested/deep.py
new file mode 100644
index 0000000..fedcba9
--- /dev/null
+++ b/src/subdir/nested/deep.py
@@ -0,0 +1 @@
+# deeply nested file
"""

        # Create parent directories for the patch to work
        (tmp_path / "src" / "subdir" / "nested").mkdir(parents=True, exist_ok=True)

        success, error = apply_path.apply_patch(patch_content, full_file_mode=True)

        assert success is True
        assert error is None

    def test_protected_path_takes_precedence_over_scope(self, tmp_path: Path):
        """Protected paths should block even if file is technically in scope."""
        apply_path = GovernedApplyPath(
            workspace=tmp_path,
            run_type="project_build",
            scope_paths=["src/autopack/"],  # In scope
            # Default protected_paths include src/autopack/
        )

        # Patch tries to modify protected file
        patch_content = """diff --git a/src/autopack/config.py b/src/autopack/config.py
new file mode 100644
--- /dev/null
+++ b/src/autopack/config.py
@@ -0,0 +1 @@
+# trying to modify core config
"""

        success, error = apply_path.apply_patch(patch_content, full_file_mode=True)

        assert success is False
        # Either protected path or scope error - protection takes precedence
        assert error is not None

    def test_scope_normalization_handles_windows_paths(self, tmp_path: Path):
        """Scope validation should handle Windows-style path separators."""
        apply_path = GovernedApplyPath(
            workspace=tmp_path,
            run_type="project_build",
            scope_paths=["src\\utils\\"],  # Windows-style path
        )

        # Validate internal method handles normalization
        ok, violations = apply_path._validate_patch_paths(["src/utils/helper.py"])

        assert ok is True
        assert violations == []
