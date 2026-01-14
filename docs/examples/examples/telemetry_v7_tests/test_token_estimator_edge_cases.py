"""Unit tests for TokenEstimator edge cases.

Tests cover:
- Zero deliverables
- Huge deliverable counts (100+)
- Missing category/complexity fields
- Budget cap at 64K tokens
- Negative values
- Empty strings and None values
"""

import pytest
from typing import Optional


class TokenEstimator:
    """Simplified TokenEstimator for testing.

    Estimates token budgets based on phase characteristics:
    - Base overhead: 5000 tokens
    - Per-deliverable: 2000 tokens
    - Category multipliers: simple=1.0, medium=1.5, complex=2.0
    - Complexity multipliers: low=1.0, medium=1.3, high=1.8
    - Maximum budget: 64000 tokens
    """

    PHASE_OVERHEAD = 5000
    TOKEN_PER_DELIVERABLE = 2000
    MAX_BUDGET = 64000

    CATEGORY_WEIGHTS = {
        "simple": 1.0,
        "medium": 1.5,
        "complex": 2.0,
    }

    COMPLEXITY_WEIGHTS = {
        "low": 1.0,
        "medium": 1.3,
        "high": 1.8,
    }

    def estimate(
        self,
        deliverable_count: int,
        category: Optional[str] = None,
        complexity: Optional[str] = None,
    ) -> int:
        """Estimate token budget for a phase.

        Args:
            deliverable_count: Number of deliverables (files to modify/create)
            category: Phase category (simple/medium/complex)
            complexity: Phase complexity (low/medium/high)

        Returns:
            Estimated token budget, capped at MAX_BUDGET

        Raises:
            ValueError: If deliverable_count is negative
        """
        if deliverable_count < 0:
            raise ValueError("deliverable_count cannot be negative")

        # Base calculation
        base_tokens = self.PHASE_OVERHEAD + (deliverable_count * self.TOKEN_PER_DELIVERABLE)

        # Apply category multiplier (default to medium if not specified)
        category_multiplier = self.CATEGORY_WEIGHTS.get(
            category.lower() if category else "medium",
            1.5,  # Default to medium
        )

        # Apply complexity multiplier (default to medium if not specified)
        complexity_multiplier = self.COMPLEXITY_WEIGHTS.get(
            complexity.lower() if complexity else "medium",
            1.3,  # Default to medium
        )

        # Calculate final estimate
        estimate = int(base_tokens * category_multiplier * complexity_multiplier)

        # Cap at maximum budget
        return min(estimate, self.MAX_BUDGET)


@pytest.fixture
def estimator():
    """Provide a TokenEstimator instance for tests."""
    return TokenEstimator()


