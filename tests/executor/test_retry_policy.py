"""
Tests for Retry Policy Module

Tests for pure retry/escalation decision functions (IMP-ARCH-007).
These are deterministic, testable decision functions with no side effects.
"""

import pytest

from autopack.executor.retry_policy import (
    AttemptContext,
    AttemptDecision,
    choose_model_for_attempt,
    next_attempt_state,
    should_escalate,
    should_run_diagnostics,
)


class TestShouldEscalate:
    """Tests for should_escalate function."""

    def test_token_escalation_status_requires_escalation(self):
        """Verify TOKEN_ESCALATION status triggers escalation."""
        assert should_escalate("TOKEN_ESCALATION") is True

    def test_other_statuses_do_not_escalate(self):
        """Verify other statuses do not trigger escalation."""
        statuses = ["COMPLETE", "FAILED", "BLOCKED", "PATCH_FAILED"]
        for status in statuses:
            assert should_escalate(status) is False

    def test_unknown_status_does_not_escalate(self):
        """Verify unknown status strings do not trigger escalation."""
        assert should_escalate("UNKNOWN_STATUS") is False

    def test_case_sensitive_token_escalation(self):
        """Verify TOKEN_ESCALATION is case-sensitive."""
        assert should_escalate("token_escalation") is False
        assert should_escalate("Token_Escalation") is False
        assert should_escalate("TOKEN_ESCALATION") is True

    def test_empty_status_does_not_escalate(self):
        """Verify empty status string does not escalate."""
        assert should_escalate("") is False


class TestShouldRunDiagnostics:
    """Tests for should_run_diagnostics function."""

    def test_token_escalation_skips_diagnostics(self):
        """Verify TOKEN_ESCALATION does not trigger diagnostics (BUILD-129)."""
        assert should_run_diagnostics("TOKEN_ESCALATION") is False

    def test_complete_status_skips_diagnostics(self):
        """Verify COMPLETE status does not trigger diagnostics."""
        assert should_run_diagnostics("COMPLETE") is False

    def test_failed_status_triggers_diagnostics(self):
        """Verify FAILED status triggers diagnostics."""
        assert should_run_diagnostics("FAILED") is True

    def test_blocked_status_triggers_diagnostics(self):
        """Verify BLOCKED status triggers diagnostics."""
        assert should_run_diagnostics("BLOCKED") is True

    def test_patch_failed_status_triggers_diagnostics(self):
        """Verify PATCH_FAILED status triggers diagnostics."""
        assert should_run_diagnostics("PATCH_FAILED") is True

    def test_unknown_status_triggers_diagnostics(self):
        """Verify unknown status triggers diagnostics (as fallback)."""
        assert should_run_diagnostics("UNKNOWN_STATUS") is True

    def test_all_failure_statuses_trigger_diagnostics(self):
        """Verify all failure statuses trigger diagnostics."""
        failure_statuses = ["FAILED", "BLOCKED", "PATCH_FAILED", "ERROR", "TIMEOUT"]
        for status in failure_statuses:
            assert should_run_diagnostics(status) is True


class TestAttemptContext:
    """Tests for AttemptContext dataclass."""

    def test_create_attempt_context(self):
        """Verify AttemptContext can be created."""
        ctx = AttemptContext(attempt_index=0, max_attempts=5, escalation_level=0)
        assert ctx.attempt_index == 0
        assert ctx.max_attempts == 5
        assert ctx.escalation_level == 0

    def test_attempt_context_immutable(self):
        """Verify AttemptContext is immutable."""
        ctx = AttemptContext(attempt_index=0, max_attempts=5, escalation_level=0)
        with pytest.raises(AttributeError):
            ctx.attempt_index = 1

    def test_various_escalation_levels(self):
        """Verify AttemptContext handles various escalation levels."""
        for level in [0, 1, 2, 3]:
            ctx = AttemptContext(attempt_index=0, max_attempts=5, escalation_level=level)
            assert ctx.escalation_level == level


