"""Tests for deliverables_validator module"""

from pathlib import Path

from autopack.deliverables_validator import (
    extract_deliverables_from_scope,
    extract_paths_from_patch,
    format_validation_feedback_for_builder,
    normalize_path,
    validate_deliverables,
)


class TestExtractPathsFromPatch:
    """Test patch path extraction"""

    def test_extract_from_diff_format(self):
        """Test extracting paths from git diff format"""
        patch = """
diff --git a/src/main.py b/src/main.py
index 123..456 789
--- a/src/main.py
+++ b/src/main.py
@@ -1,3 +1,4 @@
+import sys

diff --git a/tests/test_main.py b/tests/test_main.py
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/tests/test_main.py
@@ -0,0 +1,10 @@
+def test_example():
"""
        paths = extract_paths_from_patch(patch)
        assert "src/main.py" in paths
        assert "tests/test_main.py" in paths
        assert len(paths) == 2

    def test_extract_from_json_format(self):
        """Test extracting paths from JSON format"""
        patch = """
{
  "files": [
    {"path": "src/module.py", "content": "..."},
    {"path": "tests/test_module.py", "content": "..."}
  ]
}
"""
        paths = extract_paths_from_patch(patch)
        assert "src/module.py" in paths
        assert "tests/test_module.py" in paths
        assert len(paths) == 2

    def test_empty_patch(self):
        """Test extracting from empty patch"""
        paths = extract_paths_from_patch("")
        assert len(paths) == 0


class TestNormalizePath:
    """Test path normalization"""

    def test_forward_slashes(self):
        """Test backslash to forward slash conversion"""
        assert normalize_path("src\\module.py") == "src/module.py"

    def test_remove_leading_dot_slash(self):
        """Test removal of leading ./"""
        assert normalize_path("./src/module.py") == "src/module.py"

    def test_already_normalized(self):
        """Test already normalized path"""
        assert normalize_path("src/module.py") == "src/module.py"

    def test_with_workspace(self):
        """Test normalization with workspace"""
        # Use a Windows-compatible absolute path for testing
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            # Create an absolute path within the workspace
            absolute = os.path.join(tmpdir, "src", "module.py")
            result = normalize_path(absolute, workspace)
            # Result should be relative to workspace
            assert not Path(result).is_absolute()
            assert result.replace("\\", "/") == "src/module.py"


class TestExtractDeliverablesFromScope:
    """Test deliverables extraction from scope"""

    def test_extract_from_deliverables_dict(self):
        """Test extraction from structured deliverables"""
        scope = {
            "deliverables": {
                "code": ["src/main.py", "src/utils.py"],
                "tests": ["tests/test_main.py"],
                "docs": ["docs/README.md"],
            }
        }
        deliverables = extract_deliverables_from_scope(scope)
        assert "src/main.py" in deliverables
        assert "src/utils.py" in deliverables
        assert "tests/test_main.py" in deliverables
        assert "docs/README.md" in deliverables
        assert len(deliverables) == 4

    def test_extract_from_paths_list(self):
        """Test extraction from legacy paths format"""
        scope = {"paths": ["src/main.py", "tests/test_main.py"]}
        deliverables = extract_deliverables_from_scope(scope)
        assert "src/main.py" in deliverables
        assert "tests/test_main.py" in deliverables
        assert len(deliverables) == 2

    def test_extract_from_string_value(self):
        """Test extraction when deliverable is a string, not list"""
        scope = {"deliverables": {"code": "src/main.py"}}
        deliverables = extract_deliverables_from_scope(scope)
        assert "src/main.py" in deliverables
        assert len(deliverables) == 1

    def test_filters_non_path_prose_deliverables(self):
        """Non-path prose bullets should be dropped (e.g., 'Logging configuration')."""
        scope = {
            "deliverables": {
                "docs": [
                    "docs/research/USER_GUIDE.md",
                    "Logging configuration",
                    "CLI output formatting improvements",
                ]
            }
        }
        deliverables = extract_deliverables_from_scope(scope)
        assert "docs/research/USER_GUIDE.md" in deliverables
        assert "Logging configuration" not in deliverables
        assert "CLI output formatting improvements" not in deliverables

    def test_empty_scope(self):
        """Test extraction from empty scope"""
        deliverables = extract_deliverables_from_scope({})
        assert len(deliverables) == 0

    def test_none_scope(self):
        """Test extraction from None scope"""
        deliverables = extract_deliverables_from_scope(None)
        assert len(deliverables) == 0


