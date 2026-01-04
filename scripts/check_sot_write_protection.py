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

    # Phase F: Expanded set of runtime modules to scan
    runtime_modules = [
        "src/autopack/autonomous_executor.py",
        "src/autopack/llm_service.py",
        "src/autopack/archive_consolidator.py",
        "src/autopack/debug_journal.py",
        "src/autopack/intention_wiring.py",
        "src/autopack/autonomous/intention_first_loop.py",
        "src/autopack/autonomous/executor_wiring.py",
    ]

    all_findings = []
    missing_modules = []

    for module_rel_path in runtime_modules:
        module_path = repo_root / module_rel_path
        if not module_path.exists():
            missing_modules.append(module_rel_path)
            continue

        findings = _scan_file(module_path)
        all_findings.extend(findings)

    # Report missing modules as warnings (not failures)
    if missing_modules:
        print(f"⚠️  Warning: {len(missing_modules)} expected module(s) not found (may not exist yet):", file=sys.stderr)
        for m in missing_modules[:5]:
            print(f"  - {m}", file=sys.stderr)
        if len(missing_modules) > 5:
            print(f"  ... and {len(missing_modules) - 5} more", file=sys.stderr)

    if not all_findings:
        print(f"✅ SOT write protection check passed (no direct writes detected in {len(runtime_modules) - len(missing_modules)} runtime modules)")
        return 0

    print("❌ SOT write protection check failed.", file=sys.stderr)
    print("Runtime modules appear to reference protected SOT paths alongside write APIs:", file=sys.stderr)
    for f in all_findings[:50]:
        print(f"- {f}", file=sys.stderr)
    if len(all_findings) > 50:
        print(f"... and {len(all_findings) - 50} more", file=sys.stderr)
    print("", file=sys.stderr)
    print("Fix: remove direct writes to SOT ledgers from runtime code; write run-local artifacts instead.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


