#!/usr/bin/env python3
"""
Requirements Portability Check

Purpose: Fail fast if committed requirements.txt or requirements-dev.txt are not
portable across Linux CI/Docker, especially after regeneration on Windows.

Policy: Committed requirements must be generated on Linux/WSL (CI canonical).

Exit codes:
  0: Portable / passes checks
  1: Portability violations detected (action required)
  2: Runtime error (missing file, unreadable file, unexpected exception)

Usage:
    # Check default files
    python scripts/check_requirements_portability.py

    # Check custom paths
    python scripts/check_requirements_portability.py --requirements custom-requirements.txt

    # Enable strict mode (extra checks)
    python scripts/check_requirements_portability.py --strict
"""

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple


def check_pywin32_marker(lines: List[str], filename: str) -> List[str]:
    """
    Check that pywin32 is Windows-only (has sys_platform marker).

    Returns list of error messages (empty if passing).
    """
    errors = []
    for i, line in enumerate(lines, 1):
        # Skip comments and empty lines
        if line.strip().startswith('#') or not line.strip():
            continue

        # Check for pywin32 without marker
        if re.match(r'^pywin32==', line):
            # Must be explicitly Windows-only
            if not re.search(r'''sys_platform\s*==\s*["']win32["']''', line):
                errors.append(
                    f"{filename}:{i}: pywin32 is unconditional (must be 'sys_platform == \"win32\"')\n"
                    f"  Line: {line.strip()}"
                )

    return errors


def check_python_magic_marker(lines: List[str], filename: str) -> List[str]:
    """
    Check that python-magic exists with non-Windows marker.

    Returns list of error messages (empty if passing).
    """
    errors = []
    has_python_magic_non_win = False

    for line in lines:
        # Skip comments and empty lines
        if line.strip().startswith('#') or not line.strip():
            continue

        # Check for python-magic with non-win32 marker
        if re.match(r'^python-magic==', line):
            if re.search(r'''sys_platform\s*!=\s*["']win32["']''', line):
                has_python_magic_non_win = True
                break

    if not has_python_magic_non_win:
        errors.append(
            f"{filename}: missing python-magic with 'sys_platform != \"win32\"' marker\n"
            f"  Required for Linux/Docker compatibility (pyproject.toml includes python-magic for non-win32)"
        )

    return errors


def check_python_magic_bin_marker(lines: List[str], filename: str) -> List[str]:
    """
    Check that python-magic-bin is Windows-only (has sys_platform marker).

    Returns list of error messages (empty if passing).
    """
    errors = []
    for i, line in enumerate(lines, 1):
        # Skip comments and empty lines
        if line.strip().startswith('#') or not line.strip():
            continue

        # Check for python-magic-bin without marker
        if re.match(r'^python-magic-bin==', line):
            # Must be explicitly Windows-only
            if not re.search(r'''sys_platform\s*==\s*["']win32["']''', line):
                errors.append(
                    f"{filename}:{i}: python-magic-bin is unconditional (must be 'sys_platform == \"win32\"')\n"
                    f"  Line: {line.strip()}"
                )

    return errors


def check_generated_header(lines: List[str], filename: str) -> List[str]:
    """
    Strict mode: Check that file has pip-compile header (to discourage manual edits).

    Returns list of warnings (non-fatal in default mode).
    """
    warnings = []
    has_header = False

    for line in lines[:10]:  # Check first 10 lines
        if 'pip-compile' in line.lower() or 'pyproject.toml' in line.lower():
            has_header = True
            break

    if not has_header:
        warnings.append(
            f"{filename}: missing pip-compile header (may have been manually edited)\n"
            f"  Expected header indicating generation from pyproject.toml"
        )

    return warnings


def check_requirements_file(
    filepath: Path,
    strict: bool = False
) -> Tuple[List[str], List[str]]:
    """
    Check a single requirements file for portability violations.

    Returns (errors, warnings) tuple.
    """
    filename = filepath.name
    errors = []
    warnings = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        errors.append(f"Error: File not found: {filepath}")
        return errors, warnings
    except Exception as e:
        errors.append(f"Error: Cannot read {filepath}: {e}")
        return errors, warnings

    # Required checks (always run)
    errors.extend(check_pywin32_marker(lines, filename))
    errors.extend(check_python_magic_marker(lines, filename))
    errors.extend(check_python_magic_bin_marker(lines, filename))

    # Strict mode checks (optional)
    if strict:
        strict_warnings = check_generated_header(lines, filename)
        # In strict mode, treat warnings as errors
        errors.extend(strict_warnings)

    return errors, warnings


def print_remediation_guidance() -> None:
    """Print remediation guidance for portability failures."""
    print("\n" + "=" * 70, file=sys.stderr)
    print("REMEDIATION GUIDANCE", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print("\nIf running on Windows:", file=sys.stderr)
    print("  WARNING: Do not regenerate requirements on Windows PowerShell/CMD", file=sys.stderr)
    print("  Use WSL/Linux and run:", file=sys.stderr)
    print("     bash scripts/regenerate_requirements.sh", file=sys.stderr)
    print("\nPolicy location:", file=sys.stderr)
    print("  - security/README.md (requirements regeneration policy)", file=sys.stderr)
    print("  - docs/SECURITY_LOG.md (policy change history)", file=sys.stderr)
    print("=" * 70, file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Check requirements.txt portability (Linux/Docker canonical)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--requirements",
        type=Path,
        default=Path("requirements.txt"),
        help="Path to requirements.txt (default: requirements.txt)",
    )

    parser.add_argument(
        "--requirements-dev",
        type=Path,
        default=Path("requirements-dev.txt"),
        help="Path to requirements-dev.txt (default: requirements-dev.txt)",
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enable strict mode (extra checks, warnings become errors)",
    )

    args = parser.parse_args()

    all_errors = []
    all_warnings = []
    files_checked = []

    # Check both files (missing files are a runtime error in this repo)
    for filepath in [args.requirements, args.requirements_dev]:
        if not filepath.exists():
            print(f"Error: File not found: {filepath}", file=sys.stderr)
            print("This repo requires committed requirements files to exist.", file=sys.stderr)
            print_remediation_guidance()
            return 2

        files_checked.append(filepath.name)
        errors, warnings = check_requirements_file(filepath, strict=args.strict)
        all_errors.extend(errors)
        all_warnings.extend(warnings)

    # Print results
    if not all_errors and not all_warnings:
        # Success case
        files_list = ", ".join(files_checked)
        print(f"OK: requirements portability check passed ({files_list})")
        return 0

    # Failure case
    if all_errors:
        print("ERROR: requirements portability check failed", file=sys.stderr)
        print("", file=sys.stderr)
        for error in all_errors:
            print(error, file=sys.stderr)

        print_remediation_guidance()
        return 1

    # Warnings only (non-strict mode)
    if all_warnings:
        print("WARNING: requirements portability warnings", file=sys.stderr)
        print("", file=sys.stderr)
        for warning in all_warnings:
            print(warning, file=sys.stderr)

        # Warnings are non-fatal in default mode
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(2)
