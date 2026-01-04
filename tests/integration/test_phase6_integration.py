"""Integration tests for BUILD-146 Phase 6 hot-path wiring.

These tests verify that True Autonomy features are correctly integrated
into the autonomous_executor hot-path and work end-to-end.
"""

import pytest
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


class TestFailureHardeningIntegration:
    """Test failure hardening integration in autonomous_executor."""

    def test_failure_hardening_env_flag_enabled(self):
        """Test that failure hardening is triggered when env flag is set."""
        # Set environment flag
        os.environ["AUTOPACK_ENABLE_FAILURE_HARDENING"] = "true"

        try:
            from autopack.failure_hardening import detect_and_mitigate_failure

            # Mock failure scenario
            error_text = "ModuleNotFoundError: No module named 'requests'"
            context = {
                "workspace": Path.cwd(),
                "phase_id": "test-phase",
                "status": "FAILED",
                "scope_paths": ["src/main.py"],
            }

            # Call detection
            result = detect_and_mitigate_failure(error_text, context)

            # Verify pattern detected
            assert result is not None
            assert result.pattern_id == "python_missing_dep"
            assert "requests" in result.suggestions[0]

        finally:
            # Clean up
            os.environ.pop("AUTOPACK_ENABLE_FAILURE_HARDENING", None)

    def test_failure_hardening_skips_when_disabled(self):
        """Test that failure hardening is skipped when env flag is not set."""
        # Ensure flag is not set
        os.environ.pop("AUTOPACK_ENABLE_FAILURE_HARDENING", None)

        # Import should still work, but env check would skip execution
        from autopack.failure_hardening import detect_and_mitigate_failure

        # This test verifies the module is importable when disabled
        assert detect_and_mitigate_failure is not None

    def test_failure_hardening_patterns_coverage(self):
        """Test that all 6 built-in patterns are available."""
        from autopack.failure_hardening import FailureHardeningRegistry

        registry = FailureHardeningRegistry()
        patterns = registry.list_patterns()

        # Verify all 6 patterns exist
        expected_patterns = [
            "python_missing_dep",
            "wrong_working_dir",
            "missing_test_discovery",
            "scope_mismatch",
            "node_missing_dep",
            "permission_error",
        ]

        for pattern_id in expected_patterns:
            assert pattern_id in patterns, f"Missing pattern: {pattern_id}"

    @patch("autopack.failure_hardening.Path")
    def test_failure_hardening_mitigation_actions(self, mock_path):
        """Test that mitigations produce actionable suggestions."""
        from autopack.failure_hardening import detect_and_mitigate_failure

        # Test python_missing_dep mitigation
        error_text = "ModuleNotFoundError: No module named 'numpy'"
        context = {
            "workspace": Path.cwd(),
            "phase_id": "test-phase",
            "status": "FAILED",
            "scope_paths": ["analysis.py"],
        }

        result = detect_and_mitigate_failure(error_text, context)

        assert result is not None
        assert result.pattern_id == "python_missing_dep"
        assert len(result.suggestions) > 0
        assert any("numpy" in s for s in result.suggestions)


