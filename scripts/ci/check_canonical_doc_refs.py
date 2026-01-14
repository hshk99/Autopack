#!/usr/bin/env python3
"""CI guard to block legacy path references in canonical operator docs (P2.5).

Implements BUILD-180 P2.5: Legacy-doc containment.

Canonical operator docs must not contain references to legacy/non-existent paths
like `src/backend/` which don't exist in the current codebase structure.

This mechanical enforcement prevents documentation drift and ensures operator
docs accurately reflect the actual codebase structure.

Exit codes:
    0: No violations found
    1: Legacy path violations found in canonical docs
    2: Script error (e.g., invalid arguments)

Usage:
    python scripts/ci/check_canonical_doc_refs.py [--repo-root PATH]
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class LegacyPathViolation:
    """A legacy path reference found in a canonical doc."""

    file_path: str
    line_number: int
    pattern: str
    line_content: str


@dataclass
class CheckResult:
    """Result of checking canonical docs."""

    exit_code: int
    violations: List[LegacyPathViolation]
    remediation_message: Optional[str] = None


# Canonical operator docs per GOVERNANCE.md Section 10
# These are the authoritative docs that operators rely on
CANONICAL_OPERATOR_DOCS = [
    "docs/QUICKSTART.md",
    "docs/DEPLOYMENT.md",
    "docs/CONTRIBUTING.md",
    "docs/TROUBLESHOOTING.md",
    "docs/ARCHITECTURE.md",
    "docs/GOVERNANCE.md",
    "docs/API_BASICS.md",
    "docs/CANONICAL_API_CONTRACT.md",
    "docs/AUTHENTICATION.md",
    "docs/AUTOPILOT_OPERATIONS.md",
    "docs/PARALLEL_RUNS.md",
    "security/README.md",
]

# Legacy paths that should NOT appear in canonical docs
# These paths don't exist in the current codebase structure
LEGACY_PATH_PATTERNS = [
    (r"src/backend/", "src/backend/ (legacy path - use src/autopack/)"),
    (r"backend/", "backend/ (legacy path - use src/autopack/)"),
    # Note: src/frontend/ is CANONICAL in this repo (root Vite app), not legacy
    # Workstation-specific absolute paths (do not allow in canonical docs)
    (r"[A-Za-z]:\\\\dev\\\\Autopack", "C:\\dev\\Autopack (workstation path - use $REPO_ROOT/)"),
    (r"(?i)c:/dev/Autopack", "c:/dev/Autopack (workstation path - use $REPO_ROOT/)"),
]


def check_content_for_legacy_paths(content: str, file_path: str) -> List[LegacyPathViolation]:
    """Check file content for legacy path references.

    Properly handles fenced code blocks (``` delimited sections).

    Policy:
    - Lines outside code blocks are always scanned for legacy paths
    - Lines inside code blocks are scanned UNLESS preceded by a
      "HISTORICAL:" marker comment within the 3 lines before the fence

    Args:
        content: File content
        file_path: Path for reporting

    Returns:
        List of violations found
    """
    violations = []
    lines = content.split("\n")

    in_fence = False
    fence_is_historical = False
    fence_start_line = 0

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()

        # Track fenced code block state
        if stripped.startswith("```"):
            if not in_fence:
                # Opening fence - check if there's a HISTORICAL marker nearby
                in_fence = True
                fence_start_line = line_num
                fence_is_historical = _has_historical_marker_before(lines, line_num - 1)
            else:
                # Closing fence
                in_fence = False
                fence_is_historical = False
            continue

        # Skip content inside historical fenced blocks
        if in_fence and fence_is_historical:
            continue

        # Skip lines that are comments with HISTORICAL marker
        if stripped.startswith("#") and "HISTORICAL" in stripped.upper():
            continue

        # Check for legacy path patterns
        for pattern, description in LEGACY_PATH_PATTERNS:
            if re.search(pattern, line):
                # Skip if this is clearly marked as legacy/historical
                if any(
                    marker in line.upper()
                    for marker in ["LEGACY", "DEPRECATED", "HISTORICAL", "OLD:", "WAS:"]
                ):
                    continue

                violations.append(
                    LegacyPathViolation(
                        file_path=file_path,
                        line_number=line_num,
                        pattern=description,
                        line_content=stripped[:100],
                    )
                )
                break  # Only report first match per line

    return violations


def _has_historical_marker_before(lines: List[str], fence_line_index: int) -> bool:
    """Check if there's a HISTORICAL marker in the 3 lines before a fence.

    This allows documentation to include historical examples in code blocks
    when they are explicitly marked as such.

    Args:
        lines: List of all lines (0-indexed)
        fence_line_index: Index of the fence opening line (0-indexed)

    Returns:
        True if a HISTORICAL marker was found in the preceding context
    """
    # Look at up to 3 lines before the fence
    start = max(0, fence_line_index - 3)
    for i in range(start, fence_line_index):
        line = lines[i].upper()
        if "HISTORICAL:" in line or "HISTORICAL EXAMPLE" in line:
            return True
    return False


def check_file_for_legacy_paths(file_path: Path) -> List[LegacyPathViolation]:
    """Check a file for legacy path references.

    Args:
        file_path: Path to file

    Returns:
        List of violations found
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        return check_content_for_legacy_paths(content, str(file_path))
    except FileNotFoundError:
        # Canonical doc doesn't exist yet - not a violation
        return []
    except Exception as e:
        print(f"WARNING: Could not read {file_path}: {e}", file=sys.stderr)
        return []


def check_canonical_docs(repo_root: Path) -> CheckResult:
    """Check all canonical docs for legacy path references.

    Args:
        repo_root: Repository root directory

    Returns:
        CheckResult with violations and exit code
    """
    all_violations = []

    # Check each canonical doc
    for doc_path in CANONICAL_OPERATOR_DOCS:
        full_path = repo_root / doc_path
        violations = check_file_for_legacy_paths(full_path)
        all_violations.extend(violations)

    if all_violations:
        remediation = """
REMEDIATION REQUIRED:

Canonical operator docs must not contain references to legacy paths
that don't exist in the current codebase structure, or workstation-specific
absolute paths.

Legacy path mappings:
- src/backend/ -> src/autopack/
- backend/ -> src/autopack/

Workstation path policy:
- Use $REPO_ROOT/ or relative paths instead of C:\\dev\\Autopack or c:/dev/Autopack

To fix:
1. Update path references to use current codebase structure
2. If documenting historical context, prefix with "LEGACY:" or "HISTORICAL:"
3. For migration guides, clearly mark which paths are old vs new
4. Replace workstation paths with $REPO_ROOT/ notation

See docs/GOVERNANCE.md Section 10 for canonical doc policy.
"""
        return CheckResult(
            exit_code=1,
            violations=all_violations,
            remediation_message=remediation,
        )

    return CheckResult(
        exit_code=0,
        violations=[],
        remediation_message=None,
    )


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Check canonical docs for legacy path references")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).parent.parent.parent,
        help="Repository root directory",
    )
    args = parser.parse_args()

    print(f"Checking canonical docs in: {args.repo_root}")
    print(f"Canonical docs to check: {len(CANONICAL_OPERATOR_DOCS)}")

    result = check_canonical_docs(args.repo_root)

    if result.violations:
        print(f"\nFOUND {len(result.violations)} LEGACY PATH VIOLATION(S):\n")
        for v in result.violations:
            print(f"  {v.file_path}:{v.line_number}")
            print(f"    Pattern: {v.pattern}")
            print(f"    Content: {v.line_content}")
            print()

        if result.remediation_message:
            print(result.remediation_message)

        return 1

    print("\nSUCCESS: No legacy path references found in canonical docs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
