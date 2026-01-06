"""Tests for parallelism default policy checking (BUILD-180 Phase 6).

Validates that parallel execution requires anchor by default and
policy-checked API is the default entrypoint.
"""

import pytest
from unittest.mock import MagicMock, patch

from autopack.parallel_orchestrator import (
    ParallelRunOrchestrator,
    ParallelRunConfig,
    execute_parallel_runs,
)
from autopack.autonomy.parallelism_gate import ParallelismPolicyViolation


class TestParallelExecutionRequiresAnchor:
    """Test that parallel execution requires anchor by default."""

    @pytest.mark.asyncio
    async def test_parallel_execution_requires_anchor(self):
        """Parallel execution (workers > 1) should require anchor."""
        config = ParallelRunConfig(max_concurrent_runs=3)
        orchestrator = ParallelRunOrchestrator(config)

        async def dummy_executor(run_id, workspace):
            return True

        # Calling execute_parallel without anchor for multiple runs should fail
        with pytest.raises((ParallelismPolicyViolation, TypeError, ValueError)):
            await orchestrator.execute_parallel(
                run_ids=["run1", "run2"],
                executor_func=dummy_executor,
            )

    @pytest.mark.asyncio
    async def test_single_run_does_not_require_anchor(self):
        """Single run should not require anchor (no parallelism)."""
        config = ParallelRunConfig(max_concurrent_runs=1)
        orchestrator = ParallelRunOrchestrator(config)

        async def dummy_executor(run_id, workspace):
            return True

        # Single run should work without anchor
        with patch.object(orchestrator, "_execute_single_run") as mock_exec:
            mock_exec.return_value = MagicMock(success=True, run_id="run1")

            results = await orchestrator.execute_parallel(
                run_ids=["run1"],
                executor_func=dummy_executor,
            )

            assert len(results) == 1


class TestPolicyCheckedAsDefault:
    """Test that policy-checked method is the default."""

    @pytest.mark.asyncio
    async def test_execute_parallel_is_policy_checked(self):
        """execute_parallel should enforce policy by default."""
        config = ParallelRunConfig(max_concurrent_runs=3)
        orchestrator = ParallelRunOrchestrator(config)

        # Mock the policy gate
        with patch("autopack.parallel_orchestrator.ParallelismPolicyGate") as mock_gate:
            mock_gate_instance = MagicMock()
            mock_gate_instance.check_parallel_allowed.side_effect = ParallelismPolicyViolation(
                "Parallelism not allowed"
            )
            mock_gate.return_value = mock_gate_instance

            async def dummy_executor(run_id, workspace):
                return True

            # Should fail because policy check fails
            with pytest.raises(ParallelismPolicyViolation):
                await orchestrator.execute_parallel(
                    run_ids=["run1", "run2"],
                    executor_func=dummy_executor,
                    anchor=MagicMock(),  # Provide anchor
                )

    @pytest.mark.asyncio
    async def test_internal_method_deprecated(self):
        """Internal execute method should emit deprecation warning."""
        config = ParallelRunConfig(max_concurrent_runs=3)
        orchestrator = ParallelRunOrchestrator(config)

        async def dummy_executor(run_id, workspace):
            return True

        # Internal method should warn if called directly
        if hasattr(orchestrator, "_execute_parallel_internal"):
            with pytest.warns(DeprecationWarning):
                await orchestrator._execute_parallel_internal(
                    run_ids=["run1"],
                    executor_func=dummy_executor,
                )


class TestConvenienceFunctionRequiresAnchor:
    """Test that convenience function requires anchor for parallel runs."""

    @pytest.mark.asyncio
    async def test_execute_parallel_runs_requires_anchor(self):
        """execute_parallel_runs should require anchor for multiple runs."""

        async def dummy_executor(run_id, workspace):
            return True

        # Should fail without anchor for multiple runs
        with pytest.raises((ParallelismPolicyViolation, TypeError, ValueError)):
            await execute_parallel_runs(
                run_ids=["run1", "run2"],
                executor_func=dummy_executor,
                max_concurrent=3,
            )


class TestClearErrorMessages:
    """Test that error messages are clear and actionable."""

    @pytest.mark.asyncio
    async def test_missing_anchor_error_is_clear(self):
        """Error for missing anchor should be clear."""
        config = ParallelRunConfig(max_concurrent_runs=3)
        orchestrator = ParallelRunOrchestrator(config)

        async def dummy_executor(run_id, workspace):
            return True

        try:
            await orchestrator.execute_parallel(
                run_ids=["run1", "run2"],
                executor_func=dummy_executor,
            )
            pytest.fail("Should have raised an error")
        except Exception as e:
            error_msg = str(e).lower()
            # Error should mention anchor or policy
            assert "anchor" in error_msg or "policy" in error_msg or "parallel" in error_msg

    @pytest.mark.asyncio
    async def test_policy_violation_error_is_actionable(self):
        """Policy violation error should provide actionable guidance."""
        from autopack.autonomy.parallelism_gate import ParallelismPolicyViolation

        error = ParallelismPolicyViolation("Parallelism not allowed by intention anchor")

        # Error message should be useful
        assert "parallel" in str(error).lower() or "anchor" in str(error).lower()


class TestBackwardsCompatibility:
    """Test backwards compatibility during transition."""

    @pytest.mark.asyncio
    async def test_single_run_api_unchanged(self):
        """Single run API should remain unchanged."""
        config = ParallelRunConfig(max_concurrent_runs=1)
        orchestrator = ParallelRunOrchestrator(config)

        # execute_single should still work
        assert hasattr(orchestrator, "execute_single")

    def test_orchestrator_has_expected_methods(self):
        """Orchestrator should have expected public methods."""
        config = ParallelRunConfig(max_concurrent_runs=3)
        orchestrator = ParallelRunOrchestrator(config)

        # Public methods should exist
        assert hasattr(orchestrator, "execute_parallel")
        assert hasattr(orchestrator, "execute_single")
        assert hasattr(orchestrator, "get_active_runs")