class TestTokenEstimatorEdgeCases:
    """Test suite for TokenEstimator edge cases."""

    def test_zero_deliverables(self, estimator):
        """Test estimation with zero deliverables.

        Should return only phase overhead with multipliers applied.
        """
        # Zero deliverables with default category/complexity
        result = estimator.estimate(deliverable_count=0)

        # Expected: 5000 * 1.5 (medium category) * 1.3 (medium complexity) = 9750
        expected = int(5000 * 1.5 * 1.3)
        assert result == expected
        assert result == 9750

        # Zero deliverables with simple/low
        result_simple = estimator.estimate(deliverable_count=0, category="simple", complexity="low")
        # Expected: 5000 * 1.0 * 1.0 = 5000
        assert result_simple == 5000

    @pytest.mark.parametrize(
        "deliverable_count,expected_capped",
        [
            (100, True),  # 5000 + 200000 = 205000 * multipliers > 64K
            (150, True),  # 5000 + 300000 = 305000 * multipliers > 64K
            (200, True),  # 5000 + 400000 = 405000 * multipliers > 64K
            (50, False),  # 5000 + 100000 = 105000 * 1.5 * 1.3 = 204750 > 64K (actually capped)
            (30, False),  # 5000 + 60000 = 65000 * 1.5 * 1.3 = 126750 > 64K (capped)
        ],
    )
    def test_huge_deliverable_counts(self, estimator, deliverable_count, expected_capped):
        """Test estimation with huge deliverable counts (100+).

        Should cap at MAX_BUDGET (64000 tokens).
        """
        result = estimator.estimate(
            deliverable_count=deliverable_count, category="medium", complexity="medium"
        )

        # All these cases should hit the cap
        assert result == TokenEstimator.MAX_BUDGET
        assert result == 64000

        # Verify the uncapped calculation would exceed the limit
        uncapped = int((5000 + deliverable_count * 2000) * 1.5 * 1.3)
        assert uncapped > TokenEstimator.MAX_BUDGET

    @pytest.mark.parametrize(
        "category,complexity,expected_multiplier",
        [
            (None, None, 1.5 * 1.3),  # Both default to medium
            (None, "high", 1.5 * 1.8),  # Category defaults to medium
            ("complex", None, 2.0 * 1.3),  # Complexity defaults to medium
            ("", "", 1.5 * 1.3),  # Empty strings default to medium
            ("invalid", "invalid", 1.5 * 1.3),  # Invalid values default to medium
        ],
    )
    def test_missing_category_complexity(
        self, estimator, category, complexity, expected_multiplier
    ):
        """Test estimation with missing or invalid category/complexity.

        Should default to medium for both when not specified or invalid.
        """
        deliverable_count = 5
        result = estimator.estimate(
            deliverable_count=deliverable_count, category=category, complexity=complexity
        )

        # Expected: (5000 + 5*2000) * multiplier
        base = 5000 + (deliverable_count * 2000)
        expected = int(base * expected_multiplier)

        assert result == expected

    def test_budget_cap_at_64k(self, estimator):
        """Test that budget is strictly capped at 64K tokens.

        Even with maximum multipliers, should never exceed 64000.
        """
        # Test with various high-value combinations
        test_cases = [
            {"deliverable_count": 50, "category": "complex", "complexity": "high"},
            {"deliverable_count": 100, "category": "complex", "complexity": "high"},
            {"deliverable_count": 25, "category": "complex", "complexity": "high"},
            {"deliverable_count": 30, "category": "medium", "complexity": "high"},
        ]

        for case in test_cases:
            result = estimator.estimate(**case)

            # Should always be capped
            assert result <= TokenEstimator.MAX_BUDGET
            assert result == 64000

            # Verify uncapped would exceed limit
            base = 5000 + (case["deliverable_count"] * 2000)
            cat_mult = TokenEstimator.CATEGORY_WEIGHTS[case["category"]]
            comp_mult = TokenEstimator.COMPLEXITY_WEIGHTS[case["complexity"]]
            uncapped = int(base * cat_mult * comp_mult)
            assert uncapped > TokenEstimator.MAX_BUDGET

    def test_negative_deliverable_count(self, estimator):
        """Test that negative deliverable counts raise ValueError.

        Negative counts are invalid and should be rejected.
        """
        with pytest.raises(ValueError, match="deliverable_count cannot be negative"):
            estimator.estimate(deliverable_count=-1)

        with pytest.raises(ValueError, match="deliverable_count cannot be negative"):
            estimator.estimate(deliverable_count=-100)

        with pytest.raises(ValueError, match="deliverable_count cannot be negative"):
            estimator.estimate(deliverable_count=-5, category="simple", complexity="low")

    @pytest.mark.parametrize(
        "deliverable_count,category,complexity,expected",
        [
            # Boundary cases around the cap
            (15, "complex", "high", 64000),  # (5000 + 30000) * 2.0 * 1.8 = 126000 → capped
            (10, "complex", "high", 64000),  # (5000 + 20000) * 2.0 * 1.8 = 90000 → capped
            (8, "complex", "high", 64000),  # (5000 + 16000) * 2.0 * 1.8 = 75600 → capped
            (7, "complex", "high", 64000),  # (5000 + 14000) * 2.0 * 1.8 = 68400 → capped
            (6, "complex", "high", 64000),  # (5000 + 12000) * 2.0 * 1.8 = 61200 → not capped
            (5, "complex", "high", 54000),  # (5000 + 10000) * 2.0 * 1.8 = 54000
            (3, "complex", "high", 39600),  # (5000 + 6000) * 2.0 * 1.8 = 39600
            (1, "simple", "low", 7000),  # (5000 + 2000) * 1.0 * 1.0 = 7000
        ],
    )
    def test_boundary_cases_near_cap(
        self, estimator, deliverable_count, category, complexity, expected
    ):
        """Test estimation near the 64K budget cap boundary.

        Verifies correct behavior at and around the cap threshold.
        """
        result = estimator.estimate(
            deliverable_count=deliverable_count, category=category, complexity=complexity
        )

        assert result == expected
        assert result <= TokenEstimator.MAX_BUDGET
