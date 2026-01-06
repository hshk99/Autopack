#!/usr/bin/env python3
"""
CI guard: prevent reintroducing Windows-unsafe Unicode in console output.

Problem:
  On Windows, console output may use legacy encodings (e.g., cp1252/cp437),
  and `print()` can crash with:
    'charmap' codec can't encode character ...

Policy (BUILD-185 follow-up to BUILD-184):
  - Disallow Unicode arrow glyphs (e.g., `→`, `←`, `↔`) in *string literals*
    passed to built-in `print(...)` within production code (src/ and scripts/).
    (These are a common source of Windows 'charmap' crashes.)
  - Allow `safe_print(...)` (it is designed to handle UnicodeEncodeError).
  - Provide an explicit escape hatch pragma for rare cases:
      # autopack: allow-unicode-print

Notes:
  - This is intentionally narrow (arrows only) and AST-based.
  - It only flags obvious, reviewable cases (string literals / f-string literal parts).

Exit codes:
  0: No violations
  1: Violations found
  2: Script error
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence


PRAGMA_ALLOW = "autopack: allow-unicode-print"

# Restrict scan to production code by default (tests may intentionally contain Unicode).
#
# Important: Many legacy helper scripts under scripts/ use Unicode arrows for pretty output.
# Those scripts are not part of the BUILD-184 failure path and converting them all is
# intentionally out-of-scope for this small follow-up PR.
#
# Defaults:
# - Scan all production library code under src/
# - Scan the specific Windows-regressed script that is invoked by CI smoke tests:
#     scripts/tidy/sot_db_sync.py
DEFAULT_SCAN_DIRS = ("src",)
DEFAULT_SCAN_FILES = ("scripts/tidy/sot_db_sync.py",)

UNICODE_ARROW_CHARS = {
    "\u2192",  # → RIGHTWARDS ARROW
    "\u2190",  # ← LEFTWARDS ARROW
    "\u2194",  # ↔ LEFT RIGHT ARROW
}


@dataclass(frozen=True)
class Violation:
    file_path: str
    line: int
    col: int
    snippet: str
    reason: str


def _iter_py_files(repo_root: Path, relative_dirs: Sequence[str]) -> Iterable[Path]:
    for rel in relative_dirs:
        base = repo_root / rel
        if not base.exists():
            continue
        yield from base.rglob("*.py")

def _iter_explicit_files(repo_root: Path, relative_files: Sequence[str]) -> Iterable[Path]:
    for rel in relative_files:
        p = repo_root / rel
        if p.exists() and p.is_file():
            yield p


def _pragma_allows(lines: List[str], lineno_1based: int) -> bool:
    # Allow pragma on same line as call, or immediately preceding line.
    idx = max(lineno_1based - 1, 0)
    for j in (idx, idx - 1):
        if 0 <= j < len(lines) and PRAGMA_ALLOW in lines[j]:
            return True
    return False


def _callee_name(call: ast.Call) -> Optional[str]:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        # e.g., module.safe_print(...) or obj.print(...)
        return call.func.attr
    return None


def _extract_string_literals(node: ast.AST) -> List[str]:
    """
    Extract string literal content from a node.

    We intentionally only catch obvious literal cases:
    - Constant str
    - f-strings: constant parts in JoinedStr
    - simple concatenation of literals: "a" + "b"
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]

    if isinstance(node, ast.JoinedStr):
        parts: List[str] = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
        return parts

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _extract_string_literals(node.left)
        right = _extract_string_literals(node.right)
        return left + right

    return []