class TestAttemptDecision:
    """Tests for AttemptDecision dataclass."""

    def test_create_attempt_decision(self):
        """Verify AttemptDecision can be created."""
        decision = AttemptDecision(
            next_retry_attempt=1,
            should_run_diagnostics=True,
            should_escalate_model=False,
            terminal=False,
        )
        assert decision.next_retry_attempt == 1
        assert decision.should_run_diagnostics is True
        assert decision.should_escalate_model is False
        assert decision.terminal is False

    def test_attempt_decision_immutable(self):
        """Verify AttemptDecision is immutable."""
        decision = AttemptDecision(
            next_retry_attempt=None,
            should_run_diagnostics=False,
            should_escalate_model=False,
            terminal=True,
        )
        with pytest.raises(AttributeError):
            decision.terminal = False

    def test_decision_with_none_next_retry(self):
        """Verify AttemptDecision can have None next_retry_attempt."""
        decision = AttemptDecision(
            next_retry_attempt=None,
            should_run_diagnostics=False,
            should_escalate_model=False,
            terminal=True,
        )
        assert decision.next_retry_attempt is None


class TestNextAttemptState:
    """Tests for next_attempt_state function."""

    def test_zero_max_attempts_is_terminal(self):
        """Verify zero max_attempts results in terminal decision."""
        ctx = AttemptContext(attempt_index=0, max_attempts=0, escalation_level=0)
        decision = next_attempt_state(ctx, "FAILED")

        assert decision.terminal is True
        assert decision.next_retry_attempt is None
        assert decision.should_run_diagnostics is False
        assert decision.should_escalate_model is False

    def test_negative_max_attempts_is_terminal(self):
        """Verify negative max_attempts results in terminal decision."""
        ctx = AttemptContext(attempt_index=0, max_attempts=-1, escalation_level=0)
        decision = next_attempt_state(ctx, "FAILED")

        assert decision.terminal is True

    def test_attempt_index_exceeds_max_is_terminal(self):
        """Verify attempt_index >= max_attempts is terminal."""
        ctx = AttemptContext(attempt_index=5, max_attempts=5, escalation_level=0)
        decision = next_attempt_state(ctx, "FAILED")

        assert decision.terminal is True
        assert decision.next_retry_attempt is None

    def test_complete_status_is_terminal(self):
        """Verify COMPLETE status results in terminal decision."""
        ctx = AttemptContext(attempt_index=0, max_attempts=5, escalation_level=0)
        decision = next_attempt_state(ctx, "COMPLETE")

        assert decision.terminal is True
        assert decision.should_run_diagnostics is False
        assert decision.should_escalate_model is False
        assert decision.next_retry_attempt is None

    def test_token_escalation_advances_attempt(self):
        """Verify TOKEN_ESCALATION advances retry attempt without diagnostics."""
        ctx = AttemptContext(attempt_index=0, max_attempts=3, escalation_level=0)
        decision = next_attempt_state(ctx, "TOKEN_ESCALATION")

        assert decision.next_retry_attempt == 1
        assert decision.should_run_diagnostics is False
        assert decision.should_escalate_model is False
        assert decision.terminal is False

    def test_token_escalation_at_last_attempt_is_terminal(self):
        """Verify TOKEN_ESCALATION at last attempt is terminal."""
        ctx = AttemptContext(attempt_index=2, max_attempts=3, escalation_level=0)
        decision = next_attempt_state(ctx, "TOKEN_ESCALATION")

        assert decision.next_retry_attempt == 3
        assert decision.terminal is True

    def test_failed_status_advances_attempt_with_diagnostics(self):
        """Verify FAILED status advances attempt and triggers diagnostics."""
        ctx = AttemptContext(attempt_index=0, max_attempts=3, escalation_level=0)
        decision = next_attempt_state(ctx, "FAILED")

        assert decision.next_retry_attempt == 1
        assert decision.should_run_diagnostics is True
        assert decision.should_escalate_model is False
        assert decision.terminal is False

    def test_blocked_status_triggers_diagnostics(self):
        """Verify BLOCKED status triggers diagnostics."""
        ctx = AttemptContext(attempt_index=0, max_attempts=3, escalation_level=0)
        decision = next_attempt_state(ctx, "BLOCKED")

        assert decision.should_run_diagnostics is True
        assert decision.next_retry_attempt == 1

    def test_patch_failed_status_triggers_diagnostics(self):
        """Verify PATCH_FAILED status triggers diagnostics."""
        ctx = AttemptContext(attempt_index=0, max_attempts=3, escalation_level=0)
        decision = next_attempt_state(ctx, "PATCH_FAILED")

        assert decision.should_run_diagnostics is True
        assert decision.next_retry_attempt == 1

    def test_unknown_status_triggers_diagnostics(self):
        """Verify unknown status triggers diagnostics."""
        ctx = AttemptContext(attempt_index=0, max_attempts=3, escalation_level=0)
        decision = next_attempt_state(ctx, "UNKNOWN_STATUS")

        assert decision.should_run_diagnostics is True
        assert decision.next_retry_attempt == 1

    def test_multiple_attempts_progression(self):
        """Verify attempt progression across multiple failures."""
        for attempt_idx in range(2):  # Attempt 0 and 1
            ctx = AttemptContext(attempt_index=attempt_idx, max_attempts=3, escalation_level=0)
            decision = next_attempt_state(ctx, "FAILED")

            assert decision.next_retry_attempt == attempt_idx + 1
            assert decision.terminal is False

        # Final attempt (index 2, max 3 - next would be 3 which equals max)
        ctx = AttemptContext(attempt_index=2, max_attempts=3, escalation_level=0)
        decision = next_attempt_state(ctx, "FAILED")
        assert decision.terminal is True

    def test_first_attempt_context(self):
        """Verify first attempt (index 0) behavior."""
        ctx = AttemptContext(attempt_index=0, max_attempts=5, escalation_level=0)
        decision = next_attempt_state(ctx, "FAILED")

        assert decision.next_retry_attempt == 1
        assert decision.terminal is False
        assert decision.should_run_diagnostics is True

    def test_escalation_level_preserved_in_context(self):
        """Verify escalation_level is preserved (for future use)."""
        for level in [0, 1, 2]:
            ctx = AttemptContext(attempt_index=0, max_attempts=5, escalation_level=level)
            decision = next_attempt_state(ctx, "FAILED")

            # Escalation level doesn't affect current decision logic
            # but is preserved in context for future use
            assert ctx.escalation_level == level

    def test_complete_overrides_other_logic(self):
        """Verify COMPLETE status overrides other retry logic."""
        # Even at attempt 0, COMPLETE should be terminal
        ctx = AttemptContext(attempt_index=0, max_attempts=1, escalation_level=0)
        decision = next_attempt_state(ctx, "COMPLETE")

        assert decision.terminal is True
        assert decision.next_retry_attempt is None
        assert decision.should_run_diagnostics is False

    def test_status_comparison_case_sensitive(self):
        """Verify status comparison is case-sensitive."""
        ctx = AttemptContext(attempt_index=0, max_attempts=3, escalation_level=0)

        # Lowercase should not match TOKEN_ESCALATION special case
        decision = next_attempt_state(ctx, "token_escalation")
        assert decision.should_run_diagnostics is True

    def test_high_escalation_level(self):
        """Verify high escalation levels are handled."""
        ctx = AttemptContext(attempt_index=0, max_attempts=5, escalation_level=100)
        decision = next_attempt_state(ctx, "FAILED")

        # Escalation level doesn't affect current logic
        assert decision.next_retry_attempt == 1
        assert decision.terminal is False


