from pathlib import Path


def test_governed_apply_skips_ndjson_synthetic_patch(tmp_path: Path):
    """
    NDJSON operations are applied directly to disk by the builder client.
    The executor passes a synthetic header-only "patch" through the pipeline for validation.
    GovernedApply must treat it as already-applied and not attempt git-apply.
    """
    from autopack.governed_apply import GovernedApplyPath

    patch = """# NDJSON Operations Applied (2 files)
diff --git a/src/foo.py b/src/foo.py
+++ b/src/foo.py
diff --git a/tests/test_foo.py b/tests/test_foo.py
+++ b/tests/test_foo.py
"""

    ga = GovernedApplyPath(
        workspace=tmp_path,
        run_type="project_build",
        autopack_internal_mode=False,
        scope_paths=["src/foo.py", "tests/test_foo.py"],
        allowed_paths=["src/", "tests/"],
    )

    ok, err = ga.apply_patch(patch, full_file_mode=True)
    assert ok is True
    assert err is None


