"""Parallel run supervisor library module (BUILD-179).

Orchestrates parallel execution of multiple autonomous runs with:
1. Isolated git worktrees per run_id
2. Workspace leases to prevent concurrent workspace access
3. Concurrency policy enforcement (Postgres requirement)
4. Worker process isolation

This is a library module ported from scripts/autopack_supervisor.py.
The script remains as a thin CLI wrapper.

Safety guarantees:
- Each run gets its own git worktree (no cross-run git contamination)
- Workspace leases prevent concurrent access to same directory
- Per-run ExecutorLockManager prevents duplicate run execution
- Shared artifact root for centralized outputs
- Database concurrency handled via Postgres or per-run SQLite
"""

from __future__ import annotations

import concurrent.futures
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from ..workspace_manager import WorkspaceManager
from ..workspace_lease import WorkspaceLease
from ..config import settings

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
        per_run_sqlite: bool = False,
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

    def _validate_concurrency_policy(self) -> None:
        """Validate concurrency policy.

        Raises:
            SupervisorError: If configuration is unsafe for parallel execution
        """
        if self.per_run_sqlite:
            logger.info("[Supervisor] Using per-run SQLite databases")
            return

        # Check if database URL is Postgres
        if not self.database_url.startswith("postgresql://"):
            raise SupervisorError(
                "Parallel runs require Postgres database for safe concurrent writes.\n"
                "Options:\n"
                "  1. Use Postgres: --database-url postgresql://...\n"
                "  2. Use per-run SQLite: --per-run-sqlite (limits dashboard aggregation)"
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
            db_path = Path(self.autonomous_runs_dir) / run_id / f"{run_id}.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{db_path.resolve().as_posix()}"
        else:
            return self.database_url

    def execute_run(self, run_id: str, extra_args: Optional[List[str]] = None) -> Dict:
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
                cleanup_on_exit=True,
            )

            with workspace_manager as workspace:
                # Acquire workspace lease to prevent concurrent access
                with WorkspaceLease(workspace):
                    logger.info(f"[{run_id}] Workspace: {workspace}")

                    # Get database URL for this run
                    db_url = self._get_database_url_for_run(run_id)

                    # Build environment for worker
                    env = {
                        **os.environ,
                        "DATABASE_URL": db_url,
                        "AUTONOMOUS_RUNS_DIR": str(self.autonomous_runs_dir),
                        "PYTHONUTF8": "1",
                    }

                    # Build command - use worktree path for isolation
                    # (not source_repo, which would break Four-Layer isolation)
                    executor_path = Path(workspace) / "src" / "autopack" / "autonomous_executor.py"
                    cmd = [
                        sys.executable,
                        str(executor_path),
                        "--run-id",
                        run_id,
                        *extra_args,
                    ]

                    # Set PYTHONPATH to worktree so imports resolve correctly
                    env["PYTHONPATH"] = str(Path(workspace) / "src")

                    logger.info(f"[{run_id}] Executing: {' '.join(cmd)}")

                    # Execute autonomous run
                    result = subprocess.run(
                        cmd,
                        cwd=workspace,
                        env=env,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=None,
                    )

                    success = result.returncode == 0

                    if success:
                        logger.info(f"[{run_id}] Completed successfully")
                    else:
                        logger.error(f"[{run_id}] Failed with exit code {result.returncode}")
                        logger.error(f"[{run_id}] Stderr: {result.stderr[:500]}")

                    return {
                        "run_id": run_id,
                        "success": success,
                        "exit_code": result.returncode,
                        "workspace": str(workspace),
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "error": None,
                    }

        except subprocess.TimeoutExpired:
            logger.error(f"[{run_id}] Timeout")
            return {
                "run_id": run_id,
                "success": False,
                "exit_code": -1,
                "workspace": None,
                "stdout": "",
                "stderr": "",
                "error": "timeout",
            }
        except Exception as e:
            logger.error(f"[{run_id}] Exception: {e}")
            return {
                "run_id": run_id,
                "success": False,
                "exit_code": -1,
                "workspace": None,
                "stdout": "",
                "stderr": "",
                "error": str(e),
            }

    def execute_parallel(
        self,
        run_ids: List[str],
        max_workers: int = 3,
        extra_args: Optional[List[str]] = None,
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
                executor.submit(self.execute_run, run_id, extra_args): run_id for run_id in run_ids
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
                        "stdout": "",
                        "stderr": "",
                        "error": str(e),
                    }

        successful = sum(1 for r in results.values() if r["success"])
        failed = len(results) - successful

        logger.info(f"[Supervisor] Complete: {successful} successful, {failed} failed")

        return results

    @staticmethod
    def list_worktrees(source_repo: Path) -> List[Dict]:
        """List all existing worktrees.

        Args:
            source_repo: Path to source git repository

        Returns:
            List of worktree info dicts
        """
        return WorkspaceManager.list_worktrees(source_repo)

    @staticmethod
    def cleanup_all_worktrees(repo: Path, worktree_base: Optional[Path] = None) -> int:
        """Remove all managed worktrees.

        Args:
            repo: Path to source git repository
            worktree_base: Base directory for worktrees

        Returns:
            Number of worktrees cleaned up
        """
        if worktree_base is None:
            worktree_base = Path(settings.autonomous_runs_dir) / "workspaces"

        return WorkspaceManager.cleanup_all_worktrees(repo=repo, worktree_base=worktree_base)
