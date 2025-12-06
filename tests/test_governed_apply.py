"""
Regression tests for governed_apply patch application safeguards.
"""

from pathlib import Path

from src.autopack.governed_apply import GovernedApplyPath


def test_direct_write_fallback_skips_mixed_patches(tmp_path: Path):
    """
    When git apply fails on a patch that touches existing files, the
    direct-write fallback must NOT run. This prevents partially applied
    diffs (new files written, existing files unchanged).
    """
    workspace = tmp_path
    existing = workspace / "foo.txt"
    existing.write_text("hello\n", encoding="utf-8")

    patch_content = """diff --git a/foo.txt b/foo.txt
--- a/foo.txt
+++ b/foo.txt
@@ -1,1 +1,1 @@
-nothing
+goodbye
diff --git a/newfile.txt b/newfile.txt
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/newfile.txt
@@ -0,0 +1,2 @@
+line1
+line2
"""

    apply_path = GovernedApplyPath(workspace=workspace, run_type="project_build")
    success, error = apply_path.apply_patch(patch_content, full_file_mode=True)

    assert success is False
    assert error
    # Direct-write fallback should not have created the new file
    assert not (workspace / "newfile.txt").exists()
    # Existing file should remain unchanged
    assert existing.read_text(encoding="utf-8") == "hello\n"

