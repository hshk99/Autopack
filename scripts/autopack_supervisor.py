#!/usr/bin/env python3
"""Autopack Supervisor - Orchestrates parallel execution of multiple runs (P2.0).

The supervisor enables safe parallel execution of autonomous runs by:
1. Creating isolated git worktrees per run_id
2. Managing workspace leases to prevent concurrent workspace access
3. Enforcing concurrency policies (Postgres requirement)
4. Launching worker processes with proper environment isolation

Safety guarantees:
- Each run gets its own git worktree (no cross-run git contamination)
- Workspace leases prevent concurrent access to same directory
- Per-run ExecutorLockManager prevents duplicate run execution
- Shared artifact root for centralized outputs
- Database concurrency handled via Postgres or per-run SQLite

Usage:
    # Run 3 workers concurrently with Postgres
    python scripts/autopack_supervisor.py \\
        --run-ids run1,run2,run3 \\
        --workers 3 \\
        --database-url postgresql://autopack:autopack@localhost:5432/autopack

    # Run 2 workers with per-run SQLite databases
    python scripts/autopack_supervisor.py \\
        --run-ids run1,run2 \\
        --workers 2 \\
        --per-run-sqlite

    # List existing worktrees
    python scripts/autopack_supervisor.py --list-worktrees

    # Cleanup all worktrees
    python scripts/autopack_supervisor.py --cleanup
"""

import argparse
import sys
import logging
import subprocess
import concurrent.futures
from pathlib import Path
from typing import List, Dict, Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.workspace_manager import WorkspaceManager
from autopack.workspace_lease import WorkspaceLease
from autopack.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


class SupervisorError(Exception):
    """Supervisor-specific errors."""
    pass


