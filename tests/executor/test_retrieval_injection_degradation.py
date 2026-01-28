"""Tests for progressive budget degradation in SOT retrieval injection.

Tests the tiered degradation behavior implemented in IMP-RET-001:
- 50%+ budget: full retrieval (10 entries)
- 30-50% budget: reduced retrieval (5 entries)
- 15-30% budget: summary only (2 entries)
- <15% budget: no retrieval

This ensures graceful degradation instead of binary all-or-nothing behavior.
"""

from autopack.executor.retrieval_injection import (
    FULL_RETRIEVAL_THRESHOLD,
    REDUCED_RETRIEVAL_THRESHOLD,
    SUMMARY_ONLY_THRESHOLD,
    RetrievalInjection,
)


class TestProgressiveDegradationThresholds:
    """Tests for progressive degradation threshold constants."""

    def test_threshold_values(self):
        """Verify threshold constants are correctly defined."""
        assert FULL_RETRIEVAL_THRESHOLD == 0.5
        assert REDUCED_RETRIEVAL_THRESHOLD == 0.3
        assert SUMMARY_ONLY_THRESHOLD == 0.15

    def test_threshold_ordering(self):
        """Verify thresholds are in correct descending order."""
        assert FULL_RETRIEVAL_THRESHOLD > REDUCED_RETRIEVAL_THRESHOLD
        assert REDUCED_RETRIEVAL_THRESHOLD > SUMMARY_ONLY_THRESHOLD
        assert SUMMARY_ONLY_THRESHOLD > 0


class TestFullRetrievalMode:
    """Tests for full retrieval mode (50%+ budget)."""

    def test_full_mode_at_100_percent(self):
        """Test full retrieval mode at 100% budget."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)
        total_budget = 6000  # min required

        # 100% budget available
        gate = injection.gate_sot_retrieval(max_context_chars=6000, total_budget=total_budget)

        assert gate.allowed is True
        assert gate.retrieval_mode == "full"
        assert gate.max_entries == 10

    def test_full_mode_at_exactly_50_percent(self):
        """Test full retrieval mode at exactly 50% budget."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)
        total_budget = 10000

        # Exactly 50% budget
        gate = injection.gate_sot_retrieval(max_context_chars=5000, total_budget=total_budget)

        assert gate.allowed is True
        assert gate.retrieval_mode == "full"
        assert gate.max_entries == 10

    def test_full_mode_above_50_percent(self):
        """Test full retrieval mode with >50% budget."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)
        total_budget = 10000

        # 70% budget
        gate = injection.gate_sot_retrieval(max_context_chars=7000, total_budget=total_budget)

        assert gate.allowed is True
        assert gate.retrieval_mode == "full"
        assert gate.max_entries == 10


class TestReducedRetrievalMode:
    """Tests for reduced retrieval mode (30-50% budget)."""

    def test_reduced_mode_at_49_percent(self):
        """Test reduced retrieval mode just below 50% threshold."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)
        total_budget = 10000

        # 49% budget (just below full threshold)
        gate = injection.gate_sot_retrieval(max_context_chars=4900, total_budget=total_budget)

        assert gate.allowed is True
        assert gate.retrieval_mode == "reduced"
        assert gate.max_entries == 5

    def test_reduced_mode_at_exactly_30_percent(self):
        """Test reduced retrieval mode at exactly 30% budget."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)
        total_budget = 10000

        # Exactly 30% budget
        gate = injection.gate_sot_retrieval(max_context_chars=3000, total_budget=total_budget)

        assert gate.allowed is True
        assert gate.retrieval_mode == "reduced"
        assert gate.max_entries == 5

    def test_reduced_mode_at_40_percent(self):
        """Test reduced retrieval mode in middle of range."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)
        total_budget = 10000

        # 40% budget
        gate = injection.gate_sot_retrieval(max_context_chars=4000, total_budget=total_budget)

        assert gate.allowed is True
        assert gate.retrieval_mode == "reduced"
        assert gate.max_entries == 5


