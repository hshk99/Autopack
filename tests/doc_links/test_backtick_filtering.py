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

    refs = extract_file_references(
        content, Path("test.md"), skip_code_blocks=True, include_backticks=False
    )

    # Should only extract the markdown link
    assert len(refs) == 1
    assert "docs/file.md" in refs
    assert ".autonomous_runs/tidy_pending_moves.json" not in refs
    assert "api/auth/.well-known/jwks.json" not in refs  # leading / stripped

    print("✅ test_backtick_filtering_disabled_by_default passed")


def test_backtick_filtering_enabled():
    """Test that backticks are extracted when include_backticks=True (deep mode)."""
    content = """
# Test Document

This is a [real markdown link](docs/file.md).

And here is a backtick reference: `.autonomous_runs/tidy_pending_moves.json`.

Another backtick: `/api/auth/.well-known/jwks.json`.
"""

    refs = extract_file_references(
        content, Path("test.md"), skip_code_blocks=True, include_backticks=True
    )

    # Should extract both markdown link and backtick paths
    assert len(refs) == 3
    assert "docs/file.md" in refs
    assert ".autonomous_runs/tidy_pending_moves.json" in refs
    assert "api/auth/.well-known/jwks.json" in refs  # normalized (leading / stripped)

    print("✅ test_backtick_filtering_enabled passed")


def test_markdown_links_always_extracted():
    """Test that markdown links are always extracted regardless of backtick setting."""
    content = """
# Test Document

[Link 1](docs/file1.md)
[Link 2](docs/file2.md)
"""

    refs_without_backticks = extract_file_references(
        content, Path("test.md"), include_backticks=False
    )
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
    """Test that backtick extraction uses improved path heuristics (BUILD-166)."""
    content = """
# Test Document

Valid paths (should be extracted when include_backticks=True):
- `.autonomous_runs/tidy_pending_moves.json` (has /)
- `scripts/check_doc_links.py` (has / and .py extension)
- `config.yaml.example` (multiple dots)
- `README.md` (known extension)
- `Makefile` (known filename)
- `pyproject.toml` (known extension)

Invalid paths (should be ignored even with include_backticks=True):
- `variable_name` (no path indicators)
- `class.method` (single dot, not a file extension)
- `foo` (no path indicators)
"""

    refs = extract_file_references(
        content, Path("test.md"), skip_code_blocks=True, include_backticks=True
    )

    # Should extract paths with / or known extensions or known filenames
    assert ".autonomous_runs/tidy_pending_moves.json" in refs
    assert "scripts/check_doc_links.py" in refs
    assert "config.yaml.example" in refs
    assert "README.md" in refs  # BUILD-166: improved heuristics
    assert (
        "Makefile" in refs
    ), f"Expected Makefile in refs, got: {sorted(refs.keys())}"  # BUILD-166: improved heuristics
    assert "pyproject.toml" in refs  # BUILD-166: improved heuristics

    # Should not extract simple identifiers
    assert "variable_name" not in refs
    assert "class.method" not in refs
    assert "foo" not in refs

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
    refs = extract_file_references(
        content, Path("README.md"), skip_code_blocks=True, include_backticks=False
    )

    # Should only extract the markdown link
    assert len(refs) == 1
    assert "docs/INDEX.md" in refs

    # Backticks should be ignored
    assert ".autonomous_runs/tidy_pending_moves.json" not in refs
    assert "api/auth/.well-known/jwks.json" not in refs  # normalized (leading / stripped)

    print("✅ test_nav_mode_realistic_scenario passed")


def test_fenced_code_blocks_bypass_deep_scan():
    """Test that fenced code blocks don't trigger missing_file in deep mode (BUILD-169 regression guard)."""
    content = """
# Vector Memory Module

The memory system ([src/autopack/memory/](src/autopack/memory/)) includes:

```
embeddings.py       - OpenAI + local fallback embeddings
qdrant_store.py     - Qdrant backend (default)
faiss_store.py      - FAISS backend (dev/offline)
memory_service.py   - Collections management
```

See [src/autopack/memory/README.md](src/autopack/memory/README.md) for details.
"""

    # Deep mode with backticks enabled
    refs = extract_file_references(
        content, Path("test.md"), skip_code_blocks=True, include_backticks=True
    )

    # Should extract markdown links but NOT fenced block contents
    assert len(refs) == 2
    assert "src/autopack/memory/" in refs
    assert "src/autopack/memory/README.md" in refs

    # Fenced block contents should be skipped
    assert "embeddings.py" not in refs
    assert "qdrant_store.py" not in refs
    assert "faiss_store.py" not in refs
    assert "memory_service.py" not in refs

    print("✅ test_fenced_code_blocks_bypass_deep_scan passed")


if __name__ == "__main__":
    test_backtick_filtering_disabled_by_default()
    test_backtick_filtering_enabled()
    test_markdown_links_always_extracted()
    test_backtick_path_heuristics()
    test_nav_mode_realistic_scenario()
    test_fenced_code_blocks_bypass_deep_scan()

    print("\n" + "=" * 70)
    print("ALL BACKTICK FILTERING TESTS PASSED ✅")
    print("=" * 70)
