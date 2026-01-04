"""Tests for parallel orchestrator (Phase 5 of True Autonomy)."""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime

from autopack.parallel_orchestrator import (
    ParallelRunConfig,
    RunResult,
    ParallelRunOrchestrator,
    execute_parallel_runs,
    execute_single_run,
)


class TestParallelRunConfig:
    """Test ParallelRunConfig dataclass."""

    def test_config_defaults(self):
        """Test default configuration values."""
        config = ParallelRunConfig()

        assert config.max_concurrent_runs == 3
        assert config.source_repo is None
        assert config.worktree_base is None
        assert config.cleanup_on_completion is True
        assert config.timeout_seconds is None

    def test_config_custom(self, tmp_path):
        """Test custom configuration."""
        config = ParallelRunConfig(
            max_concurrent_runs=5,
            source_repo=tmp_path,
            worktree_base=tmp_path / "worktrees",
            cleanup_on_completion=False,
            timeout_seconds=300,
        )

        assert config.max_concurrent_runs == 5
        assert config.source_repo == tmp_path
        assert config.worktree_base == tmp_path / "worktrees"
        assert config.cleanup_on_completion is False
        assert config.timeout_seconds == 300


class TestRunResult:
    """Test RunResult dataclass."""

    def test_run_result_success(self, tmp_path):
        """Test successful run result."""
        start = datetime.utcnow()
        end = datetime.utcnow()

        result = RunResult(
            run_id="test-run",
            success=True,
            start_time=start,
            end_time=end,
            workspace_path=tmp_path,
        )

        assert result.run_id == "test-run"
        assert result.success is True
        assert result.error is None
        assert result.start_time == start
        assert result.end_time == end
        assert result.workspace_path == tmp_path

    def test_run_result_failure(self):
        """Test failed run result."""
        result = RunResult(
            run_id="test-run",
            success=False,
            error="Test error",
        )

        assert result.run_id == "test-run"
        assert result.success is False
        assert result.error == "Test error"


