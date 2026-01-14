#!/usr/bin/env python3
"""Audit LLM model string usage across the repo.

Why:
- Model names are frequently hardcoded in scripts and fallbacks.
- When upgrading (e.g., glm-4.6 -> glm-4.7), we want a single command that shows
  *exactly* where model strings are referenced, and whether they are:
  - active code paths, or
  - historical docs / archives.

This script is intentionally conservative: it reports matches; it does not modify files.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent


MODEL_REGEX = re.compile(
    r"\b("
    r"glm-\d+(?:\.\d+)?"
    r"|claude-[a-z0-9\-_.]+"
    r"|gpt-[a-z0-9\-_.]+"
    r"|o\d+(?:-[a-z0-9\-_.]+)?"
    r"|gemini-[a-z0-9\-_.]+"
    r"|text-embedding-[a-z0-9\-_.]+"
    r")\b",
    flags=re.IGNORECASE,
)


DEFAULT_INCLUDE_DIRS = ["src", "scripts", "config"]
DEFAULT_EXCLUDE_DIRS = [
    "archive",
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
]
DEFAULT_EXCLUDE_FILES = {
    "scripts/model_audit.py",  # avoid self-matches / --fail-on loops
}


@dataclass(frozen=True)
class Match:
    path: Path
    line_no: int
    line: str
    model: str


def _iter_files(
    repo_root: Path,
    include_dirs: List[str],
    exclude_dirs: List[str],
    glob: str,
) -> Iterable[Path]:
    for d in include_dirs:
        base = repo_root / d
        if not base.exists():
            continue
        for p in base.rglob(glob):
            if not p.is_file():
                continue
            rel = p.relative_to(repo_root)
            if any(part in exclude_dirs for part in rel.parts):
                continue
            yield p


def _scan_file(path: Path, regex: re.Pattern) -> List[Match]:
    out: List[Match] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return out
    for idx, line in enumerate(text.splitlines(), start=1):
        for m in regex.finditer(line):
            out.append(Match(path=path, line_no=idx, line=line.rstrip(), model=m.group(1)))
    return out


def main() -> int:
    # Windows consoles can be cp1252; ensure we never crash on printing.
    try:  # py3.7+
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Audit model string usage across the repo.")
    parser.add_argument(
        "--include",
        action="append",
        default=None,
        help="Directory to include (repeatable). Default: src,scripts,config",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        help="Directory name to exclude (repeatable). Default includes archive/.git/venv/node_modules",
    )
    parser.add_argument(
        "--glob",
        default="*.py",
        help="File glob to scan (default: *.py). Use '*.md' to scan docs too.",
    )
    parser.add_argument(
        "--filter",
        default=None,
        help="Only show matches that contain this substring (case-insensitive), e.g. glm-4.6",
    )
    parser.add_argument(
        "--fail-on",
        default=None,
        help="Exit 1 if any match contains this substring (case-insensitive)",
    )
    args = parser.parse_args()

    include_dirs = args.include or list(DEFAULT_INCLUDE_DIRS)
    exclude_dirs = DEFAULT_EXCLUDE_DIRS + (args.exclude or [])

    filt = args.filter.lower() if args.filter else None
    fail_on = args.fail_on.lower() if args.fail_on else None

    matches: List[Match] = []
    for f in _iter_files(REPO_ROOT, include_dirs, exclude_dirs, args.glob):
        rel = f.relative_to(REPO_ROOT).as_posix()
        if rel in DEFAULT_EXCLUDE_FILES:
            continue
        matches.extend(_scan_file(f, MODEL_REGEX))

    if filt:
        matches = [m for m in matches if filt in m.model.lower() or filt in m.line.lower()]

    # Print grouped by file
    by_file: dict[Path, List[Match]] = {}
    for m in matches:
        by_file.setdefault(m.path, []).append(m)

    total = 0
    for path in sorted(by_file.keys(), key=lambda p: str(p).lower()):
        rel = path.relative_to(REPO_ROOT)
        file_matches = by_file[path]
        print(f"\n== {rel} ({len(file_matches)} matches) ==")
        for m in file_matches[:200]:
            # Avoid encoding errors on Windows terminals
            safe_line = m.line.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
            print(f"{m.line_no}: [{m.model}] {safe_line}")
        if len(file_matches) > 200:
            print(f"... truncated ({len(file_matches) - 200} more)")
        total += len(file_matches)

    print(f"\nTotal matches: {total}")

    if fail_on:
        bad = [m for m in matches if fail_on in m.model.lower() or fail_on in m.line.lower()]
        if bad:
            print(f"\nFAIL: found {len(bad)} matches for --fail-on '{args.fail_on}'")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
