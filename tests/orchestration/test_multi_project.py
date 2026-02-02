"""Integration tests for multi-project orchestration system.

Tests cover:
- Parallel execution of multiple projects
- Resource management and limiting
- Error isolation between projects
- Different execution strategies
- Progress tracking
"""

import asyncio
from datetime import datetime

import pytest

from src.autopack.orchestration.multi_project import (
    ExecutionStrategy,
    MultiProjectConfig,
    MultiProjectOrchestrator,
    ProjectObjective,
    ProjectResult,
    ResourceManager,
)


class TestResourceManager:
    """Tests for ResourceManager class."""

    def test_initialization(self):
        """Test ResourceManager initialization."""
        config = MultiProjectConfig()
        manager = ResourceManager(config)

        assert manager.config == config
        assert manager._total_api_calls == 0
        assert len(manager._api_call_timestamps) == 0

    def test_api_call_tracking(self):
        """Test API call tracking and limits."""
        config = MultiProjectConfig(max_api_calls_per_minute=5)
        manager = ResourceManager(config)

        # Record API calls
        for _ in range(5):
            manager.record_api_call()

        # Should allow up to limit
        assert manager.check_api_call_limit() is False

    def test_memory_check(self):
        """Test memory limit checking."""
        config = MultiProjectConfig(max_concurrent_memory_mb=10000)
        manager = ResourceManager(config)

        # Current process should be within limit
        assert manager.check_memory_limit() is True

    def test_project_registration(self):
        """Test project registration and unregistration."""
        config = MultiProjectConfig()
        manager = ResourceManager(config)

        # Register projects
        manager.register_project("proj1")
        manager.register_project("proj2")

        snapshot = manager.get_snapshot()
        assert snapshot.active_projects == 2

        # Unregister
        manager.unregister_project("proj1")
        snapshot = manager.get_snapshot()
        assert snapshot.active_projects == 1

    def test_resource_snapshot(self):
        """Test resource snapshot generation."""
        config = MultiProjectConfig()
        manager = ResourceManager(config)

        manager.record_api_call()
        manager.register_project("proj1")

        snapshot = manager.get_snapshot()
        assert snapshot.api_calls_this_minute >= 1
        assert snapshot.active_projects == 1
        assert snapshot.total_api_calls >= 1
        assert snapshot.memory_usage_mb > 0

    def test_can_start_project(self):
        """Test project start permission checking."""
        config = MultiProjectConfig(max_parallel_projects=2)
        manager = ResourceManager(config)

        # Should allow starting projects
        assert manager.can_start_project(max_active=2) is True

        # Register at limit
        manager.register_project("proj1")
        manager.register_project("proj2")

        # Should not allow more
        assert manager.can_start_project(max_active=2) is False


