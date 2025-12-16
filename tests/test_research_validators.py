"""Tests for research citation validators module.

This test suite verifies the citation validation logic, particularly:
1. Phase 1 fix: Numeric verification only checks extraction_span, not content
2. Text normalization for citation matching
3. Three-check validation system (quote in source, hash match, numeric validation)
"""

import pytest
from src.autopack.research.models.validators import (
    Finding,
    VerificationResult,
    CitationValidator
)


class TestCitationValidatorTextNormalization:
    """Test text normalization for citation matching."""

    def test_whitespace_normalization(self):
        """Normalize whitespace variations."""
        validator = CitationValidator()

        text1 = "The   quick\n\nbrown   fox"
        text2 = "The quick brown fox"

        normalized1 = validator._normalize_text(text1)
        normalized2 = validator._normalize_text(text2)

        assert normalized1 == normalized2
        assert normalized1 == "the quick brown fox"

    def test_case_insensitive(self):
        """Normalization is case-insensitive."""
        validator = CitationValidator()

        assert validator._normalize_text("Hello World") == validator._normalize_text("hello world")
        assert validator._normalize_text("CAPS") == validator._normalize_text("caps")

    def test_empty_string(self):
        """Handle empty strings gracefully."""
        validator = CitationValidator()

        assert validator._normalize_text("") == ""
        assert validator._normalize_text(None) == ""


class TestNumericVerificationPhase1:
    """Test Phase 1 fix: Only verify extraction_span contains numbers, not content."""

    def test_market_intelligence_with_numbers_valid(self):
        """Market intelligence finding with numbers in span is valid."""
        validator = CitationValidator()

        finding = Finding(
            content="Market valued at five hundred million dollars per year",
            extraction_span="The market size is approximately $500M annually",
            category="market_intelligence"
        )

        # Phase 1: We DON'T check if content numbers match span numbers
        # We only check that span has numbers
        result = validator._verify_numeric_extraction(finding, finding.extraction_span.lower())
        assert result is True

    def test_market_intelligence_without_numbers_invalid(self):
        """Market intelligence finding without numbers in span is invalid."""
        validator = CitationValidator()

        finding = Finding(
            content="The market is growing rapidly",
            extraction_span="The market is growing rapidly",
            category="market_intelligence"
        )

        # Span has no numbers but claims to be market intelligence -> suspicious
        result = validator._verify_numeric_extraction(finding, finding.extraction_span.lower())
        assert result is False

    def test_competitive_analysis_with_numbers_valid(self):
        """Competitive analysis finding with numbers in span is valid."""
        validator = CitationValidator()

        finding = Finding(
            content="GitHub has 100M+ active developers",
            extraction_span="GitHub reports over 100 million developers using the platform",
            category="competitive_analysis"
        )

        result = validator._verify_numeric_extraction(finding, finding.extraction_span.lower())
        assert result is True

    def test_competitive_analysis_without_numbers_invalid(self):
        """Competitive analysis finding without numbers in span is invalid."""
        validator = CitationValidator()

        finding = Finding(
            content="Competitor is popular",
            extraction_span="Competitor is popular",
            category="competitive_analysis"
        )

        result = validator._verify_numeric_extraction(finding, finding.extraction_span.lower())
        assert result is False

    def test_technical_analysis_no_number_requirement(self):
        """Technical analysis doesn't require numbers."""
        validator = CitationValidator()

        finding = Finding(
            content="Uses microservices architecture",
            extraction_span="Built with microservices architecture",
            category="technical_analysis"
        )

        # Technical analysis doesn't require numbers, so this passes
        result = validator._verify_numeric_extraction(finding, finding.extraction_span.lower())
        assert result is True

    def test_technical_analysis_with_numbers_also_valid(self):
        """Technical analysis with numbers is also valid."""
        validator = CitationValidator()

        finding = Finding(
            content="Handles 10000 requests per second",
            extraction_span="System can handle 10,000 RPS",
            category="technical_analysis"
        )

        result = validator._verify_numeric_extraction(finding, finding.extraction_span.lower())
        assert result is True

    def test_content_paraphrase_no_longer_fails(self):
        """Phase 1 fix: Content paraphrase doesn't cause failure.

        This is the PRIMARY bug fix - we no longer compare content numbers to span numbers.
        """
        validator = CitationValidator()

        # Content has no numbers (paraphrased), but span has numbers
        finding = Finding(
            content="Market valued at five hundred million dollars per year",  # No digits
            extraction_span="The market size is approximately $500M annually",  # Has "500"
            category="market_intelligence"
        )

        # Phase 0 (buggy): This would FAIL because content has no numbers
        # Phase 1 (fixed): This PASSES because span has numbers
        result = validator._verify_numeric_extraction(finding, finding.extraction_span.lower())
        assert result is True