class TestChooseModelForAttempt:
    """Tests for choose_model_for_attempt function."""

    def test_returns_none_by_default(self):
        """Verify choose_model_for_attempt defers to ModelRouter."""
        ctx = AttemptContext(attempt_index=0, max_attempts=5, escalation_level=0)
        result = choose_model_for_attempt(ctx)

        assert result is None

    def test_returns_none_at_various_attempts(self):
        """Verify choose_model_for_attempt returns None at all attempt levels."""
        for attempt_idx in range(5):
            ctx = AttemptContext(attempt_index=attempt_idx, max_attempts=5, escalation_level=0)
            result = choose_model_for_attempt(ctx)
            assert result is None

    def test_returns_none_with_escalation_levels(self):
        """Verify choose_model_for_attempt returns None regardless of escalation."""
        for level in [0, 1, 2, 3]:
            ctx = AttemptContext(attempt_index=0, max_attempts=5, escalation_level=level)
            result = choose_model_for_attempt(ctx)
            assert result is None


class TestRetryPolicyIntegration:
    """Integration tests for retry policy decision-making."""

    def test_full_retry_sequence(self):
        """Verify a full retry sequence from start to terminal."""
        max_attempts = 3

        # Attempt 0 - FAILED
        ctx = AttemptContext(attempt_index=0, max_attempts=max_attempts, escalation_level=0)
        decision = next_attempt_state(ctx, "FAILED")
        assert decision.next_retry_attempt == 1
        assert decision.terminal is False

        # Attempt 1 - FAILED
        ctx = AttemptContext(attempt_index=1, max_attempts=max_attempts, escalation_level=0)
        decision = next_attempt_state(ctx, "FAILED")
        assert decision.next_retry_attempt == 2
        assert decision.terminal is False

        # Attempt 2 - COMPLETE
        ctx = AttemptContext(attempt_index=2, max_attempts=max_attempts, escalation_level=0)
        decision = next_attempt_state(ctx, "COMPLETE")
        assert decision.terminal is True

    def test_token_escalation_sequence(self):
        """Verify TOKEN_ESCALATION sequence without diagnostics."""
        max_attempts = 3

        # Attempt 0 - TOKEN_ESCALATION
        ctx = AttemptContext(attempt_index=0, max_attempts=max_attempts, escalation_level=0)
        decision = next_attempt_state(ctx, "TOKEN_ESCALATION")
        assert decision.should_run_diagnostics is False
        assert decision.next_retry_attempt == 1

        # Attempt 1 - TOKEN_ESCALATION
        ctx = AttemptContext(attempt_index=1, max_attempts=max_attempts, escalation_level=0)
        decision = next_attempt_state(ctx, "TOKEN_ESCALATION")
        assert decision.should_run_diagnostics is False

    def test_mixed_status_sequence(self):
        """Verify mixed status sequence (TOKEN_ESCALATION then FAILED then COMPLETE)."""
        max_attempts = 4

        # Attempt 0 - TOKEN_ESCALATION (no diagnostics)
        ctx = AttemptContext(attempt_index=0, max_attempts=max_attempts, escalation_level=0)
        decision = next_attempt_state(ctx, "TOKEN_ESCALATION")
        assert decision.should_run_diagnostics is False
        assert decision.next_retry_attempt == 1

        # Attempt 1 - FAILED (with diagnostics)
        ctx = AttemptContext(attempt_index=1, max_attempts=max_attempts, escalation_level=0)
        decision = next_attempt_state(ctx, "FAILED")
        assert decision.should_run_diagnostics is True
        assert decision.next_retry_attempt == 2

        # Attempt 2 - COMPLETE (terminal)
        ctx = AttemptContext(attempt_index=2, max_attempts=max_attempts, escalation_level=0)
        decision = next_attempt_state(ctx, "COMPLETE")
        assert decision.terminal is True

    def test_all_attempts_exhausted(self):
        """Verify decision when all attempts are exhausted."""
        max_attempts = 2

        # Exhaust all attempts with failures
        for attempt_idx in range(max_attempts):
            ctx = AttemptContext(
                attempt_index=attempt_idx, max_attempts=max_attempts, escalation_level=0
            )
            decision = next_attempt_state(ctx, "FAILED")
            if attempt_idx < max_attempts - 1:
                assert decision.terminal is False
            else:
                assert decision.terminal is True