class ParallelRunSupervisor:
    """Orchestrates parallel execution of autonomous runs."""

    def __init__(
        self,
        source_repo: Path,
        database_url: str,
        autonomous_runs_dir: Optional[str] = None,
        per_run_sqlite: bool = False
    ):
        """Initialize supervisor.

        Args:
            source_repo: Path to source git repository
            database_url: Database connection string (Postgres or SQLite template)
            autonomous_runs_dir: Override for runs directory (default: from settings)
            per_run_sqlite: Use per-run SQLite databases instead of shared Postgres
        """
        self.source_repo = Path(source_repo).resolve()
        self.database_url = database_url
        self.autonomous_runs_dir = autonomous_runs_dir or settings.autonomous_runs_dir
        self.per_run_sqlite = per_run_sqlite

        # Validate configuration
        self._validate_concurrency_policy()

    def _validate_concurrency_policy(self):
        """Validate concurrency policy (P2.3).

        Raises:
            SupervisorError: If configuration is unsafe for parallel execution
        """
        if self.per_run_sqlite:
            # Per-run SQLite is allowed
            logger.info("[Supervisor] Using per-run SQLite databases")
            return

        # Check if database URL is Postgres
        if not self.database_url.startswith("postgresql://"):
            raise SupervisorError(
                "Parallel runs require Postgres database for safe concurrent writes.\n"
                "Options:\n"
                "  1. Use Postgres: --database-url postgresql://...\n"
                "  2. Use per-run SQLite: --per-run-sqlite (limited dashboard aggregation)"
            )

        logger.info("[Supervisor] Using shared Postgres database")

    def _get_database_url_for_run(self, run_id: str) -> str:
        """Get database URL for a specific run.

        Args:
            run_id: Run identifier

        Returns:
            Database URL for this run
        """
        if self.per_run_sqlite:
            # Create per-run SQLite database
            db_path = Path(self.autonomous_runs_dir) / run_id / f"{run_id}.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{db_path.resolve().as_posix()}"
        else:
            # Shared Postgres database
            return self.database_url

    def execute_run(self, run_id: str, extra_args: List[str] = None) -> Dict:
        """Execute a single run in an isolated worktree.

        Args:
            run_id: Run identifier
            extra_args: Additional arguments to pass to autonomous_executor.py

        Returns:
            Dict with execution result: {run_id, success, exit_code, workspace, error}
        """
        extra_args = extra_args or []

        logger.info(f"[{run_id}] Starting execution")

        try:
            # Create isolated worktree
            workspace_manager = WorkspaceManager(
                run_id=run_id,
                source_repo=self.source_repo,
                cleanup_on_exit=True  # Auto-cleanup on completion
            )

            with workspace_manager as workspace:
                # Acquire workspace lease to prevent concurrent access
                with WorkspaceLease(workspace) as lease:
                    logger.info(f"[{run_id}] Workspace: {workspace}")

                    # Get database URL for this run
                    db_url = self._get_database_url_for_run(run_id)

                    # Build environment for worker
                    env = {
                        **subprocess.os.environ,
                        "DATABASE_URL": db_url,
                        "AUTONOMOUS_RUNS_DIR": str(self.autonomous_runs_dir),
                        "PYTHONUTF8": "1",  # Ensure UTF-8 encoding
                    }

                    # Build command
                    cmd = [
                        sys.executable,
                        str(self.source_repo / "src" / "autopack" / "autonomous_executor.py"),
                        "--run-id", run_id,
                        *extra_args
                    ]

                    logger.info(f"[{run_id}] Executing: {' '.join(cmd)}")

                    # Execute autonomous run
                    result = subprocess.run(
                        cmd,
                        cwd=workspace,
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=None  # No timeout - let run manage its own duration
                    )

                    success = result.returncode == 0

                    if success:
                        logger.info(f"[{run_id}] ✓ Completed successfully")
                    else:
                        logger.error(f"[{run_id}] ✗ Failed with exit code {result.returncode}")
                        logger.error(f"[{run_id}] Stderr: {result.stderr[:500]}")

                    return {
                        "run_id": run_id,
                        "success": success,
                        "exit_code": result.returncode,
                        "workspace": str(workspace),
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "error": None
                    }

        except subprocess.TimeoutExpired as e:
            logger.error(f"[{run_id}] ✗ Timeout")
            return {
                "run_id": run_id,
                "success": False,
                "exit_code": -1,
                "workspace": None,
                "error": "timeout"
            }
        except Exception as e:
            logger.error(f"[{run_id}] ✗ Exception: {e}")
            return {
                "run_id": run_id,
                "success": False,
                "exit_code": -1,
                "workspace": None,
                "error": str(e)
            }

    def execute_parallel(
        self,
        run_ids: List[str],
        max_workers: int = 3,
        extra_args: List[str] = None
    ) -> Dict[str, Dict]:
        """Execute multiple runs in parallel.

        Args:
            run_ids: List of run identifiers to execute
            max_workers: Maximum number of concurrent workers (default: 3)
            extra_args: Additional arguments to pass to each executor

        Returns:
            Dict mapping run_id to execution result
        """
        logger.info(f"[Supervisor] Starting {len(run_ids)} runs with {max_workers} workers")

        results = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all runs
            future_to_run_id = {
                executor.submit(self.execute_run, run_id, extra_args): run_id
                for run_id in run_ids
            }

            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_run_id):
                run_id = future_to_run_id[future]
                try:
                    result = future.result()
                    results[run_id] = result
                except Exception as e:
                    logger.error(f"[{run_id}] Unhandled exception: {e}")
                    results[run_id] = {
                        "run_id": run_id,
                        "success": False,
                        "exit_code": -1,
                        "workspace": None,
                        "error": str(e)
                    }

        # Summary
        successful = sum(1 for r in results.values() if r["success"])
        failed = len(results) - successful

        logger.info(f"[Supervisor] Complete: {successful} successful, {failed} failed")

        return results


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
        worktrees = WorkspaceManager.list_worktrees(args.source_repo)
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
        count = WorkspaceManager.cleanup_all_worktrees(
            repo=args.source_repo,
            worktree_base=Path(args.autonomous_runs_dir or settings.autonomous_runs_dir) / "workspaces"
        )
        print(f"Cleaned up {count} worktrees")
        return 0

    # Execution mode requires run-ids
    if not args.run_ids:
        parser.error("--run-ids required for execution mode (or use --list-worktrees / --cleanup)")

    run_ids = [rid.strip() for rid in args.run_ids.split(",")]

    # Determine database URL
    database_url = args.database_url or settings.database_url

    try:
        # Create supervisor
        supervisor = ParallelRunSupervisor(
            source_repo=args.source_repo,
            database_url=database_url,
            autonomous_runs_dir=args.autonomous_runs_dir,
            per_run_sqlite=args.per_run_sqlite
        )

        # Execute runs in parallel
        results = supervisor.execute_parallel(
            run_ids=run_ids,
            max_workers=args.workers
        )

        # Print summary
        print("\n" + "="*80)
        print("EXECUTION SUMMARY")
        print("="*80)

        for run_id, result in results.items():
            status = "✓ SUCCESS" if result["success"] else "✗ FAILED"
            print(f"{run_id}: {status}")
            if result.get("error"):
                print(f"  Error: {result['error']}")
            if result.get("workspace"):
                print(f"  Workspace: {result['workspace']}")

        # Exit with failure if any run failed
        all_success = all(r["success"] for r in results.values())
        return 0 if all_success else 1

    except SupervisorError as e:
        logger.error(f"Supervisor error: {e}")
        return 1
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