class TestMultiProjectOrchestrator:
    """Tests for MultiProjectOrchestrator class."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test orchestrator initialization."""
        config = MultiProjectConfig()
        orchestrator = MultiProjectOrchestrator(config)

        assert orchestrator.config == config
        assert orchestrator.resource_manager is not None
        assert len(orchestrator._projects_completed) == 0
        assert len(orchestrator._projects_failed) == 0

    @pytest.mark.asyncio
    async def test_execute_single_project(self):
        """Test execution of single project."""
        config = MultiProjectConfig()
        orchestrator = MultiProjectOrchestrator(config)

        async def mock_executor(project_id: str, objective: str) -> bool:
            await asyncio.sleep(0.1)
            return True

        projects = [ProjectObjective(project_id="proj1", objective="Test")]

        results = await orchestrator.execute_projects(
            projects=projects, executor_func=mock_executor
        )

        assert len(results) == 1
        assert results[0].project_id == "proj1"
        assert results[0].success is True
        assert results[0].start_time is not None
        assert results[0].end_time is not None
        assert results[0].duration_seconds > 0

    @pytest.mark.asyncio
    async def test_execute_multiple_projects_parallel(self):
        """Test parallel execution of multiple projects."""
        config = MultiProjectConfig(
            max_parallel_projects=3,
            execution_strategy=ExecutionStrategy.PARALLEL,
        )
        orchestrator = MultiProjectOrchestrator(config)

        async def mock_executor(project_id: str, objective: str) -> bool:
            await asyncio.sleep(0.1)
            return "success" in objective.lower()

        projects = [
            ProjectObjective(project_id="proj1", objective="Success project"),
            ProjectObjective(project_id="proj2", objective="Success project"),
            ProjectObjective(project_id="proj3", objective="Failure project"),
        ]

        results = await orchestrator.execute_projects(
            projects=projects, executor_func=mock_executor
        )

        assert len(results) == 3
        success_count = sum(1 for r in results if r.success)
        assert success_count == 2

    @pytest.mark.asyncio
    async def test_execute_sequential(self):
        """Test sequential execution strategy."""
        config = MultiProjectConfig(execution_strategy=ExecutionStrategy.SEQUENTIAL)
        orchestrator = MultiProjectOrchestrator(config)

        execution_order = []

        async def mock_executor(project_id: str, objective: str) -> bool:
            execution_order.append(project_id)
            await asyncio.sleep(0.05)
            return True

        projects = [
            ProjectObjective(project_id="proj1", objective="Test"),
            ProjectObjective(project_id="proj2", objective="Test"),
            ProjectObjective(project_id="proj3", objective="Test"),
        ]

        results = await orchestrator.execute_projects(
            projects=projects, executor_func=mock_executor
        )

        assert len(results) == 3
        assert len(execution_order) == 3
        # Sequential execution means they should complete in order
        assert execution_order == ["proj1", "proj2", "proj3"]

    @pytest.mark.asyncio
    async def test_error_isolation(self):
        """Test error isolation between projects."""
        config = MultiProjectConfig(
            error_isolation=True,
            fail_fast=False,
        )
        orchestrator = MultiProjectOrchestrator(config)

        async def mock_executor(project_id: str, objective: str) -> bool:
            if "error" in project_id:
                raise RuntimeError(f"Intentional error for {project_id}")
            return True

        projects = [
            ProjectObjective(project_id="proj1", objective="Success"),
            ProjectObjective(project_id="proj2_error", objective="Failure"),
            ProjectObjective(project_id="proj3", objective="Success"),
        ]

        results = await orchestrator.execute_projects(
            projects=projects, executor_func=mock_executor
        )

        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True

    @pytest.mark.asyncio
    async def test_project_timeout(self):
        """Test project timeout enforcement."""
        config = MultiProjectConfig(per_project_timeout_hours=0.001)  # Very short
        orchestrator = MultiProjectOrchestrator(config)

        async def slow_executor(project_id: str, objective: str) -> bool:
            await asyncio.sleep(10)  # This will timeout
            return True

        projects = [ProjectObjective(project_id="proj1", objective="Test")]

        results = await orchestrator.execute_projects(
            projects=projects, executor_func=slow_executor
        )

        assert len(results) == 1
        assert results[0].success is False
        assert "Timeout" in results[0].error

    @pytest.mark.asyncio
    async def test_progress_tracking(self):
        """Test progress tracking functionality."""
        config = MultiProjectConfig(
            enable_progress_tracking=True,
            max_parallel_projects=2,
        )
        orchestrator = MultiProjectOrchestrator(config)

        async def mock_executor(project_id: str, objective: str) -> bool:
            await asyncio.sleep(0.1)
            return True

        projects = [ProjectObjective(project_id=f"proj{i}", objective="Test") for i in range(3)]

        await orchestrator.execute_projects(projects=projects, executor_func=mock_executor)

        # Check progress
        progress = orchestrator.get_progress()
        assert progress["completed"] == 3
        assert progress["failed"] == 0
        assert progress["active"] == 0
        assert progress["success_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_get_results(self):
        """Test results retrieval."""
        config = MultiProjectConfig()
        orchestrator = MultiProjectOrchestrator(config)

        async def mock_executor(project_id: str, objective: str) -> bool:
            return "success" in objective.lower()

        projects = [
            ProjectObjective(project_id="proj1", objective="Success"),
            ProjectObjective(project_id="proj2", objective="Failure"),
        ]

        await orchestrator.execute_projects(projects=projects, executor_func=mock_executor)

        results = orchestrator.get_results()
        assert len(results["completed"]) == 1
        assert len(results["failed"]) == 1

    @pytest.mark.asyncio
    async def test_resource_constraints(self):
        """Test resource constraint enforcement."""
        config = MultiProjectConfig(
            max_parallel_projects=2,
            max_concurrent_memory_mb=100000,  # High limit (shouldn't trigger)
        )
        orchestrator = MultiProjectOrchestrator(config)

        execution_count = 0
        max_concurrent = 0
        current_concurrent = 0
        concurrent_lock = asyncio.Lock()

        async def mock_executor(project_id: str, objective: str) -> bool:
            nonlocal execution_count, max_concurrent, current_concurrent

            async with concurrent_lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)

            await asyncio.sleep(0.1)

            async with concurrent_lock:
                current_concurrent -= 1
                execution_count += 1

            return True

        projects = [ProjectObjective(project_id=f"proj{i}", objective="Test") for i in range(4)]

        results = await orchestrator.execute_projects(
            projects=projects, executor_func=mock_executor
        )

        assert len(results) == 4
        assert max_concurrent <= config.max_parallel_projects
        assert execution_count == 4

    @pytest.mark.asyncio
    async def test_executor_with_kwargs(self):
        """Test executor function with additional kwargs."""
        config = MultiProjectConfig()
        orchestrator = MultiProjectOrchestrator(config)

        received_kwargs = {}

        async def mock_executor(project_id: str, objective: str, **kwargs) -> bool:
            received_kwargs[project_id] = kwargs
            return True

        projects = [ProjectObjective(project_id="proj1", objective="Test")]

        await orchestrator.execute_projects(
            projects=projects,
            executor_func=mock_executor,
            executor_kwargs={"custom_arg": "value"},
        )

        assert "custom_arg" in received_kwargs["proj1"]
        assert received_kwargs["proj1"]["custom_arg"] == "value"

    @pytest.mark.asyncio
    async def test_sync_executor(self):
        """Test execution with synchronous executor function."""
        config = MultiProjectConfig()
        orchestrator = MultiProjectOrchestrator(config)

        def sync_executor(project_id: str, objective: str) -> bool:
            return True

        projects = [ProjectObjective(project_id="proj1", objective="Test")]

        results = await orchestrator.execute_projects(
            projects=projects, executor_func=sync_executor
        )

        assert len(results) == 1
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_request_stop(self):
        """Test graceful stop request."""
        config = MultiProjectConfig(
            execution_strategy=ExecutionStrategy.SEQUENTIAL,
        )
        orchestrator = MultiProjectOrchestrator(config)

        async def mock_executor(project_id: str, objective: str) -> bool:
            return True

        projects = [ProjectObjective(project_id=f"proj{i}", objective="Test") for i in range(5)]

        # Request stop immediately
        orchestrator.request_stop()

        results = await orchestrator.execute_projects(
            projects=projects, executor_func=mock_executor
        )

        # Not all projects should execute
        success_count = sum(1 for r in results if r.success)
        # In sequential mode with stop request, execution should stop early
        assert success_count < 5


