"""Tests for tier-aware token budget redistribution (IMP-TIER-001)."""

from src.autopack.autonomous.budgeting import (MIN_TOKENS_PER_TIER,
                                               TIER_COST_RATIOS,
                                               adjust_budget_for_tier,
                                               allocate_phase_budget)


class TestAdjustBudgetForTier:
    """Test adjust_budget_for_tier function."""

    def test_adjust_budget_for_haiku(self):
        """Haiku gets baseline budget (no adjustment)."""
        budget = adjust_budget_for_tier(4000, "haiku")
        assert budget == 4000

    def test_adjust_budget_for_sonnet(self):
        """Sonnet gets 1/3 of baseline budget (3x cost ratio)."""
        budget = adjust_budget_for_tier(4000, "sonnet")
        assert budget == 1333  # 4000 / 3.0

    def test_adjust_budget_for_opus(self):
        """Opus gets 1/15 of baseline budget (15x cost ratio)."""
        budget = adjust_budget_for_tier(4000, "opus")
        assert budget == 266  # 4000 / 15.0

    def test_adjust_budget_respects_minimum_tokens_haiku(self):
        """Haiku respects minimum tokens constraint."""
        budget = adjust_budget_for_tier(500, "haiku")
        assert budget >= MIN_TOKENS_PER_TIER["haiku"]

    def test_adjust_budget_respects_minimum_tokens_sonnet(self):
        """Sonnet respects minimum tokens constraint."""
        budget = adjust_budget_for_tier(500, "sonnet")
        assert budget >= MIN_TOKENS_PER_TIER["sonnet"]

    def test_adjust_budget_respects_minimum_tokens_opus(self):
        """Opus respects minimum tokens constraint."""
        budget = adjust_budget_for_tier(500, "opus")
        assert budget >= MIN_TOKENS_PER_TIER["opus"]

    def test_adjust_budget_unknown_tier_defaults_to_no_change(self):
        """Unknown tier defaults to cost ratio of 1.0."""
        budget = adjust_budget_for_tier(4000, "unknown_tier")
        # Cost ratio defaults to 1.0, so no adjustment
        assert budget == 4000

    def test_cost_ratios_configured(self):
        """Cost ratios are properly configured."""
        assert TIER_COST_RATIOS["haiku"] == 1.0
        assert TIER_COST_RATIOS["sonnet"] == 3.0
        assert TIER_COST_RATIOS["opus"] == 15.0


class TestAllocatePhaseBudget:
    """Test allocate_phase_budget function."""

    def test_allocate_phase_budget_defaults_to_haiku(self):
        """Phase budget defaults to haiku tier."""
        budget = allocate_phase_budget("build")
        assert budget == 4000  # Haiku baseline

    def test_allocate_phase_budget_haiku(self):
        """Phase budget for haiku tier."""
        budget = allocate_phase_budget("build", tier="haiku")
        assert budget == 4000

    def test_allocate_phase_budget_sonnet(self):
        """Phase budget for sonnet tier."""
        budget = allocate_phase_budget("build", tier="sonnet")
        assert budget == 1333  # 4000 / 3.0

    def test_allocate_phase_budget_opus(self):
        """Phase budget for opus tier."""
        budget = allocate_phase_budget("build", tier="opus")
        assert budget == 266  # 4000 / 15.0

    def test_allocate_phase_budget_respects_minimum(self):
        """Phase budget respects minimum tokens per tier."""
        budget = allocate_phase_budget("build", tier="opus")
        assert budget >= MIN_TOKENS_PER_TIER["opus"]

    def test_allocate_phase_budget_opus_less_than_haiku(self):
        """Opus budget is less than haiku budget."""
        haiku_budget = allocate_phase_budget("build", tier="haiku")
        opus_budget = allocate_phase_budget("build", tier="opus")
        assert opus_budget < haiku_budget

    def test_allocate_phase_budget_different_phase_types(self):
        """Phase budgets are consistent across phase types."""
        build_budget = allocate_phase_budget("build", tier="opus")
        audit_budget = allocate_phase_budget("audit", tier="opus")
        # Same phase type should get same budget
        assert build_budget == audit_budget


class TestBudgetScaling:
    """Test budget scaling relationships."""

    def test_cost_equivalence_haiku_to_sonnet(self):
        """Haiku and Sonnet have approximately equivalent spending (cost × tokens).

        Note: Due to integer truncation, costs may differ by up to 1 unit.
        """
        haiku_budget = adjust_budget_for_tier(4000, "haiku")
        sonnet_budget = adjust_budget_for_tier(4000, "sonnet")

        haiku_cost = haiku_budget * TIER_COST_RATIOS["haiku"]
        sonnet_cost = sonnet_budget * TIER_COST_RATIOS["sonnet"]

        # They should be approximately equal (cost equivalence within 1% tolerance)
        assert abs(haiku_cost - sonnet_cost) / haiku_cost < 0.01

    def test_cost_equivalence_haiku_to_opus(self):
        """Haiku and Opus have approximately equivalent spending (cost × tokens).

        Note: Due to integer truncation, costs may differ by up to 1 unit.
        """
        haiku_budget = adjust_budget_for_tier(4000, "haiku")
        opus_budget = adjust_budget_for_tier(4000, "opus")

        haiku_cost = haiku_budget * TIER_COST_RATIOS["haiku"]
        opus_cost = opus_budget * TIER_COST_RATIOS["opus"]

        # They should be approximately equal (cost equivalence within 1% tolerance)
        assert abs(haiku_cost - opus_cost) / haiku_cost < 0.01

    def test_token_reduction_proportional_to_cost(self):
        """Token reduction is proportional to cost increase."""
        haiku_budget = adjust_budget_for_tier(4000, "haiku")
        sonnet_budget = adjust_budget_for_tier(4000, "sonnet")
        opus_budget = adjust_budget_for_tier(4000, "opus")

        # Higher cost tiers should get progressively fewer tokens
        assert haiku_budget > sonnet_budget
        assert sonnet_budget > opus_budget