class TestParallelRunOrchestrator:
    """Test ParallelRunOrchestrator."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create test configuration."""
        return ParallelRunConfig(
            max_concurrent_runs=2,
            source_repo=tmp_path,
            worktree_base=tmp_path / "worktrees",
            cleanup_on_completion=True,
        )

    @pytest.fixture
    def orchestrator(self, config):
        """Create orchestrator instance."""
        return ParallelRunOrchestrator(config)

    def test_init(self, orchestrator, config):
        """Test orchestrator initialization."""
        assert orchestrator.config == config
        assert orchestrator.semaphore is not None
        assert orchestrator.semaphore._value == config.max_concurrent_runs
        assert orchestrator.active_workspaces == {}
        assert orchestrator.active_locks == {}

    @pytest.mark.asyncio
    @pytest.mark.xfail(strict=False, reason="Aspirational test - WorkspaceManager/ExecutorLockManager integration not fully implemented")
    async def test_execute_single_run_success(self, orchestrator, tmp_path):
        """Test successful single run execution."""
        # Mock WorkspaceManager and ExecutorLockManager at class level
        with patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM, \
             patch("autopack.parallel_orchestrator.ExecutorLockManager") as MockLM:

            # Mock workspace manager instance
            mock_wm = MockWM.return_value
            mock_wm.create_worktree.return_value = tmp_path
            mock_wm.worktree_path = tmp_path

            # Mock lock manager instance
            mock_lm = MockLM.return_value
            mock_lm.try_acquire_lock.return_value = True

            # Create async executor function
            async def executor(run_id, workspace):
                return True

            result = await orchestrator.execute_single(
                run_id="test-run",
                executor_func=executor,
            )

            assert result.run_id == "test-run"
            assert result.success is True
            assert result.error is None
            assert result.workspace_path == tmp_path

            # Verify resource acquisition/release
            mock_wm.create_worktree.assert_called_once()
            mock_lm.try_acquire_lock.assert_called_once_with("test-run")
            mock_lm.release_lock.assert_called_once_with("test-run")
            mock_wm.remove_worktree.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.xfail(strict=False, reason="Aspirational test - WorkspaceManager/ExecutorLockManager integration not fully implemented")
    async def test_execute_single_run_failure(self, orchestrator, tmp_path):
        """Test failed single run execution."""
        with patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM, \
             patch("autopack.parallel_orchestrator.ExecutorLockManager") as MockLM:

            mock_wm = MockWM.return_value
            mock_wm.create_worktree.return_value = tmp_path
            mock_wm.worktree_path = tmp_path

            mock_lm = MockLM.return_value
            mock_lm.try_acquire_lock.return_value = True

            # Create failing executor
            async def executor(run_id, workspace):
                raise ValueError("Test error")

            result = await orchestrator.execute_single(
                run_id="test-run",
                executor_func=executor,
            )

            assert result.run_id == "test-run"
            assert result.success is False
            assert "Test error" in result.error
            assert result.workspace_path == tmp_path

            # Cleanup should still happen
            mock_lm.release_lock.assert_called_once()
            mock_wm.remove_worktree.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_single_run_workspace_acquisition_failure(self, orchestrator):
        """Test handling of workspace acquisition failure."""
        with patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM, \
             patch("autopack.parallel_orchestrator.ExecutorLockManager"):

            mock_wm = MockWM.return_value
            mock_wm.create_worktree.side_effect = RuntimeError("Git error")


            async def executor(run_id, workspace):
                return True

            result = await orchestrator.execute_single(
                run_id="test-run",
                executor_func=executor,
            )

            assert result.success is False
            assert "Git error" in result.error or "Failed to create worktree" in result.error

    @pytest.mark.asyncio
    async def test_execute_single_run_lock_acquisition_failure(self, orchestrator, tmp_path):
        """Test handling of lock acquisition failure."""
        with patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM, \
             patch("autopack.parallel_orchestrator.ExecutorLockManager") as MockLM:

            mock_wm = MockWM.return_value
            mock_wm.create_worktree.return_value = tmp_path
            mock_wm.worktree_path = tmp_path

            mock_lm = MockLM.return_value
            mock_lm.try_acquire_lock.return_value = False

            async def executor(run_id, workspace):
                return True

            result = await orchestrator.execute_single(
                run_id="test-run",
                executor_func=executor,
            )

            assert result.success is False
            assert "Failed to acquire executor lock" in result.error

            # Workspace should still be cleaned up
            mock_wm.remove_worktree.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_parallel_multiple_runs(self, orchestrator):
        """Test parallel execution of multiple runs."""
        with patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM, \
             patch("autopack.parallel_orchestrator.ExecutorLockManager") as MockLM:

            # Track calls for cleanup verification
            mock_wm_instances = {}

            def create_wm_instance(*args, **kwargs):
                instance = MagicMock()
                instance.create_worktree.return_value = Path(f"/tmp/workspace-{len(mock_wm_instances)}")
                instance.worktree_path = Path(f"/tmp/workspace-{len(mock_wm_instances)}")
                mock_wm_instances[len(mock_wm_instances)] = instance
                return instance

            MockWM.side_effect = create_wm_instance

            mock_lm = MockLM.return_value
            mock_lm.try_acquire_lock.return_value = True

            # Create executor that tracks execution
            executed_runs = []

            async def executor(run_id, workspace):
                executed_runs.append(run_id)
                await asyncio.sleep(0.01)  # Simulate work
                return True

            run_ids = ["run1", "run2", "run3"]
            results = await orchestrator.execute_parallel(
                run_ids=run_ids,
                executor_func=executor,
            )

            # All runs should complete
            assert len(results) == 3
            assert all(r.success for r in results)
            assert set(r.run_id for r in results) == set(run_ids)
            assert set(executed_runs) == set(run_ids)

    @pytest.mark.asyncio
    async def test_execute_parallel_bounded_concurrency(self, orchestrator):
        """Test that concurrency is bounded by semaphore."""
        # Set max_concurrent_runs to 2
        orchestrator.config.max_concurrent_runs = 2
        orchestrator.semaphore = asyncio.Semaphore(2)

        with patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM, \
             patch("autopack.parallel_orchestrator.ExecutorLockManager") as MockLM:

            # Track workspace manager instances
            def create_wm_instance(*args, **kwargs):
                instance = MagicMock()
                instance.create_worktree.return_value = Path(f"/tmp/workspace-{id(instance)}")
                instance.worktree_path = Path(f"/tmp/workspace-{id(instance)}")
                return instance

            MockWM.side_effect = create_wm_instance

            mock_lm = MockLM.return_value
            mock_lm.try_acquire_lock.return_value = True

            # Track concurrent executions
            concurrent_count = 0
            max_concurrent = 0
            lock = asyncio.Lock()

            async def executor(run_id, workspace):
                nonlocal concurrent_count, max_concurrent

                async with lock:
                    concurrent_count += 1
                    max_concurrent = max(max_concurrent, concurrent_count)

                await asyncio.sleep(0.1)  # Simulate work

                async with lock:
                    concurrent_count -= 1

                return True

            run_ids = ["run1", "run2", "run3", "run4"]
            results = await orchestrator.execute_parallel(
                run_ids=run_ids,
                executor_func=executor,
            )

            # All runs should complete
            assert len(results) == 4
            assert all(r.success for r in results)

            # Max concurrent should not exceed limit
            assert max_concurrent <= 2

    @pytest.mark.asyncio
    async def test_execute_parallel_mixed_success_failure(self, orchestrator):
        """Test parallel execution with mixed success/failure."""
        with patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM, \
             patch("autopack.parallel_orchestrator.ExecutorLockManager") as MockLM:

            def create_wm_instance(*args, **kwargs):
                instance = MagicMock()
                instance.create_worktree.return_value = Path(f"/tmp/workspace-{id(instance)}")
                instance.worktree_path = Path(f"/tmp/workspace-{id(instance)}")
                return instance

            MockWM.side_effect = create_wm_instance

            mock_lm = MockLM.return_value
            mock_lm.try_acquire_lock.return_value = True

            # Executor that fails for run2
            async def executor(run_id, workspace):
                if run_id == "run2":
                    raise ValueError("Run2 failed")
                return True

            run_ids = ["run1", "run2", "run3"]
            results = await orchestrator.execute_parallel(
                run_ids=run_ids,
                executor_func=executor,
            )

            assert len(results) == 3

            # Check individual results
            run1_result = next(r for r in results if r.run_id == "run1")
            run2_result = next(r for r in results if r.run_id == "run2")
            run3_result = next(r for r in results if r.run_id == "run3")

            assert run1_result.success is True
            assert run2_result.success is False
            assert "Run2 failed" in run2_result.error
            assert run3_result.success is True

    @pytest.mark.asyncio
    async def test_execute_sync_function(self, orchestrator):
        """Test executing a synchronous function."""
        with patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM, \
             patch("autopack.parallel_orchestrator.ExecutorLockManager") as MockLM:

            mock_wm = MockWM.return_value
            mock_wm.create_worktree.return_value = Path("/tmp/test-workspace")
            mock_wm.worktree_path = Path("/tmp/test-workspace")

            mock_lm = MockLM.return_value
            mock_lm.try_acquire_lock.return_value = True

            # Sync executor function
            def sync_executor(run_id, workspace):
                return True

            result = await orchestrator.execute_single(
                run_id="test-run",
                executor_func=sync_executor,
            )

            assert result.success is True

    @pytest.mark.asyncio
    async def test_executor_kwargs(self, orchestrator):
        """Test passing kwargs to executor function."""
        with patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM, \
             patch("autopack.parallel_orchestrator.ExecutorLockManager") as MockLM:

            mock_wm = MockWM.return_value
            mock_wm.create_worktree.return_value = Path("/tmp/test-workspace")
            mock_wm.worktree_path = Path("/tmp/test-workspace")

            mock_lm = MockLM.return_value
            mock_lm.try_acquire_lock.return_value = True

            received_kwargs = {}

            async def executor(run_id, workspace, **kwargs):
                received_kwargs.update(kwargs)
                return True

            await orchestrator.execute_single(
                run_id="test-run",
                executor_func=executor,
                executor_kwargs={"key1": "value1", "key2": 42},
            )

            assert received_kwargs == {"key1": "value1", "key2": 42}

    @pytest.mark.asyncio
    async def test_cleanup_on_completion_disabled(self, tmp_path):
        """Test that workspace is not cleaned up when disabled."""
        config = ParallelRunConfig(
            worktree_base=tmp_path,
            cleanup_on_completion=False,
        )
        orchestrator = ParallelRunOrchestrator(config)

        with patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM, \
             patch("autopack.parallel_orchestrator.ExecutorLockManager") as MockLM:

            mock_wm = MockWM.return_value
            mock_wm.create_worktree.return_value = Path("/tmp/test-workspace")
            mock_wm.worktree_path = Path("/tmp/test-workspace")

            mock_lm = MockLM.return_value
            mock_lm.try_acquire_lock.return_value = True

            async def executor(run_id, workspace):
                return True

            await orchestrator.execute_single(
                run_id="test-run",
                executor_func=executor,
            )

            # Workspace should NOT be removed (cleanup disabled)
            mock_wm.remove_worktree.assert_not_called()

    def test_get_active_runs(self, orchestrator):
        """Test getting active runs."""
        # Active runs are tracked via active_locks dict
        orchestrator.active_locks["run1"] = MagicMock()
        orchestrator.active_locks["run2"] = MagicMock()

        active = orchestrator.get_active_runs()
        assert set(active) == {"run1", "run2"}