class TestValidateDeliverables:
    """Test deliverables validation"""

    def test_valid_deliverables(self):
        """Test validation with all deliverables present"""
        patch = """
diff --git a/src/main.py b/src/main.py
new file mode 100644
--- /dev/null
+++ b/src/main.py
@@ -0,0 +1,5 @@
+def main():
+    pass

diff --git a/tests/test_main.py b/tests/test_main.py
new file mode 100644
--- /dev/null
+++ b/tests/test_main.py
@@ -0,0 +1,5 @@
+def test_main():
+    pass
"""
        scope = {"deliverables": {"code": ["src/main.py"], "tests": ["tests/test_main.py"]}}

        is_valid, errors, details = validate_deliverables(patch, scope, "test-phase")

        assert is_valid is True
        assert len(errors) == 0
        assert len(details["missing_paths"]) == 0

    def test_missing_deliverables(self):
        """Test validation with missing deliverables"""
        patch = """
diff --git a/src/main.py b/src/main.py
new file mode 100644
--- /dev/null
+++ b/src/main.py
@@ -0,0 +1,5 @@
+def main():
+    pass
"""
        scope = {
            "deliverables": {
                "code": ["src/main.py"],
                "tests": ["tests/test_main.py"],  # Missing in patch
            }
        }

        is_valid, errors, details = validate_deliverables(patch, scope, "test-phase")

        assert is_valid is False
        assert len(errors) > 0
        assert "tests/test_main.py" in details["missing_paths"]

    def test_structured_edit_touched_paths_satisfy_directory_deliverables(self, tmp_path: Path):
        """Structured edit plans may have patch_content=='' but still touch files via operations."""
        patch = ""  # structured edit mode returns no unified diff
        scope = {
            "deliverables": {
                "code": ["src/autopack/", "src/autopack/models/"],
            }
        }

        is_valid, errors, details = validate_deliverables(
            patch_content=patch,
            phase_scope=scope,
            phase_id="test-phase",
            workspace=tmp_path,
            touched_paths=["src/autopack/models/__init__.py"],
        )

        assert is_valid is True
        assert errors == []
        assert details["missing_paths"] == []

    def test_misplaced_file(self):
        """Test detection of misplaced files"""
        patch = """
diff --git a/main.py b/main.py
new file mode 100644
--- /dev/null
+++ b/main.py
@@ -0,0 +1,5 @@
+def main():
+    pass
"""
        scope = {"deliverables": {"code": ["src/main.py"]}}  # Should be in src/, not root

        is_valid, errors, details = validate_deliverables(patch, scope, "test-phase")

        assert is_valid is False
        assert "src/main.py" in details["missing_paths"]
        assert "main.py" in details["actual_paths"]
        # Should detect misplacement
        assert "src/main.py" in details["misplaced_paths"]
        assert details["misplaced_paths"]["src/main.py"] == "main.py"

    def test_no_deliverables_specified(self):
        """Test validation with no deliverables specified"""
        patch = """
diff --git a/src/main.py b/src/main.py
new file mode 100644
--- /dev/null
+++ b/src/main.py
"""
        scope = {}  # No deliverables

        is_valid, errors, details = validate_deliverables(patch, scope, "test-phase")

        assert is_valid is True  # Should pass if no deliverables specified
        assert len(errors) == 0

    def test_extra_files_not_error(self):
        """Test that extra files (not in deliverables) are noted but not errors"""
        patch = """
diff --git a/src/main.py b/src/main.py
new file mode 100644
--- /dev/null
+++ b/src/main.py

diff --git a/src/utils.py b/src/utils.py
new file mode 100644
--- /dev/null
+++ b/src/utils.py
"""
        scope = {"deliverables": {"code": ["src/main.py"]}}  # utils.py not required

        is_valid, errors, details = validate_deliverables(patch, scope, "test-phase")

        assert is_valid is True  # Extra files are OK
        assert "src/utils.py" in details["extra_paths"]

    def test_workspace_existing_deliverable_counts_as_present(self, tmp_path):
        """Deliverables already present on disk should satisfy validation (NDJSON multi-attempt convergence)."""
        # Only create src/main.py in the patch...
        patch = """
diff --git a/src/main.py b/src/main.py
new file mode 100644
--- /dev/null
+++ b/src/main.py
@@ -0,0 +1,3 @@
+def main():
+    return 1
"""
        # ...but tests/test_main.py already exists in the workspace from a prior attempt.
        test_file = tmp_path / "tests" / "test_main.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("def test_main():\n    assert True\n", encoding="utf-8")

        scope = {
            "deliverables": {
                "code": ["src/main.py"],
                "tests": ["tests/test_main.py"],
            }
        }

        is_valid, errors, details = validate_deliverables(
            patch, scope, "test-phase", workspace=tmp_path
        )
        assert (
            is_valid is True
        ), f"Expected validation to pass using workspace state; errors={errors}"
        assert details["missing_paths"] == []

    def test_examples_directory_allowed(self):
        """Test that examples/ deliverables are properly allowed (BUILD-094 regression test)"""
        patch = """
diff --git a/examples/market_research_example.md b/examples/market_research_example.md
new file mode 100644
--- /dev/null
+++ b/examples/market_research_example.md
@@ -0,0 +1,10 @@
+# Market Research Example
+Example content here
"""
        scope = {"deliverables": {"docs": ["examples/market_research_example.md"]}}

        is_valid, errors, details = validate_deliverables(patch, scope, "test-phase")

        assert is_valid is True, f"Validation failed: {errors}"
        assert len(errors) == 0
        assert "examples/market_research_example.md" in details["actual_paths"]
        assert len(details["missing_paths"]) == 0
        # Verify examples/ is in allowed roots
        assert "examples/" in details["allowed_roots"]
        # Verify file is NOT marked as outside allowed roots
        assert "examples/market_research_example.md" not in details["paths_outside_allowed_roots"]

    def test_examples_subdirectory_file_allowed(self):
        """Test that examples/subdir/file.md is also properly allowed"""
        patch = """
diff --git a/examples/tutorials/getting_started.md b/examples/tutorials/getting_started.md
new file mode 100644
--- /dev/null
+++ b/examples/tutorials/getting_started.md
@@ -0,0 +1,5 @@
+# Getting Started
"""
        scope = {"deliverables": {"docs": ["examples/tutorials/getting_started.md"]}}

        is_valid, errors, details = validate_deliverables(patch, scope, "test-phase")

        assert is_valid is True
        assert len(errors) == 0
        assert "examples/" in details["allowed_roots"]
        assert "examples/tutorials/getting_started.md" not in details["paths_outside_allowed_roots"]


