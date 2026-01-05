"""Extended tests for context_budgeter.py.

Tests cover:
- Budget allocation strategies
- Priority handling and sorting
- Context splitting and truncation
- Edge cases (empty inputs, oversized content, zero budgets)
- Integration with file context and project rules

NOTE: This is an extended test suite for planned/enhanced ContextBudgeter features.
Tests are marked xfail until the enhanced API is implemented.
"""

import pytest

pytestmark = [
    pytest.mark.xfail(
        strict=False,
        reason="Extended ContextBudgeter API not implemented - aspirational test suite",
    ),
    pytest.mark.aspirational,
]


class TestBudgetAllocation:
    """Test budget allocation strategies."""

    def test_allocate_budget_basic(self):
        """Test basic budget allocation across categories."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=10000)
        allocation = budgeter.allocate_budget(
            categories=["file_context", "project_rules", "run_hints"]
        )

        # Should allocate budget to all categories
        assert "file_context" in allocation
        assert "project_rules" in allocation
        assert "run_hints" in allocation

        # Total should not exceed budget
        total_allocated = sum(allocation.values())
        assert total_allocated <= 10000

    def test_allocate_budget_with_priorities(self):
        """Test budget allocation respects priority weights."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=10000)
        allocation = budgeter.allocate_budget(
            categories=["file_context", "project_rules"],
            priorities={"file_context": 3, "project_rules": 1},
        )

        # Higher priority should get more budget
        assert allocation["file_context"] > allocation["project_rules"]

    def test_allocate_budget_single_category(self):
        """Test allocation with single category gets full budget."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=5000)
        allocation = budgeter.allocate_budget(categories=["file_context"])

        # Single category should get full budget
        assert allocation["file_context"] == 5000

    def test_allocate_budget_zero_budget(self):
        """Test allocation with zero budget."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=0)
        allocation = budgeter.allocate_budget(categories=["file_context", "project_rules"])

        # All allocations should be zero
        assert all(v == 0 for v in allocation.values())

    def test_allocate_budget_proportional_distribution(self):
        """Test that budget is distributed proportionally to priorities."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=10000)
        allocation = budgeter.allocate_budget(
            categories=["cat_a", "cat_b", "cat_c"], priorities={"cat_a": 2, "cat_b": 2, "cat_c": 1}
        )

        # cat_a and cat_b should have equal allocation
        assert allocation["cat_a"] == allocation["cat_b"]
        # cat_c should have half of cat_a
        assert allocation["cat_c"] * 2 == allocation["cat_a"]


class TestPriorityHandling:
    """Test priority handling and sorting."""

    def test_sort_by_priority_basic(self):
        """Test basic priority sorting."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=10000)
        items = [
            {"name": "low", "priority": 1, "content": "Low priority"},
            {"name": "high", "priority": 3, "content": "High priority"},
            {"name": "medium", "priority": 2, "content": "Medium priority"},
        ]

        sorted_items = budgeter.sort_by_priority(items, key="priority")

        # Should be sorted high to low
        assert sorted_items[0]["name"] == "high"
        assert sorted_items[1]["name"] == "medium"
        assert sorted_items[2]["name"] == "low"

    def test_sort_by_priority_with_ties(self):
        """Test priority sorting with equal priorities."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=10000)
        items = [
            {"name": "a", "priority": 2},
            {"name": "b", "priority": 2},
            {"name": "c", "priority": 1},
        ]

        sorted_items = budgeter.sort_by_priority(items, key="priority")

        # Items with same priority should maintain relative order
        assert sorted_items[0]["priority"] == 2
        assert sorted_items[1]["priority"] == 2
        assert sorted_items[2]["priority"] == 1

    def test_priority_filtering(self):
        """Test filtering items by minimum priority."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=10000)
        items = [
            {"name": "low", "priority": 1},
            {"name": "medium", "priority": 2},
            {"name": "high", "priority": 3},
        ]

        filtered = budgeter.filter_by_priority(items, min_priority=2, key="priority")

        # Should only include medium and high
        assert len(filtered) == 2
        assert all(item["priority"] >= 2 for item in filtered)


