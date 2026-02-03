"""Tests for TokenBudgetEnforcer (IMP-GENAI-002).

Tests budget enforcement mechanisms including pre-call validation,
post-call enforcement, circuit breaker pattern, and budget escalation.
"""

import pytest

from autopack.planning.token_budget_enforcer import (
    BudgetStatus,
    BudgetValidation,
    TokenBudgetEnforcer,
)


class TestBudgetEnforcer:
    """Test TokenBudgetEnforcer core functionality."""

    @pytest.fixture
    def enforcer(self):
        """Create enforcer instance."""
        return TokenBudgetEnforcer()

    # Pre-call validation tests
    def test_pre_call_ok(self, enforcer):
        """Test pre-call validation with sufficient budget."""
        validation = enforcer.validate_pre_call(
            estimated_tokens=5000,
            budget_tokens=8000,
            complexity="medium",
        )

        assert validation.status == BudgetStatus.OK
        assert not validation.should_escalate
        assert validation.utilization_pct < 0.85
        assert "sufficient" in validation.recommendation.lower()

    def test_pre_call_warning(self, enforcer):
        """Test pre-call validation approaching limit (85-100%)."""
        validation = enforcer.validate_pre_call(
            estimated_tokens=7000,
            budget_tokens=8000,
            complexity="medium",
        )

        assert validation.status == BudgetStatus.WARNING
        assert not validation.should_escalate
        assert validation.utilization_pct >= 0.85
        assert validation.utilization_pct < 1.0
        assert "utilization" in validation.recommendation.lower()

    def test_pre_call_exceeded(self, enforcer):
        """Test pre-call validation with exceeded budget (100-120%)."""
        validation = enforcer.validate_pre_call(
            estimated_tokens=9000,
            budget_tokens=8000,
            complexity="medium",
        )

        assert validation.status == BudgetStatus.EXCEEDED
        assert validation.should_escalate
        assert validation.utilization_pct > 1.0
        assert validation.utilization_pct < 1.2
        assert "Increase budget" in validation.recommendation

    def test_pre_call_critical(self, enforcer):
        """Test pre-call validation far exceeding budget (>120%)."""
        validation = enforcer.validate_pre_call(
            estimated_tokens=15000,
            budget_tokens=8000,
            complexity="medium",
        )

        assert validation.status == BudgetStatus.CRITICAL
        assert validation.should_escalate
        assert validation.utilization_pct >= 1.2

    def test_pre_call_zero_budget(self, enforcer):
        """Test pre-call validation with zero or negative budget."""
        validation = enforcer.validate_pre_call(
            estimated_tokens=5000,
            budget_tokens=0,
            complexity="medium",
        )

        assert validation.status == BudgetStatus.CRITICAL
        assert validation.should_escalate
        assert "zero or negative" in validation.recommendation.lower()

    def test_pre_call_negative_budget(self, enforcer):
        """Test pre-call validation with negative budget."""
        validation = enforcer.validate_pre_call(
            estimated_tokens=5000,
            budget_tokens=-1000,
            complexity="medium",
        )

        assert validation.status == BudgetStatus.CRITICAL
        assert validation.should_escalate

    # Post-call validation tests
    def test_post_call_ok(self, enforcer):
        """Test post-call validation within budget."""
        validation = enforcer.validate_post_call(
            actual_tokens=6000,
            budget_tokens=8000,
            stop_reason="end_turn",
        )

        assert validation.status == BudgetStatus.OK
        assert not validation.should_escalate
        assert enforcer.overflow_count == 0

    def test_post_call_high_utilization(self, enforcer):
        """Test post-call validation with high utilization (>95%)."""
        validation = enforcer.validate_post_call(
            actual_tokens=7700,
            budget_tokens=8000,
            stop_reason="end_turn",
        )

        assert validation.status == BudgetStatus.WARNING
        assert validation.should_escalate
        assert "high utilization" in validation.recommendation.lower()
        assert enforcer.overflow_count == 0  # No overflow yet

    def test_post_call_truncated(self, enforcer):
        """Test post-call validation with truncation (max_tokens)."""
        validation = enforcer.validate_post_call(
            actual_tokens=8000,
            budget_tokens=8000,
            stop_reason="max_tokens",
        )

        assert validation.status == BudgetStatus.EXCEEDED
        assert validation.should_escalate
        assert "truncated" in validation.recommendation.lower()
        assert enforcer.overflow_count == 1

    def test_post_call_multiple_truncations(self, enforcer):
        """Test post-call validation tracks multiple truncations."""
        for i in range(3):
            validation = enforcer.validate_post_call(
                actual_tokens=8000,
                budget_tokens=8000,
                stop_reason="max_tokens",
            )
            assert validation.status == BudgetStatus.EXCEEDED
            assert enforcer.overflow_count == i + 1

    def test_post_call_zero_budget(self, enforcer):
        """Test post-call validation with zero budget."""
        validation = enforcer.validate_post_call(
            actual_tokens=100,
            budget_tokens=0,
            stop_reason="end_turn",
        )

        assert validation.status == BudgetStatus.OK  # 100/0 = inf, no exception
        # utilization_pct should be 0.0 due to division check

    # Circuit breaker tests
    def test_circuit_breaker_not_tripped(self, enforcer):
        """Test circuit breaker doesn't trip below threshold."""
        # Trigger 2 overflows
        for _ in range(2):
            enforcer.validate_post_call(
                actual_tokens=8000,
                budget_tokens=8000,
                stop_reason="max_tokens",
            )

        assert not enforcer.should_circuit_break(max_overflows=3)

    def test_circuit_breaker_tripped(self, enforcer):
        """Test circuit breaker trips at threshold."""
        # Trigger 3 overflows
        for _ in range(3):
            enforcer.validate_post_call(
                actual_tokens=8000,
                budget_tokens=8000,
                stop_reason="max_tokens",
            )

        assert enforcer.should_circuit_break(max_overflows=3)

    def test_circuit_breaker_tripped_with_custom_threshold(self, enforcer):
        """Test circuit breaker with custom threshold."""
        # Trigger 5 overflows
        for _ in range(5):
            enforcer.validate_post_call(
                actual_tokens=8000,
                budget_tokens=8000,
                stop_reason="max_tokens",
            )

        # At 5 overflows, should trip with threshold of 5
        assert enforcer.should_circuit_break(max_overflows=5)
        # Should also trip with threshold of 4 (5 >= 4)
        assert enforcer.should_circuit_break(max_overflows=4)
        # Should not trip with threshold of 6 (5 < 6)
        assert not enforcer.should_circuit_break(max_overflows=6)

    # Budget escalation tests
    def test_escalated_budget_basic(self, enforcer):
        """Test budget escalation calculation (50% increase)."""
        escalated = enforcer.get_escalated_budget(
            current_budget=8000,
            complexity="medium",
        )

        # 50% increase: 8000 * 1.5 = 12000
        assert escalated == 12000

    def test_escalated_budget_low_complexity(self, enforcer):
        """Test budget escalation for low complexity."""
        escalated = enforcer.get_escalated_budget(
            current_budget=4000,
            complexity="low",
        )

        # 50% increase: 4000 * 1.5 = 6000
        assert escalated == 6000

    def test_escalated_budget_high_complexity(self, enforcer):
        """Test budget escalation for high complexity."""
        escalated = enforcer.get_escalated_budget(
            current_budget=16000,
            complexity="high",
        )

        # 50% increase: 16000 * 1.5 = 24000
        assert escalated == 24000

    def test_escalated_budget_capped_at_64k(self, enforcer):
        """Test budget escalation respects 64k cap."""
        escalated = enforcer.get_escalated_budget(
            current_budget=60000,
            complexity="high",
        )

        # Would be 90000, but capped at 64000
        assert escalated == 64000

    def test_escalated_budget_at_cap(self, enforcer):
        """Test budget escalation when already at cap."""
        escalated = enforcer.get_escalated_budget(
            current_budget=64000,
            complexity="high",
        )

        # Already at cap, stays at 64000
        assert escalated == 64000

    # Validation dataclass tests
    def test_budget_validation_creation(self):
        """Test BudgetValidation dataclass creation."""
        validation = BudgetValidation(
            status=BudgetStatus.WARNING,
            estimated_tokens=7000,
            budget_tokens=8000,
            utilization_pct=0.875,
            recommendation="Test recommendation",
            should_escalate=False,
        )

        assert validation.status == BudgetStatus.WARNING
        assert validation.estimated_tokens == 7000
        assert validation.budget_tokens == 8000
        assert validation.utilization_pct == 0.875
        assert validation.recommendation == "Test recommendation"
        assert not validation.should_escalate

    # Edge cases
    def test_pre_call_very_small_budget(self, enforcer):
        """Test pre-call with very small budget."""
        validation = enforcer.validate_pre_call(
            estimated_tokens=1000,
            budget_tokens=1,
            complexity="medium",
        )

        assert validation.status == BudgetStatus.CRITICAL
        assert validation.should_escalate
        assert validation.utilization_pct > 100

    def test_pre_call_exact_match(self, enforcer):
        """Test pre-call when estimated exactly matches budget."""
        validation = enforcer.validate_pre_call(
            estimated_tokens=8000,
            budget_tokens=8000,
            complexity="medium",
        )

        assert validation.status == BudgetStatus.EXCEEDED  # utilization >= 1.0
        assert validation.should_escalate

    def test_post_call_exact_utilization_85_percent(self, enforcer):
        """Test post-call at exact 85% threshold."""
        # 0.85 * 8000 = 6800
        validation = enforcer.validate_post_call(
            actual_tokens=6800,
            budget_tokens=8000,
            stop_reason="end_turn",
        )

        # At exactly 85%, should still be OK (not high utilization)
        assert validation.status == BudgetStatus.OK
        assert not validation.should_escalate

    def test_post_call_just_over_95_percent(self, enforcer):
        """Test post-call just over 95% threshold."""
        # 0.9501 * 8000 = 7600.8
        validation = enforcer.validate_post_call(
            actual_tokens=7601,
            budget_tokens=8000,
            stop_reason="end_turn",
        )

        assert validation.status == BudgetStatus.WARNING
        assert validation.should_escalate


