"""
Tests for DOC_SYNTHESIS detection and phase-based estimation.

BUILD-129 Phase 3: Verify that documentation tasks requiring code investigation
are correctly classified as DOC_SYNTHESIS vs DOC_WRITE.
"""
import pytest
from pathlib import Path
from autopack.token_estimator import TokenEstimator


class TestDocSynthesisDetection:
    """Test suite for DOC_SYNTHESIS classification logic."""

    def setup_method(self):
        """Setup test fixture."""
        self.estimator = TokenEstimator(workspace=Path.cwd())

    def test_api_reference_triggers_doc_synthesis(self):
        """API_REFERENCE.md deliverable should trigger DOC_SYNTHESIS."""
        deliverables = [
            "docs/API_REFERENCE.md",
            "docs/OVERVIEW.md",
        ]
        task_description = "Create comprehensive documentation from scratch"

        is_synthesis = self.estimator._is_doc_synthesis(deliverables, task_description)
        assert is_synthesis is True, "API_REFERENCE.md should trigger DOC_SYNTHESIS"

    def test_examples_with_research_triggers_doc_synthesis(self):
        """EXAMPLES.md + 'from scratch' should trigger DOC_SYNTHESIS."""
        deliverables = [
            "docs/EXAMPLES.md",
            "docs/USAGE_GUIDE.md",
        ]
        task_description = "Create documentation from scratch with code examples"

        is_synthesis = self.estimator._is_doc_synthesis(deliverables, task_description)
        assert is_synthesis is True, "EXAMPLES.md + research should trigger DOC_SYNTHESIS"

    def test_plain_readme_update_is_not_synthesis(self):
        """Simple README update should NOT trigger DOC_SYNTHESIS."""
        deliverables = ["README.md"]
        task_description = "Update README with new installation instructions"

        is_synthesis = self.estimator._is_doc_synthesis(deliverables, task_description)
        assert is_synthesis is False, "Simple README update should be DOC_WRITE"

    def test_changelog_is_not_synthesis(self):
        """CHANGELOG.md should NOT trigger DOC_SYNTHESIS."""
        deliverables = ["CHANGELOG.md"]
        task_description = "Add v1.2.0 changelog entry"

        is_synthesis = self.estimator._is_doc_synthesis(deliverables, task_description)
        assert is_synthesis is False, "CHANGELOG should be DOC_WRITE"

    def test_doc_synthesis_estimation_includes_investigation_phase(self):
        """DOC_SYNTHESIS estimate should include investigation tokens."""
        deliverables = [
            "docs/API_REFERENCE.md",
            "docs/EXAMPLES.md",
            "docs/USAGE_GUIDE.md",
            "docs/OVERVIEW.md",
            "docs/FAQ.md",
        ]
        task_description = "Create comprehensive documentation from scratch"

        estimate = self.estimator.estimate(
            deliverables=deliverables,
            category="documentation",
            complexity="low",
            scope_paths=[],  # No context = investigation required
            task_description=task_description,
        )

        # Should detect DOC_SYNTHESIS and return category override
        assert estimate.category == "doc_synthesis", "Should override category to doc_synthesis"

        # Should have investigation phase in breakdown
        assert "doc_synthesis_investigate" in estimate.breakdown
        assert estimate.breakdown["doc_synthesis_investigate"] > 0

        # Investigation should be 2500 tokens for "none" context quality
        assert estimate.breakdown["doc_synthesis_investigate"] == 2500

    def test_doc_synthesis_with_context_reduces_investigation(self):
        """DOC_SYNTHESIS with strong context should reduce investigation tokens."""
        deliverables = ["docs/API_REFERENCE.md"]
        task_description = "Document the REST API"

        # With strong context (>10 scope paths)
        estimate_with_context = self.estimator.estimate(
            deliverables=deliverables,
            category="documentation",
            complexity="low",
            scope_paths=["src/api/routes.py"] * 15,  # 15 paths = "strong" context
            task_description=task_description,
        )

        # With no context
        estimate_no_context = self.estimator.estimate(
            deliverables=deliverables,
            category="documentation",
            complexity="low",
            scope_paths=[],
            task_description=task_description,
        )

        # Investigation tokens should be lower with context
        investigate_with = estimate_with_context.breakdown["doc_synthesis_investigate"]
        investigate_without = estimate_no_context.breakdown["doc_synthesis_investigate"]

        assert investigate_with < investigate_without
        assert investigate_with == 1500  # "strong" context
        assert investigate_without == 2500  # "none" context

    def test_doc_synthesis_includes_api_extraction_phase(self):
        """DOC_SYNTHESIS with API reference should include extraction tokens."""
        deliverables = ["docs/API_REFERENCE.md"]
        task_description = "Document REST API endpoints"

        estimate = self.estimator.estimate(
            deliverables=deliverables,
            category="documentation",
            complexity="low",
            scope_paths=[],
            task_description=task_description,
        )

        # Should include API extraction phase
        assert "doc_synthesis_api_extract" in estimate.breakdown
        assert estimate.breakdown["doc_synthesis_api_extract"] == 1200

    def test_doc_synthesis_includes_examples_phase(self):
        """DOC_SYNTHESIS with examples should include examples generation tokens."""
        deliverables = ["docs/EXAMPLES.md", "docs/USAGE_GUIDE.md"]
        task_description = "Create usage guide from scratch with code examples"

        estimate = self.estimator.estimate(
            deliverables=deliverables,
            category="documentation",
            complexity="low",
            scope_paths=[],
            task_description=task_description,
        )

        # Should include examples phase
        assert "doc_synthesis_examples" in estimate.breakdown
        assert estimate.breakdown["doc_synthesis_examples"] == 1400

    def test_doc_synthesis_includes_coordination_overhead(self):
        """DOC_SYNTHESIS with >=5 deliverables should include coordination overhead."""
        deliverables = [
            "docs/OVERVIEW.md",
            "docs/USAGE_GUIDE.md",
            "docs/API_REFERENCE.md",
            "docs/EXAMPLES.md",
            "docs/FAQ.md",
        ]
        task_description = "Create comprehensive documentation from scratch"

        estimate = self.estimator.estimate(
            deliverables=deliverables,
            category="documentation",
            complexity="low",
            scope_paths=[],
            task_description=task_description,
        )

        # Should include coordination overhead (12% of writing)
        assert "doc_synthesis_coordination" in estimate.breakdown
        coordination = estimate.breakdown["doc_synthesis_coordination"]
        writing = estimate.breakdown["doc_synthesis_writing"]

        # Coordination should be ~12% of writing
        expected_coordination = int(0.12 * writing)
        assert coordination == expected_coordination
        assert coordination > 0

    def test_doc_synthesis_total_matches_real_world_sample(self):
        """DOC_SYNTHESIS estimate should be close to real-world sample (16384 actual tokens)."""
        # Real sample from telemetry:
        # - 5 deliverables (OVERVIEW, USAGE_GUIDE, API_REFERENCE, EXAMPLES, FAQ)
        # - Zero code context provided
        # - Actual tokens: 16384 (truncated)
        # - Predicted (old): 5200 tokens (SMAPE 103.6%)

        deliverables = [
            "docs/OVERVIEW.md",
            "docs/USAGE_GUIDE.md",
            "docs/API_REFERENCE.md",
            "docs/EXAMPLES.md",
            "docs/FAQ.md",
        ]
        task_description = "Create comprehensive documentation from scratch"

        estimate = self.estimator.estimate(
            deliverables=deliverables,
            category="documentation",
            complexity="low",
            scope_paths=[],  # Zero context, like real sample
            task_description=task_description,
        )

        # Phase breakdown:
        # - Investigation: 2500 (context_quality = "none")
        # - API extraction: 1200 (API_REFERENCE.md present)
        # - Examples: 1400 (EXAMPLES.md present)
        # - Writing: 850 * 5 = 4250
        # - Coordination: 0.12 * 4250 = 510
        # Base total: 2500 + 1200 + 1400 + 4250 + 510 = 9860
        # With safety margin (1.3x): 9860 * 1.3 = 12818

        expected_base = 2500 + 1200 + 1400 + (850 * 5) + int(0.12 * (850 * 5))
        expected_total = int(expected_base * 1.3)

        assert estimate.estimated_tokens == expected_total

        # New estimate should be much closer to actual 16384 than old 5200
        # SMAPE = |predicted - actual| / ((predicted + actual) / 2) * 100
        old_smape = abs(5200 - 16384) / ((5200 + 16384) / 2) * 100
        new_smape = abs(estimate.estimated_tokens - 16384) / ((estimate.estimated_tokens + 16384) / 2) * 100

        assert new_smape < old_smape, f"New SMAPE ({new_smape:.1f}%) should be < old SMAPE ({old_smape:.1f}%)"
        assert new_smape < 50, f"New SMAPE ({new_smape:.1f}%) should be <50% (target accuracy)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