class TestFormatValidationFeedback:
    """Test feedback formatting for Builder"""

    def test_format_feedback(self):
        """Test feedback formatting"""
        errors = ["Missing 2 required deliverables:", "  - src/main.py", "  - tests/test_main.py"]
        details = {
            "expected_paths": ["src/main.py", "tests/test_main.py"],
            "actual_paths": ["main.py"],
            "missing_paths": ["src/main.py", "tests/test_main.py"],
            "misplaced_paths": {"src/main.py": "main.py"},
        }

        feedback = format_validation_feedback_for_builder(errors, details, "Test phase")

        assert "DELIVERABLES VALIDATION FAILED" in feedback
        assert "REQUIRED DELIVERABLES" in feedback
        assert "src/main.py" in feedback
        assert "WRONG FILE LOCATIONS" in feedback
        assert "ACTION REQUIRED" in feedback

    def test_feedback_with_many_files(self):
        """Test feedback formatting with many files (should truncate)"""
        errors = []
        details = {
            "expected_paths": [f"src/file{i}.py" for i in range(20)],
            "actual_paths": [],
            "missing_paths": [f"src/file{i}.py" for i in range(20)],
            "misplaced_paths": {},
        }

        feedback = format_validation_feedback_for_builder(errors, details, "Test phase")

        # Should truncate long lists
        assert "..." in feedback or feedback.count("\n") < 50
