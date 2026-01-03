#!/usr/bin/env python3
"""
CI guardrail: enforce GitHub Actions supply-chain pinning policy.

Policy:
- Third-party actions (non-actions/*) MUST use full 40-char SHA pins
- First-party actions (actions/*) MAY use version tags (@v4)
- Mutable refs (@master, @main, @vX for third-party) are BLOCKED

Rationale:
- SHA pins prevent supply-chain attacks via tag hijacking
- First-party actions are lower risk (GitHub's own repos)
- Dependabot maintains SHAs automatically (weekly updates)

Exit codes:
- 0: All workflows comply with pinning policy
- 1: Violations found (PR-blocking failure)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

WORKFLOWS_DIR = Path(".github/workflows")

# Regex patterns
USES_RE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
FULL_SHA_RE = re.compile(r"@[0-9a-f]{40}$", re.IGNORECASE)
MUTABLE_RE = re.compile(r"@(master|main|v\d+)$", re.IGNORECASE)

# Policy: first-party actions allowed to use version tags
# All third-party actions must use SHA pins
ALLOWED_TAG_PREFIXES = (
    "actions/",  # e.g. actions/checkout@v4, actions/setup-python@v5
)


def is_allowed_tag_ref(uses: str) -> bool:
    """Check if action is allowed to use version tags (first-party only)."""
    return uses.startswith(ALLOWED_TAG_PREFIXES)


def main() -> int:
    if not WORKFLOWS_DIR.exists():
        print(f"[SKIP] {WORKFLOWS_DIR} not found")
        return 0

    violations: list[str] = []

    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines, start=1):
            m = USES_RE.match(line)
            if not m:
                continue

            uses = m.group(1)

            # Check for mutable refs (master/main/vX)
            if MUTABLE_RE.search(uses):
                if is_allowed_tag_ref(uses):
                    # First-party action with version tag - allowed
                    continue
                # Third-party action with mutable ref - VIOLATION
                violations.append(
                    f"{path.name}:{i}: mutable ref not allowed for third-party action: {uses}"
                )
                continue

            # For non-mutable refs: enforce SHA pinning for third-party
            if not is_allowed_tag_ref(uses):
                if not FULL_SHA_RE.search(uses):
                    violations.append(
                        f"{path.name}:{i}: third-party action must use full SHA pin: {uses}"
                    )

    if violations:
        print("=" * 70)
        print("GitHub Actions pinning policy violations found:")
        print("=" * 70)
        for v in violations:
            print(f"  - {v}")
        print()
        print("Policy:")
        print("  - Third-party actions MUST use full 40-char SHA pins")
        print("  - First-party (actions/*) MAY use version tags (@v4)")
        print("  - Mutable refs (@master, @main) are BLOCKED")
        print()
        print("Fix: pin third-party actions to commit SHAs with version comments")
        print("Example: uses: owner/repo@abc123...  # v1.2.3")
        print("=" * 70)
        return 1

    print("[OK] GitHub Actions pinning policy satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