class TestProjectObjective:
    """Tests for ProjectObjective dataclass."""

    def test_project_objective_creation(self):
        """Test ProjectObjective creation."""
        obj = ProjectObjective(
            project_id="test_proj",
            objective="Build a web app",
            metadata={"framework": "Django"},
        )

        assert obj.project_id == "test_proj"
        assert obj.objective == "Build a web app"
        assert obj.metadata["framework"] == "Django"
        assert obj.created_at is not None


class TestProjectResult:
    """Tests for ProjectResult dataclass."""

    def test_project_result_success(self):
        """Test successful ProjectResult."""
        start = datetime.utcnow()
        end = datetime.utcnow()

        result = ProjectResult(
            project_id="proj1",
            success=True,
            start_time=start,
            end_time=end,
            duration_seconds=10.5,
            phases_completed=5,
        )

        assert result.project_id == "proj1"
        assert result.success is True
        assert result.duration_seconds == 10.5
        assert result.phases_completed == 5

    def test_project_result_failure(self):
        """Test failed ProjectResult."""
        result = ProjectResult(
            project_id="proj1",
            success=False,
            error="Resource limit exceeded",
        )

        assert result.project_id == "proj1"
        assert result.success is False
        assert result.error == "Resource limit exceeded"


class TestExecutionStrategy:
    """Tests for ExecutionStrategy enum."""

    def test_strategy_values(self):
        """Test execution strategy enum values."""
        assert ExecutionStrategy.PARALLEL.value == "parallel"
        assert ExecutionStrategy.SEQUENTIAL.value == "sequential"
        assert ExecutionStrategy.STAGED.value == "staged"
        assert ExecutionStrategy.ADAPTIVE.value == "adaptive"


@pytest.mark.asyncio
async def test_end_to_end_workflow():
    """Integration test for end-to-end multi-project workflow."""
    config = MultiProjectConfig(
        max_parallel_projects=2,
        execution_strategy=ExecutionStrategy.PARALLEL,
        error_isolation=True,
    )
    orchestrator = MultiProjectOrchestrator(config)

    # Track execution
    executions = []

    async def track_executor(project_id: str, objective: str) -> bool:
        executions.append(
            {
                "project_id": project_id,
                "start": datetime.utcnow(),
                "objective": objective,
            }
        )
        await asyncio.sleep(0.05)

        success = "success" in objective.lower()
        executions[-1]["success"] = success
        executions[-1]["end"] = datetime.utcnow()

        return success

    projects = [
        ProjectObjective(project_id="api_success", objective="Build successful API"),
        ProjectObjective(project_id="web_success", objective="Build successful web app"),
        ProjectObjective(project_id="db_failure", objective="Build failing database"),
    ]

    results = await orchestrator.execute_projects(projects=projects, executor_func=track_executor)

    # Verify results
    assert len(results) == 3
    assert len(executions) == 3

    success_results = [r for r in results if r.success]
    failed_results = [r for r in results if not r.success]

    assert len(success_results) == 2
    assert len(failed_results) == 1

    # Verify progress tracking
    progress = orchestrator.get_progress()
    assert progress["completed"] == 2
    assert progress["failed"] == 1
    assert progress["success_rate"] == 2.0 / 3.0