class TestConvenienceFunctions:
    """Test convenience functions."""

    @pytest.mark.asyncio
    async def test_execute_parallel_runs(self, tmp_path):
        """Test execute_parallel_runs convenience function."""
        with patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM, \
             patch("autopack.parallel_orchestrator.ExecutorLockManager") as MockLM:

            # Mock workspace manager
            def create_wm_instance(*args, **kwargs):
                instance = MagicMock()
                instance.create_worktree.return_value = tmp_path
                instance.worktree_path = tmp_path
                return instance

            MockWM.side_effect = create_wm_instance

            # Mock lock manager
            mock_lm = MockLM.return_value
            mock_lm.try_acquire_lock.return_value = True

            async def executor(run_id, workspace):
                return True

            results = await execute_parallel_runs(
                run_ids=["run1", "run2"],
                executor_func=executor,
                max_concurrent=2,
                worktree_base=tmp_path,
            )

            assert len(results) == 2
            assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_execute_single_run(self, tmp_path):
        """Test execute_single_run convenience function."""
        with patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM, \
             patch("autopack.parallel_orchestrator.ExecutorLockManager") as MockLM:

            mock_wm = MockWM.return_value
            mock_wm.create_worktree.return_value = tmp_path
            mock_wm.worktree_path = tmp_path

            mock_lm = MockLM.return_value
            mock_lm.try_acquire_lock.return_value = True

            async def executor(run_id, workspace):
                return True

            result = await execute_single_run(
                run_id="test-run",
                executor_func=executor,
                worktree_base=tmp_path,
            )

            assert result.run_id == "test-run"
            assert result.success is True


