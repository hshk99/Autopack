#!/usr/bin/env python3
"""Smart pre-flight testing script for CI-efficient local validation.

Analyzes git changes and runs only affected tests, providing fast feedback
before pushing to CI. Categorizes changes by CI impact and estimates runtime.

Usage:
    python scripts/preflight_smart.py              # Auto-detect and run targeted tests
    python scripts/preflight_smart.py --dry-run    # Show what would run without running
    python scripts/preflight_smart.py --full       # Force run full test suite
    python scripts/preflight_smart.py --category A # Verify changes match expected category

Part of PR-INFRA-2: CI-efficient development workflow.
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Set, Tuple

# CI Impact Categories (from COMPREHENSIVE_SCAN_STRATEGY.md)
CATEGORY_PATTERNS = {
    "A": {  # Docs only (~5-10 min CI)
        "paths": ["docs/**", "*.md"],
        "description": "Docs only - backend tests skipped",
        "estimated_ci_time": "5-10 min",
    },
    "B": {  # Frontend only (~10-15 min CI)
        "paths": ["*.tsx", "*.ts", "*.css", "vite.config.ts", "package.json", "package-lock.json"],
        "description": "Frontend only - backend tests skipped",
        "estimated_ci_time": "10-15 min",
    },
    "C": {  # Backend non-critical (~15-25 min CI)
        "paths": [
            "src/autopack/research/**",
            "src/autopack/storage_optimizer/**",
            "src/autopack/diagnostics/**",
        ],
        "description": "Backend non-critical - partial test suite",
        "estimated_ci_time": "15-25 min",
    },
    "D": {  # Backend core (~30-45 min CI, or ~15-20 min with pytest-xdist)
        "paths": [
            "src/autopack/autonomous_executor.py",
            "src/autopack/llm_service.py",
            "src/autopack/anthropic_clients.py",
            "src/autopack/executor/**",
            "src/autopack/llm/**",
            "src/autopack/governed_apply.py",
            "src/autopack/memory/**",
        ],
        "description": "Backend core - full test suite",
        "estimated_ci_time": "30-45 min (15-20 min with pytest-xdist after PR-INFRA-1)",
    },
    "E": {  # Infrastructure (variable CI time)
        "paths": ["scripts/**", ".github/workflows/**", "pyproject.toml", "requirements*.txt"],
        "description": "Infrastructure/tooling - variable CI time",
        "estimated_ci_time": "15-45 min",
    },
}


def run_command(cmd: List[str], capture=True) -> Tuple[bool, str]:
    """Run a shell command and return (success, output)."""
    try:
        if capture:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            return result.returncode == 0, result.stdout + result.stderr
        else:
            result = subprocess.run(cmd, check=False)
            return result.returncode == 0, ""
    except Exception as e:
        return False, str(e)


def get_changed_files() -> List[str]:
    """Get list of changed files compared to main branch."""
    # Try to get changes from main
    success, output = run_command(["git", "diff", "main...HEAD", "--name-only"])

    if not success or not output.strip():
        # Fallback: get uncommitted changes
        success, output = run_command(["git", "diff", "HEAD", "--name-only"])

    if not success:
        print("⚠️  Warning: Could not detect git changes. Using all modified files.")
        success, output = run_command(["git", "status", "--porcelain"])
        # Parse porcelain format (e.g., " M file.py", "A  newfile.py")
        files = [line[3:] for line in output.split("\n") if line.strip()]
        return files

    return [f for f in output.split("\n") if f.strip()]


def categorize_changes(files: List[str]) -> Tuple[str, List[str]]:
    """Determine CI impact category based on changed files.

    Returns (category, matching_patterns).
    Categories are checked in priority order: A (docs) → B (frontend) → C/D/E (backend).
    """
    if not files:
        return "NONE", []

    # Convert to Path objects for pattern matching
    file_paths = [Path(f) for f in files]

    # Check each category
    category_matches = {cat: [] for cat in "ABCDE"}

    for file_path in file_paths:
        file_str = str(file_path).replace("\\", "/")  # Normalize for Windows

        # Check each category's patterns
        for category, config in CATEGORY_PATTERNS.items():
            for pattern in config["paths"]:
                # Simple pattern matching (supports ** and *)
                if match_pattern(file_str, pattern):
                    category_matches[category].append(file_str)
                    break  # File matched this category, don't check other patterns

    # Determine primary category (may be mixed)
    if category_matches["A"] and not any(category_matches[c] for c in "BCDE"):
        return "A", category_matches["A"]
    if category_matches["B"] and not any(category_matches[c] for c in "ACDE"):
        return "B", category_matches["B"]
    if category_matches["E"] and not any(category_matches[c] for c in "ABCD"):
        return "E", category_matches["E"]
    if category_matches["C"]:
        return "C", category_matches["C"]
    if category_matches["D"]:
        return "D", category_matches["D"]

    # Mixed categories or other files
    all_matches = sum(category_matches.values(), [])
    if all_matches:
        # Determine highest impact category
        if category_matches["D"]:
            return "D", category_matches["D"]
        if category_matches["C"]:
            return "C", category_matches["C"]
        return "MIXED", all_matches

    return "OTHER", files


def match_pattern(file_path: str, pattern: str) -> bool:
    """Simple glob-like pattern matching."""
    import fnmatch

    # Handle ** (recursive wildcard)
    if "**" in pattern:
        # Convert ** to * for fnmatch
        pattern_parts = pattern.split("**")
        # Check if file path contains all pattern parts in order
        current_pos = 0
        for part in pattern_parts:
            if part:
                idx = file_path.find(part.strip("/"), current_pos)
                if idx == -1:
                    return False
                current_pos = idx + len(part)
        return True

    # Regular fnmatch for * and ? wildcards
    return fnmatch.fnmatch(file_path, pattern)


def map_files_to_tests(files: List[str]) -> Set[str]:
    """Map changed source files to their corresponding test files."""
    test_files = set()

    for file_path in files:
        path = Path(file_path)

        # Direct test file
        if path.parts[0] == "tests":
            test_files.add(file_path)
            continue

        # Map src file to test file
        if path.parts[0] == "src" and len(path.parts) > 2:
            # src/autopack/foo.py → tests/autopack/test_foo.py
            rel_path = Path(*path.parts[2:])  # Remove src/autopack

            if rel_path.stem != "__init__":
                # Try exact test file match
                test_file = Path("tests") / rel_path.parent / f"test_{rel_path.stem}.py"
                if test_file.exists():
                    test_files.add(str(test_file))

                # Also check for directory-level tests
                test_dir = Path("tests") / rel_path.parent
                if test_dir.exists():
                    # Add all test files in the corresponding test directory
                    for test in test_dir.glob("test_*.py"):
                        test_files.add(str(test))

    return test_files


def get_pytest_command(category: str, test_files: Set[str], full: bool = False) -> List[str]:
    """Generate pytest command based on category and test files."""
    if full:
        return ["pytest", "tests/", "-v"]

    if category == "A":
        # Docs only - run doc tests
        return ["pytest", "tests/docs/", "-v"]

    if category == "B":
        # Frontend only - no pytest (frontend has its own npm test)
        return []

    if test_files:
        # Run specific test files
        return ["pytest"] + list(test_files) + ["-v"]

    if category in ("C", "D"):
        # Backend changes - run relevant test marker
        if category == "C":
            return ["pytest", "tests/", "-m", "research", "-v"]
        else:
            # Category D - run core tests (excluding research/aspirational)
            return [
                "pytest",
                "tests/",
                "-m",
                "not research and not aspirational and not legacy_contract",
                "-v",
            ]

    # Default: run all tests
    return ["pytest", "tests/", "-v"]


def print_analysis(category: str, files: List[str], test_files: Set[str], pytest_cmd: List[str]):
    """Print analysis of changes and testing strategy."""
    print("=" * 70)
    print("[ANALYSIS] SMART PRE-FLIGHT ANALYSIS")
    print("=" * 70)
    print()

    print(f"Changed files: {len(files)}")
    for f in files[:10]:  # Show first 10
        print(f"   - {f}")
    if len(files) > 10:
        print(f"   ... and {len(files) - 10} more")
    print()

    print(f"CI Impact Category: {category}")
    if category in CATEGORY_PATTERNS:
        config = CATEGORY_PATTERNS[category]
        print(f"   {config['description']}")
        print(f"   Estimated CI time: {config['estimated_ci_time']}")
    print()

    if test_files:
        print(f"Targeted tests: {len(test_files)} test files")
        for t in list(test_files)[:5]:
            print(f"   - {t}")
        if len(test_files) > 5:
            print(f"   ... and {len(test_files) - 5} more")
    else:
        print("Targeted tests: (determined by category)")
    print()

    if pytest_cmd:
        print(f"Pytest command: {' '.join(pytest_cmd)}")
    elif category == "B":
        print("Frontend tests: Run 'npm test' instead")
    else:
        print("No tests to run")
    print()

    # Warnings
    if category == "D":
        print("[WARNING] Core backend changes detected")
        print("   Full CI test suite will run (~30-45 min, or ~15-20 min with pytest-xdist)")
        print()
    elif category == "MIXED":
        print("[WARNING] Mixed category changes detected")
        print("   CI will run multiple test suites")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Smart pre-flight testing for CI-efficient development"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show analysis without running tests"
    )
    parser.add_argument("--full", action="store_true", help="Force run full test suite")
    parser.add_argument(
        "--category",
        choices=["A", "B", "C", "D", "E"],
        help="Verify changes match expected CI impact category",
    )

    args = parser.parse_args()

    # Get changed files
    print("Analyzing git changes...")
    files = get_changed_files()

    if not files:
        print("[OK] No changes detected. Nothing to test.")
        return 0

    # Categorize changes
    category, matching_files = categorize_changes(files)

    # Verify expected category if specified
    if args.category and category != args.category:
        print(f"[ERROR] Changes are category {category}, but expected {args.category}")
        print("   This may trigger unexpected CI jobs.")
        return 1

    # Map to test files
    test_files = map_files_to_tests(matching_files if matching_files else files)

    # Generate pytest command
    pytest_cmd = get_pytest_command(category, test_files, args.full)

    # Print analysis
    print_analysis(category, files, test_files, pytest_cmd)

    # Run tests if not dry-run
    if args.dry_run:
        print("[DRY RUN] No tests executed")
        return 0

    if not pytest_cmd:
        if category == "B":
            print("[TIP] Run 'npm test' for frontend tests")
        else:
            print("[OK] No pytest tests needed for these changes")
        return 0

    print("=" * 70)
    print("[RUNNING] TESTS...")
    print("=" * 70)
    print()

    # Run pytest
    success, _ = run_command(pytest_cmd, capture=False)

    print()
    if success:
        print("[PASSED] Pre-flight tests PASSED")
        print("   Safe to push to CI")
        return 0
    else:
        print("[FAILED] Pre-flight tests FAILED")
        print("   Fix issues before pushing to CI")
        return 1


if __name__ == "__main__":
    sys.exit(main())
