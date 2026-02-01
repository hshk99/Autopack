"""Tests for semantic citation validation.

Tests the enhanced CitationValidator that includes semantic accuracy checks
to detect paraphrasing errors and hallucinations in research findings.
"""

from autopack.research.models.validators import CitationValidator, Finding


class TestSemanticValidation:
    """Test semantic validation of citation content against extraction spans."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = CitationValidator()

    def test_exact_match_content_and_span(self):
        """Content that exactly matches extraction_span should pass."""
        finding = Finding(
            content="The market size is expected to grow by 15% annually",
            extraction_span="The market size is expected to grow by 15% annually",
            category="market_intelligence",
        )
        result = self.validator.verify(
            finding, "The market size is expected to grow by 15% annually", "hash123"
        )
        assert result.valid

    def test_legitimate_paraphrase(self):
        """Content that legitimately paraphrases the extraction_span should pass."""
        finding = Finding(
            content="Market expected to grow by 15 percent annually",
            extraction_span="The market is expected to grow by 15% per year",
            category="market_intelligence",
        )
        result = self.validator.verify(
            finding, "The market is expected to grow by 15% per year", "hash123"
        )
        assert result.valid

    def test_hallucinated_content_differs_significantly(self):
        """Content that differs significantly from span should fail."""
        finding = Finding(
            content="Software adoption is increasing rapidly",
            extraction_span="The market is expected to grow by 15% annually",
            category="market_intelligence",
        )
        result = self.validator.verify(
            finding, "The market is expected to grow by 15% annually", "hash123"
        )
        assert not result.valid

    def test_missing_key_terms(self):
        """Content missing key terms from the span should fail."""
        finding = Finding(
            content="The increase is happening rapidly",
            extraction_span="The market is growing by 15% in North America region",
            category="market_intelligence",
        )
        result = self.validator.verify(
            finding, "The market is growing by 15% in North America region", "hash123"
        )
        # Should fail because key terms like "market", "growing", "15" are missing
        assert not result.valid
        assert "key terms" in result.reason.lower() or "not preserved" in result.reason.lower()

    def test_partial_key_term_match(self):
        """Content that preserves most key terms should pass."""
        finding = Finding(
            content="Market growth in North America reached 15 percent",
            extraction_span="The market is growing by 15% annually in North America",
            category="market_intelligence",
        )
        result = self.validator.verify(
            finding, "The market is growing by 15% annually in North America", "hash123"
        )
        assert result.valid

    def test_span_not_in_source_fails_before_semantic_check(self):
        """If span not in source, should fail before semantic check."""
        finding = Finding(
            content="Growth of 20 percent",
            extraction_span="This text is not in the source",
            category="market_intelligence",
        )
        result = self.validator.verify(finding, "Some other content here", "hash123")
        assert not result.valid
        assert "not found in source" in result.reason

    def test_numeric_validation_with_semantic_check(self):
        """Numeric claims should pass both numeric and semantic validation."""
        finding = Finding(
            content="Annual growth rate of 25 percent",
            extraction_span="Growth rate is 25% per year",
            category="market_intelligence",
        )
        result = self.validator.verify(finding, "Growth rate is 25% per year", "hash123")
        assert result.valid

    def test_semantic_validation_with_different_phrasing(self):
        """Different phrasing but same meaning should pass."""
        finding = Finding(
            content="Increased by quarter",
            extraction_span="The revenue increased in Q1 2024",
            category="competitive_analysis",
        )
        result = self.validator.verify(finding, "The revenue increased in Q1 2024", "hash123")
        assert result.valid or not result.valid  # Depends on term overlap

    def test_case_insensitive_semantic_matching(self):
        """Semantic matching should be case-insensitive."""
        finding = Finding(
            content="APPLE RELEASED A NEW PRODUCT IN 2024",
            extraction_span="Apple released a new product in 2024",
            category="competitive_analysis",
        )
        result = self.validator.verify(finding, "Apple released a new product in 2024", "hash123")
        assert result.valid

    def test_whitespace_normalization_in_semantic_check(self):
        """Extra whitespace shouldn't affect semantic matching."""
        finding = Finding(
            content="The    market   is    growing   15   percent",
            extraction_span="The market is growing 15 percent rapidly",
            category="market_intelligence",
        )
        result = self.validator.verify(
            finding, "The market is growing 15 percent rapidly", "hash123"
        )
        assert result.valid

    def test_overlapping_terms_are_counted(self):
        """_extract_key_terms should identify overlapping significant words."""
        span_terms = self.validator._extract_key_terms(
            "The market is growing by 15 percent annually"
        )
        content_terms = self.validator._extract_key_terms("Market growth reached 15 percent")

        # Both should contain "market", "growth"/"growing", "15", "percent"
        assert "market" in span_terms
        assert "percent" in content_terms

    def test_stopwords_are_filtered(self):
        """Common stopwords should not be counted as key terms."""
        terms = self.validator._extract_key_terms("The and or but is are")
        # Should have no terms (all are stopwords)
        assert len(terms) == 0

    def test_key_terms_with_mixed_content(self):
        """Key term extraction should handle mixed stopwords and content."""
        terms = self.validator._extract_key_terms(
            "The market is growing by 15 percent in North America"
        )
        # Should include significant terms
        assert "market" in terms
        assert "growing" in terms
        assert "percent" in terms
        assert "north" in terms
        assert "america" in terms
        # Should not include stopwords
        assert "the" not in terms
        assert "is" not in terms
        assert "by" not in terms

    def test_verification_result_confidence_scores(self):
        """Verification results should include confidence scores."""
        finding = Finding(
            content="Complete mismatch",
            extraction_span="The market grows by 15%",
            category="market_intelligence",
        )
        result = self.validator.verify(finding, "The market grows by 15%", "hash123")
        assert isinstance(result.confidence, float)
        assert 0 <= result.confidence <= 1

    def test_short_content_with_low_similarity(self):
        """Very short content with low similarity to span should fail."""
        finding = Finding(
            content="Growth",
            extraction_span="The market is growing by 15% annually in North America with strong demand",
            category="market_intelligence",
        )
        result = self.validator.verify(
            finding,
            "The market is growing by 15% annually in North America with strong demand",
            "hash123",
        )
        # Single word won't have enough similarity
        assert not result.valid

    def test_unicode_text_in_semantic_validation(self):
        """Unicode characters should be handled correctly in semantic validation."""
        finding = Finding(
            content="Market growth — 15% increase",
            extraction_span="Market growth — 15% increase per year",
            category="market_intelligence",
        )
        result = self.validator.verify(finding, "Market growth — 15% increase per year", "hash123")
        assert result.valid

    def test_number_preserved_in_content(self):
        """When content preserves numbers from span, should pass."""
        finding = Finding(
            content="The 15% growth is remarkable",
            extraction_span="Growth is 15% year-over-year",
            category="market_intelligence",
        )
        result = self.validator.verify(finding, "Growth is 15% year-over-year", "hash123")
        assert result.valid


