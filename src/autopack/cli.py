#!/usr/bin/env python3
"""Autopack CLI - Command-line interface for Autopack tasks

Usage:
    python -m autopack.cli tidy-consolidate [--dry-run] [--directory DIR]
    python -m autopack.cli tidy-cleanup [--dry-run]
"""

import argparse
import subprocess
import sys
from pathlib import Path


def get_repo_root():
    """Get repository root directory"""
    return Path(__file__).parent.parent.parent


def run_tidy_consolidation(args):
    """Run documentation consolidation"""
    repo_root = get_repo_root()
    script = repo_root / "scripts" / "tidy" / "consolidate_docs_v2.py"

    if not script.exists():
        print(f"❌ Script not found: {script}")
        return 1

    cmd = ["python", str(script)]

    if args.dry_run:
        cmd.append("--dry-run")

    if args.directory:
        # Use directory-specific script
        dir_script = repo_root / "scripts" / "tidy" / "consolidate_docs_directory.py"
        if dir_script.exists():
            cmd = ["python", str(dir_script), "--directory", args.directory]
            if args.dry_run:
                cmd.append("--dry-run")
        else:
            print(f"❌ Directory-specific script not found: {dir_script}")
            return 1

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=repo_root)
    return result.returncode


def run_tidy_cleanup(args):
    """Run full workspace cleanup"""
    repo_root = get_repo_root()
    script = repo_root / "scripts" / "tidy" / "corrective_cleanup_v2.py"

    if not script.exists():
        print(f"❌ Script not found: {script}")
        return 1

    cmd = ["python", str(script)]

    if args.dry_run:
        cmd.append("--dry-run")
    else:
        cmd.append("--execute")

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=repo_root)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Autopack CLI - Run Autopack tasks from command line"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # tidy-consolidate command
    consolidate_parser = subparsers.add_parser(
        "tidy-consolidate",
        help="Consolidate documentation files"
    )
    consolidate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without executing"
    )
    consolidate_parser.add_argument(
        "--directory",
        help="Consolidate specific directory only (e.g., archive/research)"
    )

    # tidy-cleanup command
    cleanup_parser = subparsers.add_parser(
        "tidy-cleanup",
        help="Run full workspace cleanup"
    )
    cleanup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without executing"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "tidy-consolidate":
        return run_tidy_consolidation(args)
    elif args.command == "tidy-cleanup":
        return run_tidy_cleanup(args)
    else:
        print(f"Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