def check_python_source_for_violations(source: str, file_path: str) -> List[Violation]:
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        return [
            Violation(
                file_path=file_path,
                line=int(getattr(e, "lineno", 1) or 1),
                col=int(getattr(e, "offset", 0) or 0),
                snippet="",
                reason=f"SyntaxError while parsing file: {e.msg}",
            )
        ]

    lines = source.splitlines()
    violations: List[Violation] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        name = _callee_name(node)
        if name is None:
            continue

        # Allow safe_print explicitly.
        if name == "safe_print":
            continue

        # Only enforce built-in print(...).
        if name != "print":
            continue

        lineno = int(getattr(node, "lineno", 1) or 1)
        col = int(getattr(node, "col_offset", 0) or 0)
        if _pragma_allows(lines, lineno):
            continue

        # Gather literal strings from args and relevant keyword values.
        literals: List[str] = []
        for arg in node.args:
            literals.extend(_extract_string_literals(arg))
        for kw in node.keywords:
            if kw.value is None:
                continue
            literals.extend(_extract_string_literals(kw.value))

        if not literals:
            continue

        for lit in literals:
            if any(ch in lit for ch in UNICODE_ARROW_CHARS):
                snippet = lines[lineno - 1].rstrip() if 0 <= (lineno - 1) < len(lines) else ""
                violations.append(
                    Violation(
                        file_path=file_path,
                        line=lineno,
                        col=col,
                        snippet=snippet,
                        reason="Unicode arrow in print(...). Use safe_print(...) or ASCII '->'/'<-'/'<->'.",
                    )
                )
                break  # One violation per call is enough

    return violations


def check_file(path: Path) -> List[Violation]:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        return [
            Violation(
                file_path=str(path),
                line=1,
                col=0,
                snippet="",
                reason=f"File is not valid UTF-8: {e}",
            )
        ]
    return check_python_source_for_violations(source, str(path))


def run(repo_root: Path, scan_dirs: Sequence[str], scan_files: Sequence[str]) -> int:
    violations: List[Violation] = []
    seen: set[Path] = set()
    for py in _iter_py_files(repo_root, scan_dirs):
        if py in seen:
            continue
        seen.add(py)
        violations.extend(check_file(py))
    for py in _iter_explicit_files(repo_root, scan_files):
        if py in seen:
            continue
        seen.add(py)
        violations.extend(check_file(py))

    if violations:
        _emit("=" * 78 + "\n")
        _emit("Windows console Unicode guard violations (print(...) with Unicode arrows):\n")
        _emit("=" * 78 + "\n")
        for v in violations:
            loc = f"{v.file_path}:{v.line}:{v.col}"
            _emit(f"- {loc}\n")
            _emit(f"  Reason: {v.reason}\n")
            if v.snippet:
                # Emit ASCII-safe snippet so this tool never reproduces a Windows charmap crash.
                _emit(f"  Code: {_ascii_safe(v.snippet)}\n")
            _emit("\n")
        _emit("Remediation:\n")
        _emit("  - Replace Unicode arrows with ASCII: ->, <-, <->\n")
        _emit("  - Or use autopack.safe_print.safe_print(...)\n")
        _emit(f"  - If unavoidable, add pragma near the call: # {PRAGMA_ALLOW}\n")
        _emit("=" * 78 + "\n")
        return 1

    _emit("[OK] Windows console Unicode guard: no violations found\n")
    return 0


def _ascii_safe(text: str) -> str:
    # Make output safe on any console encoding.
    return text.encode("ascii", errors="backslashreplace").decode("ascii")


def _emit(text: str) -> None:
    # Write bytes to stdout buffer to avoid UnicodeEncodeError on Windows consoles.
    data = text.encode("utf-8", errors="backslashreplace")
    sys.stdout.buffer.write(data)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CI guard: prevent reintroducing Windows-unsafe Unicode in console output."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root (default: current directory).",
    )
    parser.add_argument(
        "--scan-dirs",
        nargs="*",
        default=list(DEFAULT_SCAN_DIRS),
        help="Relative directories to scan (default: src).",
    )
    parser.add_argument(
        "--scan-files",
        nargs="*",
        default=list(DEFAULT_SCAN_FILES),
        help="Relative files to scan in addition to dirs (default: scripts/tidy/sot_db_sync.py).",
    )
    args = parser.parse_args()

    try:
        return run(args.repo_root, args.scan_dirs, args.scan_files)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


