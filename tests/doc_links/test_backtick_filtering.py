#!/usr/bin/env python3
"""
Unit tests for backtick filtering in doc link checker (BUILD-166).

Tests that nav mode (default) ignores backtick-wrapped paths while
deep mode with --include-backticks processes them.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from check_doc_links import extract_file_references


def test_backtick_filtering_disabled_by_default():
    """Test that backticks are ignored when include_backticks=False (nav mode)."""
    content = """
# Test Document

This is a [real markdown link](docs/file.md).

And here is a backtick reference: `.autonomous_runs/tidy_pending_moves.json`.

Another backtick: `/api/auth/.well-known/jwks.json`.
"""

    refs = extract_file_references(content, Path("test.md"), skip_code_blocks=True, include_backticks=False)

    # Should only extract the markdown link
    assert len(refs) == 1
    assert "docs/file.md" in refs
    assert "autonomous_runs/tidy_pending_moves.json" not in refs  # normalized (leading . stripped)
    assert "api/auth/.well-known/jwks.json" not in refs  # normalized (leading / stripped)

    print("✅ test_backtick_filtering_disabled_by_default passed")


def test_backtick_filtering_enabled():
    """Test that backticks are extracted when include_backticks=True (deep mode)."""
    content = """
# Test Document

This is a [real markdown link](docs/file.md).

And here is a backtick reference: `.autonomous_runs/tidy_pending_moves.json`.

Another backtick: `/api/auth/.well-known/jwks.json`.
"""

    refs = extract_file_references(content, Path("test.md"), skip_code_blocks=True, include_backticks=True)

    # Should extract both markdown link and backtick paths
    assert len(refs) == 3
    assert "docs/file.md" in refs
    assert "autonomous_runs/tidy_pending_moves.json" in refs  # normalized (leading . stripped)
    assert "api/auth/.well-known/jwks.json" in refs  # normalized (leading / stripped)

    print("✅ test_backtick_filtering_enabled passed")


def test_markdown_links_always_extracted():
    """Test that markdown links are always extracted regardless of backtick setting."""
    content = """
# Test Document

[Link 1](docs/file1.md)
[Link 2](docs/file2.md)
"""

    refs_without_backticks = extract_file_references(content, Path("test.md"), include_backticks=False)
    refs_with_backticks = extract_file_references(content, Path("test.md"), include_backticks=True)

    # Both should extract the same markdown links
    assert len(refs_without_backticks) == 2
    assert len(refs_with_backticks) == 2
    assert "docs/file1.md" in refs_without_backticks
    assert "docs/file2.md" in refs_without_backticks
    assert "docs/file1.md" in refs_with_backticks
    assert "docs/file2.md" in refs_with_backticks

    print("✅ test_markdown_links_always_extracted passed")


def test_backtick_path_heuristics():
    """Test that backtick extraction uses path heuristics (requires / or multiple dots)."""
    content = """
# Test Document

Valid paths (should be extracted when include_backticks=True):
- `.autonomous_runs/tidy_pending_moves.json`
- `scripts/check_doc_links.py`
- `config.yaml.example`

Invalid paths (should be ignored even with include_backticks=True):
- `filename.md` (no slash, only one dot)
- `variable_name` (no slash, no dots)
- `class.method` (no slash, only one dot)
"""

    refs = extract_file_references(content, Path("test.md"), skip_code_blocks=True, include_backticks=True)

    # Should only extract paths with / or multiple dots
    assert "autonomous_runs/tidy_pending_moves.json" in refs  # normalized (leading . stripped)
    assert "scripts/check_doc_links.py" in refs
    assert "config.yaml.example" in refs

    # Should not extract simple identifiers
    assert "filename.md" not in refs
    assert "variable_name" not in refs
    assert "class.method" not in refs

    print("✅ test_backtick_path_heuristics passed")


def test_nav_mode_realistic_scenario():
    """Test realistic nav mode scenario with backticks in README."""
    content = """
# README

See [documentation](docs/INDEX.md) for details.

Runtime artifacts are stored in `.autonomous_runs/tidy_pending_moves.json`.

The API endpoint `/api/auth/.well-known/jwks.json` provides JWKS.
"""

    # Nav mode (include_backticks=False)
    refs = extract_file_references(content, Path("README.md"), skip_code_blocks=True, include_backticks=False)

    # Should only extract the markdown link
    assert len(refs) == 1
    assert "docs/INDEX.md" in refs

    # Backticks should be ignored
    assert "autonomous_runs/tidy_pending_moves.json" not in refs  # normalized (leading . stripped)
    assert "api/auth/.well-known/jwks.json" not in refs  # normalized (leading / stripped)

    print("✅ test_nav_mode_realistic_scenario passed")


if __name__ == "__main__":
    test_backtick_filtering_disabled_by_default()
    test_backtick_filtering_enabled()
    test_markdown_links_always_extracted()
    test_backtick_path_heuristics()
    test_nav_mode_realistic_scenario()

    print("\n" + "=" * 70)
    print("ALL BACKTICK FILTERING TESTS PASSED ✅")
    print("=" * 70)
