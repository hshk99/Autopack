"""
Tests for deterministic budget calculation.

Verifies clamping, determinism, and edge cases for budget_remaining computation.
"""

import pytest

from autopack.autonomous.budgeting import BudgetInputs, compute_budget_remaining


class TestComputeBudgetRemaining:
    """Test deterministic budget_remaining calculation."""

    def test_full_budget_available(self):
        """Budget remaining is 1.0 when nothing used."""
        inputs = BudgetInputs(
            token_cap=100_000,
            tokens_used=0,
            max_context_chars=200_000,
            context_chars_used=0,
            max_sot_chars=50_000,
            sot_chars_used=0,
        )
        assert compute_budget_remaining(inputs) == 1.0

    def test_budget_half_consumed(self):
        """Budget remaining reflects half consumption."""
        inputs = BudgetInputs(
            token_cap=100_000,
            tokens_used=50_000,
            max_context_chars=200_000,
            context_chars_used=100_000,
            max_sot_chars=50_000,
            sot_chars_used=25_000,
        )
        # All dimensions at 50% -> budget_remaining = 0.5
        assert compute_budget_remaining(inputs) == 0.5

    def test_budget_fully_exhausted(self):
        """Budget remaining is 0.0 when fully consumed."""
        inputs = BudgetInputs(
            token_cap=100_000,
            tokens_used=100_000,
            max_context_chars=200_000,
            context_chars_used=200_000,
            max_sot_chars=50_000,
            sot_chars_used=50_000,
        )
        assert compute_budget_remaining(inputs) == 0.0

    def test_budget_over_consumed_clamped_to_zero(self):
        """Budget remaining clamped to 0.0 when usage exceeds cap."""
        inputs = BudgetInputs(
            token_cap=100_000,
            tokens_used=150_000,  # Over budget
            max_context_chars=200_000,
            context_chars_used=100_000,
            max_sot_chars=50_000,
            sot_chars_used=25_000,
        )
        # Token dimension is negative, should clamp to 0
        assert compute_budget_remaining(inputs) == 0.0

    def test_minimum_dimension_wins(self):
        """Budget remaining is minimum across all dimensions."""
        inputs = BudgetInputs(
            token_cap=100_000,
            tokens_used=90_000,  # 10% remaining
            max_context_chars=200_000,
            context_chars_used=100_000,  # 50% remaining
            max_sot_chars=50_000,
            sot_chars_used=10_000,  # 80% remaining
        )
        # Token dimension is most constrained (10% remaining)
        assert compute_budget_remaining(inputs) == pytest.approx(0.1)

    def test_zero_cap_means_no_constraint(self):
        """Zero or negative cap means dimension is unconstrained."""
        inputs = BudgetInputs(
            token_cap=100_000,
            tokens_used=50_000,  # 50% remaining
            max_context_chars=0,  # No cap -> 100% available
            context_chars_used=999_999,  # Should be ignored
            max_sot_chars=-1,  # Negative cap -> 100% available
            sot_chars_used=999_999,  # Should be ignored
        )
        # Only token dimension matters (50% remaining)
        assert compute_budget_remaining(inputs) == 0.5

    def test_deterministic_same_inputs_same_output(self):
        """Same inputs always produce same output."""
        inputs = BudgetInputs(
            token_cap=100_000,
            tokens_used=30_000,
            max_context_chars=200_000,
            context_chars_used=60_000,
            max_sot_chars=50_000,
            sot_chars_used=15_000,
        )
        result1 = compute_budget_remaining(inputs)
        result2 = compute_budget_remaining(inputs)
        assert result1 == result2

    def test_token_dimension_most_constrained(self):
        """Token budget is most constrained."""
        inputs = BudgetInputs(
            token_cap=100_000,
            tokens_used=95_000,  # 5% remaining
            max_context_chars=200_000,
            context_chars_used=50_000,  # 75% remaining
            max_sot_chars=50_000,
            sot_chars_used=10_000,  # 80% remaining
        )
        assert compute_budget_remaining(inputs) == pytest.approx(0.05)

    def test_context_dimension_most_constrained(self):
        """Context budget is most constrained."""
        inputs = BudgetInputs(
            token_cap=100_000,
            tokens_used=20_000,  # 80% remaining
            max_context_chars=200_000,
            context_chars_used=190_000,  # 5% remaining
            max_sot_chars=50_000,
            sot_chars_used=10_000,  # 80% remaining
        )
        assert compute_budget_remaining(inputs) == pytest.approx(0.05)

    def test_sot_dimension_most_constrained(self):
        """SOT budget is most constrained."""
        inputs = BudgetInputs(
            token_cap=100_000,
            tokens_used=20_000,  # 80% remaining
            max_context_chars=200_000,
            context_chars_used=50_000,  # 75% remaining
            max_sot_chars=50_000,
            sot_chars_used=48_000,  # 4% remaining
        )
        assert compute_budget_remaining(inputs) == pytest.approx(0.04)

    def test_fractional_remaining_precise(self):
        """Budget remaining calculation is precise for fractional values."""
        inputs = BudgetInputs(
            token_cap=100_000,
            tokens_used=33_333,  # 66.667% remaining
            max_context_chars=200_000,
            context_chars_used=100_000,  # 50% remaining
            max_sot_chars=50_000,
            sot_chars_used=25_000,  # 50% remaining
        )
        # Minimum is 50%
        assert compute_budget_remaining(inputs) == pytest.approx(0.5)

    def test_all_dimensions_at_zero_usage(self):
        """All dimensions at zero usage gives 100% budget."""
        inputs = BudgetInputs(
            token_cap=1_000_000,
            tokens_used=0,
            max_context_chars=500_000,
            context_chars_used=0,
            max_sot_chars=100_000,
            sot_chars_used=0,
        )
        assert compute_budget_remaining(inputs) == 1.0

    def test_edge_case_one_token_remaining(self):
        """One token remaining gives very small but non-zero budget."""
        inputs = BudgetInputs(
            token_cap=100_000,
            tokens_used=99_999,
            max_context_chars=200_000,
            context_chars_used=0,
            max_sot_chars=50_000,
            sot_chars_used=0,
        )
        assert compute_budget_remaining(inputs) == pytest.approx(0.00001)
