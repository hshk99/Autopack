#!/usr/bin/env python3
"""
Standalone Script Organizer - Organize scattered scripts in Autopack

This is a convenience wrapper around the script_organizer module.

Usage:
    # Preview what will be organized
    python scripts/organize_scripts.py

    # Execute the organization
    python scripts/organize_scripts.py --execute
"""

import sys
from pathlib import Path

# Add tidy module to path
sys.path.insert(0, str(Path(__file__).parent / "tidy"))

from script_organizer import ScriptOrganizer


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Organize scattered scripts in Autopack repository",
        epilog="""
This script will organize:
  - Root scripts (*.py, *.sh, *.bat) → scripts/archive/root_scripts/
  - examples/ → scripts/examples/
  - tasks/ (*.yaml, *.yml) → archive/tasks/
  - patches/ (*.patch, *.diff) → archive/patches/

Excluded (will not be moved):
  - setup.py, manage.py, conftest.py (special files)
  - scripts/ (already organized)
  - src/ (source code)
  - tests/ (test suites)
  - config/ (configuration)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the organization (default is dry-run preview)"
    )

    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent

    organizer = ScriptOrganizer(
        repo_root=repo_root,
        dry_run=not args.execute
    )

    count = organizer.organize()

    if count == 0:
        return 0

    if not args.execute:
        print("\n" + "=" * 80)
        print("To execute these changes, run:")
        print("  python scripts/organize_scripts.py --execute")
        print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
