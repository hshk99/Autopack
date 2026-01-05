"""Autopack CLI package.

Historically this repo had a single module at `autopack/cli.py`.
Some tests and integrations expect a package layout (`autopack.cli.commands.*`).

This package preserves the original `python -m autopack.cli ...` behavior while
also providing a `commands/` subpackage for click-based CLIs used in tests.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def get_repo_root() -> Path:
    """Get repository root directory."""
    return Path(__file__).resolve().parent.parent.parent


def run_tidy_consolidation(args: argparse.Namespace) -> int:
    """Run documentation consolidation."""
    repo_root = get_repo_root()
    script = repo_root / "scripts" / "tidy" / "consolidate_docs_v2.py"

    if not script.exists():
        print(f"❌ Script not found: {script}")
        return 1

    cmd: list[str] = ["python", str(script)]

    if getattr(args, "dry_run", False):
        cmd.append("--dry-run")

    directory = getattr(args, "directory", None)
    if directory:
        dir_script = repo_root / "scripts" / "tidy" / "consolidate_docs_directory.py"
        if dir_script.exists():
            cmd = ["python", str(dir_script), "--directory", directory]
            if getattr(args, "dry_run", False):
                cmd.append("--dry-run")
        else:
            print(f"❌ Directory-specific script not found: {dir_script}")
            return 1

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=repo_root, check=False)
    return result.returncode


def run_tidy_cleanup(args: argparse.Namespace) -> int:
    """Run full workspace cleanup."""
    repo_root = get_repo_root()
    script = repo_root / "scripts" / "tidy" / "corrective_cleanup_v2.py"

    if not script.exists():
        print(f"❌ Script not found: {script}")
        return 1

    cmd: list[str] = ["python", str(script)]
    if getattr(args, "dry_run", False):
        cmd.append("--dry-run")
    else:
        cmd.append("--execute")

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=repo_root, check=False)
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Autopack CLI - Run Autopack tasks from command line"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    consolidate_parser = subparsers.add_parser(
        "tidy-consolidate",
        help="Consolidate documentation files",
    )
    consolidate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without executing",
    )
    consolidate_parser.add_argument(
        "--directory",
        help="Consolidate specific directory only (e.g., archive/research)",
    )

    cleanup_parser = subparsers.add_parser(
        "tidy-cleanup",
        help="Run full workspace cleanup",
    )
    cleanup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without executing",
    )

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "tidy-consolidate":
        return run_tidy_consolidation(args)
    if args.command == "tidy-cleanup":
        return run_tidy_cleanup(args)

    print(f"Unknown command: {args.command}")
    return 1
