"""Tests for SOT hygiene check script (BUILD-187 Phase 11)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def test_find_build_docs_empty_dir():
    """Test finding BUILD docs in empty directory."""
    from scripts.ci.check_sot_hygiene import find_build_docs

    with tempfile.TemporaryDirectory() as tmpdir:
        docs_dir = Path(tmpdir) / "docs"
        docs_dir.mkdir()

        result = find_build_docs(docs_dir)
        assert result == []


def test_find_build_docs_with_files():
    """Test finding BUILD docs with files present."""
    from scripts.ci.check_sot_hygiene import find_build_docs

    with tempfile.TemporaryDirectory() as tmpdir:
        docs_dir = Path(tmpdir) / "docs"
        docs_dir.mkdir()

        # Create test BUILD docs
        (docs_dir / "BUILD-001.md").write_text("# BUILD-001")
        (docs_dir / "BUILD-002_TEST.md").write_text("# BUILD-002")
        (docs_dir / "OTHER.md").write_text("# Other")

        result = find_build_docs(docs_dir)

        assert len(result) == 2
        assert result[0].name == "BUILD-001.md"
        assert result[1].name == "BUILD-002_TEST.md"


def test_find_referenced_builds():
    """Test finding BUILD references in BUILD_HISTORY.md."""
    from scripts.ci.check_sot_hygiene import find_referenced_builds

    with tempfile.TemporaryDirectory() as tmpdir:
        history_path = Path(tmpdir) / "BUILD_HISTORY.md"
        history_path.write_text("""# Build History

## Recent Builds
- BUILD-001: Initial setup
- BUILD-002_TEST: Testing feature
- See BUILD-003 for details

## Older Builds
- BUILD-100
""")

        result = find_referenced_builds(history_path)

        assert "BUILD-001" in result
        assert "BUILD-002_TEST" in result
        assert "BUILD-003" in result
        assert "BUILD-100" in result


def test_check_unreferenced_build_docs():
    """Test checking for unreferenced BUILD docs."""
    from scripts.ci.check_sot_hygiene import check_unreferenced_build_docs

    with tempfile.TemporaryDirectory() as tmpdir:
        docs_dir = Path(tmpdir) / "docs"
        docs_dir.mkdir()

        # Create BUILD docs
        (docs_dir / "BUILD-001.md").write_text("# BUILD-001")
        (docs_dir / "BUILD-002.md").write_text("# BUILD-002")
        (docs_dir / "BUILD-003.md").write_text("# BUILD-003")

        # Create BUILD_HISTORY referencing only BUILD-001
        (docs_dir / "BUILD_HISTORY.md").write_text("## History\n- BUILD-001: Done")

        findings = check_unreferenced_build_docs(docs_dir)

        # BUILD-002 and BUILD-003 should be flagged as unreferenced
        assert len(findings) == 2
        unreferenced_names = {Path(f.file_path).name for f in findings}
        assert "BUILD-002.md" in unreferenced_names
        assert "BUILD-003.md" in unreferenced_names


def test_format_findings_empty():
    """Test formatting with no findings."""
    from scripts.ci.check_sot_hygiene import format_findings

    result = format_findings([])
    assert "No SOT hygiene issues found" in result


def test_format_findings_with_items():
    """Test formatting with findings."""
    from scripts.ci.check_sot_hygiene import Finding, format_findings

    findings = [
        Finding(
            category="test_category",
            severity="warning",
            message="Test message",
            file_path="/path/to/file.md",
        ),
    ]

    result = format_findings(findings)

    assert "1 SOT hygiene finding" in result
    assert "test_category" in result
    assert "WARN" in result
    assert "Test message" in result


def test_script_is_check_only():
    """Verify the script doesn't write any files."""
    # This test ensures the script respects the check-only constraint
    import inspect
    from scripts.ci import check_sot_hygiene

    source = inspect.getsource(check_sot_hygiene)

    # Should not contain file write operations in main code paths
    # (excluding the module docstring and test fixtures)
    main_source = source.split('if __name__ == "__main__"')[0]

    # Count actual write calls (excluding comments and strings)
    write_calls = main_source.count(".write_text(")
    write_calls += main_source.count(".write_bytes(")
    write_calls += main_source.count("open(") - main_source.count("# open(")

    # The script should have no write operations in the check functions
    # (Note: format_findings returns a string, doesn't write)
    assert write_calls == 0, "Script should not write files - check-only mode required"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
