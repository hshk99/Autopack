"""Tests for the verification module."""


from autopack.verification import (
    extract_numbers,
    verify_citation_in_source,
    verify_extraction,
    verify_numeric_values,
)


class TestExtractNumbers:
    """Tests for extract_numbers function."""

    def test_extract_integers(self):
        """Test extracting simple integers."""
        text = "The study included 42 participants and lasted 30 days."
        numbers = extract_numbers(text)
        assert numbers == ['42', '30']

    def test_extract_decimals(self):
        """Test extracting decimal numbers."""
        text = "The average was 3.14 with standard deviation of 0.52."
        numbers = extract_numbers(text)
        assert '3.14' in numbers
        assert '0.52' in numbers

    def test_extract_with_commas(self):
        """Test extracting numbers with comma separators."""
        text = "The total cost was $1,234,567.89."
        numbers = extract_numbers(text)
        # Commas should be removed in result
        assert '1234567.89' in numbers

    def test_extract_negative_numbers(self):
        """Test extracting negative numbers."""
        text = "The temperature dropped to -15 degrees."
        numbers = extract_numbers(text)
        assert '-15' in numbers

    def test_empty_text(self):
        """Test with empty text."""
        assert extract_numbers('') == []
        assert extract_numbers(None) == []


class TestVerifyNumericValues:
    """Tests for verify_numeric_values function."""

    def test_exact_match(self):
        """Test when all numbers in extracted appear in source."""
        extracted = "The average age was 42 years."
        source = "Study demographics: 100 participants, average age was 42 years, range 18-65."
        result = verify_numeric_values(extracted, source)
        assert result['valid'] is True
        assert '42' in result['extracted_numbers']

    def test_multiple_numbers_match(self):
        """Test when multiple numbers all match."""
        extracted = "Results: 95% CI [1.2, 3.4]"
        source = "The confidence interval was 95% with bounds 1.2 and 3.4."
        result = verify_numeric_values(extracted, source)
        assert result['valid'] is True

    def test_missing_number(self):
        """Test when extracted number not in source."""
        extracted = "The result was 99."
        source = "We measured values of 42 and 58."
        result = verify_numeric_values(extracted, source)
        assert result['valid'] is False
        assert '99.0' in result['missing_numbers']

    def test_empty_extracted(self):
        """Test with empty extracted text."""
        result = verify_numeric_values('', 'source with 42')
        assert result['valid'] is True  # No numbers to verify
        assert result['extracted_numbers'] == []

    def test_no_source(self):
        """Test with no source text."""
        result = verify_numeric_values('extracted with 42', '')
        assert result['valid'] is False
        assert result['extracted_numbers'] == ['42']

    def test_floating_point_tolerance(self):
        """Test that floating point comparison uses tolerance."""
        extracted = "Value: 3.14159"
        source = "Measured pi as 3.14159265"
        result = verify_numeric_values(extracted, source, tolerance=0.001)
        # 3.14159 should match 3.14159265 within tolerance
        assert result['valid'] is True


class TestVerifyCitationInSource:
    """Tests for verify_citation_in_source function."""

    def test_exact_match(self):
        """Test exact text match."""
        extracted = "the quick brown fox"
        source = "Once upon a time, the quick brown fox jumped over the lazy dog."
        result = verify_citation_in_source(extracted, source, normalize=False)
        assert result['valid'] is True
        assert result['match_quality'] == 'exact'
        assert result['match_position'] >= 0

    def test_normalized_match(self):
        """Test match after normalization."""
        extracted = "The   quick\n\nbrown   fox"
        source = "Once upon a time, the quick brown fox jumped over the lazy dog."
        result = verify_citation_in_source(extracted, source, normalize=True)
        assert result['valid'] is True
        assert result['match_quality'] == 'normalized'

    def test_no_match(self):
        """Test when text not found in source."""
        extracted = "unicorns and rainbows"
        source = "The quick brown fox jumped over the lazy dog."
        result = verify_citation_in_source(extracted, source)
        assert result['valid'] is False
        assert result['match_quality'] == 'none'
        assert result['match_position'] == -1

    def test_empty_extracted(self):
        """Test with empty extracted text."""
        result = verify_citation_in_source('', 'source text')
        assert result['valid'] is True  # Nothing to verify

    def test_empty_source(self):
        """Test with empty source."""
        result = verify_citation_in_source('extracted', '')
        assert result['valid'] is False

    def test_min_length_skip(self):
        """Test that short extractions are skipped."""
        extracted = "fox"
        source = "The quick brown fox"
        result = verify_citation_in_source(extracted, source, min_match_length=10)
        assert result['valid'] is True  # Skipped due to length
        assert result['match_quality'] == 'skipped'

    def test_with_html_entities(self):
        """Test matching with HTML entities when normalized."""
        extracted = "it's a test"
        source = "This is a test: it&apos;s a test case."
        result = verify_citation_in_source(extracted, source, normalize=True)
        # Should match after normalization handles HTML entities
        assert result['valid'] is True


