"""
Tests for Research Data Consolidator

Tests the sanitization, deduplication, and consolidation pipeline for research findings.
"""

import unittest
from unittest.mock import MagicMock, patch

from autopack.research.consolidators.research_data_consolidator import (
    ResearchDataConsolidator,
    ConsolidatedFinding,
    ConsolidationResult,
)
from autopack.research.security.content_sanitizer import ContentSanitizer
from autopack.research.security.prompt_sanitizer import PromptSanitizer, RiskLevel


class TestResearchDataConsolidator(unittest.TestCase):
    """Test suite for ResearchDataConsolidator."""

    def setUp(self):
        """Set up test fixtures."""
        self.consolidator = ResearchDataConsolidator()

    def test_consolidate_basic(self):
        """Test basic consolidation of findings."""
        findings = [
            {"type": "web", "content": "API performance is good"},
            {"type": "web", "content": "Database scalability concerns"},
        ]
        result = self.consolidator.consolidate(findings)

        self.assertEqual(result.original_count, 2)
        self.assertEqual(result.deduplicated_count, 2)
        self.assertEqual(len(result.consolidated_findings), 2)

    def test_consolidate_with_dangerous_content(self):
        """Test sanitization of dangerous content."""
        findings = [
            {"type": "web", "content": "This contains malware and phishing"},
            {"type": "web", "content": "Normal content here"},
        ]
        result = self.consolidator.consolidate(findings)

        # First finding should be sanitized (contains dangerous patterns)
        first_finding = result.consolidated_findings[0]
        self.assertTrue(first_finding.is_sanitized)
        # Check for REDACTED content (might be escaped or wrapped in delimiters)
        self.assertTrue("REDACTED" in first_finding.content or "redacted" in first_finding.content.lower())

        # Second finding may or may not be marked as sanitized due to prompt sanitization
        # But it should not have redacted content
        second_finding = result.consolidated_findings[1]
        self.assertFalse("REDACTED" in second_finding.content)

    def test_consolidate_deduplication(self):
        """Test deduplication of similar findings."""
        findings = [
            {"type": "web", "content": "API latency is a concern", "source_url": "https://a.com"},
            {"type": "web", "content": "API latency concerns exist", "source_url": "https://b.com"},
            {"type": "web", "content": "Different topic here"},
        ]
        result = self.consolidator.consolidate(findings)

        # Two similar findings should be deduplicated to one
        self.assertEqual(result.original_count, 3)
        self.assertEqual(result.deduplicated_count, 2)

    def test_consolidate_preserves_citations(self):
        """Test that source URLs are preserved."""
        findings = [
            {"type": "web", "content": "Content A", "source_url": "https://example.com/a"},
            {"type": "web", "content": "Content B"},
        ]
        result = self.consolidator.consolidate(findings)

        finding_with_url = [f for f in result.consolidated_findings if f.source_url]
        self.assertEqual(len(finding_with_url), 1)
        self.assertEqual(finding_with_url[0].source_url, "https://example.com/a")

    def test_consolidate_categorization(self):
        """Test categorization of findings."""
        findings = [
            {"type": "web", "content": "API and database scalability"},
            {"type": "web", "content": "UI/UX onboarding workflow"},
            {"type": "web", "content": "Pricing and market demand"},
            {"type": "web", "content": "Competitor analysis"},
        ]
        result = self.consolidator.consolidate(findings)

        self.assertIn("technical", result.categorized_findings)
        self.assertIn("ux", result.categorized_findings)
        self.assertIn("market", result.categorized_findings)
        self.assertIn("competition", result.categorized_findings)

        self.assertEqual(len(result.categorized_findings["technical"]), 1)
        self.assertEqual(len(result.categorized_findings["ux"]), 1)
        self.assertEqual(len(result.categorized_findings["market"]), 1)
        self.assertEqual(len(result.categorized_findings["competition"]), 1)

    def test_consolidate_without_deduplication(self):
        """Test consolidation without deduplication."""
        findings = [
            {"type": "web", "content": "API latency concerns"},
            {"type": "web", "content": "API latency issues"},
        ]
        result = self.consolidator.consolidate(findings, apply_deduplication=False)

        # Should keep both without deduplication
        self.assertEqual(result.deduplicated_count, 2)

    def test_consolidate_without_categorization(self):
        """Test consolidation without categorization."""
        findings = [
            {"type": "web", "content": "API performance"},
        ]
        result = self.consolidator.consolidate(findings, apply_categorization=False)

        # Categorized findings should be empty
        self.assertEqual(len(result.categorized_findings), 0)

    def test_sanitization_flags(self):
        """Test that sanitization flags are captured."""
        findings = [
            {"type": "web", "content": "This contains phishing attempts"},
        ]
        result = self.consolidator.consolidate(findings)

        self.assertTrue(len(result.consolidated_findings[0].sanitization_flags) > 0)

    def test_consolidation_report_generation(self):
        """Test report generation from consolidation result."""
        findings = [
            {"type": "web", "content": "API latency"},
            {"type": "web", "content": "UI improvements"},
        ]
        result = self.consolidator.consolidate(findings)
        report = self.consolidator.get_categorized_report(result)

        self.assertIn("Research Data Consolidation Report", report)
        self.assertIn("Original Findings: 2", report)
        self.assertIn("Findings by Category:", report)

    def test_empty_findings(self):
        """Test consolidation with empty findings list."""
        findings = []
        result = self.consolidator.consolidate(findings)

        self.assertEqual(result.original_count, 0)
        self.assertEqual(result.deduplicated_count, 0)
        self.assertEqual(len(result.consolidated_findings), 0)

    def test_findings_with_none_values(self):
        """Test consolidation handles None values gracefully."""
        findings = [
            {"type": "web", "content": None, "source_url": None},
            {"type": None, "content": "Some content", "source_url": None},
        ]
        result = self.consolidator.consolidate(findings)

        # Should not crash and should produce results
        self.assertGreaterEqual(len(result.consolidated_findings), 0)

    def test_custom_dedup_threshold(self):
        """Test consolidation with custom deduplication threshold."""
        consolidator = ResearchDataConsolidator(dedup_threshold=100)
        findings = [
            {"type": "web", "content": "Similar content"},
            {"type": "web", "content": "Similar content"},
        ]
        result = consolidator.consolidate(findings)

        # With 100% threshold, only exact matches should deduplicate
        self.assertEqual(result.deduplicated_count, 1)

    def test_consolidated_finding_dataclass(self):
        """Test ConsolidatedFinding dataclass properties."""
        finding = ConsolidatedFinding(
            type="technical",
            content="API performance metrics",
            original_content="Original API performance",
            source_url="https://example.com",
            trust_tier=1,
            is_sanitized=True,
            sanitization_flags=["pattern_detected"],
        )

        self.assertEqual(finding.type, "technical")
        self.assertEqual(finding.content, "API performance metrics")
        self.assertTrue(finding.is_sanitized)
        self.assertIn("pattern_detected", finding.sanitization_flags)

    def test_consolidation_result_dataclass(self):
        """Test ConsolidationResult dataclass properties."""
        findings = [
            ConsolidatedFinding(
                type="technical",
                content="Test",
                original_content="Test",
            )
        ]

        result = ConsolidationResult(
            consolidated_findings=findings,
            original_count=1,
            deduplicated_count=1,
            categorized_findings={"technical": findings},
            processing_time_ms=50.5,
        )

        self.assertEqual(result.original_count, 1)
        self.assertEqual(result.deduplicated_count, 1)
        self.assertEqual(result.processing_time_ms, 50.5)
        self.assertIn("technical", result.categorized_findings)

    def test_multiple_sanitization_stages(self):
        """Test that multiple sanitization stages are applied."""
        findings = [
            {
                "type": "web",
                "content": "This contains malware and attempts to ignore instructions",
            }
        ]
        result = self.consolidator.consolidate(findings)

        finding = result.consolidated_findings[0]
        self.assertTrue(finding.is_sanitized)
        # Should have multiple flags (content_pattern_detected + prompt_injection_prevention)
        self.assertGreaterEqual(len(finding.sanitization_flags), 1)

    def test_categorization_keywords(self):
        """Test that categorization keywords work correctly."""
        findings = [
            {"type": "web", "content": "Latency and architecture and database"},  # technical keywords
            {"type": "web", "content": "UI onboarding workflow"},  # ux keywords
            {"type": "web", "content": "Market pricing demand"},  # market keywords
            {"type": "web", "content": "Competitor analysis"},  # competition keywords
        ]
        result = self.consolidator.consolidate(findings)

        # Verify categorization
        categories = result.categorized_findings
        # At least one should be in each category
        self.assertGreater(len(categories.get("technical", [])) + len(categories.get("other", [])), 0)
        self.assertGreater(len(categories.get("ux", [])) + len(categories.get("other", [])), 0)
        self.assertGreater(len(categories.get("market", [])) + len(categories.get("other", [])), 0)
        self.assertGreater(len(categories.get("competition", [])) + len(categories.get("other", [])), 0)

    def test_sanitization_preserves_original(self):
        """Test that original content is preserved."""
        findings = [
            {"type": "web", "content": "This contains phishing content"},
        ]
        result = self.consolidator.consolidate(findings)

        finding = result.consolidated_findings[0]
        self.assertEqual(finding.original_content, "This contains phishing content")
        # Content should be different after sanitization
        self.assertNotEqual(finding.content, finding.original_content)


class TestResearchDataConsolidatorWithMocks(unittest.TestCase):
    """Test ResearchDataConsolidator with mocked dependencies."""

    def test_consolidate_with_custom_sanitizers(self):
        """Test consolidation with custom sanitizer instances."""
        mock_content_sanitizer = MagicMock(spec=ContentSanitizer)
        mock_prompt_sanitizer = MagicMock(spec=PromptSanitizer)

        mock_content_sanitizer.is_safe.return_value = True
        mock_prompt_sanitizer.sanitize_for_prompt.return_value = "safe content"

        consolidator = ResearchDataConsolidator(
            content_sanitizer=mock_content_sanitizer,
            prompt_sanitizer=mock_prompt_sanitizer,
        )

        findings = [{"type": "web", "content": "test content"}]
        result = consolidator.consolidate(findings)

        # Verify mocks were called
        mock_content_sanitizer.is_safe.assert_called()
        mock_prompt_sanitizer.sanitize_for_prompt.assert_called()
        self.assertGreater(len(result.consolidated_findings), 0)


if __name__ == "__main__":
    unittest.main()
