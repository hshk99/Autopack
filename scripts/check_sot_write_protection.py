"""
Static, read-only check to ensure executor code does not directly write to SOT ledgers.

This is intentionally conservative and lightweight: it scans for obvious direct write
patterns targeting canonical SOT files. It is not a sandbox, but it *does* catch
accidental regressions like adding a `write_text()` to `docs/BUILD_HISTORY.md`.

CI contract:
- exits 0 if no forbidden write patterns are found
- exits 1 with an actionable message if potential writes are detected
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


PROTECTED_SOT_PATHS = [
    "README.md",
    "docs/BUILD_HISTORY.md",
    "docs/DEBUG_LOG.md",
    "docs/ARCHITECTURE_DECISIONS.md",
]

# A small set of common write APIs we want to catch in executor code.
# We only match when the protected path is in the same line to avoid overly broad false positives.
WRITE_CALL_SNIPPETS = [
    r"\bopen\(",
    r"\.write_text\(",
    r"\.write_bytes\(",
    r"\bPath\(",
]


def _scan_file(path: Path) -> list[str]:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Executor code should always be UTF-8; fail loudly if not.
        return [f"{path}: Unable to read as UTF-8 (unexpected for source file)"]

    findings: list[str] = []
    for i, line in enumerate(content.splitlines(), start=1):
        for protected in PROTECTED_SOT_PATHS:
            if protected not in line:
                continue
            if any(re.search(snippet, line) for snippet in WRITE_CALL_SNIPPETS):
                findings.append(f"{path}:{i}: potential direct write reference to {protected}: {line.strip()}")
    return findings


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    executor_path = repo_root / "src" / "autopack" / "autonomous_executor.py"

    if not executor_path.exists():
        print(f"ERROR: expected executor at {executor_path} but file does not exist", file=sys.stderr)
        return 2

    findings = _scan_file(executor_path)
    if not findings:
        print("✅ SOT write protection check passed (no direct executor writes detected)")
        return 0

    print("❌ SOT write protection check failed.", file=sys.stderr)
    print("Executor appears to reference protected SOT paths alongside write APIs:", file=sys.stderr)
    for f in findings[:50]:
        print(f"- {f}", file=sys.stderr)
    if len(findings) > 50:
        print(f"... and {len(findings) - 50} more", file=sys.stderr)
    print("", file=sys.stderr)
    print("Fix: remove direct writes to SOT ledgers from executor; write run-local artifacts instead.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