class TestVerifyExtraction:
    """Tests for verify_extraction combined function."""

    def test_both_verifications_pass(self):
        """Test when both numeric and text verification pass."""
        extraction = "The average was 42 years"
        source = "Study results: The average was 42 years in our cohort."
        result = verify_extraction(extraction, source)
        assert result['valid'] is True
        assert 'numeric_check' in result
        assert 'text_check' in result

    def test_numeric_fails(self):
        """Test when numeric verification fails."""
        extraction = "The result was 99."
        source = "The result was 42."
        result = verify_extraction(extraction, source)
        assert result['valid'] is False
        assert result['numeric_check']['valid'] is False

    def test_text_fails(self):
        """Test when text verification fails."""
        extraction = "unicorns are real"
        source = "The quick brown fox jumped."
        result = verify_extraction(extraction, source)
        assert result['valid'] is False
        assert result['text_check']['valid'] is False

    def test_only_numeric_verification(self):
        """Test with only numeric verification enabled."""
        extraction = "Value: 42"
        source = "Different text but has 42 in it."
        result = verify_extraction(extraction, source, verify_numbers=True, verify_text=False)
        assert result['valid'] is True
        assert 'numeric_check' in result
        assert 'text_check' not in result

    def test_only_text_verification(self):
        """Test with only text verification enabled."""
        extraction = "the quick fox"
        source = "Once upon a time, the quick fox ran."
        result = verify_extraction(extraction, source, verify_numbers=False, verify_text=True)
        assert result['valid'] is True
        assert 'numeric_check' not in result
        assert 'text_check' in result

    def test_real_world_scenario(self):
        """Test a realistic citation verification scenario."""
        extraction_span = "In a study of 1,234 participants (mean age 45.2 years)"
        source_doc = """
        Research Study Report

        Methods: In a study of 1,234 participants (mean age 45.2 years), we examined
        the effects of intervention X on outcome Y. The cohort was recruited from...
        """
        result = verify_extraction(extraction_span, source_doc)
        assert result['valid'] is True
        assert result['numeric_check']['valid'] is True
        assert result['text_check']['valid'] is True


class TestIntegrationWithTextNormalization:
    """Tests for integration with text_normalization module."""

    def test_markdown_formatting(self):
        """Test that markdown artifacts are handled."""
        extracted = "the result was significant"
        source = "As shown in **Figure 1**, the result was significant (p < 0.05)."
        result = verify_citation_in_source(extracted, source, normalize=True)
        assert result['valid'] is True

    def test_unicode_normalization(self):
        """Test that Unicode differences are normalized."""
        extracted = "café"
        # Different Unicode representations of é
        source_nfc = "We visited the café yesterday."
        result = verify_citation_in_source(extracted, source_nfc, normalize=True)
        assert result['valid'] is True

    def test_whitespace_normalization(self):
        """Test that whitespace differences are handled."""
        extracted = "the quick   brown\nfox"
        source = "the quick brown fox jumped"
        result = verify_citation_in_source(extracted, source, normalize=True)
        assert result['valid'] is True
