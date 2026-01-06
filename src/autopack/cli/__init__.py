"""Autopack CLI package.

Historically this repo had a single module at `autopack/cli.py`.
Some tests and integrations expect a package layout (`autopack.cli.commands.*`).

This package preserves the original `python -m autopack.cli ...` behavior while
also providing a `commands/` subpackage for click-based CLIs used in tests.

BUILD-179 adds unified CLI commands:
    - autopack gaps scan ...
    - autopack plan propose ...
    - autopack autopilot run ...
    - autopack autopilot supervise ... (parallel runs)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import click

# Import command groups for registration
from .commands.gaps import gaps_group
from .commands.planning import plan_group
from .commands.autopilot import autopilot_group


def get_repo_root() -> Path:
    """Get repository root directory."""
    return Path(__file__).resolve().parent.parent.parent


# ============================================================================
# Click-based unified CLI (BUILD-179)
# ============================================================================

@click.group()
@click.version_option(package_name="autopack", prog_name="autopack")
def cli() -> None:
    """Autopack CLI - Autonomous execution with governance gates.

    Run `autopack <command> --help` for command-specific help.
    """
    pass


# Register command groups
cli.add_command(gaps_group)
cli.add_command(plan_group)
cli.add_command(autopilot_group)


# ============================================================================
# Legacy argparse CLI (preserved for backwards compatibility)
# ============================================================================


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
    """Main CLI entry point.

    Routes to Click CLI for BUILD-179 commands (gaps, plan, autopilot),
    or falls back to legacy argparse CLI for tidy commands.

    Usage:
        python -m autopack.cli gaps scan --run-id ... --project-id ...
        python -m autopack.cli plan propose --run-id ... --project-id ...
        python -m autopack.cli autopilot run --run-id ... --project-id ...
        python -m autopack.cli tidy-consolidate [--dry-run]
        python -m autopack.cli tidy-cleanup [--dry-run]
    """
    # Determine which CLI to use based on first argument
    args_list = argv if argv is not None else sys.argv[1:]

    # BUILD-179 commands use Click CLI
    click_commands = {"gaps", "plan", "autopilot", "--help", "-h", "--version"}

    if args_list and args_list[0] in click_commands:
        # Use Click CLI
        return cli(args_list, standalone_mode=False) or 0

    # Legacy argparse CLI for tidy commands
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
        # Show unified help
        print("Autopack CLI - Autonomous execution with governance gates")
        print()
        print("BUILD-179 commands (use --help for details):")
        print("  gaps scan         Scan workspace for gaps")
        print("  plan propose      Propose plan from anchor and gap report")
        print("  autopilot run     Run autopilot session (single run)")
        print()
        print("Legacy tidy commands:")
        print("  tidy-consolidate  Consolidate documentation files")
        print("  tidy-cleanup      Run full workspace cleanup")
        print()
        print("Use 'autopack <command> --help' for command-specific help.")
        return 1

    if args.command == "tidy-consolidate":
        return run_tidy_consolidation(args)
    if args.command == "tidy-cleanup":
        return run_tidy_cleanup(args)

    print(f"Unknown command: {args.command}")
    return 1
