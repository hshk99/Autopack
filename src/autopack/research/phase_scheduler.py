"""Phase scheduler for research pipeline with dependency-aware scheduling.

This module provides dependency-aware scheduling for research phases with:
- Explicit phase dependency declaration
- Topological sorting of phases
- Resource-aware scheduling with priority levels
- Concurrent execution optimization
- Scheduler metrics and monitoring
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class PhasePriority(Enum):
    """Priority levels for research phases."""

    CRITICAL = 1  # Must complete before other phases
    HIGH = 2  # Should complete early to enable others
    NORMAL = 3  # Standard priority
    LOW = 4  # Can be deferred if resources limited


class PhaseStatus(Enum):
    """Status of a scheduled phase."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PhaseTask:
    """Represents a research phase task with dependencies and metadata."""

    phase_id: str
    phase_name: str
    task_func: Callable
    priority: PhasePriority = PhasePriority.NORMAL
    dependencies: list[str] = field(default_factory=list)
    estimated_duration_seconds: float = 10.0
    resource_requirement: float = 1.0  # 0-1 scale for resource usage
    timeout_seconds: Optional[float] = None
    retryable: bool = True
    max_retries: int = 1

    @property
    def has_dependencies(self) -> bool:
        """Check if phase has dependencies."""
        return len(self.dependencies) > 0


@dataclass
class PhaseScheduleMetrics:
    """Metrics for phase scheduling and execution."""

    total_phases: int = 0
    completed_phases: int = 0
    failed_phases: int = 0
    skipped_phases: int = 0
    total_execution_time: float = 0.0
    sequential_baseline_time: float = 0.0  # Sum of all durations
    parallel_speedup: float = 1.0  # Actual time / Sequential baseline
    resource_utilization: float = 0.0
    phase_durations: dict[str, float] = field(default_factory=dict)
    phase_start_times: dict[str, datetime] = field(default_factory=dict)
    phase_end_times: dict[str, datetime] = field(default_factory=dict)
    phase_dependencies_resolved: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "total_phases": self.total_phases,
            "completed_phases": self.completed_phases,
            "failed_phases": self.failed_phases,
            "skipped_phases": self.skipped_phases,
            "total_execution_time": self.total_execution_time,
            "sequential_baseline_time": self.sequential_baseline_time,
            "parallel_speedup": self.parallel_speedup,
            "resource_utilization": self.resource_utilization,
            "phase_durations": self.phase_durations,
        }


class DependencyGraph:
    """Manages phase dependencies and topological sorting."""

    def __init__(self):
        """Initialize dependency graph."""
        self.graph: dict[str, set[str]] = {}  # phase_id -> set of dependent phase_ids
        self.reverse_graph: dict[str, set[str]] = {}  # phase_id -> set of prerequisite phase_ids

    def add_phase(self, phase_id: str) -> None:
        """Add phase to graph.

        Args:
            phase_id: Unique phase identifier
        """
        if phase_id not in self.graph:
            self.graph[phase_id] = set()
            self.reverse_graph[phase_id] = set()

    def add_dependency(self, phase_id: str, depends_on: str) -> None:
        """Add dependency: phase_id depends on depends_on.

        Args:
            phase_id: Phase that depends on another
            depends_on: Phase that must complete first

        Raises:
            ValueError: If dependency creates a cycle
        """
        self.add_phase(phase_id)
        self.add_phase(depends_on)

        # Check for cycle before adding
        if self._would_create_cycle(phase_id, depends_on):
            raise ValueError(f"Dependency {phase_id} -> {depends_on} would create a cycle")

        self.reverse_graph[phase_id].add(depends_on)
        self.graph[depends_on].add(phase_id)

    def _would_create_cycle(self, from_phase: str, to_phase: str) -> bool:
        """Check if adding a dependency would create a cycle.

        Args:
            from_phase: Source phase
            to_phase: Target phase

        Returns:
            True if cycle would be created
        """
        # DFS from to_phase to see if we can reach from_phase
        visited = set()
        stack = [to_phase]

        while stack:
            current = stack.pop()
            if current == from_phase:
                return True
            if current in visited:
                continue
            visited.add(current)
            stack.extend(self.reverse_graph.get(current, set()))

        return False

    def get_ready_phases(self, completed: set[str]) -> set[str]:
        """Get phases that are ready to execute (dependencies met).

        Args:
            completed: Set of completed phase IDs

        Returns:
            Set of phase IDs ready for execution
        """
        ready = set()
        for phase_id, dependencies in self.reverse_graph.items():
            if phase_id not in completed and dependencies.issubset(completed):
                ready.add(phase_id)
        return ready

    def topological_sort(self) -> list[str]:
        """Topologically sort phases based on dependencies.

        Returns:
            List of phase IDs in execution order
        """
        visited = set()
        temp_visited = set()
        result = []

        def dfs(node: str) -> None:
            if node in visited:
                return
            if node in temp_visited:
                raise ValueError(f"Cycle detected involving {node}")

            temp_visited.add(node)

            # Visit dependencies first (prerequisites)
            for dep in self.reverse_graph.get(node, set()):
                dfs(dep)

            temp_visited.remove(node)
            visited.add(node)
            result.append(node)

        # Visit all nodes
        for node in self.graph:
            if node not in visited:
                dfs(node)

        return result