class TestContextSplitting:
    """Test context splitting and truncation."""

    def test_split_content_basic(self):
        """Test basic content splitting."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=10000)
        content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"

        chunks = budgeter.split_content(content, max_chunk_size=20)

        # Should split into multiple chunks
        assert len(chunks) > 1
        # Each chunk should be within size limit
        assert all(len(chunk) <= 20 for chunk in chunks)

    def test_split_content_preserves_lines(self):
        """Test that splitting preserves line boundaries."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=10000)
        content = "Line 1\nLine 2\nLine 3"

        chunks = budgeter.split_content(content, max_chunk_size=10, preserve_lines=True)

        # Should not split in middle of lines
        for chunk in chunks:
            assert not chunk.startswith(" ")
            assert not chunk.endswith(" ")

    def test_truncate_content_basic(self):
        """Test basic content truncation."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=10000)
        content = "A" * 1000

        truncated = budgeter.truncate_content(content, max_length=100)

        # Should be truncated to max length
        assert len(truncated) <= 100
        # Should indicate truncation
        assert "..." in truncated or "[truncated]" in truncated

    def test_truncate_content_with_ellipsis(self):
        """Test truncation adds ellipsis marker."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=10000)
        content = "This is a very long piece of content that needs truncation"

        truncated = budgeter.truncate_content(content, max_length=30, add_ellipsis=True)

        assert len(truncated) <= 30
        assert truncated.endswith("...")

    def test_split_large_file_context(self):
        """Test splitting large file context into manageable chunks."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=5000)
        large_file = {"path": "test.py", "content": "X" * 10000}

        chunks = budgeter.split_file_context(large_file, max_chunk_size=2000)

        # Should split into multiple chunks
        assert len(chunks) > 1
        # Each chunk should have path metadata
        assert all("path" in chunk for chunk in chunks)
        # Total content should be preserved
        total_content = "".join(chunk["content"] for chunk in chunks)
        assert len(total_content) <= 10000


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_input(self):
        """Test handling of empty input."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=10000)
        result = budgeter.allocate_budget(categories=[])

        # Should return empty allocation
        assert result == {}

    def test_oversized_single_item(self):
        """Test handling of single item exceeding budget."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=100)
        content = "X" * 1000

        truncated = budgeter.fit_to_budget(content, budget=100)

        # Should truncate to fit budget
        assert len(truncated) <= 100

    def test_negative_budget(self):
        """Test handling of negative budget."""
        from autopack.context_budgeter import ContextBudgeter

        with pytest.raises(ValueError, match="budget.*positive"):
            ContextBudgeter(total_budget=-1000)

    def test_none_content(self):
        """Test handling of None content."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=10000)
        result = budgeter.truncate_content(None, max_length=100)

        # Should handle gracefully
        assert result == "" or result is None

    def test_unicode_content(self):
        """Test handling of unicode content."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=10000)
        content = "Hello 世界 🌍 Привет"

        truncated = budgeter.truncate_content(content, max_length=20)

        # Should handle unicode correctly
        assert len(truncated) <= 20
        # Should not break unicode characters
        assert truncated.encode("utf-8", errors="ignore").decode("utf-8") == truncated


class TestIntegration:
    """Test integration with file context and project rules."""

    def test_budget_file_context(self):
        """Test budgeting file context."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=5000)
        file_context = {
            "file1.py": "Content 1" * 100,
            "file2.py": "Content 2" * 100,
            "file3.py": "Content 3" * 100,
        }

        budgeted = budgeter.budget_file_context(file_context, budget=2000)

        # Should fit within budget
        total_size = sum(len(content) for content in budgeted.values())
        assert total_size <= 2000

    def test_budget_project_rules(self):
        """Test budgeting project rules."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=5000)
        rules = [
            {"rule": "Rule 1", "priority": 3, "content": "Important rule" * 50},
            {"rule": "Rule 2", "priority": 1, "content": "Less important" * 50},
            {"rule": "Rule 3", "priority": 2, "content": "Medium priority" * 50},
        ]

        budgeted = budgeter.budget_project_rules(rules, budget=1000)

        # Should prioritize high-priority rules
        assert len(budgeted) > 0
        # First rule should be highest priority
        assert budgeted[0]["priority"] == 3

    def test_budget_run_hints(self):
        """Test budgeting run hints."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=5000)
        hints = [
            "Hint 1: Use async" * 20,
            "Hint 2: Add tests" * 20,
            "Hint 3: Update docs" * 20,
        ]

        budgeted = budgeter.budget_run_hints(hints, budget=500)

        # Should fit within budget
        total_size = sum(len(hint) for hint in budgeted)
        assert total_size <= 500

    def test_full_context_budgeting(self):
        """Test complete context budgeting workflow."""
        from autopack.context_budgeter import ContextBudgeter

        budgeter = ContextBudgeter(total_budget=10000)

        file_context = {"file.py": "Content" * 500}
        project_rules = [{"rule": "Rule", "priority": 2, "content": "Rule content" * 100}]
        run_hints = ["Hint" * 100]

        result = budgeter.budget_all_context(
            file_context=file_context, project_rules=project_rules, run_hints=run_hints
        )

        # Should return budgeted versions of all inputs
        assert "file_context" in result
        assert "project_rules" in result
        assert "run_hints" in result

        # Total should fit within budget
        total_size = (
            sum(len(c) for c in result["file_context"].values())
            + sum(len(r["content"]) for r in result["project_rules"])
            + sum(len(h) for h in result["run_hints"])
        )
        assert total_size <= 10000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
