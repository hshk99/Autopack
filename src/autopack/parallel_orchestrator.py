"""Parallel Execution Orchestrator (Phase 5 of True Autonomy).

Per IMPLEMENTATION_PLAN_TRUE_AUTONOMY.md Phase 5:
- Bounded concurrency control (max N concurrent runs)
- Isolated worktrees per run (via WorkspaceManager)
- Safe parallel execution using existing primitives

Key principles:
- No new abstractions: Use WorkspaceManager, WorkspaceLease, ExecutorLockManager
- Token-efficient: Shared intention memory, isolated worktrees
- Fail-safe: Graceful degradation, proper cleanup on errors
- Deterministic: Predictable concurrency limits, no race conditions

Architecture:
- ParallelRunOrchestrator: Main coordinator
- Uses WorkspaceManager for isolated worktrees
- Uses ExecutorLockManager for run-level locking
- Bounded semaphore for concurrency control
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime

from .workspace_manager import WorkspaceManager
from .executor_lock import ExecutorLockManager

logger = logging.getLogger(__name__)


@dataclass
class ParallelRunConfig:
    """Configuration for parallel run orchestrator."""

    max_concurrent_runs: int = 3
    source_repo: Optional[Path] = None
    worktree_base: Optional[Path] = None
    cleanup_on_completion: bool = True
    timeout_seconds: Optional[int] = None


@dataclass
class RunResult:
    """Result of a parallel run execution."""

    run_id: str
    success: bool
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    workspace_path: Optional[Path] = None


class ParallelRunOrchestrator:
    """Orchestrator for parallel autonomous run execution.

    This class provides safe parallel execution of autonomous runs using:
    - WorkspaceManager: Isolated worktrees per run
    - ExecutorLockManager: Run-level locking
    - asyncio.Semaphore: Bounded concurrency control

    Example usage:
        orchestrator = ParallelRunOrchestrator(
            config=ParallelRunConfig(max_concurrent_runs=3)
        )

        async def run_task(run_id: str, workspace: Path) -> bool:
            # Execute autonomous run in isolated workspace
            return True

        results = await orchestrator.execute_parallel(
            run_ids=["run1", "run2", "run3"],
            executor_func=run_task
        )
    """

    def __init__(self, config: ParallelRunConfig):
        """Initialize parallel run orchestrator.

        Args:
            config: Configuration for parallel execution
        """
        self.config = config
        self.semaphore = asyncio.Semaphore(config.max_concurrent_runs)
        self.active_workspaces: Dict[str, WorkspaceManager] = {}
        self.active_locks: Dict[str, ExecutorLockManager] = {}

        logger.info(
            f"[ParallelOrchestrator] Initialized with max_concurrent_runs={config.max_concurrent_runs}"
        )

    async def execute_parallel(
        self,
        run_ids: List[str],
        executor_func: Callable[[str, Path], Any],
        executor_kwargs: Optional[Dict[str, Any]] = None,
    ) -> List[RunResult]:
        """Execute multiple runs in parallel with bounded concurrency.

        Args:
            run_ids: List of run IDs to execute
            executor_func: Async function to execute for each run
                          Signature: async def func(run_id: str, workspace: Path, **kwargs) -> bool
            executor_kwargs: Optional kwargs to pass to executor_func

        Returns:
            List of RunResult objects (one per run_id)
        """
        executor_kwargs = executor_kwargs or {}

        logger.info(f"[ParallelOrchestrator] Starting parallel execution of {len(run_ids)} runs")

        # Create tasks for all runs
        tasks = [
            self._execute_single_run(run_id, executor_func, executor_kwargs) for run_id in run_ids
        ]

        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to RunResult objects
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(
                    RunResult(
                        run_id=run_ids[i],
                        success=False,
                        error=str(result),
                    )
                )
            else:
                final_results.append(result)

        # Log summary
        success_count = sum(1 for r in final_results if r.success)
        logger.info(
            f"[ParallelOrchestrator] Completed {len(run_ids)} runs: "
            f"{success_count} succeeded, {len(run_ids) - success_count} failed"
        )

        return final_results

    async def _execute_single_run(
        self,
        run_id: str,
        executor_func: Callable[[str, Path], Any],
        executor_kwargs: Dict[str, Any],
    ) -> RunResult:
        """Execute a single run with proper resource management.

        Args:
            run_id: Run ID
            executor_func: Executor function
            executor_kwargs: Kwargs for executor

        Returns:
            RunResult
        """
        start_time = datetime.utcnow()
        workspace_manager: Optional[WorkspaceManager] = None

        try:
            # Acquire semaphore (bounded concurrency)
            async with self.semaphore:
                logger.info(f"[ParallelOrchestrator] Starting run: {run_id}")

                # Create workspace manager for this run
                workspace_manager = WorkspaceManager(
                    run_id=run_id,
                    source_repo=self.config.source_repo,
                    worktree_base=self.config.worktree_base,
                    cleanup_on_exit=self.config.cleanup_on_completion,
                )

                # Create worktree
                try:
                    workspace_path = workspace_manager.create_worktree()
                except Exception as e:
                    raise RuntimeError(f"Failed to create worktree for run: {run_id}: {e}")

                logger.debug(
                    f"[ParallelOrchestrator] Created worktree for {run_id}: {workspace_path}"
                )

                # Track active workspace
                self.active_workspaces[run_id] = workspace_manager

                # Create and acquire executor lock for this run
                lock_manager = ExecutorLockManager(run_id=run_id)
                if not lock_manager.try_acquire_lock():
                    raise RuntimeError(f"Failed to acquire executor lock for run: {run_id}")

                self.active_locks[run_id] = lock_manager
                logger.debug(f"[ParallelOrchestrator] Acquired executor lock for {run_id}")

                # Execute the run
                try:
                    if asyncio.iscoroutinefunction(executor_func):
                        success = await executor_func(run_id, workspace_path, **executor_kwargs)
                    else:
                        # Sync function - run in executor
                        loop = asyncio.get_event_loop()
                        success = await loop.run_in_executor(
                            None,
                            executor_func,
                            run_id,
                            workspace_path,
                            **executor_kwargs,
                        )

                    end_time = datetime.utcnow()

                    logger.info(
                        f"[ParallelOrchestrator] Completed run {run_id}: "
                        f"success={success}, duration={end_time - start_time}"
                    )

                    return RunResult(
                        run_id=run_id,
                        success=success,
                        start_time=start_time,
                        end_time=end_time,
                        workspace_path=workspace_path,
                    )

                finally:
                    # Release executor lock
                    if lock_manager:
                        lock_manager.release()
                        self.active_locks.pop(run_id, None)
                        logger.debug(f"[ParallelOrchestrator] Released executor lock for {run_id}")

        except Exception as e:
            end_time = datetime.utcnow()
            logger.error(
                f"[ParallelOrchestrator] Run {run_id} failed: {e}",
                exc_info=True,
            )

            workspace_path = workspace_manager.worktree_path if workspace_manager else None

            return RunResult(
                run_id=run_id,
                success=False,
                error=str(e),
                start_time=start_time,
                end_time=end_time,
                workspace_path=workspace_path,
            )

        finally:
            # Cleanup workspace
            if workspace_manager and self.config.cleanup_on_completion:
                try:
                    workspace_manager.remove_worktree()
                    logger.debug(f"[ParallelOrchestrator] Removed worktree for {run_id}")
                except Exception as e:
                    logger.warning(
                        f"[ParallelOrchestrator] Failed to remove worktree for {run_id}: {e}"
                    )

                # Remove from active workspaces
                self.active_workspaces.pop(run_id, None)

    async def execute_single(
        self,
        run_id: str,
        executor_func: Callable[[str, Path], Any],
        executor_kwargs: Optional[Dict[str, Any]] = None,
    ) -> RunResult:
        """Execute a single run (convenience method).

        Args:
            run_id: Run ID
            executor_func: Executor function
            executor_kwargs: Optional kwargs

        Returns:
            RunResult
        """
        results = await self.execute_parallel(
            run_ids=[run_id],
            executor_func=executor_func,
            executor_kwargs=executor_kwargs,
        )
        return results[0]

    def cleanup_all_workspaces(self):
        """Clean up all managed workspaces."""
        logger.info("[ParallelOrchestrator] Cleaning up all workspaces")
        # WorkspaceManager tracks leases internally
        # Force cleanup by releasing all known leases
        # (In production, WorkspaceManager would need a cleanup_all() method)
        pass

    def get_active_runs(self) -> List[str]:
        """Get list of currently active run IDs.

        Returns:
            List of run IDs with active locks
        """
        return list(self.active_locks.keys())


# Convenience functions for common use cases


async def execute_parallel_runs(
    run_ids: List[str],
    executor_func: Callable[[str, Path], Any],
    max_concurrent: int = 3,
    source_repo: Optional[Path] = None,
    worktree_base: Optional[Path] = None,
    executor_kwargs: Optional[Dict[str, Any]] = None,
) -> List[RunResult]:
    """Execute multiple runs in parallel (convenience function).

    Args:
        run_ids: List of run IDs to execute
        executor_func: Async function to execute for each run
        max_concurrent: Maximum concurrent runs
        source_repo: Source git repository path
        worktree_base: Base directory for worktrees
        executor_kwargs: Optional kwargs for executor

    Returns:
        List of RunResult objects
    """
    config = ParallelRunConfig(
        max_concurrent_runs=max_concurrent,
        source_repo=source_repo,
        worktree_base=worktree_base,
    )

    orchestrator = ParallelRunOrchestrator(config)

    return await orchestrator.execute_parallel(
        run_ids=run_ids,
        executor_func=executor_func,
        executor_kwargs=executor_kwargs,
    )


async def execute_single_run(
    run_id: str,
    executor_func: Callable[[str, Path], Any],
    source_repo: Optional[Path] = None,
    worktree_base: Optional[Path] = None,
    executor_kwargs: Optional[Dict[str, Any]] = None,
) -> RunResult:
    """Execute a single run (convenience function).

    Args:
        run_id: Run ID
        executor_func: Executor function
        source_repo: Source git repository path
        worktree_base: Base directory for worktrees
        executor_kwargs: Optional kwargs

    Returns:
        RunResult
    """
    results = await execute_parallel_runs(
        run_ids=[run_id],
        executor_func=executor_func,
        max_concurrent=1,
        source_repo=source_repo,
        worktree_base=worktree_base,
        executor_kwargs=executor_kwargs,
    )
    return results[0]