class TestSummaryRetrievalMode:
    """Tests for summary retrieval mode (15-30% budget)."""

    def test_summary_mode_at_29_percent(self):
        """Test summary retrieval mode just below 30% threshold."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)
        total_budget = 10000

        # 29% budget (just below reduced threshold)
        gate = injection.gate_sot_retrieval(max_context_chars=2900, total_budget=total_budget)

        assert gate.allowed is True
        assert gate.retrieval_mode == "summary"
        assert gate.max_entries == 2

    def test_summary_mode_at_exactly_15_percent(self):
        """Test summary retrieval mode at exactly 15% budget."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)
        total_budget = 10000

        # Exactly 15% budget
        gate = injection.gate_sot_retrieval(max_context_chars=1500, total_budget=total_budget)

        assert gate.allowed is True
        assert gate.retrieval_mode == "summary"
        assert gate.max_entries == 2

    def test_summary_mode_at_20_percent(self):
        """Test summary retrieval mode in middle of range."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)
        total_budget = 10000

        # 20% budget
        gate = injection.gate_sot_retrieval(max_context_chars=2000, total_budget=total_budget)

        assert gate.allowed is True
        assert gate.retrieval_mode == "summary"
        assert gate.max_entries == 2


class TestNoRetrievalMode:
    """Tests for no retrieval mode (<15% budget)."""

    def test_no_retrieval_at_14_percent(self):
        """Test no retrieval just below 15% threshold."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)
        total_budget = 10000

        # 14% budget (just below summary threshold)
        gate = injection.gate_sot_retrieval(max_context_chars=1400, total_budget=total_budget)

        assert gate.allowed is False
        assert gate.retrieval_mode == "none"
        assert gate.max_entries == 0
        assert "too tight" in gate.reason.lower()

    def test_no_retrieval_at_10_percent(self):
        """Test no retrieval at 10% budget."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)
        total_budget = 10000

        # 10% budget
        gate = injection.gate_sot_retrieval(max_context_chars=1000, total_budget=total_budget)

        assert gate.allowed is False
        assert gate.retrieval_mode == "none"
        assert gate.max_entries == 0

    def test_no_retrieval_at_zero_percent(self):
        """Test no retrieval at 0% budget."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)
        total_budget = 10000

        # 0% budget
        gate = injection.gate_sot_retrieval(max_context_chars=0, total_budget=total_budget)

        assert gate.allowed is False
        assert gate.retrieval_mode == "none"
        assert gate.max_entries == 0


