#!/usr/bin/env python3
"""
CI guardrail: prevent CONSOLIDATED_*.md files in docs/.

Policy:
- Files matching docs/**/CONSOLIDATED_*.md MUST NOT be tracked in git
- These are derived rollups that create "second truth" documentation
- Exception: archive/ subdirectories are allowed (historical preservation)

Rationale:
- Consolidated/derived documents tend to become stale and diverge from source
- They create ambiguity about which document is authoritative
- Operators should use the primary source documents instead

Exit codes:
- 0: No violations found
- 1: Tracked CONSOLIDATED_*.md files found in docs/ (PR-blocking failure)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path, PurePosixPath


def get_tracked_docs_consolidated() -> list[str]:
    """Find tracked CONSOLIDATED_*.md files in docs/ (excluding archive/)."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "docs/"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []

    violations = []
    for path in result.stdout.split("\0"):
        if not path:
            continue

        # Use PurePosixPath for consistent path handling
        posix_path = PurePosixPath(path)

        # Check if it's a CONSOLIDATED_*.md file
        if not posix_path.name.startswith("CONSOLIDATED_"):
            continue
        if not posix_path.name.endswith(".md"):
            continue

        # Allow files in archive/ subdirectories
        if "archive" in posix_path.parts:
            continue

        violations.append(path)

    return violations


def main() -> int:
    violations = get_tracked_docs_consolidated()

    if violations:
        print("=" * 70)
        print("CONSOLIDATED_*.md files found in docs/ (policy violation):")
        print("=" * 70)
        for v in violations:
            print(f"  - {v}")
        print()
        print("Policy:")
        print("  - CONSOLIDATED_*.md files MUST NOT be tracked in docs/")
        print("  - These are derived rollups that create 'second truth' documentation")
        print("  - Exception: archive/ subdirectories are allowed")
        print()
        print("Fix options:")
        print("  1. Delete the file if no longer needed")
        print("  2. Move to archive/docs/ if historical preservation is needed")
        print("  3. Rename to a non-CONSOLIDATED prefix if it's a primary source")
        print("=" * 70)
        return 1

    print("[OK] No CONSOLIDATED_*.md files tracked in docs/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