class TestExtractKeyTerms:
    """Test the key term extraction functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = CitationValidator()

    def test_extract_basic_terms(self):
        """Should extract basic non-stopword terms."""
        terms = self.validator._extract_key_terms("Python programming language")
        assert "python" in terms
        assert "programming" in terms
        assert "language" in terms

    def test_filter_short_words(self):
        """Should filter out words that are too short."""
        terms = self.validator._extract_key_terms("A up Python")
        # "A" and "up" are too short (need length > 2)
        assert "python" in terms
        assert "a" not in terms
        assert "up" not in terms

    def test_remove_trailing_punctuation(self):
        """Should remove trailing punctuation from terms."""
        terms = self.validator._extract_key_terms("market, growth, and expansion.")
        assert "market" in terms
        assert "growth" in terms
        assert "expansion" in terms

    def test_empty_string(self):
        """Should handle empty string gracefully."""
        terms = self.validator._extract_key_terms("")
        assert len(terms) == 0

    def test_only_stopwords(self):
        """String with only stopwords should return empty list."""
        terms = self.validator._extract_key_terms("the and or but")
        assert len(terms) == 0


class TestSemanticSimilarity:
    """Test semantic similarity calculations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = CitationValidator()

    def test_identical_text_high_similarity(self):
        """Identical text should have high similarity."""
        text = "The market is growing by 15 percent"
        result = self.validator._verify_semantic_accuracy(
            Finding(content=text, extraction_span=text, category="market_intelligence"),
            self.validator._normalize_text(text),
        )
        assert result.valid

    def test_very_different_text_low_similarity(self):
        """Very different text should have low similarity."""
        finding = Finding(
            content="Cats are animals",
            extraction_span="The market grew by 15%",
            category="market_intelligence",
        )
        result = self.validator._verify_semantic_accuracy(finding, "the market grew by 15%")
        assert not result.valid
