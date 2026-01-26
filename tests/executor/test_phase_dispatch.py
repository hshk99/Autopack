"""Tests for phase_dispatch.py.

IMP-TEST-014: Add tests for phase dispatch helpers.

These tests verify the phase dispatch registry used by AutonomousExecutor
to map special phase IDs to their corresponding handler method names.

Test coverage:
1. resolve_special_phase_method returns correct handler for each special phase
2. resolve_special_phase_method returns None for unknown phases
3. resolve_special_phase_method handles None and empty string inputs
4. SPECIAL_PHASE_METHODS registry contains expected entries
"""

import pytest

from autopack.executor.phase_dispatch import (
    SPECIAL_PHASE_METHODS,
    resolve_special_phase_method,
)


class TestResolveSpecialPhaseMethod:
    """Test resolve_special_phase_method function."""

    def test_research_tracer_bullet_returns_correct_handler(self):
        """Test research-tracer-bullet maps to batched handler."""
        result = resolve_special_phase_method("research-tracer-bullet")
        assert result == "_execute_research_tracer_bullet_batched"

    def test_research_gatherers_web_compilation_returns_correct_handler(self):
        """Test research-gatherers-web-compilation maps to batched handler."""
        result = resolve_special_phase_method("research-gatherers-web-compilation")
        assert result == "_execute_research_gatherers_web_compilation_batched"

    def test_diagnostics_handoff_bundle_returns_correct_handler(self):
        """Test diagnostics-handoff-bundle maps to batched handler."""
        result = resolve_special_phase_method("diagnostics-handoff-bundle")
        assert result == "_execute_diagnostics_handoff_bundle_batched"

    def test_diagnostics_cursor_prompt_returns_correct_handler(self):
        """Test diagnostics-cursor-prompt maps to batched handler."""
        result = resolve_special_phase_method("diagnostics-cursor-prompt")
        assert result == "_execute_diagnostics_cursor_prompt_batched"

    def test_diagnostics_second_opinion_triage_returns_correct_handler(self):
        """Test diagnostics-second-opinion-triage maps to batched handler."""
        result = resolve_special_phase_method("diagnostics-second-opinion-triage")
        assert result == "_execute_diagnostics_second_opinion_batched"

    def test_diagnostics_deep_retrieval_returns_correct_handler(self):
        """Test diagnostics-deep-retrieval maps to batched handler."""
        result = resolve_special_phase_method("diagnostics-deep-retrieval")
        assert result == "_execute_diagnostics_deep_retrieval_batched"

    def test_diagnostics_iteration_loop_returns_correct_handler(self):
        """Test diagnostics-iteration-loop maps to batched handler."""
        result = resolve_special_phase_method("diagnostics-iteration-loop")
        assert result == "_execute_diagnostics_iteration_loop_batched"

    def test_generated_task_execution_returns_correct_handler(self):
        """Test generated-task-execution maps to batched handler (IMP-LOOP-004)."""
        result = resolve_special_phase_method("generated-task-execution")
        assert result == "_execute_generated_task_batched"

    def test_unknown_phase_returns_none(self):
        """Test that unknown phase IDs return None."""
        result = resolve_special_phase_method("unknown-phase")
        assert result is None

    def test_similar_but_incorrect_phase_returns_none(self):
        """Test that similar but incorrect phase IDs return None."""
        result = resolve_special_phase_method("research-tracer-bullets")  # plural
        assert result is None

    def test_none_input_returns_none(self):
        """Test that None input returns None."""
        result = resolve_special_phase_method(None)
        assert result is None

    def test_empty_string_returns_none(self):
        """Test that empty string returns None."""
        result = resolve_special_phase_method("")
        assert result is None

    def test_whitespace_only_returns_none(self):
        """Test that whitespace-only string returns None (not in registry)."""
        result = resolve_special_phase_method("   ")
        assert result is None

    def test_case_sensitivity(self):
        """Test that phase IDs are case-sensitive."""
        result = resolve_special_phase_method("Research-Tracer-Bullet")
        assert result is None

        result_lower = resolve_special_phase_method("research-tracer-bullet")
        assert result_lower == "_execute_research_tracer_bullet_batched"

    def test_partial_match_returns_none(self):
        """Test that partial phase ID matches return None."""
        result = resolve_special_phase_method("research")
        assert result is None

        result2 = resolve_special_phase_method("tracer-bullet")
        assert result2 is None


