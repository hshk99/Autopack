#!/usr/bin/env python3
"""SOT hygiene check for CI (BUILD-187 Phase 11).

Checks:
1. BUILD-*.md files not referenced in BUILD_HISTORY.md (report-only)
2. Stale "TODO implement X" claims when X exists (report-only)

This script is CHECK-ONLY and does NOT write to any files.
All output is to stdout for CI capture.

Exit codes:
- 0: All checks pass (or report-only mode with findings)
- 1: Script error
- 2: Findings detected in strict mode (default is report-only)

Usage:
    python scripts/ci/check_sot_hygiene.py [--strict]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, NamedTuple, Set


class Finding(NamedTuple):
    """A hygiene finding."""

    category: str
    severity: str  # "info", "warning", "error"
    message: str
    file_path: str
    line_number: int | None = None


def find_build_docs(docs_dir: Path) -> List[Path]:
    """Find all BUILD-*.md files in docs directory."""
    if not docs_dir.exists():
        return []
    return sorted(docs_dir.glob("BUILD-*.md"))


def find_referenced_builds(build_history_path: Path) -> Set[str]:
    """Find BUILD doc references in BUILD_HISTORY.md."""
    if not build_history_path.exists():
        return set()

    content = build_history_path.read_text(encoding="utf-8")
    # Match BUILD-XXX patterns (with optional suffixes like BUILD-187_SOMETHING)
    pattern = r"BUILD-\d+(?:_[A-Z0-9_]+)?"
    matches = re.findall(pattern, content, re.IGNORECASE)
    return set(matches)


def check_unreferenced_build_docs(docs_dir: Path) -> List[Finding]:
    """Check for BUILD-*.md files not referenced in BUILD_HISTORY.md."""
    findings = []

    build_docs = find_build_docs(docs_dir)
    build_history_path = docs_dir / "BUILD_HISTORY.md"
    referenced = find_referenced_builds(build_history_path)

    for doc_path in build_docs:
        # Extract BUILD-XXX from filename
        stem = doc_path.stem  # e.g., "BUILD-187_SOMETHING"
        # Get the BUILD-XXX prefix
        match = re.match(r"(BUILD-\d+)", stem)
        if not match:
            continue

        build_id = match.group(1)

        # Check if referenced (case-insensitive)
        is_referenced = any(
            ref.upper() == build_id.upper() or ref.upper().startswith(build_id.upper() + "_")
            for ref in referenced
        )

        if not is_referenced:
            findings.append(
                Finding(
                    category="unreferenced_build_doc",
                    severity="warning",
                    message=f"{doc_path.name} not referenced in BUILD_HISTORY.md",
                    file_path=str(doc_path),
                )
            )

    return findings


def find_todo_implement_claims(docs_dir: Path) -> List[tuple[Path, int, str, str]]:
    """Find 'TODO implement X' claims in docs.

    Returns list of (file_path, line_number, claimed_item, full_line).
    """
    claims = []

    # Patterns for TODO implement claims
    patterns = [
        r"TODO[:\s]+implement\s+([a-zA-Z0-9_\-./]+)",
        r"TODO[:\s]+add\s+([a-zA-Z0-9_\-./]+)",
        r"TODO[:\s]+create\s+([a-zA-Z0-9_\-./]+)",
        r"\[ \]\s+implement\s+([a-zA-Z0-9_\-./]+)",
        r"\[ \]\s+add\s+([a-zA-Z0-9_\-./]+)",
    ]

    for doc_path in docs_dir.glob("**/*.md"):
        try:
            content = doc_path.read_text(encoding="utf-8")
            for line_num, line in enumerate(content.split("\n"), 1):
                for pattern in patterns:
                    matches = re.findall(pattern, line, re.IGNORECASE)
                    for match in matches:
                        claims.append((doc_path, line_num, match, line.strip()))
        except Exception:
            continue

    return claims


def check_stale_todo_claims(repo_root: Path) -> List[Finding]:
    """Check for stale TODO claims where the item now exists."""
    findings = []
    docs_dir = repo_root / "docs"

    claims = find_todo_implement_claims(docs_dir)

    for doc_path, line_num, claimed_item, full_line in claims:
        # Check if the claimed item exists
        exists = False

        # Check as file path
        potential_paths = [
            repo_root / claimed_item,
            repo_root / "src" / claimed_item,
            repo_root / "scripts" / claimed_item,
            repo_root / "tests" / claimed_item,
        ]

        for potential_path in potential_paths:
            if potential_path.exists():
                exists = True
                break

        # Check if it's a known script/module name
        if not exists:
            # Search for the filename in common locations
            filename = Path(claimed_item).name
            for search_pattern in [f"**/{filename}", f"**/{filename}.py"]:
                matches = list(repo_root.glob(search_pattern))
                if matches:
                    exists = True
                    break

        if exists:
            findings.append(
                Finding(
                    category="stale_todo_claim",
                    severity="info",
                    message=f"TODO claims '{claimed_item}' needs implementation, but it exists",
                    file_path=str(doc_path),
                    line_number=line_num,
                )
            )

    return findings


def format_findings(findings: List[Finding]) -> str:
    """Format findings for console output (ASCII-safe for Windows)."""
    if not findings:
        return "[OK] No SOT hygiene issues found"

    lines = [f"[REPORT] Found {len(findings)} SOT hygiene finding(s):", ""]

    # Group by category
    by_category: dict[str, List[Finding]] = {}
    for f in findings:
        by_category.setdefault(f.category, []).append(f)

    for category, category_findings in sorted(by_category.items()):
        lines.append(f"== {category} ({len(category_findings)}) ==")
        for f in category_findings:
            severity_marker = {"info": "[INFO]", "warning": "[WARN]", "error": "[ERROR]"}.get(
                f.severity, "[????]"
            )
            if f.line_number:
                lines.append(f"  {severity_marker} {f.file_path}:{f.line_number}")
            else:
                lines.append(f"  {severity_marker} {f.file_path}")
            lines.append(f"           {f.message}")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="SOT hygiene check for CI")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with error code if findings detected",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: auto-detect)",
    )
    args = parser.parse_args()

    # Find repo root
    if args.repo_root:
        repo_root = args.repo_root
    else:
        # Auto-detect from script location
        repo_root = Path(__file__).parent.parent.parent
        if not (repo_root / "docs").exists():
            print("[ERROR] Could not find docs directory. Specify --repo-root.", file=sys.stderr)
            return 1

    docs_dir = repo_root / "docs"

    print("[CHECK] SOT hygiene check starting...")
    print(f"        Repo root: {repo_root}")
    print(f"        Docs dir: {docs_dir}")
    print()

    all_findings: List[Finding] = []

    # Run checks
    print("[CHECK] Checking for unreferenced BUILD docs...")
    unreferenced = check_unreferenced_build_docs(docs_dir)
    all_findings.extend(unreferenced)
    print(f"        Found {len(unreferenced)} unreferenced BUILD doc(s)")

    print("[CHECK] Checking for stale TODO claims...")
    stale_todos = check_stale_todo_claims(repo_root)
    all_findings.extend(stale_todos)
    print(f"        Found {len(stale_todos)} stale TODO claim(s)")

    print()
    print(format_findings(all_findings))

    # Determine exit code
    if args.strict and all_findings:
        print()
        print("[STRICT] Exiting with error due to findings in strict mode")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