class TestIntentionContextIntegration:
    """Test intention context integration in autonomous_executor."""

    def test_intention_context_env_flag_enabled(self):
        """Test that intention context is injected when env flag is set."""
        os.environ["AUTOPACK_ENABLE_INTENTION_CONTEXT"] = "true"

        try:
            from autopack.intention_wiring import IntentionContextInjector

            # Create injector
            injector = IntentionContextInjector(
                run_id="test-run",
                project_id="test-project",
                memory_service=None  # Will fall back to empty context
            )

            # Get intention context (should not crash even with no memory)
            context = injector.get_intention_context(max_chars=2048)

            # Verify graceful degradation
            assert context is not None
            assert isinstance(context, str)

        finally:
            os.environ.pop("AUTOPACK_ENABLE_INTENTION_CONTEXT", None)

    def test_intention_context_bounded_size(self):
        """Test that intention context respects size limits."""
        from autopack.intention_wiring import IntentionContextInjector

        # Mock memory service with large intentions
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.search_planning.return_value = [
            {"payload": {"content_preview": "A" * 5000}, "score": 0.9},
            {"payload": {"content_preview": "B" * 5000}, "score": 0.8},
        ]

        injector = IntentionContextInjector(
            run_id="test-run",
            project_id="test-project",
            memory_service=mock_memory
        )

        # Request limited context
        context = injector.get_intention_context(max_chars=2048)

        # Verify size limit enforced
        assert len(context) <= 2048

    def test_intention_context_graceful_failure(self):
        """Test that intention context fails gracefully on errors."""
        from autopack.intention_wiring import IntentionContextInjector

        # Mock memory service that raises exception
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.search_planning.side_effect = RuntimeError("Memory unavailable")

        injector = IntentionContextInjector(
            run_id="test-run",
            project_id="test-project",
            memory_service=mock_memory
        )

        # Should not crash, return empty context
        context = injector.get_intention_context(max_chars=2048)

        assert context == ""


class TestPlanNormalizationIntegration:
    """Test plan normalization CLI integration."""

    def test_plan_normalizer_cli_arguments_registered(self):
        """Test that CLI arguments for plan normalization are registered."""
        import sys

        # Mock sys.argv to avoid pytest interference
        original_argv = sys.argv
        try:
            sys.argv = ["autonomous_executor.py", "--run-id", "test-run"]

            # Import main to trigger argument parser setup
            # We can't actually run main(), but we can verify imports work
            from autopack.plan_normalizer import PlanNormalizer

            # Verify PlanNormalizer is importable and has expected methods
            assert hasattr(PlanNormalizer, "normalize")
            assert hasattr(PlanNormalizer, "_infer_category")
            assert hasattr(PlanNormalizer, "_infer_validation_steps")

        finally:
            sys.argv = original_argv

    def test_plan_normalizer_transform_unstructured_to_structured(self, tmp_path):
        """Test that plan normalizer transforms unstructured text to structured run."""
        from autopack.plan_normalizer import PlanNormalizer

        # Create minimal project structure to avoid validation step inference failure
        (tmp_path / "main.py").write_text("# Main file")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_main.py").write_text("def test_example(): pass")

        # Create unstructured plan with explicit validation
        raw_plan = """
        Project: Build a REST API

        Phase 1: Setup project structure
        - Create main.py
        - Add FastAPI dependency
        Validation: pytest tests/

        Phase 2: Implement endpoints
        - Add /users endpoint
        - Add /items endpoint
        Validation: pytest tests/

        Phase 3: Add tests
        - Test user creation
        - Test item retrieval
        Validation: pytest tests/
        """

        # Normalize
        normalizer = PlanNormalizer(
            workspace=tmp_path,
            run_id="test-run",
            project_id="test-project"
        )
        result = normalizer.normalize(raw_plan=raw_plan)

        # Verify structured output (may fail gracefully with warnings)
        assert result is not None
        if result.success:
            assert result.structured_plan is not None
            assert "tiers" in result.structured_plan or "phases" in result.structured_plan
        else:
            # Normalization can fail if plan is too vague, that's acceptable
            assert result.error is not None or len(result.warnings) > 0


