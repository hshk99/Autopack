"""Tests for migrated phase handler modules.

These tests verify the extracted phase handler modules:
1. Are importable with correct execute() signature
2. Call through to underlying batched deliverables phase (for diagnostics handlers)
3. Have no circular imports to autonomous_executor

This test file follows table-driven testing pattern for all 7 migrated handlers.
"""

from __future__ import annotations

import importlib
import inspect
from unittest.mock import MagicMock, patch

import pytest

# Table of all migrated handler modules
MIGRATED_HANDLERS = [
    "batched_diagnostics_deep_retrieval",
    "batched_diagnostics_iteration_loop",
    "batched_diagnostics_handoff_bundle",
    "batched_diagnostics_cursor_prompt",
    "batched_diagnostics_second_opinion",
    "batched_research_tracer_bullet",
    "batched_research_gatherers_web_compilation",
]


class TestPhaseHandlerModulesImportable:
    """Verify all migrated handler modules are importable."""

    @pytest.mark.parametrize("module_name", MIGRATED_HANDLERS)
    def test_handler_module_imports(self, module_name: str) -> None:
        """Each handler module should import without errors."""
        mod = importlib.import_module(f"autopack.executor.phase_handlers.{module_name}")
        assert mod is not None

    @pytest.mark.parametrize("module_name", MIGRATED_HANDLERS)
    def test_handler_module_has_execute_function(self, module_name: str) -> None:
        """Each handler module should have an execute() function."""
        mod = importlib.import_module(f"autopack.executor.phase_handlers.{module_name}")
        assert hasattr(mod, "execute"), f"{module_name} missing execute()"
        assert callable(mod.execute), f"{module_name}.execute is not callable"


class TestPhaseHandlerSignatures:
    """Verify all execute() functions have expected signature."""

    @pytest.mark.parametrize("module_name", MIGRATED_HANDLERS)
    def test_execute_signature_matches_contract(self, module_name: str) -> None:
        """execute() should match: (executor, *, phase, attempt_index, allowed_paths)."""
        mod = importlib.import_module(f"autopack.executor.phase_handlers.{module_name}")
        sig = inspect.signature(mod.execute)
        params = list(sig.parameters.keys())

        # Required parameters
        assert "executor" in params, f"{module_name} missing 'executor' param"
        assert "phase" in params, f"{module_name} missing 'phase' param"
        assert "attempt_index" in params, f"{module_name} missing 'attempt_index' param"
        assert "allowed_paths" in params, f"{module_name} missing 'allowed_paths' param"

    @pytest.mark.parametrize("module_name", MIGRATED_HANDLERS)
    def test_execute_return_type_annotation(self, module_name: str) -> None:
        """execute() should have Tuple[bool, str] return annotation."""
        mod = importlib.import_module(f"autopack.executor.phase_handlers.{module_name}")
        sig = inspect.signature(mod.execute)

        # Check return annotation exists
        assert (
            sig.return_annotation is not inspect.Signature.empty
        ), f"{module_name}.execute() missing return type annotation"


class TestDiagnosticsHandlersDelegation:
    """Verify diagnostics handlers delegate to _execute_batched_deliverables_phase."""

    # Diagnostics handlers that delegate to batched_deliverables_phase
    DIAGNOSTICS_HANDLERS = [
        "batched_diagnostics_deep_retrieval",
        "batched_diagnostics_iteration_loop",
        "batched_diagnostics_handoff_bundle",
        "batched_diagnostics_cursor_prompt",
        "batched_diagnostics_second_opinion",
    ]

    @pytest.mark.parametrize("module_name", DIAGNOSTICS_HANDLERS)
    def test_handler_calls_batched_deliverables_phase(self, module_name: str) -> None:
        """Diagnostics handlers should call executor._execute_batched_deliverables_phase."""
        mod = importlib.import_module(f"autopack.executor.phase_handlers.{module_name}")

        # Create mock executor with the method we expect to be called
        mock_executor = MagicMock()
        mock_executor._execute_batched_deliverables_phase.return_value = (True, "COMPLETE")

        # Mock the extract_deliverables_from_scope import
        with patch(
            "autopack.deliverables_validator.extract_deliverables_from_scope"
        ) as mock_extract:
            mock_extract.return_value = []

            # Call execute
            result = mod.execute(
                mock_executor,
                phase={"phase_id": f"test-{module_name}"},
                attempt_index=0,
                allowed_paths=None,
            )

        # Verify delegation
        mock_executor._execute_batched_deliverables_phase.assert_called_once()
        assert result == (True, "COMPLETE")


class TestResearchHandlersExist:
    """Verify research handlers have full execution logic."""

    RESEARCH_HANDLERS = [
        "batched_research_tracer_bullet",
        "batched_research_gatherers_web_compilation",
    ]

    @pytest.mark.parametrize("module_name", RESEARCH_HANDLERS)
    def test_research_handler_has_substantial_code(self, module_name: str) -> None:
        """Research handlers should have substantial implementation (not thin wrappers)."""
        mod = importlib.import_module(f"autopack.executor.phase_handlers.{module_name}")

        # Get source code
        source = inspect.getsource(mod.execute)

        # Research handlers should have substantial logic
        # They should reference key components like context loading, memory, batching
        assert len(source) > 500, f"{module_name}.execute() too short for research handler"


class TestNoCircularImports:
    """Verify handler modules don't import autonomous_executor directly."""

    @pytest.mark.parametrize("module_name", MIGRATED_HANDLERS)
    def test_no_direct_autonomous_executor_import(self, module_name: str) -> None:
        """Handler modules should not import autonomous_executor at module level."""
        mod = importlib.import_module(f"autopack.executor.phase_handlers.{module_name}")
        source = inspect.getsource(mod)

        # Should not have top-level import of autonomous_executor
        # Local imports inside execute() are allowed
        import_lines = [
            line
            for line in source.split("\n")
            if line.strip().startswith("from autopack.autonomous_executor")
            or line.strip().startswith("import autopack.autonomous_executor")
        ]

        # Filter to only top-level imports (not indented)
        top_level_imports = [line for line in import_lines if not line.startswith((" ", "\t"))]

        assert (
            len(top_level_imports) == 0
        ), f"{module_name} has top-level autonomous_executor import: {top_level_imports}"