class TestTokenEstimatorEnforcement:
    """Test TokenEstimator.enforce_budget() integration."""

    @pytest.fixture
    def estimator(self, tmp_path):
        """Create estimator instance."""
        from autopack.token_estimator import TokenEstimator

        return TokenEstimator(workspace=tmp_path)

    def test_enforce_budget_ok(self, estimator):
        """Test enforcement with sufficient budget."""
        from autopack.token_estimator import TokenEstimate

        estimate = TokenEstimate(
            estimated_tokens=5000,
            deliverable_count=5,
            category="backend",
            complexity="medium",
            confidence=0.8,
        )

        result = estimator.enforce_budget(
            estimate=estimate,
            budget=8000,
            complexity="medium",
        )

        assert result["status"] == "ok"
        assert not result["should_escalate"]
        assert "recommended_budget" not in result
        assert result["utilization_pct"] < 0.85

    def test_enforce_budget_warning(self, estimator):
        """Test enforcement approaching limit."""
        from autopack.token_estimator import TokenEstimate

        estimate = TokenEstimate(
            estimated_tokens=7000,
            deliverable_count=7,
            category="backend",
            complexity="medium",
            confidence=0.8,
        )

        result = estimator.enforce_budget(
            estimate=estimate,
            budget=8000,
            complexity="medium",
        )

        assert result["status"] == "warning"
        assert not result["should_escalate"]
        assert result["utilization_pct"] >= 0.85

    def test_enforce_budget_exceeded(self, estimator):
        """Test enforcement with insufficient budget."""
        from autopack.token_estimator import TokenEstimate

        estimate = TokenEstimate(
            estimated_tokens=9000,
            deliverable_count=10,
            category="backend",
            complexity="medium",
            confidence=0.8,
        )

        result = estimator.enforce_budget(
            estimate=estimate,
            budget=8000,
            complexity="medium",
        )

        assert result["status"] == "exceeded"
        assert result["should_escalate"]
        assert "recommended_budget" in result
        assert result["recommended_budget"] > 8000
        assert result["recommended_budget"] == 12000  # 8000 * 1.5

    def test_enforce_budget_critical(self, estimator):
        """Test enforcement far exceeding budget."""
        from autopack.token_estimator import TokenEstimate

        estimate = TokenEstimate(
            estimated_tokens=15000,
            deliverable_count=15,
            category="backend",
            complexity="high",
            confidence=0.8,
        )

        result = estimator.enforce_budget(
            estimate=estimate,
            budget=8000,
            complexity="high",
        )

        assert result["status"] == "critical"
        assert result["should_escalate"]
        assert "recommended_budget" in result
        # 8000 * 1.5 = 12000 (escalation applied)
        assert result["recommended_budget"] == 12000

    def test_enforce_budget_integration(self, estimator):
        """Test full budget enforcement flow."""
        deliverables = ["Create src/large_module.py"] * 5

        # Estimate tokens
        estimate = estimator.estimate(
            deliverables=deliverables,
            category="backend",
            complexity="high",
        )

        # Select budget
        budget = estimator.select_budget(estimate, complexity="high")

        # Enforce budget
        enforcement = estimator.enforce_budget(
            estimate=estimate,
            budget=budget,
            complexity="high",
        )

        # Budget should be sufficient (select_budget considers estimate)
        assert enforcement["status"] in ["ok", "warning"]
        assert not enforcement["should_escalate"]


class TestBudgetStatusEnum:
    """Test BudgetStatus enum."""

    def test_budget_status_values(self):
        """Test BudgetStatus enum has correct values."""
        assert BudgetStatus.OK.value == "ok"
        assert BudgetStatus.WARNING.value == "warning"
        assert BudgetStatus.EXCEEDED.value == "exceeded"
        assert BudgetStatus.CRITICAL.value == "critical"

    def test_budget_status_enum_members(self):
        """Test BudgetStatus enum has all expected members."""
        members = {member.value for member in BudgetStatus}
        assert members == {"ok", "warning", "exceeded", "critical"}
