"""Supervisor library API (BUILD-179).

Provides a thin library façade for the parallel run supervisor, with
explicit parallelism policy enforcement via IntentionAnchorV2.

Key safety feature: parallel execution is ONLY allowed when:
1. An IntentionAnchorV2 is provided with parallelism_isolation.allowed=true
2. The anchor explicitly authorizes the requested parallelism level

This prevents accidental parallel execution without explicit intention.

Usage:
    from autopack.supervisor.api import run_parallel_supervised

    result = run_parallel_supervised(
        run_ids=["run1", "run2", "run3"],
        anchor_path=Path("anchor.json"),  # Must allow parallelism
        max_workers=3,
    )
    print(f"Success: {result.successful_runs}/{result.total_runs}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .models import RunResult
from .parallel_run_supervisor import ParallelRunSupervisor, SupervisorError
from ..autonomy.parallelism_gate import (
    ParallelismPolicyGate,
    ParallelismPolicyViolation,
    load_and_check_parallelism_policy,
)
from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class SupervisorResult:
    """Result of a parallel supervisor execution."""

    run_results: Dict[str, RunResult] = field(default_factory=dict)
    """Map of run_id to individual run results."""

    parallelism_allowed: bool = False
    """Whether parallelism was allowed by policy."""

    anchor_path: Optional[Path] = None
    """Path to the intention anchor used for policy check."""

    @property
    def total_runs(self) -> int:
        """Total number of runs attempted."""
        return len(self.run_results)

    @property
    def successful_runs(self) -> int:
        """Number of successful runs."""
        return sum(1 for r in self.run_results.values() if r.success)

    @property
    def failed_runs(self) -> int:
        """Number of failed runs."""
        return self.total_runs - self.successful_runs

    @property
    def all_successful(self) -> bool:
        """True if all runs completed successfully."""
        return all(r.success for r in self.run_results.values())

    def get_failed_run_ids(self) -> List[str]:
        """Get list of run IDs that failed."""
        return [run_id for run_id, r in self.run_results.items() if not r.success]

    def get_successful_run_ids(self) -> List[str]:
        """Get list of run IDs that succeeded."""
        return [run_id for run_id, r in self.run_results.items() if r.success]


def check_parallelism_allowed(
    anchor_path: Path,
    requested_workers: int,
) -> bool:
    """Check if parallelism is allowed by the intention anchor.

    Args:
        anchor_path: Path to IntentionAnchorV2 JSON file.
        requested_workers: Number of parallel workers requested.

    Returns:
        True if parallelism is allowed.

    Raises:
        ParallelismPolicyViolation: If parallelism is not allowed.
        FileNotFoundError: If anchor file doesn't exist.
    """
    if not anchor_path.exists():
        raise FileNotFoundError(
            f"Intention anchor not found: {anchor_path}. "
            "Parallel execution requires an explicit anchor with "
            "parallelism_isolation.allowed=true."
        )

    # Load and check parallelism policy
    load_and_check_parallelism_policy(
        anchor_path=anchor_path,
        requested_parallelism=requested_workers,
    )

    return True


def run_parallel_supervised(
    *,
    run_ids: List[str],
    anchor_path: Path,
    source_repo: Optional[Path] = None,
    database_url: Optional[str] = None,
    autonomous_runs_dir: Optional[str] = None,
    per_run_sqlite: bool = False,
    max_workers: int = 3,
    extra_args: Optional[List[str]] = None,
) -> SupervisorResult:
    """Run multiple autonomous runs in parallel with policy enforcement.

    This is the primary library API for supervised parallel execution.
    It enforces the parallelism policy from the intention anchor before
    allowing any parallel execution.

    SAFETY: Parallel execution is BLOCKED unless:
    1. anchor_path points to a valid IntentionAnchorV2
    2. The anchor has parallelism_isolation.allowed=true
    3. The requested max_workers doesn't exceed anchor limits

    Args:
        run_ids: List of run identifiers to execute.
        anchor_path: Path to IntentionAnchorV2 JSON (REQUIRED for parallelism).
        source_repo: Path to source git repository (default: cwd).
        database_url: Database connection string (default: from settings).
        autonomous_runs_dir: Override for runs directory (default: from settings).
        per_run_sqlite: Use per-run SQLite databases instead of shared Postgres.
        max_workers: Maximum number of concurrent workers (default: 3).
        extra_args: Additional arguments to pass to each executor.

    Returns:
        SupervisorResult with run outcomes and policy info.

    Raises:
        ParallelismPolicyViolation: If parallelism not allowed by anchor.
        SupervisorError: If supervisor configuration is invalid.
        FileNotFoundError: If anchor file doesn't exist.
    """
    source = (source_repo or Path.cwd()).resolve()
    db_url = database_url or settings.database_url

    # POLICY GATE: Check parallelism is allowed
    logger.info(f"Checking parallelism policy from anchor: {anchor_path}")

    try:
        check_parallelism_allowed(
            anchor_path=anchor_path,
            requested_workers=max_workers,
        )
        parallelism_allowed = True
        logger.info(
            f"Parallelism policy check PASSED: {max_workers} workers allowed"
        )
    except ParallelismPolicyViolation as e:
        logger.error(f"Parallelism policy check FAILED: {e}")
        raise

    # Create supervisor
    supervisor = ParallelRunSupervisor(
        source_repo=source,
        database_url=db_url,
        autonomous_runs_dir=autonomous_runs_dir,
        per_run_sqlite=per_run_sqlite,
    )

    # Execute runs
    raw_results = supervisor.execute_parallel(
        run_ids=run_ids,
        max_workers=max_workers,
        extra_args=extra_args,
    )

    # Convert to typed results
    run_results = {}
    for run_id, raw in raw_results.items():
        run_results[run_id] = RunResult(
            run_id=raw["run_id"],
            success=raw["success"],
            exit_code=raw["exit_code"],
            workspace=Path(raw["workspace"]) if raw.get("workspace") else None,
            stdout=raw.get("stdout", ""),
            stderr=raw.get("stderr", ""),
            error=raw.get("error"),
        )

    return SupervisorResult(
        run_results=run_results,
        parallelism_allowed=parallelism_allowed,
        anchor_path=anchor_path,
    )


def list_worktrees(source_repo: Optional[Path] = None) -> List[Dict]:
    """List all existing worktrees.

    Args:
        source_repo: Path to source git repository (default: cwd).

    Returns:
        List of worktree info dicts.
    """
    source = (source_repo or Path.cwd()).resolve()
    return ParallelRunSupervisor.list_worktrees(source)


def cleanup_worktrees(
    source_repo: Optional[Path] = None,
    worktree_base: Optional[Path] = None,
) -> int:
    """Remove all managed worktrees.

    Args:
        source_repo: Path to source git repository (default: cwd).
        worktree_base: Base directory for worktrees.

    Returns:
        Number of worktrees cleaned up.
    """
    source = (source_repo or Path.cwd()).resolve()

    if worktree_base is None:
        worktree_base = Path(settings.autonomous_runs_dir) / "workspaces"

    return ParallelRunSupervisor.cleanup_all_worktrees(
        repo=source, worktree_base=worktree_base
    )
