#!/usr/bin/env python3
"""
Normalize Unicode console glyphs to ASCII equivalents (BUILD-186).

This tool performs deterministic, mechanical normalization of Unicode
glyphs in Python source files to ASCII equivalents. This prevents
Windows console crashes due to 'charmap' codec errors.

Usage:
    # Check mode (no writes, exits non-zero if changes would be made):
    python scripts/tools/normalize_console_glyphs.py --check --files-from critical_scripts.txt

    # Fix mode (writes changes):
    python scripts/tools/normalize_console_glyphs.py --files-from critical_scripts.txt

    # With explicit paths:
    python scripts/tools/normalize_console_glyphs.py scripts/check_doc_links.py scripts/tidy/sot_db_sync.py

    # Generate critical scripts list from CI workflows:
    python scripts/tools/normalize_console_glyphs.py --list-critical

The tool is idempotent: running twice makes no further changes.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ASCII replacements for common Unicode glyphs (subset from safe_print.py)
# Only includes glyphs commonly used in console output
GLYPH_REPLACEMENTS: dict[str, str] = {
    # Arrows
    "\u2192": "->",  # RIGHTWARDS ARROW
    "\u2190": "<-",  # LEFTWARDS ARROW
    "\u2194": "<->",  # LEFT RIGHT ARROW
    # Check marks and X marks
    "\u2713": "[x]",  # CHECK MARK
    "\u2714": "[x]",  # HEAVY CHECK MARK
    "\u2705": "[OK]",  # WHITE HEAVY CHECK MARK (emoji)
    "\u2717": "[X]",  # BALLOT X
    "\u2718": "[X]",  # HEAVY BALLOT X
    "\u274c": "[X]",  # CROSS MARK (emoji)
    "\u274e": "[X]",  # CROSS MARK (negative squared)
    # Bullets
    "\u2022": "*",  # BULLET
    "\u2023": ">",  # TRIANGULAR BULLET
    "\u2219": "*",  # BULLET OPERATOR
    # Warning/info symbols
    "\u26a0": "[!]",  # WARNING SIGN
    "\u2139": "[i]",  # INFORMATION SOURCE
    # Common emoji that might appear in console output
    "\U0001f4a5": "(!)",  # COLLISION SYMBOL
    "\U0001f6ab": "[X]",  # NO ENTRY SIGN
}

# Pattern to match any of the target glyphs
GLYPH_PATTERN = re.compile("|".join(re.escape(g) for g in GLYPH_REPLACEMENTS.keys()))


def normalize_content(content: str) -> str:
    """
    Replace Unicode glyphs with ASCII equivalents.

    Args:
        content: Source file content.

    Returns:
        Content with glyphs replaced by ASCII equivalents.
    """
    result = content
    for glyph, replacement in GLYPH_REPLACEMENTS.items():
        result = result.replace(glyph, replacement)
    return result


def check_file(filepath: Path) -> tuple[bool, str]:
    """
    Check if a file needs normalization.

    Args:
        filepath: Path to the Python file.

    Returns:
        Tuple of (needs_changes, normalized_content).
    """
    try:
        content = filepath.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        # File is not valid UTF-8; report but don't crash
        return False, f"ERROR: {filepath} is not valid UTF-8: {e}"
    except FileNotFoundError:
        return False, f"ERROR: {filepath} not found"

    normalized = normalize_content(content)
    needs_changes = content != normalized
    return needs_changes, normalized


def fix_file(filepath: Path, normalized_content: str) -> None:
    """
    Write normalized content back to file.

    Args:
        filepath: Path to the Python file.
        normalized_content: The normalized content to write.
    """
    filepath.write_text(normalized_content, encoding="utf-8")


def find_glyphs_in_file(filepath: Path) -> list[tuple[int, str, str]]:
    """
    Find all Unicode glyphs in a file with line numbers.

    Args:
        filepath: Path to the Python file.

    Returns:
        List of (line_number, glyph, replacement) tuples.
    """
    try:
        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError):
        return []

    findings: list[tuple[int, str, str]] = []
    for line_num, line in enumerate(content.splitlines(), start=1):
        for match in GLYPH_PATTERN.finditer(line):
            glyph = match.group()
            replacement = GLYPH_REPLACEMENTS.get(glyph, "?")
            findings.append((line_num, glyph, replacement))
    return findings


def parse_ci_workflows(repo_root: Path) -> set[str]:
    """
    Parse CI workflow files to find Python scripts invoked in CI.

    Args:
        repo_root: Repository root directory.

    Returns:
        Set of script paths relative to repo root.
    """
    workflows_dir = repo_root / ".github" / "workflows"
    if not workflows_dir.exists():
        return set()

    scripts: set[str] = set()
    # Pattern to match: python scripts/... or PYTHONUTF8=1 python scripts/...
    script_pattern = re.compile(r"python\s+(\S*scripts/\S+\.py)")

    for workflow_file in workflows_dir.glob("*.yml"):
        try:
            content = workflow_file.read_text(encoding="utf-8")
            for match in script_pattern.finditer(content):
                script_path = match.group(1)
                # Clean up path (remove any leading env vars like PYTHONPATH=src)
                if "=" in script_path:
                    continue  # Skip malformed matches
                scripts.add(script_path)
        except (UnicodeDecodeError, FileNotFoundError):
            continue

    return scripts


def parse_test_subprocess_invocations(repo_root: Path) -> set[str]:
    """
    Parse test files to find scripts invoked via subprocess.

    Args:
        repo_root: Repository root directory.

    Returns:
        Set of script paths relative to repo root.
    """
    tests_dir = repo_root / "tests"
    if not tests_dir.exists():
        return set()

    scripts: set[str] = set()
    # Pattern to match subprocess calls with scripts/
    # e.g., subprocess.run(["python", "scripts/..."], ...)
    # or [sys.executable, "scripts/..."]
    script_pattern = re.compile(r'["\']scripts/[^"\']+\.py["\']')

    for test_file in tests_dir.rglob("*.py"):
        try:
            content = test_file.read_text(encoding="utf-8")
            for match in script_pattern.finditer(content):
                script_path = match.group().strip("\"'")
                scripts.add(script_path)
        except (UnicodeDecodeError, FileNotFoundError):
            continue

    return scripts


def get_critical_scripts(repo_root: Path) -> set[str]:
    """
    Get the set of critical-path scripts.

    Critical scripts are those invoked by:
    - CI workflows
    - Tests via subprocess

    Args:
        repo_root: Repository root directory.

    Returns:
        Set of script paths relative to repo root.
    """
    ci_scripts = parse_ci_workflows(repo_root)
    test_scripts = parse_test_subprocess_invocations(repo_root)
    return ci_scripts | test_scripts


def main(argv: list[str] | None = None) -> int:
    """
    Main entry point.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 for success, 1 for check failures).
    """
    parser = argparse.ArgumentParser(
        description="Normalize Unicode console glyphs to ASCII equivalents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Python files to process",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check mode: exit non-zero if changes would be made",
    )
    parser.add_argument(
        "--files-from",
        type=str,
        help="Read file list from a text file (one path per line)",
    )
    parser.add_argument(
        "--list-critical",
        action="store_true",
        help="List critical-path scripts and exit",
    )
    parser.add_argument(
        "--repo-root",
        type=str,
        help="Repository root directory (default: auto-detect)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Exclude specific files (can be used multiple times)",
    )

    args = parser.parse_args(argv)

    # Determine repo root
    if args.repo_root:
        repo_root = Path(args.repo_root)
    else:
        # Auto-detect from script location
        repo_root = Path(__file__).resolve().parent.parent.parent

    # Handle --list-critical
    if args.list_critical:
        critical = sorted(get_critical_scripts(repo_root))
        for script in critical:
            # Use ASCII-safe output
            print(script)
        return 0

    # Gather files to process
    files: list[Path] = []

    if args.files_from:
        files_from_path = Path(args.files_from)
        if not files_from_path.exists():
            print(f"ERROR: --files-from path not found: {args.files_from}")
            return 1
        for line in files_from_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                files.append(repo_root / line)

    for file_arg in args.files:
        file_path = Path(file_arg)
        # Resolve relative paths against repo root
        if not file_path.is_absolute():
            file_path = repo_root / file_path
        files.append(file_path)

    if not files:
        print("ERROR: No files specified. Use --files-from or provide file paths.")
        print("       Use --list-critical to see critical-path scripts.")
        return 1

    # Build exclusion set
    excluded: set[str] = set()
    for excl in args.exclude:
        # Normalize exclusion paths
        excl_path = Path(excl)
        if not excl_path.is_absolute():
            excl_path = repo_root / excl_path
        excluded.add(str(excl_path.resolve()))

    # Filter out excluded files
    if excluded:
        files = [f for f in files if str(f.resolve()) not in excluded]

    # Process files
    changes_needed = 0
    errors = 0
    processed = 0

    for filepath in files:
        if not filepath.exists():
            print(f"WARNING: File not found: {filepath}")
            errors += 1
            continue

        needs_changes, result = check_file(filepath)

        if result.startswith("ERROR:"):
            print(result)
            errors += 1
            continue

        processed += 1

        if needs_changes:
            changes_needed += 1
            # Get details for reporting
            findings = find_glyphs_in_file(filepath)
            rel_path = (
                filepath.relative_to(repo_root) if filepath.is_relative_to(repo_root) else filepath
            )

            if args.check:
                print(f"WOULD CHANGE: {rel_path}")
                for line_num, glyph, replacement in findings:
                    # Print ASCII-safe representation
                    glyph_code = f"U+{ord(glyph):04X}"
                    print(f"  Line {line_num}: {glyph_code} -> {replacement}")
            else:
                print(f"FIXED: {rel_path}")
                for line_num, glyph, replacement in findings:
                    glyph_code = f"U+{ord(glyph):04X}"
                    print(f"  Line {line_num}: {glyph_code} -> {replacement}")
                fix_file(filepath, result)

    # Summary (ASCII-safe)
    print("")
    print(f"Processed: {processed} files")
    print(f"Changes: {changes_needed} files")
    if errors:
        print(f"Errors: {errors} files")

    if args.check and changes_needed > 0:
        print("")
        print("CHECK FAILED: Unicode glyphs found in critical scripts.")
        print("Run without --check to fix automatically.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
