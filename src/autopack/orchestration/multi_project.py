"""Multi-Project Parallel Orchestration System.

Enables batch processing and parallel execution of multiple projects with:
- Resource pooling (API calls, memory, disk I/O)
- Multiple execution strategies (parallel, sequential, staged, adaptive)
- Per-project error isolation
- Real-time progress tracking

Architecture:
- MultiProjectOrchestrator: Main coordinator
- ResourceManager: Tracks and enforces resource limits
- ProjectExecutor: Executes single project with resource constraints
- ExecutionStrategy: Controls execution order and parallelism
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from threading import RLock
from typing import Any, Callable, Dict, List, Optional, Set

import psutil

logger = logging.getLogger(__name__)


class ExecutionStrategy(Enum):
    """Execution strategy for multi-project orchestration."""

    PARALLEL = "parallel"  # All projects simultaneously
    SEQUENTIAL = "sequential"  # One at a time (fallback)
    STAGED = "staged"  # All research, then all builds, etc.
    ADAPTIVE = "adaptive"  # Monitor resources and adjust


@dataclass
class MultiProjectConfig:
    """Configuration for multi-project orchestration."""

    # Resource limits
    max_parallel_projects: int = 4
    max_api_calls_per_minute: int = 100
    max_concurrent_memory_mb: int = 2000
    max_disk_io_mbps: float = 50.0
    per_project_timeout_hours: int = 2
    phase_timeout_minutes: int = 30

    # Execution strategy
    execution_strategy: ExecutionStrategy = ExecutionStrategy.PARALLEL
    enable_adaptive_strategy: bool = True

    # Resource tracking
    enable_resource_tracking: bool = True
    resource_check_interval_seconds: float = 5.0

    # Error handling
    fail_fast: bool = False  # Stop on first project failure
    error_isolation: bool = True  # Don't fail batch on project error

    # Monitoring
    enable_progress_tracking: bool = True
    progress_report_interval_seconds: float = 10.0


@dataclass
class ProjectObjective:
    """Represents a single project to process."""

    project_id: str
    objective: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ProjectResult:
    """Result of a project execution."""

    project_id: str
    success: bool
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    phases_completed: int = 0
    phases_failed: int = 0
    api_calls_made: int = 0
    memory_peak_mb: float = 0.0


@dataclass
class ResourceSnapshot:
    """Snapshot of current resource usage."""

    timestamp: datetime
    api_calls_this_minute: int
    memory_usage_mb: float
    disk_io_mbps: float
    active_projects: int
    total_api_calls: int


class ResourceManager:
    """Manages resource constraints across projects."""

    def __init__(self, config: MultiProjectConfig):
        """Initialize resource manager.

        Args:
            config: Configuration with resource limits
        """
        self.config = config
        self._lock = RLock()

        # API call tracking (per minute)
        self._api_call_timestamps: List[datetime] = []
        self._total_api_calls = 0

        # Memory tracking
        self._memory_peak_mb = 0.0
        self._last_memory_check = datetime.utcnow()

        # Disk I/O tracking
        self._last_disk_io_check = datetime.utcnow()
        self._last_disk_io_counters = psutil.disk_io_counters()

        # Active project tracking
        self._active_projects: Set[str] = set()

        logger.info(
            f"[ResourceManager] Initialized with limits: "
            f"api_calls={config.max_api_calls_per_minute}/min, "
            f"memory={config.max_concurrent_memory_mb}MB, "
            f"disk_io={config.max_disk_io_mbps}MB/s"
        )

    def record_api_call(self) -> None:
        """Record an API call timestamp."""
        with self._lock:
            self._api_call_timestamps.append(datetime.utcnow())
            self._total_api_calls += 1

    def check_api_call_limit(self) -> bool:
        """Check if API call limit allows another call.

        Returns:
            True if within limit, False if limit exceeded
        """
        with self._lock:
            # Remove timestamps older than 1 minute
            cutoff = datetime.utcnow() - timedelta(minutes=1)
            self._api_call_timestamps = [ts for ts in self._api_call_timestamps if ts > cutoff]

            current_rate = len(self._api_call_timestamps)
            remaining = self.config.max_api_calls_per_minute - current_rate

            if current_rate >= self.config.max_api_calls_per_minute:
                logger.warning(
                    f"[ResourceManager] API call limit reached: "
                    f"{current_rate}/{self.config.max_api_calls_per_minute}"
                )
                return False

            if remaining < 10:
                logger.debug(
                    f"[ResourceManager] Approaching API limit: "
                    f"{current_rate}/{self.config.max_api_calls_per_minute}"
                )

            return True

    def check_memory_limit(self) -> bool:
        """Check if memory usage is within limits.

        Returns:
            True if within limit, False if limit exceeded
        """
        with self._lock:
            try:
                process = psutil.Process()
                memory_mb = process.memory_info().rss / (1024 * 1024)
                self._memory_peak_mb = max(self._memory_peak_mb, memory_mb)

                if memory_mb > self.config.max_concurrent_memory_mb:
                    logger.warning(
                        f"[ResourceManager] Memory limit exceeded: "
                        f"{memory_mb:.1f}MB/{self.config.max_concurrent_memory_mb}MB"
                    )
                    return False

                if memory_mb > self.config.max_concurrent_memory_mb * 0.8:
                    logger.debug(
                        f"[ResourceManager] Approaching memory limit: "
                        f"{memory_mb:.1f}MB/{self.config.max_concurrent_memory_mb}MB"
                    )

                return True
            except Exception as e:
                logger.warning(f"[ResourceManager] Failed to check memory: {e}")
                return True

    def check_disk_io_limit(self) -> bool:
        """Check if disk I/O is within limits.

        Returns:
            True if within limit, False if limit exceeded
        """
        with self._lock:
            try:
                now = datetime.utcnow()
                current_counters = psutil.disk_io_counters()

                if self._last_disk_io_counters is None or current_counters is None:
                    return True

                time_delta = (now - self._last_disk_io_check).total_seconds()
                if time_delta < 1:
                    return True

                # Calculate bytes written per second
                bytes_written_delta = (
                    current_counters.write_bytes - self._last_disk_io_counters.write_bytes
                )
                mbps = (bytes_written_delta / time_delta) / (1024 * 1024)

                self._last_disk_io_check = now
                self._last_disk_io_counters = current_counters

                if mbps > self.config.max_disk_io_mbps:
                    logger.warning(
                        f"[ResourceManager] Disk I/O limit exceeded: "
                        f"{mbps:.1f}MB/s/{self.config.max_disk_io_mbps}MB/s"
                    )
                    return False

                return True
            except Exception as e:
                logger.warning(f"[ResourceManager] Failed to check disk I/O: {e}")
                return True

    def can_start_project(self, max_active: int) -> bool:
        """Check if a new project can be started.

        Args:
            max_active: Maximum number of active projects allowed

        Returns:
            True if resource limits allow starting a new project
        """
        with self._lock:
            if len(self._active_projects) >= max_active:
                return False

            return (
                self.check_memory_limit()
                and self.check_api_call_limit()
                and self.check_disk_io_limit()
            )

    def register_project(self, project_id: str) -> None:
        """Register a project as active.

        Args:
            project_id: ID of project being started
        """
        with self._lock:
            self._active_projects.add(project_id)
            logger.debug(
                f"[ResourceManager] Registered project {project_id}, "
                f"active={len(self._active_projects)}"
            )

    def unregister_project(self, project_id: str) -> None:
        """Unregister a project as complete.

        Args:
            project_id: ID of project completed
        """
        with self._lock:
            self._active_projects.discard(project_id)
            logger.debug(
                f"[ResourceManager] Unregistered project {project_id}, "
                f"active={len(self._active_projects)}"
            )

    def get_snapshot(self) -> ResourceSnapshot:
        """Get current resource usage snapshot.

        Returns:
            ResourceSnapshot of current resource state
        """
        with self._lock:
            cutoff = datetime.utcnow() - timedelta(minutes=1)
            api_calls_this_minute = len([ts for ts in self._api_call_timestamps if ts > cutoff])

            try:
                process = psutil.Process()
                memory_mb = process.memory_info().rss / (1024 * 1024)
            except Exception:
                memory_mb = 0.0

            return ResourceSnapshot(
                timestamp=datetime.utcnow(),
                api_calls_this_minute=api_calls_this_minute,
                memory_usage_mb=memory_mb,
                disk_io_mbps=0.0,  # Simplified
                active_projects=len(self._active_projects),
                total_api_calls=self._total_api_calls,
            )


class MultiProjectOrchestrator:
    """Orchestrates parallel execution of multiple projects.

    Features:
    - Multiple execution strategies (parallel, sequential, staged, adaptive)
    - Resource pooling with API call, memory, and I/O limits
    - Per-project error isolation
    - Real-time progress tracking
    - Configurable timeouts and resource constraints

    Example usage:
        orchestrator = MultiProjectOrchestrator(
            config=MultiProjectConfig(max_parallel_projects=4)
        )

        async def execute_project(project_id: str, objective: str) -> bool:
            # Execute project autonomously
            return True

        projects = [
            ProjectObjective(project_id="proj1", objective="Build web app"),
            ProjectObjective(project_id="proj2", objective="Build API service"),
        ]

        results = await orchestrator.execute_projects(
            projects=projects,
            executor_func=execute_project
        )
    """

    def __init__(self, config: Optional[MultiProjectConfig] = None):
        """Initialize multi-project orchestrator.

        Args:
            config: Configuration for orchestration (uses defaults if None)
        """
        self.config = config or MultiProjectConfig()
        self.resource_manager = ResourceManager(self.config)

        # Project tracking
        self._projects_completed: List[ProjectResult] = []
        self._projects_failed: List[ProjectResult] = []
        self._projects_active: Dict[str, ProjectResult] = {}
        self._lock = RLock()

        # Execution control
        self._semaphore = asyncio.Semaphore(self.config.max_parallel_projects)
        self._stop_requested = False

        logger.info(
            f"[MultiProjectOrchestrator] Initialized with "
            f"strategy={self.config.execution_strategy.value}, "
            f"max_parallel={self.config.max_parallel_projects}"
        )

    async def execute_projects(
        self,
        projects: List[ProjectObjective],
        executor_func: Callable[[str, str], Any],
        executor_kwargs: Optional[Dict[str, Any]] = None,
    ) -> List[ProjectResult]:
        """Execute multiple projects with resource management.

        Args:
            projects: List of ProjectObjective instances
            executor_func: Async function to execute project
                          Signature: async def func(project_id: str, objective: str, **kwargs) -> bool
            executor_kwargs: Optional kwargs to pass to executor_func

        Returns:
            List of ProjectResult objects (one per project)
        """
        executor_kwargs = executor_kwargs or {}

        logger.info(
            f"[MultiProjectOrchestrator] Starting execution of {len(projects)} projects "
            f"with strategy={self.config.execution_strategy.value}"
        )

        # Reset state
        self._projects_completed.clear()
        self._projects_failed.clear()
        self._projects_active.clear()
        self._stop_requested = False

        # Select strategy and execute
        if self.config.execution_strategy == ExecutionStrategy.PARALLEL:
            results = await self._execute_parallel(projects, executor_func, executor_kwargs)
        elif self.config.execution_strategy == ExecutionStrategy.SEQUENTIAL:
            results = await self._execute_sequential(projects, executor_func, executor_kwargs)
        elif self.config.execution_strategy == ExecutionStrategy.STAGED:
            results = await self._execute_staged(projects, executor_func, executor_kwargs)
        elif self.config.execution_strategy == ExecutionStrategy.ADAPTIVE:
            results = await self._execute_adaptive(projects, executor_func, executor_kwargs)
        else:
            raise ValueError(f"Unknown execution strategy: {self.config.execution_strategy}")

        # Log summary
        success_count = sum(1 for r in results if r.success)
        logger.info(
            f"[MultiProjectOrchestrator] Completed {len(projects)} projects: "
            f"{success_count} succeeded, {len(projects) - success_count} failed"
        )

        return results

    async def _execute_parallel(
        self,
        projects: List[ProjectObjective],
        executor_func: Callable,
        executor_kwargs: Dict[str, Any],
    ) -> List[ProjectResult]:
        """Execute all projects in parallel.

        Args:
            projects: List of projects to execute
            executor_func: Executor function
            executor_kwargs: Kwargs for executor

        Returns:
            List of ProjectResult objects
        """
        logger.info(
            f"[MultiProjectOrchestrator] Executing {len(projects)} projects in parallel "
            f"(max {self.config.max_parallel_projects} concurrent)"
        )

        tasks = [
            self._execute_single_project(proj, executor_func, executor_kwargs) for proj in projects
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to ProjectResult objects
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(
                    ProjectResult(
                        project_id=projects[i].project_id,
                        success=False,
                        error=str(result),
                        start_time=datetime.utcnow(),
                        end_time=datetime.utcnow(),
                    )
                )
            else:
                final_results.append(result)

        return final_results

    async def _execute_sequential(
        self,
        projects: List[ProjectObjective],
        executor_func: Callable,
        executor_kwargs: Dict[str, Any],
    ) -> List[ProjectResult]:
        """Execute projects one at a time.

        Args:
            projects: List of projects to execute
            executor_func: Executor function
            executor_kwargs: Kwargs for executor

        Returns:
            List of ProjectResult objects
        """
        logger.info(f"[MultiProjectOrchestrator] Executing {len(projects)} projects sequentially")

        results = []
        for project in projects:
            if self._stop_requested:
                logger.warning("[MultiProjectOrchestrator] Stopping execution: stop requested")
                break

            result = await self._execute_single_project(project, executor_func, executor_kwargs)
            results.append(result)

            if not result.success and self.config.fail_fast:
                logger.warning(
                    f"[MultiProjectOrchestrator] Stopping execution: "
                    f"project {result.project_id} failed"
                )
                break

        return results

    async def _execute_staged(
        self,
        projects: List[ProjectObjective],
        executor_func: Callable,
        executor_kwargs: Dict[str, Any],
    ) -> List[ProjectResult]:
        """Execute projects in stages (research, build, deploy, etc.).

        Args:
            projects: List of projects to execute
            executor_func: Executor function
            executor_kwargs: Kwargs for executor

        Returns:
            List of ProjectResult objects
        """
        logger.info(f"[MultiProjectOrchestrator] Executing {len(projects)} projects in stages")

        # For now, fall back to parallel execution
        # Full staged implementation would require tracking phases per project
        return await self._execute_parallel(projects, executor_func, executor_kwargs)

    async def _execute_adaptive(
        self,
        projects: List[ProjectObjective],
        executor_func: Callable,
        executor_kwargs: Dict[str, Any],
    ) -> List[ProjectResult]:
        """Execute projects with adaptive parallelism based on resources.

        Starts with limited parallelism and increases as resources allow.

        Args:
            projects: List of projects to execute
            executor_func: Executor function
            executor_kwargs: Kwargs for executor

        Returns:
            List of ProjectResult objects
        """
        logger.info(f"[MultiProjectOrchestrator] Executing {len(projects)} projects adaptively")

        # For now, fall back to parallel execution with resource checks
        # Full adaptive implementation would dynamically adjust concurrency
        return await self._execute_parallel(projects, executor_func, executor_kwargs)

    async def _execute_single_project(
        self,
        project: ProjectObjective,
        executor_func: Callable,
        executor_kwargs: Dict[str, Any],
    ) -> ProjectResult:
        """Execute a single project with resource management.

        Args:
            project: Project to execute
            executor_func: Executor function
            executor_kwargs: Kwargs for executor

        Returns:
            ProjectResult
        """
        start_time = datetime.utcnow()

        try:
            # Wait for semaphore (respects max_parallel_projects)
            async with self._semaphore:
                # Wait for resources to be available
                max_retries = 30
                retry_count = 0
                while not self.resource_manager.can_start_project(
                    self.config.max_parallel_projects
                ):
                    if retry_count >= max_retries:
                        raise RuntimeError(
                            f"Resource limits not satisfied after {max_retries} attempts"
                        )
                    retry_count += 1
                    await asyncio.sleep(self.config.resource_check_interval_seconds)

                # Register project
                self.resource_manager.register_project(project.project_id)

                logger.info(f"[MultiProjectOrchestrator] Starting project: {project.project_id}")

                with self._lock:
                    self._projects_active[project.project_id] = ProjectResult(
                        project_id=project.project_id,
                        success=False,
                        start_time=start_time,
                    )

                # Execute project with timeout
                try:
                    timeout_seconds = self.config.per_project_timeout_hours * 3600
                    success = await asyncio.wait_for(
                        self._call_executor(
                            executor_func,
                            project.project_id,
                            project.objective,
                            executor_kwargs,
                        ),
                        timeout=timeout_seconds,
                    )

                    end_time = datetime.utcnow()
                    duration = (end_time - start_time).total_seconds()

                    result = ProjectResult(
                        project_id=project.project_id,
                        success=success,
                        start_time=start_time,
                        end_time=end_time,
                        duration_seconds=duration,
                    )

                    logger.info(
                        f"[MultiProjectOrchestrator] Completed project {project.project_id}: "
                        f"success={success}, duration={duration:.1f}s"
                    )

                    with self._lock:
                        self._projects_active.pop(project.project_id, None)
                        if success:
                            self._projects_completed.append(result)
                        else:
                            self._projects_failed.append(result)

                    return result

                except asyncio.TimeoutError:
                    end_time = datetime.utcnow()
                    duration = (end_time - start_time).total_seconds()

                    result = ProjectResult(
                        project_id=project.project_id,
                        success=False,
                        error=f"Timeout after {duration:.1f}s "
                        f"(limit: {self.config.per_project_timeout_hours}h)",
                        start_time=start_time,
                        end_time=end_time,
                        duration_seconds=duration,
                    )

                    logger.error(
                        f"[MultiProjectOrchestrator] Project {project.project_id} "
                        f"timeout after {duration:.1f}s"
                    )

                    with self._lock:
                        self._projects_active.pop(project.project_id, None)
                        self._projects_failed.append(result)

                    if not self.config.error_isolation:
                        raise

                    return result

                finally:
                    # Cleanup within semaphore context
                    self.resource_manager.unregister_project(project.project_id)

        except Exception as e:
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()

            result = ProjectResult(
                project_id=project.project_id,
                success=False,
                error=str(e),
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration,
            )

            logger.error(
                f"[MultiProjectOrchestrator] Project {project.project_id} failed: {e}",
                exc_info=True,
            )

            with self._lock:
                self._projects_active.pop(project.project_id, None)
                self._projects_failed.append(result)

            if not self.config.error_isolation:
                raise

            return result

    async def _call_executor(
        self,
        executor_func: Callable,
        project_id: str,
        objective: str,
        executor_kwargs: Dict[str, Any],
    ) -> bool:
        """Call executor function, handling both sync and async.

        Args:
            executor_func: Executor function
            project_id: Project ID
            objective: Project objective
            executor_kwargs: Additional kwargs

        Returns:
            True if execution succeeded
        """
        if asyncio.iscoroutinefunction(executor_func):
            return await executor_func(project_id, objective, **executor_kwargs)
        else:
            # Sync function - run in executor
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                executor_func,
                project_id,
                objective,
                **executor_kwargs,
            )

    def request_stop(self) -> None:
        """Request graceful stop of orchestration."""
        logger.info("[MultiProjectOrchestrator] Stop requested")
        self._stop_requested = True

    def get_progress(self) -> Dict[str, Any]:
        """Get current progress information.

        Returns:
            Dictionary with progress metrics
        """
        with self._lock:
            return {
                "total_projects": (
                    len(self._projects_completed)
                    + len(self._projects_failed)
                    + len(self._projects_active)
                ),
                "completed": len(self._projects_completed),
                "failed": len(self._projects_failed),
                "active": len(self._projects_active),
                "success_rate": (
                    len(self._projects_completed)
                    / (len(self._projects_completed) + len(self._projects_failed))
                    if (len(self._projects_completed) + len(self._projects_failed)) > 0
                    else 0
                ),
                "resources": self.resource_manager.get_snapshot().__dict__,
            }

    def get_results(self) -> Dict[str, List[ProjectResult]]:
        """Get all project results.

        Returns:
            Dictionary with completed and failed results
        """
        with self._lock:
            return {
                "completed": self._projects_completed.copy(),
                "failed": self._projects_failed.copy(),
            }
