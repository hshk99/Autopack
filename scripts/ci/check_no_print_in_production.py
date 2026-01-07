#!/usr/bin/env python3
"""
BUILD-188 P5.7: Static check for print() statements in production modules.

Policy: Production code should use logging, not print().
- print() output is not captured by structured logging
- print() bypasses log level controls
- print() in production modules can leak sensitive data

Exceptions:
- CLI scripts (scripts/) are allowed to use print()
- Test files (tests/) are allowed to use print()
- Files with "# print: allow" comment are exempted

Usage:
    python scripts/ci/check_no_print_in_production.py [--fix]

Exit codes:
    0: No violations
    1: Violations found
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import List, NamedTuple


class PrintViolation(NamedTuple):
    """A print() call violation."""

    file: Path
    line: int
    col: int


def has_allow_comment(file_path: Path) -> bool:
    """Check if file has a '# print: allow' exemption comment."""
    try:
        content = file_path.read_text(encoding="utf-8")
        return "# print: allow" in content or "# noqa: print" in content
    except Exception:
        return False


def find_print_calls(file_path: Path) -> List[PrintViolation]:
    """Find print() calls in a Python file."""
    violations = []
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except Exception:
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Check for print() or builtins.print()
            if isinstance(node.func, ast.Name) and node.func.id == "print":
                violations.append(PrintViolation(file_path, node.lineno, node.col_offset))
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "print":
                # builtins.print or sys.stdout.write disguised as print
                pass  # Only catch direct print() for now

    return violations


def check_module(src_dir: Path) -> List[PrintViolation]:
    """Check all production Python files for print() calls."""
    all_violations = []

    for py_file in src_dir.rglob("*.py"):
        # Skip __pycache__ and .git
        if "__pycache__" in str(py_file) or ".git" in str(py_file):
            continue

        # Skip files with exemption comments
        if has_allow_comment(py_file):
            continue

        violations = find_print_calls(py_file)
        all_violations.extend(violations)

    return all_violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Check for print() in production code")
    parser.add_argument("--path", default="src/autopack", help="Path to check")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    src_dir = Path(args.path)
    if not src_dir.exists():
        print(f"Error: {src_dir} does not exist", file=sys.stderr)
        return 1

    violations = check_module(src_dir)

    if violations:
        print(f"Found {len(violations)} print() violations in production code:")
        print()
        for v in violations:
            rel_path = (
                v.file.relative_to(Path.cwd()) if v.file.is_relative_to(Path.cwd()) else v.file
            )
            print(f"  {rel_path}:{v.line}:{v.col}: print() call")
        print()
        print("Policy: Use logging.info/debug/warning/error instead of print()")
        print("To exempt a file, add '# print: allow' comment at the top")
        return 1
    else:
        if args.verbose:
            print(f"No print() violations found in {src_dir}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
