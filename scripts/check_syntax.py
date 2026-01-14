"""CI Guard: Check for SyntaxErrors in critical Python files.

This script prevents SyntaxErrors from landing in the repo by compiling
all Python files in src/autopack/ and reporting any compilation failures.

Usage:
    python scripts/check_syntax.py

Exit codes:
    0: All files compile successfully
    1: One or more files have SyntaxErrors
"""

import sys
from pathlib import Path
import py_compile


def check_syntax(root_dir: Path) -> int:
    """Check syntax of all .py files in root_dir."""
    errors = []
    checked = 0

    print(f"Checking Python syntax in {root_dir}...")

    for py_file in root_dir.rglob("*.py"):
        # Skip __pycache__ and build directories
        if "__pycache__" in str(py_file) or "/build/" in str(py_file):
            continue

        try:
            py_compile.compile(str(py_file), doraise=True)
            checked += 1
        except py_compile.PyCompileError as e:
            errors.append((py_file, e))

    print(f"\nChecked {checked} Python files")

    if errors:
        print(f"\nERROR: Found {len(errors)} SyntaxError(s):")
        for py_file, error in errors:
            print(f"\n  File: {py_file}")
            print(f"  {error}")
        return 1
    else:
        print("SUCCESS: All Python files compile without SyntaxErrors")
        return 0


if __name__ == "__main__":
    root = Path(__file__).parent.parent / "src" / "autopack"
    sys.exit(check_syntax(root))
