"""Tests for text normalization module."""

import pytest
from src.autopack.text_normalization import (
    decode_html_entities,
    normalize_unicode,
    strip_markdown_artifacts,
    normalize_whitespace,
    normalize_text,
)


class TestDecodeHtmlEntities:
    """Tests for HTML entity decoding."""
    
    def test_basic_entities(self):
        """Test decoding of common HTML entities."""
        assert decode_html_entities("&amp;") == "&"
        assert decode_html_entities("&lt;") == "<"
        assert decode_html_entities("&gt;") == ">"
        assert decode_html_entities("&quot;") == '"'
        assert decode_html_entities("&apos;") == "'"
    
    def test_numeric_entities(self):
        """Test decoding of numeric HTML entities."""
        assert decode_html_entities("&#38;") == "&"
        assert decode_html_entities("&#x26;") == "&"
        assert decode_html_entities("&#169;") == "©"
    
    def test_mixed_content(self):
        """Test decoding with mixed content."""
        text = "Tom &amp; Jerry &lt;3 cartoons"
        expected = "Tom & Jerry <3 cartoons"
        assert decode_html_entities(text) == expected
    
    def test_empty_input(self):
        """Test handling of empty input."""
        assert decode_html_entities("") == ""
        assert decode_html_entities(None) is None


class TestNormalizeUnicode:
    """Tests for Unicode normalization."""
    
    def test_nfc_normalization(self):
        """Test NFC normalization."""
        # é as e + combining acute vs precomposed é
        composed = "caf\u00e9"  # precomposed
        decomposed = "cafe\u0301"  # e + combining acute
        assert normalize_unicode(decomposed) == composed
    
    def test_replacement_char_removal(self):
        """Test removal of replacement characters."""
        text = "Hello\ufffdWorld"
        assert normalize_unicode(text) == "HelloWorld"
    
    def test_empty_input(self):
        """Test handling of empty input."""
        assert normalize_unicode("") == ""
        assert normalize_unicode(None) is None


class TestStripMarkdownArtifacts:
    """Tests for markdown artifact removal."""
    
    def test_link_removal(self):
        """Test removal of markdown links."""
        text = "Check [this link](https://example.com) out"
        expected = "Check this link out"
        assert strip_markdown_artifacts(text) == expected
    
    def test_image_removal(self):
        """Test removal of markdown images."""
        text = "See ![alt text](image.png) here"
        expected = "See alt text here"
        assert strip_markdown_artifacts(text) == expected
    
    def test_bold_removal(self):
        """Test removal of bold markers."""
        assert strip_markdown_artifacts("**bold**") == "bold"
        assert strip_markdown_artifacts("__bold__") == "bold"
    
    def test_italic_removal(self):
        """Test removal of italic markers."""
        assert strip_markdown_artifacts("*italic*") == "italic"
        assert strip_markdown_artifacts("_italic_") == "italic"
    
    def test_code_removal(self):
        """Test removal of inline code markers."""
        assert strip_markdown_artifacts("`code`") == "code"
    
    def test_header_removal(self):
        """Test removal of header markers."""
        assert strip_markdown_artifacts("# Header") == "Header"
        assert strip_markdown_artifacts("### Header") == "Header"
    
    def test_empty_input(self):
        """Test handling of empty input."""
        assert strip_markdown_artifacts("") == ""
        assert strip_markdown_artifacts(None) is None


class TestNormalizeWhitespace:
    """Tests for whitespace normalization."""
    
    def test_multiple_spaces(self):
        """Test collapsing multiple spaces."""
        assert normalize_whitespace("hello    world") == "hello world"
    
    def test_mixed_whitespace(self):
        """Test handling mixed whitespace."""
        assert normalize_whitespace("hello\t\nworld") == "hello world"
    
    def test_trim(self):
        """Test trimming leading/trailing whitespace."""
        assert normalize_whitespace("  hello  ") == "hello"


class TestNormalizeText:
    """Tests for full normalization pipeline."""
    
    def test_full_pipeline(self):
        """Test complete normalization pipeline."""
        text = "  &amp; **bold** [link](url)  "
        expected = "& bold link"
        assert normalize_text(text) == expected
    
    def test_empty_input(self):
        """Test handling of empty/None input."""
        assert normalize_text("") == ""
        assert normalize_text(None) == ""