class ResourceManager:
    """Manages resource allocation for concurrent phase execution."""

    def __init__(self, max_concurrent_tasks: int = 3, max_total_resources: float = 1.0):
        """Initialize resource manager.

        Args:
            max_concurrent_tasks: Maximum concurrent phases
            max_total_resources: Maximum total resource usage (0-1 scale)
        """
        self.max_concurrent_tasks = max_concurrent_tasks
        self.max_total_resources = max_total_resources
        self.active_tasks: dict[str, float] = {}  # phase_id -> resource_requirement
        self.semaphore = asyncio.Semaphore(max_concurrent_tasks)

    def can_allocate(self, phase_id: str, resource_requirement: float) -> bool:
        """Check if resources can be allocated for phase.

        Args:
            phase_id: Phase identifier
            resource_requirement: Resource requirement (0-1)

        Returns:
            True if resources available
        """
        # Check if at task limit
        if len(self.active_tasks) >= self.max_concurrent_tasks:
            return False

        # Check if total resource usage would exceed limit
        current_usage = sum(self.active_tasks.values())
        return current_usage + resource_requirement <= self.max_total_resources

    async def acquire(self, phase_id: str, resource_requirement: float) -> None:
        """Acquire resources for phase.

        Args:
            phase_id: Phase identifier
            resource_requirement: Resource requirement (0-1)
        """
        await self.semaphore.acquire()
        self.active_tasks[phase_id] = resource_requirement
        logger.debug(
            f"Acquired resources for {phase_id}: {resource_requirement:.2f} "
            f"(total: {self.get_total_utilization():.2f})"
        )

    def release(self, phase_id: str) -> None:
        """Release resources for phase.

        Args:
            phase_id: Phase identifier
        """
        if phase_id in self.active_tasks:
            del self.active_tasks[phase_id]
        self.semaphore.release()
        logger.debug(
            f"Released resources for {phase_id} (total: {self.get_total_utilization():.2f})"
        )

    def get_total_utilization(self) -> float:
        """Get current total resource utilization.

        Returns:
            Current resource usage (0-1)
        """
        return sum(self.active_tasks.values())

    def get_available_slots(self) -> int:
        """Get number of available execution slots.

        Returns:
            Number of slots available for concurrent tasks
        """
        return self.max_concurrent_tasks - len(self.active_tasks)


