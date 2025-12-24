from pathlib import Path

import pytest

from autopack.governed_apply import GovernedApplyPath


def test_governed_apply_rejects_new_file_conflict_without_deleting_protected(tmp_path: Path):
    """
    Regression test for repeated "mysterious deletions":
    Previously, GovernedApplyPath would delete an existing file if a patch incorrectly
    marked it as 'new file mode', *before* protected-path validation ran.

    That could delete core modules (e.g. src/autopack/config.py) even when the patch
    was later rejected.
    """
    workspace = tmp_path
    target_rel = Path("src/autopack/config.py")
    target_abs = workspace / target_rel
    target_abs.parent.mkdir(parents=True, exist_ok=True)
    target_abs.write_text("ORIGINAL = True\n", encoding="utf-8")

    ga = GovernedApplyPath(workspace=workspace, autopack_internal_mode=False, run_type="project_build")

    # A malformed patch that tries to "create" an existing protected file
    patch = "\n".join(
        [
            "diff --git a/src/autopack/config.py b/src/autopack/config.py",
            "new file mode 100644",
            "index 0000000..e69de29",
            "--- /dev/null",
            "+++ b/src/autopack/config.py",
            "@@ -0,0 +1 @@",
            "+BROKEN = False",
            "",
        ]
    )

    ok, err = ga.apply_patch(patch, full_file_mode=False)
    assert ok is False
    assert err is not None

    # File must still exist and remain unmodified
    assert target_abs.exists()
    assert target_abs.read_text(encoding="utf-8") == "ORIGINAL = True\n"


