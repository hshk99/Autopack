#!/usr/bin/env python3
"""Autopack Supervisor - Orchestrates parallel execution of multiple runs.

This script is a thin CLI wrapper around the supervisor library module.
See src/autopack/supervisor/ for the actual implementation.

BUILD-179: This script now uses the library module for all functionality.
The library module enforces parallelism policy gates via IntentionAnchorV2.

Usage:
    # Run 3 workers concurrently with Postgres (requires anchor):
    python scripts/autopack_supervisor.py \\
        --run-ids run1,run2,run3 \\
        --anchor-path anchor.json \\
        --workers 3 \\
        --database-url postgresql://autopack:autopack@localhost:5432/autopack

    # Run 2 workers with per-run SQLite databases:
    python scripts/autopack_supervisor.py \\
        --run-ids run1,run2 \\
        --anchor-path anchor.json \\
        --workers 2 \\
        --per-run-sqlite

    # List existing worktrees:
    python scripts/autopack_supervisor.py --list-worktrees

    # Cleanup all worktrees:
    python scripts/autopack_supervisor.py --cleanup

IMPORTANT: Parallel execution now REQUIRES an IntentionAnchorV2 with
parallelism_isolation.allowed=true. This is a BUILD-179 safety gate.
"""

import argparse
import sys
import logging
from pathlib import Path
from typing import List

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.supervisor import (
    SupervisorError,
    run_parallel_supervised,
)
from autopack.supervisor.api import list_worktrees, cleanup_worktrees
from autopack.autonomy.parallelism_gate import ParallelismPolicyViolation

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Autopack Supervisor - Orchestrate parallel run execution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Execution mode
    parser.add_argument(
        "--run-ids",
        type=str,
        help="Comma-separated list of run IDs to execute (e.g., 'run1,run2,run3')"
    )

    parser.add_argument(
        "--anchor-path",
        type=Path,
        help="Path to IntentionAnchorV2 JSON (REQUIRED for parallel execution)"
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Maximum number of concurrent workers (default: 3)"
    )

    # Database configuration
    parser.add_argument(
        "--database-url",
        type=str,
        help="Database URL (default: from settings). Postgres recommended for parallel runs."
    )

    parser.add_argument(
        "--per-run-sqlite",
        action="store_true",
        help="Use per-run SQLite databases instead of shared Postgres (limits aggregation)"
    )

    # Directories
    parser.add_argument(
        "--source-repo",
        type=Path,
        default=Path.cwd(),
        help="Source git repository path (default: current directory)"
    )

    parser.add_argument(
        "--autonomous-runs-dir",
        type=str,
        help="Override autonomous runs directory (default: from settings)"
    )

    # Utility commands
    parser.add_argument(
        "--list-worktrees",
        action="store_true",
        help="List all existing worktrees and exit"
    )

    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove all managed worktrees and exit"
    )

    args = parser.parse_args()

    # Handle utility commands
    if args.list_worktrees:
        worktrees = list_worktrees(args.source_repo)
        print(f"\nFound {len(worktrees)} worktrees:")
        for wt in worktrees:
            path = wt.get("path", "unknown")
            branch = wt.get("branch", "(detached)")
            commit = wt.get("commit", "unknown")[:8]
            print(f"  {path}")
            print(f"    Branch: {branch}")
            print(f"    Commit: {commit}")
        return 0

    if args.cleanup:
        wt_base = None
        if args.autonomous_runs_dir:
            wt_base = Path(args.autonomous_runs_dir) / "workspaces"
        count = cleanup_worktrees(args.source_repo, wt_base)
        print(f"Cleaned up {count} worktrees")
        return 0

    # Execution mode requires run-ids and anchor-path
    if not args.run_ids:
        parser.error("--run-ids required for execution mode (or use --list-worktrees / --cleanup)")

    if not args.anchor_path:
        parser.error(
            "--anchor-path required for parallel execution.\n"
            "Parallel runs require an IntentionAnchorV2 with parallelism_isolation.allowed=true."
        )

    if not args.anchor_path.exists():
        logger.error(f"Anchor file not found: {args.anchor_path}")
        return 1

    run_ids: List[str] = [rid.strip() for rid in args.run_ids.split(",")]

    try:
        # Use library API with policy gate enforcement
        result = run_parallel_supervised(
            run_ids=run_ids,
            anchor_path=args.anchor_path,
            source_repo=args.source_repo,
            database_url=args.database_url,
            autonomous_runs_dir=args.autonomous_runs_dir,
            per_run_sqlite=args.per_run_sqlite,
            max_workers=args.workers,
        )

        # Print summary
        print("\n" + "="*80)
        print("EXECUTION SUMMARY")
        print("="*80)

        for run_id, run_result in result.run_results.items():
            status = "SUCCESS" if run_result.success else "FAILED"
            print(f"{run_id}: {status}")
            if run_result.error:
                print(f"  Error: {run_result.error}")
            if run_result.workspace:
                print(f"  Workspace: {run_result.workspace}")

        print(f"\nTotal: {result.successful_runs}/{result.total_runs} successful")

        return 0 if result.all_successful else 1

    except ParallelismPolicyViolation as e:
        logger.error(f"PARALLELISM BLOCKED: {e}")
        logger.error(
            "Parallel execution requires an IntentionAnchorV2 "
            "with parallelism_isolation.allowed=true."
        )
        return 1

    except SupervisorError as e:
        logger.error(f"Supervisor error: {e}")
        return 1

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return 1

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
