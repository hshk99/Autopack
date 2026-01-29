"""Unit tests for executor.retry_policy module.

Tests for pure retry/escalation decision functions, table-driven.
"""

from __future__ import annotations

import pytest

from autopack.executor.retry_policy import (AttemptContext, AttemptDecision,
                                            choose_model_for_attempt,
                                            next_attempt_state,
                                            should_escalate,
                                            should_run_diagnostics)


# ============================================================================
# Test: should_escalate
# ============================================================================
class TestShouldEscalate:
    @pytest.mark.parametrize(
        "status,expected",
        [
            ("TOKEN_ESCALATION", True),
            ("COMPLETE", False),
            ("FAILED", False),
            ("BLOCKED", False),
            ("PATCH_FAILED", False),
            ("", False),
        ],
    )
    def test_should_escalate(self, status: str, expected: bool) -> None:
        assert should_escalate(status) is expected


# ============================================================================
# Test: should_run_diagnostics
# ============================================================================
class TestShouldRunDiagnostics:
    @pytest.mark.parametrize(
        "status,expected",
        [
            ("TOKEN_ESCALATION", False),  # P10: don't run diagnostics for token escalation
            ("COMPLETE", False),  # success: no diagnostics needed
            ("FAILED", True),
            ("BLOCKED", True),
            ("PATCH_FAILED", True),
            ("", True),  # unknown failures should trigger diagnostics
        ],
    )
    def test_should_run_diagnostics(self, status: str, expected: bool) -> None:
        assert should_run_diagnostics(status) is expected


# ============================================================================
# Test: next_attempt_state - table-driven
# ============================================================================
class TestNextAttemptState:
    """Table-driven tests for next_attempt_state decision logic."""

    @pytest.mark.parametrize(
        "ctx,status,expected",
        [
            # TOKEN_ESCALATION: advance retry_attempt, no diagnostics, not terminal
            pytest.param(
                AttemptContext(attempt_index=0, max_attempts=5, escalation_level=0),
                "TOKEN_ESCALATION",
                AttemptDecision(
                    next_retry_attempt=1,
                    should_run_diagnostics=False,
                    should_escalate_model=False,
                    terminal=False,
                ),
                id="token_escalation_from_attempt_0",
            ),
            pytest.param(
                AttemptContext(attempt_index=2, max_attempts=5, escalation_level=0),
                "TOKEN_ESCALATION",
                AttemptDecision(
                    next_retry_attempt=3,
                    should_run_diagnostics=False,
                    should_escalate_model=False,
                    terminal=False,
                ),
                id="token_escalation_from_attempt_2",
            ),
            # COMPLETE: success, no state change needed
            pytest.param(
                AttemptContext(attempt_index=0, max_attempts=5, escalation_level=0),
                "COMPLETE",
                AttemptDecision(
                    next_retry_attempt=None,
                    should_run_diagnostics=False,
                    should_escalate_model=False,
                    terminal=True,
                ),
                id="complete_success",
            ),
            # FAILED: normal failure -> advance retry, run diagnostics
            pytest.param(
                AttemptContext(attempt_index=0, max_attempts=5, escalation_level=0),
                "FAILED",
                AttemptDecision(
                    next_retry_attempt=1,
                    should_run_diagnostics=True,
                    should_escalate_model=False,
                    terminal=False,
                ),
                id="failed_attempt_0",
            ),
            pytest.param(
                AttemptContext(attempt_index=1, max_attempts=5, escalation_level=0),
                "FAILED",
                AttemptDecision(
                    next_retry_attempt=2,
                    should_run_diagnostics=True,
                    should_escalate_model=False,
                    terminal=False,
                ),
                id="failed_attempt_1",
            ),
            # FAILED at max attempts - 1: advance and become terminal
            pytest.param(
                AttemptContext(attempt_index=4, max_attempts=5, escalation_level=0),
                "FAILED",
                AttemptDecision(
                    next_retry_attempt=5,
                    should_run_diagnostics=True,
                    should_escalate_model=False,
                    terminal=True,
                ),
                id="failed_at_max_minus_one_becomes_terminal",
            ),
            # Already exhausted: terminal immediately
            pytest.param(
                AttemptContext(attempt_index=5, max_attempts=5, escalation_level=0),
                "FAILED",
                AttemptDecision(
                    next_retry_attempt=None,
                    should_run_diagnostics=False,
                    should_escalate_model=False,
                    terminal=True,
                ),
                id="exhausted_attempts_terminal",
            ),
            # BLOCKED: same as FAILED but status is different
            pytest.param(
                AttemptContext(attempt_index=1, max_attempts=5, escalation_level=0),
                "BLOCKED",
                AttemptDecision(
                    next_retry_attempt=2,
                    should_run_diagnostics=True,
                    should_escalate_model=False,
                    terminal=False,
                ),
                id="blocked_attempt_1",
            ),
            # PATCH_FAILED: same treatment as FAILED
            pytest.param(
                AttemptContext(attempt_index=2, max_attempts=5, escalation_level=0),
                "PATCH_FAILED",
                AttemptDecision(
                    next_retry_attempt=3,
                    should_run_diagnostics=True,
                    should_escalate_model=False,
                    terminal=False,
                ),
                id="patch_failed_attempt_2",
            ),
        ],
    )
    def test_next_attempt_state(
        self, ctx: AttemptContext, status: str, expected: AttemptDecision
    ) -> None:
        result = next_attempt_state(ctx, status)
        assert result == expected


