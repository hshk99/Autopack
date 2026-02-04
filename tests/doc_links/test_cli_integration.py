#!/usr/bin/env python3
"""
Integration tests for doc link checker CLI (BUILD-166).

Tests that CLI wiring matches intent:
- Nav mode (default) does NOT report backticks
- Deep mode DOES include backticks
"""

import os
import subprocess
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))


def _run_doc_link_checker(*args: str) -> subprocess.CompletedProcess:
    """
    Run scripts/check_doc_links.py in a Windows/encoding-safe way.

    Notes:
    - On Windows, subprocess with text=True defaults to locale encoding (often cp1252).
      The doc link checker prints Unicode symbols, which can cause decode issues.
    - Force UTF-8 decoding for captured output to keep tests platform-stable.
    """
    repo_root = Path(__file__).parents[2]
    env = dict(os.environ)
    # Force UTF-8 mode for the child Python process to stabilize encoding.
    env.setdefault("PYTHONUTF8", "1")

    return subprocess.run(
        [sys.executable, "scripts/check_doc_links.py", *args, "--repo-root", str(repo_root)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def test_nav_mode_ignores_backticks():
    """Test that nav mode (default) does NOT report backtick references."""
    # Modify README.md temporarily to test nav mode behavior
    readme_file = Path(__file__).parents[2] / "README.md"
    original_content = readme_file.read_text(encoding="utf-8")

    test_content = (
        original_content
        + """

<!-- TEST MARKER: TEMPORARY TEST CONTENT -->
This is a [test link to nonexistent file](docs/TEST_NONEXISTENT_FILE.md).

And here is a backtick reference: `.autonomous_runs/test_fake_file.json`.
"""
    )

    try:
        readme_file.write_text(test_content, encoding="utf-8")

        # Run nav mode (default) with verbose to see broken link details
        result = _run_doc_link_checker("--verbose")

        # Output should mention the markdown link but NOT the backtick reference
        assert "TEST_NONEXISTENT_FILE" in result.stdout, (
            f"Expected TEST_NONEXISTENT_FILE in output, got: {result.stdout}"
        )
        assert "test_fake_file" not in result.stdout, (
            "Nav mode should not report backtick references"
        )

        print("✅ test_nav_mode_ignores_backticks passed")
    finally:
        # Restore original README
        readme_file.write_text(original_content, encoding="utf-8")


def test_deep_mode_includes_backticks():
    """Test that deep mode DOES include backtick references."""
    # Create a temporary test file with both markdown links and backticks
    test_content = """# Test Document

This is a [real markdown link](docs/TEST_DEEP_NONEXISTENT_FILE.md).

And here is a backtick reference: `.autonomous_runs/test_deep_fake_file.json`.
"""

    test_file = Path(__file__).parents[2] / "docs" / "test_deep_mode.md"
    try:
        test_file.write_text(test_content, encoding="utf-8")

        # Run deep mode with verbose - should detect both markdown link and backtick
        result = _run_doc_link_checker("--deep", "--verbose")

        # Output should mention both the markdown link AND the backtick reference
        # Note: paths may be normalized (leading . and / stripped)
        assert "TEST_DEEP_NONEXISTENT_FILE" in result.stdout, (
            "Expected TEST_DEEP_NONEXISTENT_FILE in output"
        )
        # Backtick may appear as normalized path (without leading .)
        assert "test_deep_fake_file" in result.stdout, (
            "Expected test_deep_fake_file (backtick) in output"
        )

        print("✅ test_deep_mode_includes_backticks passed")
    finally:
        # Cleanup
        if test_file.exists():
            test_file.unlink()


def test_deep_mode_defaults_to_backticks():
    """Test that deep mode defaults to include backticks without explicit flag."""
    # Create a temporary test file with backticks only
    test_content = """# Test Document

Backtick reference: `scripts/test_nonexistent_default_script.py`.
"""

    test_file = Path(__file__).parents[2] / "docs" / "test_deep_default.md"
    try:
        test_file.write_text(test_content, encoding="utf-8")

        # Run deep mode WITHOUT --include-backticks flag, with verbose
        result = _run_doc_link_checker("--deep", "--verbose")

        # Should still detect backtick reference (deep mode defaults to include backticks)
        assert "test_nonexistent_default_script" in result.stdout, (
            "Deep mode should include backticks by default"
        )

        print("✅ test_deep_mode_defaults_to_backticks passed")
    finally:
        # Cleanup
        if test_file.exists():
            test_file.unlink()


def test_output_labeling():
    """Test that output clearly labels informational vs enforced categories."""
    # Create a temporary test file with informational reference
    test_content = """# Test Document

Runtime endpoint: `/api/test_auth/test_endpoint`.
"""

    test_file = Path(__file__).parents[2] / "docs" / "test_labeling.md"
    try:
        test_file.write_text(test_content, encoding="utf-8")

        # Run deep mode (not verbose, to see summary)
        result = _run_doc_link_checker("--deep")

        # Output should label informational references clearly
        # (Should be marked as informational/report-only in the summary)
        assert "Informational" in result.stdout or "report-only" in result.stdout, (
            f"Expected 'Informational' or 'report-only' in output, got: {result.stdout[-500:]}"
        )

        print("✅ test_output_labeling passed")
    finally:
        # Cleanup
        if test_file.exists():
            test_file.unlink()


if __name__ == "__main__":
    test_nav_mode_ignores_backticks()
    test_deep_mode_includes_backticks()
    test_deep_mode_defaults_to_backticks()
    test_output_labeling()

    print("\n" + "=" * 70)
    print("ALL CLI INTEGRATION TESTS PASSED ✅")
    print("=" * 70)