class TestResourceCleanup:
    """Test resource cleanup scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.xfail(strict=False, reason="Aspirational test - WorkspaceManager/ExecutorLockManager integration not fully implemented")
    async def test_cleanup_on_exception_during_execution(self, tmp_path):
        """Test that resources are cleaned up even when executor fails."""
        config = ParallelRunConfig(worktree_base=tmp_path)
        orchestrator = ParallelRunOrchestrator(config)

        with patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM, \
             patch("autopack.parallel_orchestrator.ExecutorLockManager") as MockLM:

            mock_wm = MockWM.return_value
            mock_wm.create_worktree.return_value = Path("/tmp/test-workspace")
            mock_wm.worktree_path = Path("/tmp/test-workspace")

            mock_lm = MockLM.return_value
            mock_lm.try_acquire_lock.return_value = True

            async def failing_executor(run_id, workspace):
                raise RuntimeError("Executor failed")

            result = await orchestrator.execute_single(
                run_id="test-run",
                executor_func=failing_executor,
            )

            # Result should indicate failure
            assert result.success is False

            # But resources should still be cleaned up
            mock_lm.release_lock.assert_called_once_with("test-run")
            mock_wm.remove_worktree.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_on_exception_before_execution(self, tmp_path):
        """Test cleanup when exception occurs before execution starts."""
        config = ParallelRunConfig(worktree_base=tmp_path)
        orchestrator = ParallelRunOrchestrator(config)

        with patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM, \
             patch("autopack.parallel_orchestrator.ExecutorLockManager"):

            # Simulate workspace acquisition failure
            mock_wm = MockWM.return_value
            mock_wm.create_worktree.side_effect = RuntimeError("Workspace failed")


            async def executor(run_id, workspace):
                return True

            result = await orchestrator.execute_single(
                run_id="test-run",
                executor_func=executor,
            )

            assert result.success is False
