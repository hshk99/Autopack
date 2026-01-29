"""Tests for IMP-COST-001: Per-run budget enforcement with automatic abort."""

import pytest

from autopack.autonomous.budgeting import (BudgetExhaustedError,
                                           get_budget_remaining_pct,
                                           is_budget_exhausted)


class TestBudgetExhaustion:
    """Tests for budget exhaustion detection."""

    def test_budget_exhausted_when_tokens_exceed_cap(self):
        """Verify budget is detected as exhausted when tokens exceed cap."""
        assert is_budget_exhausted(token_cap=1000, tokens_used=1001) is True
        assert is_budget_exhausted(token_cap=1000, tokens_used=1000) is True

    def test_budget_not_exhausted_when_tokens_under_cap(self):
        """Verify budget is not exhausted when under cap."""
        assert is_budget_exhausted(token_cap=1000, tokens_used=999) is False
        assert is_budget_exhausted(token_cap=1000, tokens_used=0) is False

    def test_budget_not_exhausted_when_cap_is_none(self):
        """Verify None cap means unlimited budget."""
        assert is_budget_exhausted(token_cap=None, tokens_used=1000000) is False


class TestBudgetRemainingPercentage:
    """Tests for budget remaining percentage calculation."""

    def test_full_budget_remaining(self):
        """Verify 100% remaining when no tokens used."""
        assert get_budget_remaining_pct(token_cap=1000, tokens_used=0) == 1.0

    def test_half_budget_remaining(self):
        """Verify 50% remaining when half tokens used."""
        assert get_budget_remaining_pct(token_cap=1000, tokens_used=500) == 0.5

    def test_budget_exhausted_returns_zero(self):
        """Verify 0% remaining when budget exhausted."""
        assert get_budget_remaining_pct(token_cap=1000, tokens_used=1000) == 0.0
        assert get_budget_remaining_pct(token_cap=1000, tokens_used=1500) == 0.0

    def test_none_cap_returns_full_budget(self):
        """Verify None cap returns 100% (unlimited)."""
        assert get_budget_remaining_pct(token_cap=None, tokens_used=1000000) == 1.0

    def test_zero_cap_returns_zero(self):
        """Verify zero cap returns 0%."""
        assert get_budget_remaining_pct(token_cap=0, tokens_used=0) == 0.0


class TestBudgetExhaustedError:
    """Tests for BudgetExhaustedError exception."""

    def test_exception_can_be_raised(self):
        """Verify BudgetExhaustedError can be raised with message."""
        with pytest.raises(BudgetExhaustedError) as exc_info:
            raise BudgetExhaustedError("token budget exhausted (1001/1000 tokens used)")

        assert "token budget exhausted" in str(exc_info.value).lower()
        assert "1001/1000" in str(exc_info.value)

    def test_exception_is_subclass_of_exception(self):
        """Verify BudgetExhaustedError is a proper Exception subclass."""
        assert issubclass(BudgetExhaustedError, Exception)