class PhaseScheduler:
    """Scheduler for research phases with dependency-aware execution.

    Coordinates parallel execution of research phases while respecting
    dependencies, resource constraints, and priority levels.
    """

    def __init__(
        self,
        max_concurrent_tasks: int = 3,
        max_total_resources: float = 1.0,
    ):
        """Initialize phase scheduler.

        Args:
            max_concurrent_tasks: Maximum concurrent phases
            max_total_resources: Maximum total resource usage (0-1 scale)
        """
        self.phases: dict[str, PhaseTask] = {}
        self.dependency_graph = DependencyGraph()
        self.resource_manager = ResourceManager(max_concurrent_tasks, max_total_resources)
        self.metrics = PhaseScheduleMetrics()
        self._phase_results: dict[str, Any] = {}
        self._phase_status: dict[str, PhaseStatus] = {}

    def register_phase(self, phase: PhaseTask) -> None:
        """Register a phase with the scheduler.

        Args:
            phase: PhaseTask to register

        Raises:
            ValueError: If phase ID already registered
        """
        if phase.phase_id in self.phases:
            raise ValueError(f"Phase {phase.phase_id} already registered")

        self.phases[phase.phase_id] = phase
        self.dependency_graph.add_phase(phase.phase_id)
        self._phase_status[phase.phase_id] = PhaseStatus.PENDING
        self.metrics.total_phases += 1

        # Register dependencies
        for dep_id in phase.dependencies:
            self.dependency_graph.add_dependency(phase.phase_id, dep_id)

        logger.debug(f"Registered phase: {phase.phase_name} ({phase.phase_id})")

    def get_execution_order(self) -> list[str]:
        """Get optimal execution order based on dependencies and priorities.

        Returns:
            List of phase IDs in execution order
        """
        # Get topological sort
        topo_order = self.dependency_graph.topological_sort()

        # Sort by priority within independent groups
        # We'll group phases by their "depth" in dependency tree
        depth_map = self._calculate_phase_depths()

        def phase_sort_key(phase_id: str) -> tuple[int, int, float]:
            # Sort by: depth (dependencies first), priority, then estimated duration
            phase = self.phases[phase_id]
            return (
                depth_map.get(phase_id, 0),
                phase.priority.value,
                -phase.estimated_duration_seconds,  # Longer tasks first
            )

        return sorted(topo_order, key=phase_sort_key)

    def _calculate_phase_depths(self) -> dict[str, int]:
        """Calculate dependency depth for each phase.

        Phases with no dependencies have depth 0, phases depending on them have depth 1, etc.

        Returns:
            Mapping of phase_id to depth
        """
        depths: dict[str, int] = {}

        def get_depth(phase_id: str) -> int:
            if phase_id in depths:
                return depths[phase_id]

            dependencies = self.dependency_graph.reverse_graph.get(phase_id, set())
            if not dependencies:
                depths[phase_id] = 0
            else:
                max_dep_depth = max(get_depth(dep) for dep in dependencies)
                depths[phase_id] = max_dep_depth + 1

            return depths[phase_id]

        for phase_id in self.phases:
            get_depth(phase_id)

        return depths

    async def schedule_and_execute(
        self,
        skip_phases: Optional[set[str]] = None,
        sequential: bool = False,
    ) -> dict[str, Any]:
        """Schedule and execute all registered phases.

        Args:
            skip_phases: Set of phase IDs to skip
            sequential: If True, execute phases sequentially (for debugging/testing)

        Returns:
            Dictionary with execution results and metrics
        """
        skip_phases = skip_phases or set()
        start_time = datetime.now()
        completed: set[str] = set()
        failed: set[str] = set()
        tasks: dict[str, asyncio.Task] = {}

        # Calculate sequential baseline (sum of all durations)
        for phase_id, phase in self.phases.items():
            if phase_id not in skip_phases:
                self.metrics.sequential_baseline_time += phase.estimated_duration_seconds

        try:
            if sequential:
                # Execute sequentially
                execution_order = self.get_execution_order()
                for phase_id in execution_order:
                    if phase_id in skip_phases:
                        self._phase_status[phase_id] = PhaseStatus.SKIPPED
                        self.metrics.skipped_phases += 1
                        continue

                    result = await self._execute_phase(phase_id)
                    if result.get("success", False):
                        completed.add(phase_id)
                    else:
                        failed.add(phase_id)
            else:
                # Execute with dependency awareness and parallel execution
                while len(completed) + len(failed) + len(skip_phases) < len(self.phases):
                    # Get phases ready to execute
                    ready = self.dependency_graph.get_ready_phases(completed)
                    ready = ready - skip_phases - set(tasks.keys()) - failed

                    if not ready and not tasks:
                        # No phases ready and no tasks running
                        if len(completed) + len(failed) + len(skip_phases) < len(self.phases):
                            logger.warning("No ready phases and no running tasks - deadlock?")
                        break

                    # Sort ready phases by priority and resource efficiency
                    ready_sorted = self._sort_ready_phases(ready)

                    # Start as many ready phases as resources allow
                    for phase_id in ready_sorted:
                        phase = self.phases[phase_id]

                        if self.resource_manager.can_allocate(phase_id, phase.resource_requirement):
                            task = asyncio.create_task(self._execute_phase(phase_id))
                            tasks[phase_id] = task
                        else:
                            logger.debug(
                                f"Insufficient resources to start {phase_id}, "
                                f"current utilization: {self.resource_manager.get_total_utilization():.2f}"
                            )

                    if not tasks:
                        # No new tasks started, wait a bit for existing tasks
                        await asyncio.sleep(0.1)
                        continue

                    # Wait for at least one task to complete
                    done, pending = await asyncio.wait(
                        tasks.values(),
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    # Process completed tasks
                    for task in done:
                        phase_id = next(pid for pid, t in tasks.items() if t is task)
                        del tasks[phase_id]

                        if task.exception():
                            logger.error(f"Phase {phase_id} failed: {task.exception()}")
                            failed.add(phase_id)
                        else:
                            result = task.result()
                            if result.get("success", False):
                                completed.add(phase_id)
                            else:
                                failed.add(phase_id)

                    # Mark skipped phases
                    for phase_id in skip_phases:
                        if (
                            phase_id not in self._phase_status
                            or self._phase_status[phase_id] != PhaseStatus.SKIPPED
                        ):
                            self._phase_status[phase_id] = PhaseStatus.SKIPPED
                            self.metrics.skipped_phases += 1

        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
            # Cancel all pending tasks
            for task in tasks.values():
                if not task.done():
                    task.cancel()

        # Calculate final metrics
        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()

        self.metrics.total_execution_time = total_time
        self.metrics.completed_phases = len(completed)
        self.metrics.failed_phases = len(failed)
        self.metrics.resource_utilization = self.metrics.sequential_baseline_time / max(
            total_time, 1.0
        )

        if self.metrics.sequential_baseline_time > 0:
            self.metrics.parallel_speedup = self.metrics.sequential_baseline_time / max(
                total_time, 0.001
            )

        return {
            "success": len(failed) == 0,
            "completed_phases": list(completed),
            "failed_phases": list(failed),
            "skipped_phases": list(skip_phases),
            "total_execution_time": total_time,
            "metrics": self.metrics.to_dict(),
            "phase_results": self._phase_results,
        }

    def _sort_ready_phases(self, ready: set[str]) -> list[str]:
        """Sort ready phases by priority and resource efficiency.

        Args:
            ready: Set of ready phase IDs

        Returns:
            Sorted list of phase IDs
        """

        def sort_key(phase_id: str) -> tuple[int, float]:
            phase = self.phases[phase_id]
            # Sort by: priority (lower is better), then by resource efficiency (duration/resources)
            efficiency = phase.estimated_duration_seconds / max(phase.resource_requirement, 0.1)
            return (phase.priority.value, -efficiency)

        return sorted(ready, key=sort_key)

    async def _execute_phase(self, phase_id: str) -> dict[str, Any]:
        """Execute a single phase with error handling and resource management.

        Args:
            phase_id: Phase ID to execute

        Returns:
            Execution result with success status
        """
        phase = self.phases[phase_id]
        start_time = datetime.now()

        # Check budget before execution
        if not self._check_budget_before_phase(phase):
            self._phase_status[phase_id] = PhaseStatus.SKIPPED
            self.metrics.skipped_phases += 1
            logger.info(f"Phase {phase_id} skipped due to budget constraints")
            return {"success": False, "phase_id": phase_id, "reason": "budget_exhausted"}

        # Acquire resources
        await self.resource_manager.acquire(phase_id, phase.resource_requirement)

        self._phase_status[phase_id] = PhaseStatus.RUNNING
        self.metrics.phase_start_times[phase_id] = start_time

        try:
            logger.info(f"Starting phase: {phase.phase_name} ({phase_id})")

            # Execute with timeout
            if phase.timeout_seconds:
                result = await asyncio.wait_for(
                    phase.task_func(),
                    timeout=phase.timeout_seconds,
                )
            else:
                result = await phase.task_func()

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            self._phase_status[phase_id] = PhaseStatus.COMPLETED
            self.metrics.phase_durations[phase_id] = duration
            self.metrics.phase_end_times[phase_id] = end_time
            self._phase_results[phase_id] = result

            logger.info(f"Completed phase: {phase.phase_name} ({phase_id}) in {duration:.2f}s")

            return {
                "success": True,
                "phase_id": phase_id,
                "duration": duration,
                "result": result,
            }

        except asyncio.TimeoutError:
            self._phase_status[phase_id] = PhaseStatus.FAILED
            error_msg = f"Phase {phase_id} timed out after {phase.timeout_seconds}s"
            logger.error(error_msg)
            self._phase_results[phase_id] = {"error": "timeout", "message": error_msg}
            return {"success": False, "phase_id": phase_id, "reason": "timeout"}

        except Exception as e:
            self._phase_status[phase_id] = PhaseStatus.FAILED
            error_msg = f"Phase {phase_id} failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self._phase_results[phase_id] = {"error": str(e)}
            return {"success": False, "phase_id": phase_id, "reason": "execution_error"}

        finally:
            self.resource_manager.release(phase_id)

    def _check_budget_before_phase(self, phase: PhaseTask) -> bool:
        """Check if budget allows phase execution.

        This is a placeholder - subclasses or callers can override.

        Args:
            phase: PhaseTask to check

        Returns:
            True if phase can execute
        """
        # Default: always allow execution
        return True

    def get_phase_status(self, phase_id: str) -> Optional[PhaseStatus]:
        """Get status of a phase.

        Args:
            phase_id: Phase ID

        Returns:
            PhaseStatus or None if not found
        """
        return self._phase_status.get(phase_id)

    def get_phase_result(self, phase_id: str) -> Optional[Any]:
        """Get result of a phase.

        Args:
            phase_id: Phase ID

        Returns:
            Phase result or None if not found
        """
        return self._phase_results.get(phase_id)

    def get_metrics(self) -> PhaseScheduleMetrics:
        """Get scheduler metrics.

        Returns:
            PhaseScheduleMetrics instance
        """
        return self.metrics

    def reset(self) -> None:
        """Reset scheduler state for new execution."""
        self.phases.clear()
        self.dependency_graph = DependencyGraph()
        self._phase_results.clear()
        self._phase_status.clear()
        self.metrics = PhaseScheduleMetrics()
        logger.debug("Phase scheduler reset")
