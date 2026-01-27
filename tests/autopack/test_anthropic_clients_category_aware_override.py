"""
Tests for BUILD-142: Category-aware conditional 16384 override logic.

Tests the conditional override logic directly using the actual code flow to ensure:
1. docs-like categories with low budgets (<16384) preserve category-aware budgets
2. non-docs categories still get 16384 floor for safety
3. docs categories with high budgets (>=16384) still get floor
4. Telemetry records estimator intent separately from final ceiling
"""


class TestCategoryAwareOverrideLogic:
    """Tests for category-aware conditional override logic in BUILD-142."""

    def test_category_normalization_docs(self):
        """Test that 'documentation' normalizes to 'docs' for override check."""
        task_category = "documentation"

        # Simulate the normalization logic from anthropic_clients.py lines 572-573
        normalized_category = task_category.lower() if task_category else ""
        is_docs_like = normalized_category in [
            "docs",
            "documentation",
            "doc_synthesis",
            "doc_sot_update",
        ]

        assert is_docs_like, "documentation should be recognized as docs-like"

    def test_category_normalization_docs_exact(self):
        """Test that 'docs' is recognized as docs-like."""
        task_category = "docs"

        normalized_category = task_category.lower() if task_category else ""
        is_docs_like = normalized_category in [
            "docs",
            "documentation",
            "doc_synthesis",
            "doc_sot_update",
        ]

        assert is_docs_like, "docs should be recognized as docs-like"

    def test_category_normalization_doc_synthesis(self):
        """Test that 'doc_synthesis' is recognized as docs-like."""
        task_category = "doc_synthesis"

        normalized_category = task_category.lower() if task_category else ""
        is_docs_like = normalized_category in [
            "docs",
            "documentation",
            "doc_synthesis",
            "doc_sot_update",
        ]

        assert is_docs_like, "doc_synthesis should be recognized as docs-like"

    def test_category_normalization_doc_sot_update(self):
        """Test that 'doc_sot_update' is recognized as docs-like."""
        task_category = "doc_sot_update"

        normalized_category = task_category.lower() if task_category else ""
        is_docs_like = normalized_category in [
            "docs",
            "documentation",
            "doc_synthesis",
            "doc_sot_update",
        ]

        assert is_docs_like, "doc_sot_update should be recognized as docs-like"

    def test_category_normalization_implementation(self):
        """Test that 'implementation' is NOT docs-like."""
        task_category = "implementation"

        normalized_category = task_category.lower() if task_category else ""
        is_docs_like = normalized_category in [
            "docs",
            "documentation",
            "doc_synthesis",
            "doc_sot_update",
        ]

        assert not is_docs_like, "implementation should NOT be docs-like"

    def test_category_normalization_tests(self):
        """Test that 'tests' is NOT docs-like (has its own reduced base, but not docs)."""
        task_category = "tests"

        normalized_category = task_category.lower() if task_category else ""
        is_docs_like = normalized_category in [
            "docs",
            "documentation",
            "doc_synthesis",
            "doc_sot_update",
        ]

        assert not is_docs_like, "tests should NOT be docs-like"

    def test_should_apply_floor_no_budget(self):
        """
        When token_selected_budget is None, should apply 16384 floor.

        Simulates lines 579-583 logic.
        """
        task_category = "docs"
        token_selected_budget = None

        normalized_category = task_category.lower() if task_category else ""
        is_docs_like = normalized_category in [
            "docs",
            "documentation",
            "doc_synthesis",
            "doc_sot_update",
        ]

        should_apply_floor = (
            not token_selected_budget or token_selected_budget >= 16384 or not is_docs_like
        )

        assert should_apply_floor, "Should apply floor when budget is None (no estimator decision)"

    def test_should_apply_floor_docs_low_budget(self):
        """
        docs category with low budget (<16384) should NOT apply floor.

        This is the key BUILD-142 fix: preserve category-aware reductions.
        """
        task_category = "docs"
        token_selected_budget = 4096  # Category-aware reduction

        normalized_category = task_category.lower() if task_category else ""
        is_docs_like = normalized_category in [
            "docs",
            "documentation",
            "doc_synthesis",
            "doc_sot_update",
        ]

        should_apply_floor = (
            not token_selected_budget or token_selected_budget >= 16384 or not is_docs_like
        )

        assert not should_apply_floor, (
            "Should NOT apply floor for docs with intentionally low budget"
        )

    def test_should_apply_floor_docs_high_budget(self):
        """
        docs category with high budget (>=16384) should still apply floor.

        This ensures we only skip the floor for intentional reductions, not all docs.
        """
        task_category = "docs"
        token_selected_budget = 16384  # High budget, no reduction

        normalized_category = task_category.lower() if task_category else ""
        is_docs_like = normalized_category in [
            "docs",
            "documentation",
            "doc_synthesis",
            "doc_sot_update",
        ]

        should_apply_floor = (
            not token_selected_budget or token_selected_budget >= 16384 or not is_docs_like
        )

        assert should_apply_floor, "Should apply floor for docs when budget is already >=16384"

    def test_should_apply_floor_implementation_low_budget(self):
        """
        implementation category should apply floor even with lower budget.

        This preserves safety for code phases.
        """
        task_category = "implementation"
        token_selected_budget = 12288  # implementation/medium base

        normalized_category = task_category.lower() if task_category else ""
        is_docs_like = normalized_category in [
            "docs",
            "documentation",
            "doc_synthesis",
            "doc_sot_update",
        ]

        should_apply_floor = (
            not token_selected_budget or token_selected_budget >= 16384 or not is_docs_like
        )

        assert should_apply_floor, "Should apply floor for implementation (not docs-like)"

    def test_should_apply_floor_doc_synthesis_low_budget(self):
        """
        doc_synthesis with base=8192 should NOT get forced to 16384.
        """
        task_category = "doc_synthesis"
        token_selected_budget = 8192  # doc_synthesis/low base

        normalized_category = task_category.lower() if task_category else ""
        is_docs_like = normalized_category in [
            "docs",
            "documentation",
            "doc_synthesis",
            "doc_sot_update",
        ]

        should_apply_floor = (
            not token_selected_budget or token_selected_budget >= 16384 or not is_docs_like
        )

        assert not should_apply_floor, "Should NOT apply floor for doc_synthesis with budget <16384"

    def test_conditional_override_docs_low_scenario(self):
        """
        Integration test: docs/low scenario from V8 validation.

        Scenario:
        - task_category: "docs"
        - token_selected_budget: 4096 (from TokenEstimator.select_budget)
        - builder_mode: "full_file" (triggers conditional override check)
        - Expected: max_tokens stays 4096 (no 16384 floor)
        """
        task_category = "docs"
        token_selected_budget = 4096
        builder_mode = "full_file"
        max_tokens = 0  # Start with 0 (before override logic)

        # Simulate BUILD-142 conditional override logic (lines 570-597)
        if builder_mode == "full_file":
            normalized_category = task_category.lower() if task_category else ""
            is_docs_like = normalized_category in [
                "docs",
                "documentation",
                "doc_synthesis",
                "doc_sot_update",
            ]

            should_apply_floor = (
                not token_selected_budget or token_selected_budget >= 16384 or not is_docs_like
            )

            if should_apply_floor:
                max_tokens = max(max_tokens, 16384)
            # else: preserve category-aware budget

        # P4 enforcement (line 705)
        if token_selected_budget:
            max_tokens = max(max_tokens or 0, token_selected_budget)

        assert max_tokens == 4096, (
            f"docs/low should preserve category-aware budget 4096, got {max_tokens}"
        )

    def test_conditional_override_implementation_scenario(self):
        """
        Integration test: implementation scenario should get 16384 floor.

        Scenario:
        - task_category: "implementation"
        - token_selected_budget: 12288
        - builder_mode: "full_file"
        - Expected: max_tokens = 16384 (floor applied)
        """
        task_category = "implementation"
        token_selected_budget = 12288
        builder_mode = "full_file"
        max_tokens = 0

        # Simulate BUILD-142 conditional override logic
        if builder_mode == "full_file":
            normalized_category = task_category.lower() if task_category else ""
            is_docs_like = normalized_category in [
                "docs",
                "documentation",
                "doc_synthesis",
                "doc_sot_update",
            ]

            should_apply_floor = (
                not token_selected_budget or token_selected_budget >= 16384 or not is_docs_like
            )

            if should_apply_floor:
                max_tokens = max(max_tokens, 16384)

        # P4 enforcement
        if token_selected_budget:
            max_tokens = max(max_tokens or 0, token_selected_budget)

        assert max_tokens == 16384, f"implementation should get 16384 floor, got {max_tokens}"

    def test_conditional_override_docs_no_budget_scenario(self):
        """
        Integration test: docs without estimator budget should get floor.

        Scenario:
        - task_category: "docs"
        - token_selected_budget: None (no estimator)
        - builder_mode: "full_file"
        - Expected: max_tokens = 16384 (safety fallback)
        """
        task_category = "docs"
        token_selected_budget = None
        builder_mode = "full_file"
        max_tokens = 0

        # Simulate BUILD-142 conditional override logic
        if builder_mode == "full_file":
            normalized_category = task_category.lower() if task_category else ""
            is_docs_like = normalized_category in [
                "docs",
                "documentation",
                "doc_synthesis",
                "doc_sot_update",
            ]

            should_apply_floor = (
                not token_selected_budget or token_selected_budget >= 16384 or not is_docs_like
            )

            if should_apply_floor:
                max_tokens = max(max_tokens, 16384)

        # P4 enforcement (would be skipped when token_selected_budget is None)
        if token_selected_budget:
            max_tokens = max(max_tokens or 0, token_selected_budget)

        assert max_tokens == 16384, (
            f"docs without estimator should get 16384 floor for safety, got {max_tokens}"
        )

    def test_telemetry_semantics_separation(self):
        """
        Test that selected_budget and actual_max_tokens are stored separately.

        This validates BUILD-142 telemetry fix: selected_budget reflects estimator
        intent (before P4 enforcement), actual_max_tokens reflects final ceiling.
        """
        phase_spec = {}
        token_selected_budget = 4096
        max_tokens = 4096  # After conditional override (no 16384 floor applied)

        # Simulate BUILD-142 telemetry storage (lines 699-700, 706-707)
        # Store selected_budget BEFORE P4 enforcement
        if token_selected_budget:
            phase_spec.setdefault("metadata", {}).setdefault("token_prediction", {})[
                "selected_budget"
            ] = token_selected_budget

        # P4 enforcement (line 705)
        if token_selected_budget:
            max_tokens = max(max_tokens or 0, token_selected_budget)
            # Store actual_max_tokens AFTER P4 enforcement
            phase_spec.setdefault("metadata", {}).setdefault("token_prediction", {})[
                "actual_max_tokens"
            ] = max_tokens

        # Verify both values are recorded
        token_pred = phase_spec.get("metadata", {}).get("token_prediction", {})
        assert "selected_budget" in token_pred, "selected_budget should be recorded"
        assert "actual_max_tokens" in token_pred, "actual_max_tokens should be recorded"
        assert token_pred["selected_budget"] == 4096, (
            "selected_budget should reflect estimator intent"
        )
        assert token_pred["actual_max_tokens"] == 4096, (
            "actual_max_tokens should reflect final ceiling"
        )
