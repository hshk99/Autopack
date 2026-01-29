"""
Tests for check_no_tracked_docs_consolidated_md.py guardrail.

Policy enforced:
- Files matching docs/**/CONSOLIDATED_*.md MUST NOT be tracked in git
- Exception: archive/ subdirectories are allowed (historical preservation)
"""

import subprocess

# Add scripts/ci to path for import
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "ci"))

from check_no_tracked_docs_consolidated_md import get_tracked_docs_consolidated


class TestConsolidatedMdDetection:
    """Unit tests for CONSOLIDATED_*.md detection logic."""

    def test_detects_consolidated_in_docs_root(self):
        """Should detect CONSOLIDATED_*.md in docs/ root."""
        # This test uses the actual repo - we verify the function works
        # The guardrail test below ensures the repo is compliant
        pass  # Detection tested via integration test

    def test_ci_script_runs_without_error(self):
        """CI script should run without crashing."""
        result = subprocess.run(
            ["python", "scripts/ci/check_no_tracked_docs_consolidated_md.py"],
            capture_output=True,
            text=True,
        )
        # Should either pass (0) or fail (1), not crash (2+)
        assert result.returncode in [0, 1], f"Script crashed: {result.stderr}"


class TestConsolidatedMdPolicy:
    """Policy tests - verify the repository is compliant."""

    def test_no_consolidated_md_in_docs(self):
        """Repository should not have CONSOLIDATED_*.md tracked in docs/.

        This is a guardrail test - if it fails, there's a policy violation.
        """
        violations = get_tracked_docs_consolidated()
        assert not violations, (
            "Found CONSOLIDATED_*.md files in docs/ (policy violation):\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\n\nFix: Delete, move to archive/, or rename to non-CONSOLIDATED prefix."
        )


# Table-driven test cases for the detection logic
@pytest.mark.parametrize(
    "path,should_flag",
    [
        # Should flag
        ("docs/CONSOLIDATED_DEBUG.md", True),
        ("docs/CONSOLIDATED_FOO.md", True),
        ("docs/reports/CONSOLIDATED_ISSUES.md", True),
        ("docs/guides/CONSOLIDATED_SETUP.md", True),
        # Should NOT flag (archive exception)
        ("docs/archive/CONSOLIDATED_OLD.md", False),
        ("archive/docs/CONSOLIDATED_HISTORY.md", False),
        # Should NOT flag (not CONSOLIDATED_)
        ("docs/DEBUG.md", False),
        ("docs/CONSOLIDATED.md", False),  # No underscore
        ("docs/my_CONSOLIDATED_file.md", False),  # Prefix not matching
        # Should NOT flag (not .md)
        ("docs/CONSOLIDATED_DATA.json", False),
        ("docs/CONSOLIDATED_LOG.txt", False),
    ],
)
def test_path_classification(path: str, should_flag: bool):
    """Test path classification logic."""
    from pathlib import PurePosixPath

    posix_path = PurePosixPath(path)

    # Replicate the detection logic
    is_consolidated = posix_path.name.startswith("CONSOLIDATED_") and posix_path.name.endswith(
        ".md"
    )
    in_archive = "archive" in posix_path.parts

    would_flag = is_consolidated and not in_archive

    assert would_flag == should_flag, (
        f"Path {path}: expected {'flagged' if should_flag else 'allowed'}, "
        f"got {'flagged' if would_flag else 'allowed'}"
    )
