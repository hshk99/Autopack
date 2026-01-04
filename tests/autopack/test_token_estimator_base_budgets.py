"""
Tests for BUILD-142: Category-aware base budget floors in TokenEstimator.

Validates that base budgets are correctly selected based on category/complexity
to reduce budget waste while maintaining safety.
"""

import pytest
from autopack.token_estimator import TokenEstimator, TokenEstimate


class TestCategoryAwareBaseBudgets:
    """Tests for category-aware base budget floor selection."""

    @pytest.fixture
    def estimator(self, tmp_path):
        """Create TokenEstimator instance."""
        return TokenEstimator(workspace=tmp_path)

    def test_docs_low_base_budget_reduced(self, estimator):
        """docs/low should use 4096 base (down from 8192)."""
        estimate = TokenEstimate(
            estimated_tokens=2000,
            deliverable_count=1,
            category="docs",
            complexity="low",
            breakdown={},
            confidence=0.8
        )
        budget = estimator.select_budget(estimate, "low")
        # With 2000 * 1.2 buffer = 2400, base floor of 4096 should apply
        assert budget == 4096, f"Expected docs/low base=4096, got {budget}"

    def test_docs_medium_base_unchanged(self, estimator):
        """docs/medium should keep 8192 base."""
        estimate = TokenEstimate(
            estimated_tokens=3000,
            deliverable_count=1,
            category="docs",
            complexity="medium",
            breakdown={},
            confidence=0.8
        )
        budget = estimator.select_budget(estimate, "medium")
        # With 3000 * 1.2 buffer = 3600, base floor of 8192 should apply
        assert budget == 8192, f"Expected docs/medium base=8192, got {budget}"

    def test_tests_low_base_budget_reduced(self, estimator):
        """tests/low should use 6144 base (down from 8192)."""
        estimate = TokenEstimate(
            estimated_tokens=2500,
            deliverable_count=1,
            category="tests",
            complexity="low",
            breakdown={},
            confidence=0.8
        )
        budget = estimator.select_budget(estimate, "low")
        # With 2500 * 1.2 buffer = 3000, base floor of 6144 should apply
        assert budget == 6144, f"Expected tests/low base=6144, got {budget}"

    def test_doc_synthesis_base_unchanged(self, estimator):
        """doc_synthesis should keep high base (8192) for safety."""
        estimate = TokenEstimate(
            estimated_tokens=2000,
            deliverable_count=1,
            category="doc_synthesis",
            complexity="low",
            breakdown={},
            confidence=0.8
        )
        budget = estimator.select_budget(estimate, "low")
        # doc_synthesis gets 2.2x buffer: 2000 * 2.2 = 4400
        # Base floor is 8192 (unchanged), so should use base
        assert budget == 8192, f"Expected doc_synthesis/low base=8192, got {budget}"

    def test_doc_sot_update_base_unchanged(self, estimator):
        """doc_sot_update should keep high base (8192) for safety."""
        estimate = TokenEstimate(
            estimated_tokens=2000,
            deliverable_count=1,
            category="doc_sot_update",
            complexity="low",
            breakdown={},
            confidence=0.8
        )
        budget = estimator.select_budget(estimate, "low")
        # doc_sot_update gets 2.2x buffer: 2000 * 2.2 = 4400
        # Base floor is 8192 (unchanged), so should use base
        assert budget == 8192, f"Expected doc_sot_update/low base=8192, got {budget}"

    def test_implementation_low_base_unchanged(self, estimator):
        """implementation/low should keep 8192 base (high variance)."""
        estimate = TokenEstimate(
            estimated_tokens=3000,
            deliverable_count=1,
            category="implementation",
            complexity="low",
            breakdown={},
            confidence=0.8
        )
        budget = estimator.select_budget(estimate, "low")
        # With 3000 * 1.2 buffer = 3600, base floor of 8192 should apply
        assert budget == 8192, f"Expected implementation/low base=8192, got {budget}"

    def test_default_category_fallback(self, estimator):
        """Unknown categories should fall back to universal base budgets."""
        estimate = TokenEstimate(
            estimated_tokens=3000,
            deliverable_count=1,
            category="unknown_category",
            complexity="low",
            breakdown={},
            confidence=0.8
        )
        budget = estimator.select_budget(estimate, "low")
        # Should fall back to universal low=8192
        assert budget == 8192, f"Expected fallback low base=8192, got {budget}"

    def test_category_normalization_documentation(self, estimator):
        """'documentation' category should normalize to 'docs'."""
        estimate = TokenEstimate(
            estimated_tokens=2000,
            deliverable_count=1,
            category="documentation",  # Should normalize to "docs"
            complexity="low",
            breakdown={},
            confidence=0.8
        )
        budget = estimator.select_budget(estimate, "low")
        # Should use docs/low base=4096
        assert budget == 4096, f"Expected normalized docs/low base=4096, got {budget}"

    def test_category_normalization_testing(self, estimator):
        """'testing' category should normalize to 'tests'."""
        estimate = TokenEstimate(
            estimated_tokens=2500,
            deliverable_count=1,
            category="testing",  # Should normalize to "tests"
            complexity="low",
            breakdown={},
            confidence=0.8
        )
        budget = estimator.select_budget(estimate, "low")
        # Should use tests/low base=6144
        assert budget == 6144, f"Expected normalized tests/low base=6144, got {budget}"

    def test_estimate_exceeds_base_floor(self, estimator):
        """If estimated_with_buffer > base, should use estimated_with_buffer."""
        estimate = TokenEstimate(
            estimated_tokens=5000,  # 5000 * 1.2 = 6000 > 4096 base
            deliverable_count=1,
            category="docs",
            complexity="low",
            breakdown={},
            confidence=0.8
        )
        budget = estimator.select_budget(estimate, "low")
        # Should use estimated_with_buffer (6000) instead of base (4096)
        assert budget == 6000, f"Expected estimated_with_buffer=6000, got {budget}"

    def test_docs_low_waste_reduction_scenario(self, estimator):
        """
        Typical docs/low scenario from telemetry:
        - Predicted: 2600 tokens
        - Actual: ~3500 tokens
        - Old base: 8192 (waste 2.34x)
        - New base: 4096 (waste 1.17x)
        """
        estimate = TokenEstimate(
            estimated_tokens=2600,
            deliverable_count=1,
            category="docs",
            complexity="low",
            breakdown={},
            confidence=0.8
        )
        budget = estimator.select_budget(estimate, "low")
        # 2600 * 1.2 = 3120 < 4096, so should use base=4096
        assert budget == 4096, f"Expected new docs/low base=4096, got {budget}"

        # Verify waste improvement: 4096 / 3500 ≈ 1.17x (vs old 8192 / 3500 = 2.34x)
        typical_actual = 3500
        new_waste = budget / typical_actual
        old_waste = 8192 / typical_actual
        assert new_waste < 1.5, f"New waste {new_waste:.2f}x should be <1.5x"
        assert old_waste > 2.0, f"Old waste {old_waste:.2f}x should be >2.0x"
        assert new_waste < old_waste / 1.8, "Should reduce waste by >45%"
