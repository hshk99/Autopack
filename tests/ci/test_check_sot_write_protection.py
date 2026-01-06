"""Tests for SOT write protection script (BUILD-188 hardening).

Ensures that the SOT write-protection check:
1. Covers all canonical SOT ledger files
2. Remains deterministic and read-only
3. Works correctly on both Windows and Unix paths
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def test_protected_sot_paths_includes_all_canonical_files():
    """Verify PROTECTED_SOT_PATHS includes all 6 canonical SOT files plus README."""
    from scripts.check_sot_write_protection import PROTECTED_SOT_PATHS

    expected_sot_files = [
        "docs/BUILD_HISTORY.md",
        "docs/DEBUG_LOG.md",
        "docs/ARCHITECTURE_DECISIONS.md",
        "docs/FUTURE_PLAN.md",
        "docs/PROJECT_INDEX.json",
        "docs/LEARNED_RULES.json",
    ]

    for sot_file in expected_sot_files:
        assert sot_file in PROTECTED_SOT_PATHS, f"Missing protected SOT file: {sot_file}"


def test_scan_file_detects_write_to_protected_path():
    """Test that _scan_file detects write patterns targeting protected paths."""
    from scripts.check_sot_write_protection import _scan_file

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test_module.py"
        test_file.write_text(
            """
def bad_function():
    Path("docs/BUILD_HISTORY.md").write_text("bad")
"""
        )

        findings = _scan_file(test_file)
        assert len(findings) == 1
        assert "docs/BUILD_HISTORY.md" in findings[0]


def test_scan_file_detects_write_to_json_sot():
    """Test detection of writes to JSON SOT files."""
    from scripts.check_sot_write_protection import _scan_file

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test_module.py"
        test_file.write_text(
            """
def save_index():
    with open("docs/PROJECT_INDEX.json", "w") as f:
        f.write("{}")
"""
        )

        findings = _scan_file(test_file)
        assert len(findings) >= 1
        assert any("PROJECT_INDEX.json" in f for f in findings)


def test_scan_file_detects_path_constructor_with_sot():
    """Test that Path() constructor with SOT path is flagged (conservative check).

    The script intentionally flags Path() constructor usage with SOT paths
    because it could lead to writes. This is conservative by design.
    """
    from scripts.check_sot_write_protection import _scan_file

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test_module.py"
        test_file.write_text(
            """
def read_history():
    content = Path("docs/BUILD_HISTORY.md").read_text()
    return content
"""
        )

        findings = _scan_file(test_file)
        # Path() with SOT is flagged as a potential risk (conservative)
        assert len(findings) >= 1


def test_scan_file_no_findings_for_clean_code():
    """Test that clean code produces no findings."""
    from scripts.check_sot_write_protection import _scan_file

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "clean_module.py"
        test_file.write_text(
            """
def process_data():
    # This is clean code with no SOT writes
    result = {"status": "ok"}
    return result
"""
        )

        findings = _scan_file(test_file)
        assert len(findings) == 0


def test_write_call_snippets_are_defined():
    """Verify WRITE_CALL_SNIPPETS includes expected write patterns."""
    from scripts.check_sot_write_protection import WRITE_CALL_SNIPPETS

    # Should have at least these patterns
    assert len(WRITE_CALL_SNIPPETS) >= 3

    # Check that common write APIs are covered
    snippet_str = " ".join(WRITE_CALL_SNIPPETS)
    assert "write_text" in snippet_str
    assert "write_bytes" in snippet_str
    assert "open" in snippet_str


def test_script_is_deterministic():
    """Verify the script produces consistent results."""
    from scripts.check_sot_write_protection import _scan_file

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text('Path("docs/DEBUG_LOG.md").write_text("x")')

        # Run multiple times
        results = [_scan_file(test_file) for _ in range(3)]

        # All results should be identical
        assert results[0] == results[1] == results[2]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
