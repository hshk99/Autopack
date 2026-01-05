"""Simplified tests for parallel orchestrator (Phase 5 of True Autonomy)."""

import pytest
import asyncio
from unittest.mock import MagicMock, patch

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

    def test_config_custom(self, tmp_path):
        """Test custom configuration."""
        config = ParallelRunConfig(
            max_concurrent_runs=5,
            source_repo=tmp_path,
            worktree_base=tmp_path / "worktrees",
            cleanup_on_completion=False,
        )

        assert config.max_concurrent_runs == 5
        assert config.source_repo == tmp_path


class TestRunResult:
    """Test RunResult dataclass."""

    def test_run_result_success(self, tmp_path):
        """Test successful run result."""
        result = RunResult(
            run_id="test-run",
            success=True,
            workspace_path=tmp_path,
        )

        assert result.run_id == "test-run"
        assert result.success is True
        assert result.error is None

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
        )

    @pytest.fixture
    def orchestrator(self, config):
        """Create orchestrator instance."""
        return ParallelRunOrchestrator(config)

    def test_init(self, orchestrator, config):
        """Test orchestrator initialization."""
        assert orchestrator.config == config
        assert orchestrator.semaphore is not None
        assert orchestrator.active_workspaces == {}
        assert orchestrator.active_locks == {}

    @pytest.mark.asyncio
    async def test_execute_single_run_success(self, orchestrator, tmp_path):
        """Test successful single run execution."""
        with (
            patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM,
            patch("autopack.parallel_orchestrator.ExecutorLockManager") as MockLM,
        ):

            mock_wm = MockWM.return_value
            mock_wm.create_worktree.return_value = tmp_path
            mock_wm.worktree_path = tmp_path

            mock_lm = MockLM.return_value
            mock_lm.try_acquire_lock.return_value = True

            async def executor(run_id, workspace):
                assert run_id == "test-run"
                assert workspace == tmp_path
                return True

            result = await orchestrator.execute_single(
                run_id="test-run",
                executor_func=executor,
            )

            assert result.success is True
            assert result.run_id == "test-run"

    @pytest.mark.asyncio
    async def test_execute_single_run_failure(self, orchestrator, tmp_path):
        """Test failed single run execution."""
        with (
            patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM,
            patch("autopack.parallel_orchestrator.ExecutorLockManager") as MockLM,
        ):

            mock_wm = MockWM.return_value
            mock_wm.create_worktree.return_value = tmp_path
            mock_wm.worktree_path = tmp_path

            mock_lm = MockLM.return_value
            mock_lm.try_acquire_lock.return_value = True

            async def executor(run_id, workspace):
                raise ValueError("Test error")

            result = await orchestrator.execute_single(
                run_id="test-run",
                executor_func=executor,
            )

            assert result.success is False
            assert "Test error" in result.error

    @pytest.mark.asyncio
    async def test_execute_parallel_multiple_runs(self, orchestrator, tmp_path):
        """Test parallel execution of multiple runs."""
        with (
            patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM,
            patch("autopack.parallel_orchestrator.ExecutorLockManager") as MockLM,
        ):

            def create_workspace_mock(run_id, **kwargs):
                mock = MagicMock()
                mock.create_worktree.return_value = tmp_path / run_id
                mock.worktree_path = tmp_path / run_id
                return mock

            MockWM.side_effect = create_workspace_mock

            mock_lm = MockLM.return_value
            mock_lm.try_acquire_lock.return_value = True

            executed_runs = []

            async def executor(run_id, workspace):
                executed_runs.append(run_id)
                await asyncio.sleep(0.01)
                return True

            results = await orchestrator.execute_parallel(
                run_ids=["run1", "run2", "run3"],
                executor_func=executor,
            )

            assert len(results) == 3
            assert all(r.success for r in results)
            assert set(executed_runs) == {"run1", "run2", "run3"}

    @pytest.mark.asyncio
    async def test_execute_with_kwargs(self, orchestrator, tmp_path):
        """Test passing kwargs to executor."""
        with (
            patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM,
            patch("autopack.parallel_orchestrator.ExecutorLockManager") as MockLM,
        ):

            mock_wm = MockWM.return_value
            mock_wm.create_worktree.return_value = tmp_path
            mock_wm.worktree_path = tmp_path

            mock_lm = MockLM.return_value
            mock_lm.try_acquire_lock.return_value = True

            received = {}

            async def executor(run_id, workspace, **kwargs):
                received.update(kwargs)
                return True

            await orchestrator.execute_single(
                run_id="test-run",
                executor_func=executor,
                executor_kwargs={"key1": "value1"},
            )

            assert received == {"key1": "value1"}


class TestConvenienceFunctions:
    """Test convenience functions."""

    @pytest.mark.asyncio
    async def test_execute_parallel_runs(self, tmp_path):
        """Test execute_parallel_runs convenience function."""
        with (
            patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM,
            patch("autopack.parallel_orchestrator.ExecutorLockManager") as MockLM,
        ):

            mock_wm = MockWM.return_value
            mock_wm.create_worktree.return_value = tmp_path
            mock_wm.worktree_path = tmp_path

            mock_lm = MockLM.return_value
            mock_lm.try_acquire_lock.return_value = True

            async def executor(run_id, workspace):
                return True

            results = await execute_parallel_runs(
                run_ids=["run1", "run2"],
                executor_func=executor,
                source_repo=tmp_path,
            )

            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_execute_single_run(self, tmp_path):
        """Test execute_single_run convenience function."""
        with (
            patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM,
            patch("autopack.parallel_orchestrator.ExecutorLockManager") as MockLM,
        ):

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
                source_repo=tmp_path,
            )

            assert result.run_id == "test-run"
            assert result.success is True
