"""Text normalization module for handling HTML entities, Unicode, and markdown artifacts.

This module provides utilities to clean and normalize text extracted from various
sources, ensuring consistent representation for downstream processing.
"""

import html
import logging
import re
import unicodedata
from typing import Optional

logger = logging.getLogger(__name__)


# Common HTML entities that may appear in extracted text
HTML_ENTITY_PATTERN = re.compile(r'&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);')

# Markdown link pattern: [text](url)
MARKDOWN_LINK_PATTERN = re.compile(r'\[([^\]]+)\]\([^)]+\)')

# Markdown image pattern: ![alt](url)
MARKDOWN_IMAGE_PATTERN = re.compile(r'!\[([^\]]*)\]\([^)]+\)')

# Markdown emphasis patterns
MARKDOWN_BOLD_PATTERN = re.compile(r'\*\*([^*]+)\*\*|__([^_]+)__')
MARKDOWN_ITALIC_PATTERN = re.compile(r'\*([^*]+)\*|_([^_]+)_')
MARKDOWN_CODE_INLINE_PATTERN = re.compile(r'`([^`]+)`')

# Markdown header pattern
MARKDOWN_HEADER_PATTERN = re.compile(r'^#{1,6}\s+', re.MULTILINE)

# Multiple whitespace pattern
MULTIPLE_WHITESPACE_PATTERN = re.compile(r'\s+')

# Unicode replacement characters and other problematic chars
REPLACEMENT_CHAR = '\ufffd'


def decode_html_entities(text: str) -> str:
    """Decode HTML entities in text.
    
    Args:
        text: Input text potentially containing HTML entities.
        
    Returns:
        Text with HTML entities decoded to their character equivalents.
    """
    if not text:
        return text
    
    try:
        # Use html.unescape for comprehensive entity handling
        decoded = html.unescape(text)
        return decoded
    except Exception as e:
        logger.warning(f"Failed to decode HTML entities: {e}")
        return text


def normalize_unicode(text: str, form: str = 'NFC') -> str:
    """Normalize Unicode text to a consistent form.
    
    Args:
        text: Input text with potentially inconsistent Unicode.
        form: Unicode normalization form ('NFC', 'NFD', 'NFKC', 'NFKD').
        
    Returns:
        Unicode-normalized text.
    """
    if not text:
        return text
    
    try:
        # Remove replacement characters
        text = text.replace(REPLACEMENT_CHAR, '')
        
        # Normalize to specified form
        normalized = unicodedata.normalize(form, text)
        return normalized
    except Exception as e:
        logger.warning(f"Failed to normalize Unicode: {e}")
        return text


def strip_markdown_artifacts(text: str) -> str:
    """Remove common markdown formatting artifacts from text.
    
    Args:
        text: Input text potentially containing markdown formatting.
        
    Returns:
        Text with markdown artifacts removed, preserving content.
    """
    if not text:
        return text
    
    try:
        # Remove images first (before links, as they have similar syntax)
        result = MARKDOWN_IMAGE_PATTERN.sub(r'\1', text)
        
        # Convert links to just their text
        result = MARKDOWN_LINK_PATTERN.sub(r'\1', result)
        
        # Remove bold markers, keeping content
        result = MARKDOWN_BOLD_PATTERN.sub(lambda m: m.group(1) or m.group(2), result)
        
        # Remove italic markers, keeping content
        result = MARKDOWN_ITALIC_PATTERN.sub(lambda m: m.group(1) or m.group(2), result)
        
        # Remove inline code markers, keeping content
        result = MARKDOWN_CODE_INLINE_PATTERN.sub(r'\1', result)
        
        # Remove header markers
        result = MARKDOWN_HEADER_PATTERN.sub('', result)
        
        return result
    except Exception as e:
        logger.warning(f"Failed to strip markdown artifacts: {e}")
        return text


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace in text.
    
    Args:
        text: Input text with potentially irregular whitespace.
        
    Returns:
        Text with normalized whitespace (single spaces, trimmed).
    """
    if not text:
        return text
    
    # Replace multiple whitespace with single space
    result = MULTIPLE_WHITESPACE_PATTERN.sub(' ', text)
    return result.strip()


def normalize_text(text: Optional[str], strip_markdown: bool = True) -> str:
    """Apply full text normalization pipeline.

    Args:
        text: Input text to normalize.
        strip_markdown: Whether to remove markdown formatting artifacts.

    Returns:
        Fully normalized text (lowercase).
    """
    if not text:
        return ''

    result = text

    # Step 1: Decode HTML entities
    result = decode_html_entities(result)

    # Step 2: Normalize Unicode
    result = normalize_unicode(result)

    # Step 3: Optionally strip markdown
    if strip_markdown:
        result = strip_markdown_artifacts(result)

    # Step 4: Normalize whitespace
    result = normalize_whitespace(result)

    # Step 5: Convert to lowercase for case-insensitive matching
    result = result.lower()

    return result