class TestFullVerificationPipeline:
    """Test the complete verification pipeline with all 3 checks."""

    def test_all_checks_pass(self):
        """Valid citation passes all checks."""
        validator = CitationValidator()

        source_text = "Our platform has grown to serve over 100 million developers worldwide."
        source_hash = "abc123"

        finding = Finding(
            content="Platform serves 100M+ developers globally",
            extraction_span="serve over 100 million developers worldwide",
            category="market_intelligence",
            source_hash="abc123"
        )

        result = validator.verify(finding, source_text, source_hash)

        assert result.valid is True
        assert result.reason == "citation verified successfully"
        assert result.confidence == 0.95

    def test_extraction_span_not_in_source(self):
        """Check 1 fails: Extraction span not found in source."""
        validator = CitationValidator()

        source_text = "Our platform serves developers."
        source_hash = "abc123"

        finding = Finding(
            content="100M developers",
            extraction_span="over 500 million users",  # Not in source!
            category="market_intelligence",
            source_hash="abc123"
        )

        result = validator.verify(finding, source_text, source_hash)

        assert result.valid is False
        assert result.reason == "extraction_span not found in source document"
        assert result.confidence == 0.95

    def test_hash_mismatch(self):
        """Check 2 fails: Source hash mismatch."""
        validator = CitationValidator()

        source_text = "Our platform has grown to serve over 100 million developers worldwide."
        source_hash = "abc123"

        finding = Finding(
            content="Platform serves 100M+ developers",
            extraction_span="serve over 100 million developers worldwide",
            category="market_intelligence",
            source_hash="xyz789"  # Wrong hash!
        )

        result = validator.verify(finding, source_text, source_hash)

        assert result.valid is False
        assert result.reason == "source document hash mismatch"
        assert result.confidence == 0.99

    def test_numeric_claim_without_numbers(self):
        """Check 3 fails: Market intelligence claim without numbers in span."""
        validator = CitationValidator()

        source_text = "The market is growing rapidly with strong adoption."
        source_hash = "abc123"

        finding = Finding(
            content="Strong market growth",
            extraction_span="The market is growing rapidly",  # No numbers
            category="market_intelligence",
            source_hash="abc123"
        )

        result = validator.verify(finding, source_text, source_hash)

        assert result.valid is False
        assert result.reason == "numeric claim does not match extraction_span"
        assert result.confidence == 0.9

    def test_case_insensitive_matching(self):
        """Quote matching is case-insensitive after normalization."""
        validator = CitationValidator()

        source_text = "The Quick Brown Fox jumped over the LAZY dog."
        source_hash = "abc123"

        finding = Finding(
            content="Fox jumping behavior",
            extraction_span="THE QUICK BROWN FOX JUMPED OVER THE lazy DOG",
            category="technical_analysis",
            source_hash="abc123"
        )

        result = validator.verify(finding, source_text, source_hash)

        assert result.valid is True

    def test_whitespace_variations(self):
        """Quote matching handles whitespace variations."""
        validator = CitationValidator()

        source_text = "The   quick\n\nbrown   fox jumped over the lazy dog."
        source_hash = "abc123"

        finding = Finding(
            content="Fox jumping behavior",
            extraction_span="The quick brown fox jumped over the lazy dog",
            category="technical_analysis",
            source_hash="abc123"
        )

        result = validator.verify(finding, source_text, source_hash)

        assert result.valid is True

    def test_no_source_hash_skips_check2(self):
        """If finding has no source_hash, skip Check 2."""
        validator = CitationValidator()

        source_text = "Our platform serves over 100 million developers."
        source_hash = "abc123"

        finding = Finding(
            content="100M developers",
            extraction_span="serves over 100 million developers",
            category="market_intelligence",
            source_hash=None  # No hash provided
        )

        result = validator.verify(finding, source_text, source_hash)

        # Should pass (Check 2 is skipped)
        assert result.valid is True


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_extraction_span(self):
        """Empty extraction span edge case.

        Note: Empty string is technically a substring of any string after normalization,
        so this actually passes Check 1. This is acceptable since real usage won't have
        empty extraction spans (LLM prompts require minimum 20 characters).
        """
        validator = CitationValidator()

        source_text = "Some content here."
        source_hash = "abc123"

        finding = Finding(
            content="Some finding",
            extraction_span="",  # Empty!
            category="technical_analysis",
            source_hash="abc123"
        )

        result = validator.verify(finding, source_text, source_hash)

        # Empty normalized string "" is found in any normalized source
        # This is acceptable edge case behavior
        assert result.valid is True

    def test_numeric_extraction_with_decimals(self):
        """Numeric extraction handles decimal numbers."""
        validator = CitationValidator()

        finding = Finding(
            content="Growth rate is 12.5%",
            extraction_span="annual growth rate of 12.5 percent",
            category="market_intelligence"
        )

        result = validator._verify_numeric_extraction(finding, finding.extraction_span.lower())
        assert result is True

    def test_numeric_extraction_multiple_numbers(self):
        """Numeric extraction handles multiple numbers."""
        validator = CitationValidator()

        finding = Finding(
            content="Revenue between $50M and $100M",
            extraction_span="revenue ranging from 50 million to 100 million dollars",
            category="market_intelligence"
        )

        result = validator._verify_numeric_extraction(finding, finding.extraction_span.lower())
        assert result is True