class TestDegradationWithDisabledConfig:
    """Tests for degradation behavior when disabled by config."""

    def test_disabled_returns_none_mode(self):
        """Test that disabled config returns none mode regardless of budget."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=False)
        total_budget = 10000

        # Even with 100% budget
        gate = injection.gate_sot_retrieval(max_context_chars=10000, total_budget=total_budget)

        assert gate.allowed is False
        assert gate.retrieval_mode == "none"
        assert gate.max_entries == 0
        assert "disabled" in gate.reason.lower()


class TestDegradationWithoutTotalBudget:
    """Tests for degradation when total_budget is not provided."""

    def test_uses_min_required_as_baseline(self):
        """Test that missing total_budget uses min_required as baseline."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)

        # Without total_budget, uses min_required (6000) as baseline
        # 6000/6000 = 100% = full mode
        gate = injection.gate_sot_retrieval(max_context_chars=6000)

        assert gate.allowed is True
        assert gate.retrieval_mode == "full"
        assert gate.max_entries == 10

    def test_insufficient_budget_without_total(self):
        """Test insufficient budget detection without total_budget."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)

        # 500/6000 = 8.3% = no retrieval
        gate = injection.gate_sot_retrieval(max_context_chars=500)

        assert gate.allowed is False
        assert gate.retrieval_mode == "none"


class TestDegradationEdgeCases:
    """Tests for edge cases in progressive degradation."""

    def test_negative_budget(self):
        """Test handling of negative budget."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)

        gate = injection.gate_sot_retrieval(max_context_chars=-1000, total_budget=10000)

        assert gate.allowed is False
        assert gate.retrieval_mode == "none"
        assert gate.max_entries == 0

    def test_zero_total_budget(self):
        """Test handling of zero total_budget."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)

        # Zero total budget results in 0 ratio = no retrieval
        gate = injection.gate_sot_retrieval(max_context_chars=1000, total_budget=0)

        assert gate.allowed is False
        assert gate.retrieval_mode == "none"

    def test_negative_total_budget(self):
        """Test handling of negative total_budget."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)

        gate = injection.gate_sot_retrieval(max_context_chars=1000, total_budget=-1000)

        assert gate.allowed is False
        assert gate.retrieval_mode == "none"

    def test_very_large_budget(self):
        """Test with very large budget values."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)

        gate = injection.gate_sot_retrieval(max_context_chars=1_000_000, total_budget=1_000_000)

        assert gate.allowed is True
        assert gate.retrieval_mode == "full"
        assert gate.max_entries == 10


class TestGateDecisionFields:
    """Tests for GateDecision fields with degradation."""

    def test_full_mode_includes_all_fields(self):
        """Test GateDecision contains all required fields in full mode."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)

        gate = injection.gate_sot_retrieval(max_context_chars=10000, total_budget=10000)

        assert hasattr(gate, "allowed")
        assert hasattr(gate, "reason")
        assert hasattr(gate, "budget_remaining")
        assert hasattr(gate, "sot_budget")
        assert hasattr(gate, "reserve_budget")
        assert hasattr(gate, "retrieval_mode")
        assert hasattr(gate, "max_entries")

    def test_budget_remaining_calculated_correctly(self):
        """Test budget_remaining is calculated correctly in each mode."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)

        # Full mode
        gate = injection.gate_sot_retrieval(max_context_chars=10000, total_budget=10000)
        assert gate.budget_remaining == 6000  # 10000 - 4000

        # Reduced mode
        gate = injection.gate_sot_retrieval(max_context_chars=4000, total_budget=10000)
        assert gate.budget_remaining == 0  # 4000 - 4000

        # Summary mode
        gate = injection.gate_sot_retrieval(max_context_chars=2000, total_budget=10000)
        assert gate.budget_remaining == -2000  # 2000 - 4000 (can be negative)


class TestDegradationScenarios:
    """Integration tests for realistic degradation scenarios."""

    def test_gradual_budget_consumption(self):
        """Test degradation as budget is consumed across phases."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)
        total_budget = 10000

        # Phase 1: Full budget available -> full mode
        gate1 = injection.gate_sot_retrieval(max_context_chars=10000, total_budget=total_budget)
        assert gate1.retrieval_mode == "full"
        assert gate1.max_entries == 10

        # Phase 2: 45% budget remaining -> reduced mode
        gate2 = injection.gate_sot_retrieval(max_context_chars=4500, total_budget=total_budget)
        assert gate2.retrieval_mode == "reduced"
        assert gate2.max_entries == 5

        # Phase 3: 25% budget remaining -> summary mode
        gate3 = injection.gate_sot_retrieval(max_context_chars=2500, total_budget=total_budget)
        assert gate3.retrieval_mode == "summary"
        assert gate3.max_entries == 2

        # Phase 4: 10% budget remaining -> no retrieval
        gate4 = injection.gate_sot_retrieval(max_context_chars=1000, total_budget=total_budget)
        assert gate4.retrieval_mode == "none"
        assert gate4.max_entries == 0
        assert gate4.allowed is False

    def test_70_percent_usage_scenario(self):
        """Test the specific scenario from IMP-RET-001: 70% usage = 30% remaining."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)
        total_budget = 10000

        # 70% used = 30% remaining (exactly at reduced threshold)
        gate = injection.gate_sot_retrieval(max_context_chars=3000, total_budget=total_budget)

        # Should get reduced retrieval instead of being blocked
        assert gate.allowed is True
        assert gate.retrieval_mode == "reduced"
        assert gate.max_entries == 5

    def test_85_percent_usage_scenario(self):
        """Test 85% usage = 15% remaining (summary mode boundary)."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)
        total_budget = 10000

        # 85% used = 15% remaining
        gate = injection.gate_sot_retrieval(max_context_chars=1500, total_budget=total_budget)

        # Should get summary retrieval
        assert gate.allowed is True
        assert gate.retrieval_mode == "summary"
        assert gate.max_entries == 2
