"""Contract-first tests for changed files extraction (BUILD-187 Phase 6).

These tests verify:
- Deterministic output for same inputs
- Explicit None for unknown (not empty list)
- Sorted output for reproducibility
- Evidence flags for extraction failures
"""

from __future__ import annotations

import pytest


def test_extract_changed_files_from_patch_empty():
    """Empty patch returns unknown status, not empty list."""
    from autopack.executor.changed_files import extract_changed_files_from_patch

    result = extract_changed_files_from_patch("")

    assert result.status == "unknown"
    assert result.files is None
    assert result.evidence_flag == "empty_patch"


def test_extract_changed_files_from_patch_valid():
    """Valid patch extracts files deterministically."""
    from autopack.executor.changed_files import extract_changed_files_from_patch

    patch = """diff --git a/src/foo.py b/src/foo.py
--- a/src/foo.py
+++ b/src/foo.py
@@ -1,3 +1,4 @@
 def foo():
     pass
+    # new line
diff --git a/src/bar.py b/src/bar.py
--- a/src/bar.py
+++ b/src/bar.py
@@ -1 +1,2 @@
 def bar():
+    pass
"""

    result = extract_changed_files_from_patch(patch)

    assert result.status == "available"
    assert result.files == ["src/bar.py", "src/foo.py"]  # Sorted
    assert result.evidence_flag is None


def test_extract_changed_files_from_patch_deterministic():
    """Same patch always produces same output."""
    from autopack.executor.changed_files import extract_changed_files_from_patch

    patch = """diff --git a/z.py b/z.py
+++ b/z.py
diff --git a/a.py b/a.py
+++ b/a.py
diff --git a/m.py b/m.py
+++ b/m.py
"""

    result1 = extract_changed_files_from_patch(patch)
    result2 = extract_changed_files_from_patch(patch)
    result3 = extract_changed_files_from_patch(patch)

    assert result1.files == result2.files == result3.files
    assert result1.files == ["a.py", "m.py", "z.py"]  # Always sorted


def test_changed_files_result_properties():
    """ChangedFilesResult properties work correctly."""
    from autopack.executor.changed_files import ChangedFilesResult

    # Unknown case
    unknown = ChangedFilesResult(files=None, status="unknown")
    assert not unknown.is_known
    assert unknown.file_count is None

    # Empty case
    empty = ChangedFilesResult(files=[], status="empty")
    assert empty.is_known
    assert empty.file_count == 0

    # Available case
    available = ChangedFilesResult(files=["a.py", "b.py"], status="available")
    assert available.is_known
    assert available.file_count == 2


def test_changed_files_result_to_dict():
    """ChangedFilesResult serializes correctly."""
    from autopack.executor.changed_files import ChangedFilesResult

    result = ChangedFilesResult(
        files=["a.py"],
        status="available",
        evidence_flag=None,
        error_message=None,
    )

    d = result.to_dict()

    assert d["files"] == ["a.py"]
    assert d["status"] == "available"
    assert d["evidence_flag"] is None


def test_format_changed_files_unknown():
    """Format displays unknown status correctly."""
    from autopack.executor.changed_files import (
        ChangedFilesResult,
        format_changed_files_for_display,
    )

    result = ChangedFilesResult(files=None, status="unknown", evidence_flag="git_unavailable")

    formatted = format_changed_files_for_display(result)

    assert "unknown" in formatted
    assert "git_unavailable" in formatted


def test_format_changed_files_available():
    """Format displays available files correctly."""
    from autopack.executor.changed_files import (
        ChangedFilesResult,
        format_changed_files_for_display,
    )

    result = ChangedFilesResult(files=["a.py", "b.py"], status="available")

    formatted = format_changed_files_for_display(result)

    assert "2" in formatted
    assert "a.py" in formatted


def test_unknown_not_empty_list():
    """Ensure unknown status never returns empty list (critical contract)."""
    from autopack.executor.changed_files import ChangedFilesResult

    # If status is unknown, files MUST be None, not []
    unknown = ChangedFilesResult(files=None, status="unknown")
    assert unknown.files is None

    # Empty list is only valid with "empty" status
    empty = ChangedFilesResult(files=[], status="empty")
    assert empty.files == []
    assert empty.status == "empty"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