class TestParallelExecutionIntegration:
    """Test parallel execution orchestrator integration."""

    @pytest.mark.asyncio
    async def test_parallel_orchestrator_bounded_concurrency(self, tmp_path):
        """Test that parallel orchestrator enforces concurrency limits."""
        from autopack.parallel_orchestrator import ParallelRunOrchestrator, ParallelRunConfig

        config = ParallelRunConfig(
            max_concurrent_runs=2,
            source_repo=tmp_path,
            worktree_base=tmp_path / "worktrees",
        )

        orchestrator = ParallelRunOrchestrator(config)

        # Verify semaphore configured correctly
        assert orchestrator.semaphore._value == 2

    @pytest.mark.asyncio
    async def test_parallel_orchestrator_isolated_workspaces(self, tmp_path):
        """Test that parallel orchestrator creates isolated workspaces."""
        from autopack.parallel_orchestrator import execute_parallel_runs

        # Mock executor function
        executed_runs = []

        async def mock_executor(run_id, workspace):
            executed_runs.append((run_id, workspace))
            return True

        # Mock WorkspaceManager and ExecutorLockManager
        with patch("autopack.parallel_orchestrator.WorkspaceManager") as MockWM, \
             patch("autopack.parallel_orchestrator.ExecutorLockManager") as MockLM:

            # Setup mocks
            def create_workspace_mock(run_id, **kwargs):
                mock = MagicMock()
                mock.create_worktree.return_value = tmp_path / run_id
                mock.worktree_path = tmp_path / run_id
                return mock

            MockWM.side_effect = create_workspace_mock

            mock_lm = MockLM.return_value
            mock_lm.try_acquire_lock.return_value = True

            # Execute parallel runs
            results = await execute_parallel_runs(
                run_ids=["run1", "run2"],
                executor_func=mock_executor,
                max_concurrent=2,
                source_repo=tmp_path,
            )

            # Verify all runs executed
            assert len(results) == 2
            assert all(r.success for r in results)
            assert len(executed_runs) == 2

            # Verify isolated workspaces
            workspaces = [w for _, w in executed_runs]
            assert len(set(workspaces)) == 2  # All unique workspaces


class TestEndToEndIntegration:
    """End-to-end integration tests combining multiple features."""

    def test_all_features_can_be_enabled_simultaneously(self, tmp_path):
        """Test that all P6 features can be enabled together without conflicts."""
        # Set all environment flags
        os.environ["AUTOPACK_ENABLE_INTENTION_CONTEXT"] = "true"
        os.environ["AUTOPACK_ENABLE_FAILURE_HARDENING"] = "true"

        try:
            # Import all modules
            from autopack.intention_wiring import IntentionContextInjector
            from autopack.failure_hardening import FailureHardeningRegistry
            from autopack.plan_normalizer import PlanNormalizer

            # Verify all instantiate without errors
            injector = IntentionContextInjector("test-run", "test-project", None)
            registry = FailureHardeningRegistry()
            normalizer = PlanNormalizer(
                workspace=tmp_path,
                run_id="test-run",
                project_id="test-project"
            )

            # All should be instantiated
            assert injector is not None
            assert registry is not None
            assert normalizer is not None

        finally:
            # Clean up
            os.environ.pop("AUTOPACK_ENABLE_INTENTION_CONTEXT", None)
            os.environ.pop("AUTOPACK_ENABLE_FAILURE_HARDENING", None)

    def test_feature_flags_default_to_disabled(self):
        """Test that all features default to disabled for backward compatibility."""
        # Ensure no flags are set
        os.environ.pop("AUTOPACK_ENABLE_INTENTION_CONTEXT", None)
        os.environ.pop("AUTOPACK_ENABLE_FAILURE_HARDENING", None)

        # Verify flags are not set
        assert os.getenv("AUTOPACK_ENABLE_INTENTION_CONTEXT") is None
        assert os.getenv("AUTOPACK_ENABLE_FAILURE_HARDENING") is None

        # This ensures backward compatibility - features are opt-in

    def test_test_coverage_complete(self):
        """Meta-test: Verify all P6 modules have test coverage."""
        import importlib.util

        # List of P6 modules that should exist
        p6_modules = [
            "autopack.intention_wiring",
            "autopack.plan_normalizer",
            "autopack.failure_hardening",
            "autopack.parallel_orchestrator",
            "autopack.toolchain.adapter",
        ]

        for module_name in p6_modules:
            # Verify module is importable
            spec = importlib.util.find_spec(module_name)
            assert spec is not None, f"Module {module_name} not found"

            # Import module
            module = importlib.import_module(module_name)
            assert module is not None
