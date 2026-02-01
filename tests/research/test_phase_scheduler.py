"""Tests for research phase scheduler with dependency-aware execution."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from autopack.research.phase_scheduler import (DependencyGraph, PhasePriority,
                                               PhaseScheduler, PhaseStatus,
                                               PhaseTask, ResourceManager)


class TestPhasePriority:
    """Test PhasePriority enum."""

    def test_priority_values(self) -> None:
        """Test priority enum values."""
        assert PhasePriority.CRITICAL.value == 1
        assert PhasePriority.HIGH.value == 2
        assert PhasePriority.NORMAL.value == 3
        assert PhasePriority.LOW.value == 4

    def test_priority_comparison(self) -> None:
        """Test priority comparison."""
        assert PhasePriority.CRITICAL.value < PhasePriority.HIGH.value
        assert PhasePriority.HIGH.value < PhasePriority.NORMAL.value


class TestPhaseTask:
    """Test PhaseTask data class."""

    def test_phase_task_creation(self) -> None:
        """Test creating a phase task."""
        task_func = AsyncMock()
        task = PhaseTask(
            phase_id="test_phase",
            phase_name="Test Phase",
            task_func=task_func,
            priority=PhasePriority.HIGH,
            dependencies=["dep1"],
        )

        assert task.phase_id == "test_phase"
        assert task.phase_name == "Test Phase"
        assert task.priority == PhasePriority.HIGH
        assert task.dependencies == ["dep1"]
        assert task.has_dependencies

    def test_phase_task_no_dependencies(self) -> None:
        """Test phase task without dependencies."""
        task = PhaseTask(
            phase_id="test_phase",
            phase_name="Test Phase",
            task_func=AsyncMock(),
        )

        assert not task.has_dependencies


class TestDependencyGraph:
    """Test dependency graph construction and analysis."""

    def test_add_phase(self) -> None:
        """Test adding phases to graph."""
        graph = DependencyGraph()
        graph.add_phase("phase1")
        graph.add_phase("phase2")

        assert "phase1" in graph.graph
        assert "phase2" in graph.graph

    def test_add_dependency(self) -> None:
        """Test adding dependencies."""
        graph = DependencyGraph()
        graph.add_dependency("phase_a", "phase_b")

        assert "phase_b" in graph.reverse_graph["phase_a"]
        assert "phase_a" in graph.graph["phase_b"]

    def test_cycle_detection(self) -> None:
        """Test that cycles are detected."""
        graph = DependencyGraph()
        graph.add_dependency("phase_a", "phase_b")
        graph.add_dependency("phase_b", "phase_c")

        with pytest.raises(ValueError, match="cycle"):
            graph.add_dependency("phase_c", "phase_a")

    def test_topological_sort(self) -> None:
        """Test topological sorting."""
        graph = DependencyGraph()
        graph.add_dependency("phase_a", "phase_b")
        graph.add_dependency("phase_a", "phase_c")
        graph.add_phase("phase_d")

        order = graph.topological_sort()

        # phase_b and phase_c should come before phase_a
        assert order.index("phase_b") < order.index("phase_a")
        assert order.index("phase_c") < order.index("phase_a")

    def test_get_ready_phases(self) -> None:
        """Test getting ready phases based on completed ones."""
        graph = DependencyGraph()
        graph.add_dependency("phase_a", "phase_b")
        graph.add_dependency("phase_a", "phase_c")
        graph.add_phase("phase_d")

        # Initially, only phases with no dependencies are ready
        ready = graph.get_ready_phases(set())
        assert "phase_b" in ready
        assert "phase_c" in ready
        assert "phase_d" in ready
        assert "phase_a" not in ready

        # After completing phase_b and phase_c, phase_a is ready
        ready = graph.get_ready_phases({"phase_b", "phase_c"})
        assert "phase_a" in ready

    def test_complex_dependency_graph(self) -> None:
        """Test complex dependency graph."""
        graph = DependencyGraph()
        # Create a diamond dependency: D depends on B and C, which depend on A
        graph.add_dependency("phase_b", "phase_a")
        graph.add_dependency("phase_c", "phase_a")
        graph.add_dependency("phase_d", "phase_b")
        graph.add_dependency("phase_d", "phase_c")

        ready = graph.get_ready_phases(set())
        assert "phase_a" in ready
        assert "phase_b" not in ready
        assert "phase_c" not in ready

        ready = graph.get_ready_phases({"phase_a"})
        assert "phase_b" in ready
        assert "phase_c" in ready
        assert "phase_d" not in ready


class TestResourceManager:
    """Test resource manager for concurrent execution."""

    @pytest.mark.asyncio
    async def test_resource_allocation(self) -> None:
        """Test allocating and releasing resources."""
        manager = ResourceManager(max_concurrent_tasks=2, max_total_resources=1.0)

        # Acquire resources
        await manager.acquire("phase1", 0.5)
        assert "phase1" in manager.active_tasks
        assert manager.get_total_utilization() == 0.5

        # Release resources
        manager.release("phase1")
        assert "phase1" not in manager.active_tasks
        assert manager.get_total_utilization() == 0.0

    def test_can_allocate(self) -> None:
        """Test checking if resources are available."""
        manager = ResourceManager(max_concurrent_tasks=2, max_total_resources=1.0)

        # Should be able to allocate first phase
        assert manager.can_allocate("phase1", 0.5)

        # Manually add a task for testing
        manager.active_tasks["phase1"] = 0.5

        # Should be able to allocate second phase
        assert manager.can_allocate("phase2", 0.3)

        # Should not exceed total resources
        assert not manager.can_allocate("phase3", 0.3)

    @pytest.mark.asyncio
    async def test_concurrent_task_limit(self) -> None:
        """Test that concurrent task limit is enforced."""
        manager = ResourceManager(max_concurrent_tasks=1)

        await manager.acquire("phase1", 0.5)
        assert manager.get_available_slots() == 0

        assert not manager.can_allocate("phase2", 0.1)


class TestPhaseScheduler:
    """Test phase scheduler."""

    def test_scheduler_creation(self) -> None:
        """Test creating a scheduler."""
        scheduler = PhaseScheduler(max_concurrent_tasks=3)
        assert scheduler is not None
        assert scheduler.metrics.total_phases == 0

    def test_register_phase(self) -> None:
        """Test registering phases."""
        scheduler = PhaseScheduler()
        task = PhaseTask(
            phase_id="phase1",
            phase_name="Phase 1",
            task_func=AsyncMock(),
        )

        scheduler.register_phase(task)
        assert "phase1" in scheduler.phases
        assert scheduler.metrics.total_phases == 1

    def test_register_phase_duplicate(self) -> None:
        """Test that duplicate phases raise error."""
        scheduler = PhaseScheduler()
        task = PhaseTask(
            phase_id="phase1",
            phase_name="Phase 1",
            task_func=AsyncMock(),
        )

        scheduler.register_phase(task)
        with pytest.raises(ValueError, match="already registered"):
            scheduler.register_phase(task)

    def test_register_phase_with_dependencies(self) -> None:
        """Test registering phases with dependencies."""
        scheduler = PhaseScheduler()

        task1 = PhaseTask(
            phase_id="phase1",
            phase_name="Phase 1",
            task_func=AsyncMock(),
        )

        task2 = PhaseTask(
            phase_id="phase2",
            phase_name="Phase 2",
            task_func=AsyncMock(),
            dependencies=["phase1"],
        )

        scheduler.register_phase(task1)
        scheduler.register_phase(task2)

        assert "phase1" in scheduler.dependency_graph.graph
        assert "phase2" in scheduler.dependency_graph.reverse_graph

    def test_get_execution_order(self) -> None:
        """Test getting execution order."""
        scheduler = PhaseScheduler()

        # Register phases
        scheduler.register_phase(
            PhaseTask(
                phase_id="phase1",
                phase_name="Phase 1",
                task_func=AsyncMock(),
                priority=PhasePriority.NORMAL,
                estimated_duration_seconds=5.0,
            )
        )

        scheduler.register_phase(
            PhaseTask(
                phase_id="phase2",
                phase_name="Phase 2",
                task_func=AsyncMock(),
                priority=PhasePriority.HIGH,
                dependencies=["phase1"],
                estimated_duration_seconds=5.0,
            )
        )

        order = scheduler.get_execution_order()
        assert "phase1" in order
        assert "phase2" in order
        assert order.index("phase1") < order.index("phase2")

    @pytest.mark.asyncio
    async def test_execute_single_phase(self) -> None:
        """Test executing a single phase."""
        scheduler = PhaseScheduler()
        mock_func = AsyncMock(return_value={"result": "success"})

        scheduler.register_phase(
            PhaseTask(
                phase_id="phase1",
                phase_name="Phase 1",
                task_func=mock_func,
            )
        )

        result = await scheduler.schedule_and_execute()

        assert result["success"]
        assert "phase1" in result["completed_phases"]
        mock_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_multiple_independent_phases(self) -> None:
        """Test executing multiple independent phases in parallel."""
        scheduler = PhaseScheduler(max_concurrent_tasks=3)

        mock_func1 = AsyncMock(return_value={"result": "success1"})
        mock_func2 = AsyncMock(return_value={"result": "success2"})
        mock_func3 = AsyncMock(return_value={"result": "success3"})

        scheduler.register_phase(
            PhaseTask(
                phase_id="phase1",
                phase_name="Phase 1",
                task_func=mock_func1,
            )
        )
        scheduler.register_phase(
            PhaseTask(
                phase_id="phase2",
                phase_name="Phase 2",
                task_func=mock_func2,
            )
        )
        scheduler.register_phase(
            PhaseTask(
                phase_id="phase3",
                phase_name="Phase 3",
                task_func=mock_func3,
            )
        )

        result = await scheduler.schedule_and_execute()

        assert result["success"]
        assert len(result["completed_phases"]) == 3

    @pytest.mark.asyncio
    async def test_execute_with_dependencies(self) -> None:
        """Test executing phases with dependencies."""
        scheduler = PhaseScheduler()
        execution_order = []

        async def phase1_func():
            execution_order.append("phase1")
            return {"result": "phase1"}

        async def phase2_func():
            execution_order.append("phase2")
            return {"result": "phase2"}

        scheduler.register_phase(
            PhaseTask(
                phase_id="phase1",
                phase_name="Phase 1",
                task_func=phase1_func,
            )
        )

        scheduler.register_phase(
            PhaseTask(
                phase_id="phase2",
                phase_name="Phase 2",
                task_func=phase2_func,
                dependencies=["phase1"],
            )
        )

        result = await scheduler.schedule_and_execute()

        assert result["success"]
        assert execution_order.index("phase1") < execution_order.index("phase2")

    @pytest.mark.asyncio
    async def test_execute_sequential(self) -> None:
        """Test executing phases sequentially."""
        scheduler = PhaseScheduler()
        execution_times = []

        async def phase1_func():
            execution_times.append(("phase1", "start"))
            await asyncio.sleep(0.01)
            execution_times.append(("phase1", "end"))

        async def phase2_func():
            execution_times.append(("phase2", "start"))
            await asyncio.sleep(0.01)
            execution_times.append(("phase2", "end"))

        scheduler.register_phase(
            PhaseTask(
                phase_id="phase1",
                phase_name="Phase 1",
                task_func=phase1_func,
            )
        )

        scheduler.register_phase(
            PhaseTask(
                phase_id="phase2",
                phase_name="Phase 2",
                task_func=phase2_func,
            )
        )

        result = await scheduler.schedule_and_execute(sequential=True)

        assert result["success"]
        # Verify sequential execution: phase1 must finish before phase2 starts
        phase1_end_idx = next(
            i for i, (p, e) in enumerate(execution_times) if p == "phase1" and e == "end"
        )
        phase2_start_idx = next(
            i for i, (p, e) in enumerate(execution_times) if p == "phase2" and e == "start"
        )
        assert phase1_end_idx < phase2_start_idx

    @pytest.mark.asyncio
    async def test_execute_with_timeout(self) -> None:
        """Test phase execution with timeout."""
        scheduler = PhaseScheduler()

        async def slow_phase():
            await asyncio.sleep(10)  # Longer than timeout

        scheduler.register_phase(
            PhaseTask(
                phase_id="slow_phase",
                phase_name="Slow Phase",
                task_func=slow_phase,
                timeout_seconds=0.01,
            )
        )

        result = await scheduler.schedule_and_execute()

        assert not result["success"]
        assert "slow_phase" in result["failed_phases"]

    @pytest.mark.asyncio
    async def test_skip_phases(self) -> None:
        """Test skipping phases."""
        scheduler = PhaseScheduler()
        mock_func1 = AsyncMock()
        mock_func2 = AsyncMock()

        scheduler.register_phase(
            PhaseTask(
                phase_id="phase1",
                phase_name="Phase 1",
                task_func=mock_func1,
            )
        )

        scheduler.register_phase(
            PhaseTask(
                phase_id="phase2",
                phase_name="Phase 2",
                task_func=mock_func2,
            )
        )

        result = await scheduler.schedule_and_execute(skip_phases={"phase2"})

        assert result["success"]
        assert "phase1" in result["completed_phases"]
        assert "phase2" in result["skipped_phases"]
        mock_func1.assert_called_once()
        mock_func2.assert_not_called()

    def test_get_phase_status(self) -> None:
        """Test getting phase status."""
        scheduler = PhaseScheduler()
        task = PhaseTask(
            phase_id="phase1",
            phase_name="Phase 1",
            task_func=AsyncMock(),
        )

        scheduler.register_phase(task)
        status = scheduler.get_phase_status("phase1")
        assert status == PhaseStatus.PENDING

    def test_metrics(self) -> None:
        """Test scheduler metrics."""
        scheduler = PhaseScheduler()
        task = PhaseTask(
            phase_id="phase1",
            phase_name="Phase 1",
            task_func=AsyncMock(),
            estimated_duration_seconds=5.0,
        )

        scheduler.register_phase(task)
        metrics = scheduler.get_metrics()

        assert metrics.total_phases == 1
        assert metrics.sequential_baseline_time == 0.0  # Not executed yet


class TestPhaseSchedulerIntegration:
    """Integration tests for phase scheduler."""

    @pytest.mark.asyncio
    async def test_research_phases_simulation(self) -> None:
        """Test simulating research phase execution."""
        scheduler = PhaseScheduler(max_concurrent_tasks=3)

        # Simulate research phases
        async def market_research():
            await asyncio.sleep(0.01)
            return {"market_attractiveness": 7.5}

        async def competitive_analysis():
            await asyncio.sleep(0.01)
            return {"competitive_intensity": 6.0}

        async def technical_feasibility():
            await asyncio.sleep(0.015)
            return {"feasibility_score": 8.0}

        # Register phases
        scheduler.register_phase(
            PhaseTask(
                phase_id="market_research",
                phase_name="Market Research",
                task_func=market_research,
                priority=PhasePriority.HIGH,
                estimated_duration_seconds=10.0,
                resource_requirement=0.33,
            )
        )

        scheduler.register_phase(
            PhaseTask(
                phase_id="competitive_analysis",
                phase_name="Competitive Analysis",
                task_func=competitive_analysis,
                priority=PhasePriority.HIGH,
                estimated_duration_seconds=10.0,
                resource_requirement=0.33,
            )
        )

        scheduler.register_phase(
            PhaseTask(
                phase_id="technical_feasibility",
                phase_name="Technical Feasibility",
                task_func=technical_feasibility,
                priority=PhasePriority.NORMAL,
                estimated_duration_seconds=12.0,
                resource_requirement=0.33,
            )
        )

        # Execute
        result = await scheduler.schedule_and_execute()

        assert result["success"]
        assert len(result["completed_phases"]) == 3
        assert result["metrics"]["parallel_speedup"] > 1.0

    @pytest.mark.asyncio
    async def test_parallel_vs_sequential_execution(self) -> None:
        """Test that parallel execution is faster than sequential."""
        # Create two schedulers - one parallel, one sequential
        parallel_scheduler = PhaseScheduler(max_concurrent_tasks=3)
        sequential_scheduler = PhaseScheduler()

        # Create slow phases to make timing differences obvious
        async def slow_phase(duration=0.02):
            await asyncio.sleep(duration)

        for i in range(3):
            parallel_scheduler.register_phase(
                PhaseTask(
                    phase_id=f"phase{i}",
                    phase_name=f"Phase {i}",
                    task_func=lambda d=0.02: slow_phase(d),
                    estimated_duration_seconds=10.0,
                )
            )

            sequential_scheduler.register_phase(
                PhaseTask(
                    phase_id=f"phase{i}",
                    phase_name=f"Phase {i}",
                    task_func=lambda d=0.02: slow_phase(d),
                    estimated_duration_seconds=10.0,
                )
            )

        # Execute parallel
        parallel_result = await parallel_scheduler.schedule_and_execute(sequential=False)

        # Execute sequential
        sequential_result = await sequential_scheduler.schedule_and_execute(sequential=True)

        # Parallel should be faster
        parallel_time = parallel_result["total_execution_time"]
        sequential_time = sequential_result["total_execution_time"]

        assert parallel_time < sequential_time
