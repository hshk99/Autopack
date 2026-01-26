"""Unit tests for executor.attempt_runner module.

Tests for the single-attempt execution wrapper with error recovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Tuple

import pytest

from autopack.executor.attempt_runner import AttemptRunResult, run_single_attempt_with_recovery


@dataclass
class FakeErrorRecovery:
    """Fake error recovery that records calls and returns configured result."""

    call_count: int = 0
    last_func: Callable | None = None
    last_operation_name: str | None = None
    last_max_retries: int | None = None
    configured_result: Tuple[bool, str] = (True, "COMPLETE")

    def execute_with_retry(
        self,
        func: Callable,
        operation_name: str = "",
        max_retries: int = 1,
    ) -> Tuple[bool, str]:
        self.call_count += 1
        self.last_func = func
        self.last_operation_name = operation_name
        self.last_max_retries = max_retries
        # Actually call the function to verify it would work
        func()
        return self.configured_result


@dataclass
class FakeExecutor:
    """Fake executor with error_recovery and _execute_phase_with_recovery."""

    error_recovery: Any
    execute_phase_calls: list = None

    def __post_init__(self) -> None:
        if self.execute_phase_calls is None:
            self.execute_phase_calls = []

    def _execute_phase_with_recovery(
        self,
        phase: dict,
        attempt_index: int,
        allowed_paths: list[str] | None,
        memory_context: str | None = None,  # IMP-ARCH-002: memory context injection
        context_reduction_factor: float | None = None,  # IMP-TEL-005: telemetry adjustment
        model_downgrade: str | None = None,  # IMP-TEL-005: telemetry adjustment
    ) -> Tuple[bool, str]:
        self.execute_phase_calls.append(
            {
                "phase": phase,
                "attempt_index": attempt_index,
                "allowed_paths": allowed_paths,
                "memory_context": memory_context,
                "context_reduction_factor": context_reduction_factor,
                "model_downgrade": model_downgrade,
            }
        )
        return (True, "COMPLETE")


class TestRunSingleAttemptWithRecovery:
    """Tests for run_single_attempt_with_recovery."""

    def test_calls_execute_phase_with_recovery_via_error_recovery(self) -> None:
        """Verify the function calls _execute_phase_with_recovery through error_recovery."""
        error_recovery = FakeErrorRecovery(configured_result=(True, "COMPLETE"))
        executor = FakeExecutor(error_recovery=error_recovery)
        phase = {"phase_id": "test-phase", "name": "Test Phase"}

        result = run_single_attempt_with_recovery(
            executor=executor,
            phase=phase,
            attempt_index=0,
            allowed_paths=["src/"],
        )

        # Verify error_recovery.execute_with_retry was called
        assert error_recovery.call_count == 1
        assert "Phase execution: test-phase" in error_recovery.last_operation_name
        assert error_recovery.last_max_retries == 1

        # Verify _execute_phase_with_recovery was called with correct params
        assert len(executor.execute_phase_calls) == 1
        call = executor.execute_phase_calls[0]
        assert call["phase"] == phase
        assert call["attempt_index"] == 0
        assert call["allowed_paths"] == ["src/"]

        # Verify result
        assert result == AttemptRunResult(success=True, status="COMPLETE")

    def test_returns_failure_result(self) -> None:
        """Verify failure results are returned correctly."""
        error_recovery = FakeErrorRecovery(configured_result=(False, "FAILED"))
        executor = FakeExecutor(error_recovery=error_recovery)
        phase = {"phase_id": "fail-phase"}

        result = run_single_attempt_with_recovery(
            executor=executor,
            phase=phase,
            attempt_index=2,
            allowed_paths=None,
        )

        assert result == AttemptRunResult(success=False, status="FAILED")

    def test_returns_token_escalation_status(self) -> None:
        """Verify TOKEN_ESCALATION status is returned correctly."""
        error_recovery = FakeErrorRecovery(configured_result=(False, "TOKEN_ESCALATION"))
        executor = FakeExecutor(error_recovery=error_recovery)
        phase = {"phase_id": "escalate-phase"}

        result = run_single_attempt_with_recovery(
            executor=executor,
            phase=phase,
            attempt_index=1,
            allowed_paths=["tests/"],
        )

        assert result == AttemptRunResult(success=False, status="TOKEN_ESCALATION")

    def test_passes_none_allowed_paths(self) -> None:
        """Verify None allowed_paths is passed through correctly."""
        error_recovery = FakeErrorRecovery(configured_result=(True, "COMPLETE"))
        executor = FakeExecutor(error_recovery=error_recovery)
        phase = {"phase_id": "no-scope-phase"}

        run_single_attempt_with_recovery(
            executor=executor,
            phase=phase,
            attempt_index=0,
            allowed_paths=None,
        )

        assert executor.execute_phase_calls[0]["allowed_paths"] is None

    def test_operation_name_includes_phase_id(self) -> None:
        """Verify operation name includes the phase_id for logging/tracing."""
        error_recovery = FakeErrorRecovery(configured_result=(True, "COMPLETE"))
        executor = FakeExecutor(error_recovery=error_recovery)
        phase = {"phase_id": "my-unique-phase-123"}

        run_single_attempt_with_recovery(
            executor=executor,
            phase=phase,
            attempt_index=0,
            allowed_paths=None,
        )

        assert "my-unique-phase-123" in error_recovery.last_operation_name


class TestAttemptRunResult:
    """Tests for AttemptRunResult dataclass."""

    def test_result_is_immutable(self) -> None:
        """Verify AttemptRunResult is frozen (immutable)."""
        result = AttemptRunResult(success=True, status="COMPLETE")
        with pytest.raises(Exception):  # FrozenInstanceError
            result.success = False  # type: ignore

    def test_equality(self) -> None:
        """Verify AttemptRunResult equality comparison."""
        r1 = AttemptRunResult(success=True, status="COMPLETE")
        r2 = AttemptRunResult(success=True, status="COMPLETE")
        r3 = AttemptRunResult(success=False, status="FAILED")

        assert r1 == r2
        assert r1 != r3
