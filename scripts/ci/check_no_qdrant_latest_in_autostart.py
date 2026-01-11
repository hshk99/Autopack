#!/usr/bin/env python3
"""
CI guardrail: prevent qdrant/qdrant:latest in autostart code paths.

Policy:
- Autostart fallback paths (docker run) MUST use pinned Qdrant images
- The literal string "qdrant/qdrant:latest" MUST NOT appear in src/autopack/
- This ensures deterministic, supply-chain-safe runtime behavior

Rationale:
- :latest is a moving target that undermines determinism
- Autostart paths can execute during health checks or runtime
- All autostart images should match docker-compose.yml pinning (v1.12.5)

Exit codes:
- 0: No violations found
- 1: :latest usage detected (PR-blocking failure)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Files to scan for :latest usage in autostart paths
AUTOSTART_FILES = [
    Path("src/autopack/health_checks.py"),
    Path("src/autopack/memory/memory_service.py"),
]

# Pattern that indicates a supply-chain violation
FORBIDDEN_PATTERN = "qdrant/qdrant:latest"


def get_tracked_files() -> set[str]:
    """Get list of tracked files from git."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return set()
    return {f for f in result.stdout.split("\0") if f}


def main() -> int:
    violations: list[str] = []

    tracked = get_tracked_files()

    for file_path in AUTOSTART_FILES:
        # Only check tracked files
        if str(file_path).replace("\\", "/") not in tracked:
            continue

        if not file_path.exists():
            continue

        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        for i, line in enumerate(lines, start=1):
            if FORBIDDEN_PATTERN in line:
                # Skip comments
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                violations.append(f"{file_path}:{i}: {line.strip()}")

    if violations:
        print("=" * 70)
        print("Qdrant :latest in autostart paths violation(s) found:")
        print("=" * 70)
        for v in violations:
            print(f"  - {v}")
        print()
        print("Policy:")
        print("  - Autostart fallback paths MUST use pinned Qdrant images")
        print("  - The literal 'qdrant/qdrant:latest' MUST NOT appear in src/autopack/")
        print("  - Use AUTOPACK_QDRANT_IMAGE env or config/memory.yaml qdrant.image")
        print()
        print("Fix: replace :latest with pinned version (e.g., qdrant/qdrant:v1.12.5)")
        print("     or use the qdrant_image variable from config")
        print("=" * 70)
        return 1

    print("[OK] No qdrant/qdrant:latest found in autostart code paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