class TestNextAttemptStateEdgeCases:
    """Edge cases and boundary conditions for next_attempt_state."""

    def test_max_attempts_of_one(self) -> None:
        """Single attempt scenario: first failure is terminal."""
        ctx = AttemptContext(attempt_index=0, max_attempts=1, escalation_level=0)
        result = next_attempt_state(ctx, "FAILED")
        # Next attempt would be 1, which equals max_attempts, so terminal
        assert result.terminal is True
        assert result.next_retry_attempt == 1

    def test_zero_max_attempts_always_terminal(self) -> None:
        """Zero max attempts: always terminal."""
        ctx = AttemptContext(attempt_index=0, max_attempts=0, escalation_level=0)
        result = next_attempt_state(ctx, "FAILED")
        assert result.terminal is True
        assert result.next_retry_attempt is None

    def test_token_escalation_at_max_attempts(self) -> None:
        """TOKEN_ESCALATION at max still advances but becomes terminal."""
        ctx = AttemptContext(attempt_index=4, max_attempts=5, escalation_level=0)
        result = next_attempt_state(ctx, "TOKEN_ESCALATION")
        assert result.next_retry_attempt == 5
        assert result.should_run_diagnostics is False
        assert result.terminal is True


# ============================================================================
# Test: choose_model_for_attempt
# ============================================================================
class TestChooseModelForAttempt:
    """Tests for choose_model_for_attempt function.

    Currently this function always returns None, deferring to ModelRouter.
    These tests document the expected behavior and guard against regressions.
    """

    @pytest.mark.parametrize(
        "attempt_index,max_attempts,escalation_level",
        [
            (0, 5, 0),  # First attempt, base level
            (1, 5, 0),  # Mid attempt, base level
            (4, 5, 0),  # Last attempt, base level
            (0, 5, 1),  # First attempt, escalated level
            (2, 5, 2),  # Mid attempt, higher escalation
            (0, 1, 0),  # Single attempt scenario
            (0, 10, 3),  # High escalation level
        ],
    )
    def test_choose_model_for_attempt_returns_none(
        self, attempt_index: int, max_attempts: int, escalation_level: int
    ) -> None:
        """Verify choose_model_for_attempt defers to ModelRouter (returns None)."""
        ctx = AttemptContext(
            attempt_index=attempt_index,
            max_attempts=max_attempts,
            escalation_level=escalation_level,
        )
        result = choose_model_for_attempt(ctx)
        assert result is None

    def test_choose_model_for_attempt_is_pure_function(self) -> None:
        """Verify function is pure: same input always produces same output."""
        ctx = AttemptContext(attempt_index=2, max_attempts=5, escalation_level=1)
        result1 = choose_model_for_attempt(ctx)
        result2 = choose_model_for_attempt(ctx)
        assert result1 == result2
        assert result1 is None
