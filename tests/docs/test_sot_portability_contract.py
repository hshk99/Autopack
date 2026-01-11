"""
6-file SOT portability contract: prevent workstation-absolute-path copy/paste traps.

Goal: Block workstation-specific paths from being reintroduced into the 6-file SOT docs:
- docs/PROJECT_INDEX.json (strict)
- docs/LEARNED_RULES.json (strict)
- docs/FUTURE_PLAN.md (strict)
- docs/BUILD_HISTORY.md (recent-window only to avoid rewriting history)
- docs/DEBUG_LOG.md (recent-window only)
- docs/ARCHITECTURE_DECISIONS.md (recent-window only)

Patterns blocked (unless marked HISTORICAL/LEGACY on same line):
- c:/dev/Autopack (case-insensitive)
- C:\\dev\\Autopack (and variants like D:\\dev\\Autopack)

Per PR-02 of IMPROVEMENT_OPPORTUNITIES_COMPREHENSIVE_2026-01-11.md
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple


class ViolationResult(NamedTuple):
    file: str
    line_num: int
    line_content: str
    pattern: str


def _repo_root() -> Path:
    return Path(__file__).parents[2]


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


# Patterns to forbid
WORKSTATION_PATH_PATTERNS = [
    re.compile(
        r"[a-zA-Z]:[/\\]dev[/\\]Autopack", re.IGNORECASE
    ),  # c:/dev/Autopack, D:\dev\Autopack, etc.
]

# Markers that exempt a line from enforcement
EXEMPTION_MARKERS = ["HISTORICAL", "LEGACY", "DEPRECATED", "(historical)", "(legacy)"]


def _is_exempted(line: str) -> bool:
    """Check if line contains exemption markers."""
    line_upper = line.upper()
    return any(marker.upper() in line_upper for marker in EXEMPTION_MARKERS)


def _check_file_strict(path: Path) -> list[ViolationResult]:
    """Check entire file for violations (strict mode)."""
    violations = []
    lines = _read_lines(path)
    for i, line in enumerate(lines, start=1):
        if _is_exempted(line):
            continue
        for pattern in WORKSTATION_PATH_PATTERNS:
            if pattern.search(line):
                violations.append(
                    ViolationResult(
                        file=str(path.relative_to(_repo_root())),
                        line_num=i,
                        line_content=line[:120] + ("..." if len(line) > 120 else ""),
                        pattern=pattern.pattern,
                    )
                )
    return violations


def _check_file_recent_window(path: Path, recent_lines: int = 200) -> list[ViolationResult]:
    """Check only recent entries (last N lines) for violations.

    For append-only ledgers, we avoid rewriting history by only enforcing on recent entries.
    This allows historical context to remain while preventing new violations.
    """
    violations = []
    lines = _read_lines(path)
    if not lines:
        return violations

    # Only check the last `recent_lines` lines
    start_line = max(0, len(lines) - recent_lines)
    for i, line in enumerate(lines[start_line:], start=start_line + 1):
        if _is_exempted(line):
            continue
        for pattern in WORKSTATION_PATH_PATTERNS:
            if pattern.search(line):
                violations.append(
                    ViolationResult(
                        file=str(path.relative_to(_repo_root())),
                        line_num=i,
                        line_content=line[:120] + ("..." if len(line) > 120 else ""),
                        pattern=pattern.pattern,
                    )
                )
    return violations


def test_sot_strict_docs_no_workstation_paths():
    """Strict SOT docs must not contain workstation-specific paths.

    These are high-risk docs that are frequently copy/pasted:
    - docs/PROJECT_INDEX.json
    - docs/LEARNED_RULES.json
    - docs/FUTURE_PLAN.md
    """
    repo_root = _repo_root()

    strict_sot_docs = [
        repo_root / "docs" / "PROJECT_INDEX.json",
        repo_root / "docs" / "LEARNED_RULES.json",
        repo_root / "docs" / "FUTURE_PLAN.md",
    ]

    all_violations: list[ViolationResult] = []

    for doc in strict_sot_docs:
        if not doc.exists():
            continue
        all_violations.extend(_check_file_strict(doc))

    if all_violations:
        msg_lines = ["Workstation-path copy/paste traps detected in strict SOT docs:"]
        for v in all_violations:
            msg_lines.append(f"  {v.file}:{v.line_num}: {v.line_content}")
        msg_lines.append("")
        msg_lines.append(
            "Fix: Replace workstation paths with $REPO_ROOT or 'run from repository root',"
        )
        msg_lines.append("     or add HISTORICAL/LEGACY marker if documenting past issues.")
        assert False, "\n".join(msg_lines)


def test_sot_append_only_ledgers_recent_window():
    """Append-only SOT ledgers must not have workstation paths in recent entries.

    These docs are historical records - we only enforce on recent entries to avoid
    rewriting history while preventing new violations:
    - docs/BUILD_HISTORY.md (last 200 lines)
    - docs/DEBUG_LOG.md (last 200 lines)
    - docs/ARCHITECTURE_DECISIONS.md (last 200 lines)
    """
    repo_root = _repo_root()

    # Recent window size - check last N lines of each ledger
    RECENT_WINDOW = 200

    append_only_ledgers = [
        repo_root / "docs" / "BUILD_HISTORY.md",
        repo_root / "docs" / "DEBUG_LOG.md",
        repo_root / "docs" / "ARCHITECTURE_DECISIONS.md",
    ]

    all_violations: list[ViolationResult] = []

    for doc in append_only_ledgers:
        if not doc.exists():
            continue
        all_violations.extend(_check_file_recent_window(doc, recent_lines=RECENT_WINDOW))

    if all_violations:
        msg_lines = [
            f"Workstation-path copy/paste traps detected in recent entries (last {RECENT_WINDOW} lines):"
        ]
        for v in all_violations:
            msg_lines.append(f"  {v.file}:{v.line_num}: {v.line_content}")
        msg_lines.append("")
        msg_lines.append(
            "Fix: Replace workstation paths with $REPO_ROOT or 'run from repository root',"
        )
        msg_lines.append("     or add HISTORICAL/LEGACY marker if documenting past issues.")
        assert False, "\n".join(msg_lines)
