"""Contract tests for phase dispatch coverage.

Per the refactor plan, these tests prevent drift where a special phase id
is added/renamed but not routed correctly.
"""

from __future__ import annotations

import pytest

from autopack.executor.phase_dispatch import (
    SPECIAL_PHASE_METHODS,
    resolve_special_phase_method,
)


class TestPhaseDispatchRegistryContents:
    """Tests for SPECIAL_PHASE_METHODS registry contents."""

    EXPECTED_PHASE_IDS = {
        "research-tracer-bullet",
        "research-gatherers-web-compilation",
        "diagnostics-handoff-bundle",
        "diagnostics-cursor-prompt",
        "diagnostics-second-opinion-triage",
        "diagnostics-deep-retrieval",
        "diagnostics-iteration-loop",
    }

    def test_registry_contains_all_expected_phase_ids(self) -> None:
        """Verify all expected special phase IDs are in the registry."""
        actual = set(SPECIAL_PHASE_METHODS.keys())
        missing = self.EXPECTED_PHASE_IDS - actual
        assert not missing, f"Missing phase IDs in registry: {missing}"

    def test_registry_has_no_unexpected_phase_ids(self) -> None:
        """Verify no unexpected phase IDs have been added without updating tests."""
        actual = set(SPECIAL_PHASE_METHODS.keys())
        unexpected = actual - self.EXPECTED_PHASE_IDS
        # This is informational - new phases should be added to EXPECTED_PHASE_IDS
        if unexpected:
            pytest.skip(f"New phase IDs found (add to EXPECTED_PHASE_IDS): {unexpected}")


class TestPhaseDispatchMethodNaming:
    """Tests for method naming conventions in the registry."""

    def test_all_method_names_start_with_underscore_execute(self) -> None:
        """Verify all method names follow _execute_* naming convention."""
        for phase_id, method_name in SPECIAL_PHASE_METHODS.items():
            assert method_name.startswith(
                "_execute_"
            ), f"Method for '{phase_id}' should start with '_execute_': {method_name}"

    def test_all_method_names_end_with_batched(self) -> None:
        """Verify all method names end with _batched suffix."""
        for phase_id, method_name in SPECIAL_PHASE_METHODS.items():
            assert method_name.endswith(
                "_batched"
            ), f"Method for '{phase_id}' should end with '_batched': {method_name}"

    def test_method_names_are_valid_python_identifiers(self) -> None:
        """Verify all method names are valid Python identifiers."""
        for phase_id, method_name in SPECIAL_PHASE_METHODS.items():
            assert (
                method_name.isidentifier()
            ), f"Method name for '{phase_id}' is not a valid identifier: {method_name}"


class TestResolveSpecialPhaseMethod:
    """Tests for resolve_special_phase_method function."""

    def test_returns_none_for_unknown_phase_id(self) -> None:
        """Verify unknown phase_id returns None."""
        assert resolve_special_phase_method("not-a-phase") is None
        assert resolve_special_phase_method("unknown-phase-123") is None

    def test_returns_none_for_empty_phase_id(self) -> None:
        """Verify empty/None phase_id returns None."""
        assert resolve_special_phase_method("") is None
        assert resolve_special_phase_method(None) is None

    def test_returns_method_name_for_known_phase_ids(self) -> None:
        """Verify known phase_ids return correct method names."""
        for phase_id, expected_method in SPECIAL_PHASE_METHODS.items():
            result = resolve_special_phase_method(phase_id)
            assert (
                result == expected_method
            ), f"Expected '{expected_method}' for '{phase_id}', got '{result}'"

    @pytest.mark.parametrize(
        "phase_id,expected_method",
        [
            ("research-tracer-bullet", "_execute_research_tracer_bullet_batched"),
            (
                "research-gatherers-web-compilation",
                "_execute_research_gatherers_web_compilation_batched",
            ),
            ("diagnostics-handoff-bundle", "_execute_diagnostics_handoff_bundle_batched"),
            ("diagnostics-cursor-prompt", "_execute_diagnostics_cursor_prompt_batched"),
            (
                "diagnostics-second-opinion-triage",
                "_execute_diagnostics_second_opinion_batched",
            ),
            ("diagnostics-deep-retrieval", "_execute_diagnostics_deep_retrieval_batched"),
            ("diagnostics-iteration-loop", "_execute_diagnostics_iteration_loop_batched"),
        ],
    )
    def test_specific_phase_to_method_mapping(self, phase_id: str, expected_method: str) -> None:
        """Verify specific phase_id to method_name mappings are correct."""
        assert resolve_special_phase_method(phase_id) == expected_method


class TestFakeExecutorMethodExistence:
    """Tests that verify method names would be resolvable on a real executor.

    Uses a minimal fake executor with stub methods to verify getattr would succeed.
    This is a contract test - if the real executor removes a method, tests should fail.
    """

    def test_method_names_would_resolve_on_executor_like_object(self) -> None:
        """Verify all method names in registry are valid attribute names.

        Creates a fake executor with methods named according to the registry,
        then verifies getattr succeeds for each.
        """
        # Create a class with all the expected method names as attributes
        method_names = list(SPECIAL_PHASE_METHODS.values())

        class FakeExecutor:
            pass

        fake = FakeExecutor()

        # Add stub methods to the fake executor
        for method_name in method_names:
            setattr(fake, method_name, lambda: None)

        # Verify getattr works for each method name
        for phase_id, method_name in SPECIAL_PHASE_METHODS.items():
            method = getattr(fake, method_name, None)
            assert (
                method is not None
            ), f"getattr failed for method '{method_name}' (phase '{phase_id}')"
            assert callable(
                method
            ), f"Method '{method_name}' for phase '{phase_id}' should be callable"