class TestSpecialPhaseMethodsRegistry:
    """Test SPECIAL_PHASE_METHODS registry structure."""

    def test_registry_is_dict(self):
        """Test that SPECIAL_PHASE_METHODS is a dictionary."""
        assert isinstance(SPECIAL_PHASE_METHODS, dict)

    def test_registry_has_expected_count(self):
        """Test registry contains expected number of entries."""
        # IMP-LOOP-004: Updated count to include generated-task-execution handler
        assert len(SPECIAL_PHASE_METHODS) == 8

    def test_all_keys_are_strings(self):
        """Test all registry keys are strings."""
        for key in SPECIAL_PHASE_METHODS:
            assert isinstance(key, str)

    def test_all_values_are_strings(self):
        """Test all registry values are strings."""
        for value in SPECIAL_PHASE_METHODS.values():
            assert isinstance(value, str)

    def test_all_values_are_method_names(self):
        """Test all registry values follow method naming convention."""
        for value in SPECIAL_PHASE_METHODS.values():
            assert value.startswith("_execute_")
            assert value.endswith("_batched")

    def test_all_keys_are_kebab_case(self):
        """Test all registry keys use kebab-case."""
        for key in SPECIAL_PHASE_METHODS:
            assert "-" in key
            assert "_" not in key
            assert key == key.lower()

    def test_expected_phases_present(self):
        """Test all expected special phases are in registry."""
        expected_phases = [
            "research-tracer-bullet",
            "research-gatherers-web-compilation",
            "diagnostics-handoff-bundle",
            "diagnostics-cursor-prompt",
            "diagnostics-second-opinion-triage",
            "diagnostics-deep-retrieval",
            "diagnostics-iteration-loop",
            # IMP-LOOP-004: Generated task execution handler
            "generated-task-execution",
        ]
        for phase in expected_phases:
            assert phase in SPECIAL_PHASE_METHODS

    def test_research_phases_count(self):
        """Test correct number of research phases."""
        research_phases = [k for k in SPECIAL_PHASE_METHODS if k.startswith("research-")]
        assert len(research_phases) == 2

    def test_diagnostics_phases_count(self):
        """Test correct number of diagnostics phases."""
        diagnostics_phases = [k for k in SPECIAL_PHASE_METHODS if k.startswith("diagnostics-")]
        assert len(diagnostics_phases) == 5


class TestPhaseDispatchEdgeCases:
    """Test edge cases and integration scenarios."""

    def test_all_registered_phases_resolve_correctly(self):
        """Test that all registered phases resolve to their handlers."""
        for phase_id, expected_method in SPECIAL_PHASE_METHODS.items():
            result = resolve_special_phase_method(phase_id)
            assert result == expected_method, f"Phase {phase_id} did not resolve correctly"

    def test_resolve_is_idempotent(self):
        """Test that resolving the same phase multiple times returns same result."""
        phase_id = "research-tracer-bullet"
        result1 = resolve_special_phase_method(phase_id)
        result2 = resolve_special_phase_method(phase_id)
        result3 = resolve_special_phase_method(phase_id)

        assert result1 == result2 == result3

    def test_registry_not_modified_by_resolve(self):
        """Test that resolve function doesn't modify the registry."""
        original_len = len(SPECIAL_PHASE_METHODS)
        original_keys = set(SPECIAL_PHASE_METHODS.keys())

        resolve_special_phase_method("research-tracer-bullet")
        resolve_special_phase_method("unknown-phase")
        resolve_special_phase_method(None)

        assert len(SPECIAL_PHASE_METHODS) == original_len
        assert set(SPECIAL_PHASE_METHODS.keys()) == original_keys


class TestGeneratedTaskExecutionHandler:
    """Test generated-task-execution handler (IMP-LOOP-004)."""

    def test_generated_task_handler_registered(self):
        """Test generated-task-execution handler is in registry."""
        assert "generated-task-execution" in SPECIAL_PHASE_METHODS

    def test_generated_task_handler_follows_naming_convention(self):
        """Test handler follows _execute_*_batched naming convention."""
        handler = SPECIAL_PHASE_METHODS["generated-task-execution"]
        assert handler.startswith("_execute_")
        assert handler.endswith("_batched")

    def test_generated_task_phase_resolves(self):
        """Test generated-task-execution resolves to handler."""
        result = resolve_special_phase_method("generated-task-execution")
        assert result is not None
        assert result == "_execute_generated_task_batched"

    def test_generated_task_prefixed_phases_dont_match(self):
        """Test that prefixed/suffixed variants don't match."""
        # Variations should not resolve
        assert resolve_special_phase_method("generated-task-execution-1") is None
        assert resolve_special_phase_method("test-generated-task-execution") is None
        assert resolve_special_phase_method("generated-task") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
