#!/usr/bin/env python3
"""CI script to detect documentation drift back to backend server.

BUILD-146 P12 API Consolidation - Phase 4:
Prevents re-introduction of backend server references in documentation.

This script checks that documentation does not reference the deprecated
backend server entrypoint. It's meant to run in CI to catch drift.

Exit codes:
    0: No drift detected
    1: Drift detected (backend server references found)
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple


# Patterns to detect (these indicate drift back to backend server)
FORBIDDEN_PATTERNS = [
    # Direct backend server uvicorn commands
    (r"uvicorn\s+backend\.main:app", "Direct backend.main:app uvicorn command"),
    (r"uvicorn\s+src\.backend\.main:app", "Direct src.backend.main:app uvicorn command"),

    # Python module execution of backend main
    (r"python\s+-m\s+backend\.main", "Direct python -m backend.main"),
    (r"python\s+src/backend/main\.py", "Direct python src/backend/main.py"),
    (r"python\s+src\\backend\\main\.py", "Direct python src\\backend\\main.py (Windows)"),

    # Backend server recommendation language
    (r"run\s+the\s+backend\s+server", "Instruction to run backend server"),
    (r"start\s+the\s+backend\s+server", "Instruction to start backend server"),
    (r"use\s+the\s+backend\s+server", "Recommendation to use backend server"),
]

# Files/directories to exclude from checking
EXCLUDED_PATHS = [
    "docs/CANONICAL_API_CONSOLIDATION_PLAN.md",  # Planning doc mentions both servers
    "scripts/check_docs_drift.py",  # This file (self-reference)
    ".git",  # Git metadata
    "__pycache__",  # Python cache
    ".pytest_cache",  # Pytest cache
    "node_modules",  # Node modules
    ".venv",  # Virtual environment
    "venv",  # Virtual environment
]


def should_check_file(file_path: Path) -> bool:
    """Determine if file should be checked for drift."""
    # Check if any excluded path is in the file path
    for excluded in EXCLUDED_PATHS:
        if excluded in str(file_path):
            return False

    # Only check markdown and text documentation files
    return file_path.suffix in [".md", ".txt", ".rst"]


def check_file_for_drift(file_path: Path) -> List[Tuple[int, str, str]]:
    """Check a single file for backend server references.

    Returns:
        List of (line_number, pattern_description, line_content) tuples
    """
    violations = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                # Check each forbidden pattern
                for pattern, description in FORBIDDEN_PATTERNS:
                    if re.search(pattern, line, re.IGNORECASE):
                        violations.append((line_num, description, line.strip()))

    except Exception as e:
        print(f"WARNING: Could not read {file_path}: {e}", file=sys.stderr)

    return violations


def main():
    """Main entry point for drift detection."""
    repo_root = Path(__file__).parent.parent
    print(f"Checking for docs drift in: {repo_root}")
    print(f"Forbidden patterns: {len(FORBIDDEN_PATTERNS)}")
    print()

    # Find all documentation files
    doc_files = []
    for pattern in ["**/*.md", "**/*.txt", "**/*.rst"]:
        doc_files.extend(repo_root.glob(pattern))

    # Filter to files we should check
    files_to_check = [f for f in doc_files if should_check_file(f)]
    print(f"Checking {len(files_to_check)} documentation files...")
    print()

    # Check each file
    total_violations = 0
    files_with_violations = 0

    for file_path in files_to_check:
        violations = check_file_for_drift(file_path)

        if violations:
            files_with_violations += 1
            total_violations += len(violations)

            # Print violations for this file
            rel_path = file_path.relative_to(repo_root)
            print(f"DRIFT DETECTED: {rel_path}")

            for line_num, description, line_content in violations:
                print(f"   Line {line_num}: {description}")
                print(f"   > {line_content}")
                print()

    # Summary
    print("=" * 80)
    if total_violations == 0:
        print("SUCCESS: No documentation drift detected!")
        print()
        print("All documentation correctly references the canonical server:")
        print("  PYTHONPATH=src uvicorn autopack.main:app")
        return 0
    else:
        print(f"FAILURE: Documentation drift detected!")
        print()
        print(f"Found {total_violations} violations in {files_with_violations} files.")
        print()
        print("REQUIRED FIX:")
        print("  Update documentation to reference the canonical server:")
        print("  PYTHONPATH=src uvicorn autopack.main:app")
        print()
        print("  NOT the deprecated backend server:")
        print("  uvicorn backend.main:app  (DEPRECATED)")
        print()
        print("See docs/CANONICAL_API_CONTRACT.md for canonical API documentation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
