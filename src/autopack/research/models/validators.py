"""Citation validation for research findings.

This module validates that extracted research findings contain accurate citations
that match the source documents.

FIXES APPLIED:
- Phase 1 (2025-12-16): Numeric verification only checks extraction_span, not content
- Phase 2 (2025-12-16): Enhanced text normalization (HTML entities, Unicode, whitespace)
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

from autopack.text_normalization import normalize_text


@dataclass
class Finding:
    """Research finding with citation metadata."""

    content: str  # LLM's summary/interpretation
    extraction_span: str  # Direct quote from source
    category: str  # e.g., "market_intelligence", "competitive_analysis"
    source_hash: Optional[str] = None


@dataclass
class VerificationResult:
    """Result of citation verification."""

    valid: bool
    reason: str
    confidence: float


class CitationValidator:
    """Validates that research findings have accurate citations.

    Performs 3 checks:
    1. Quote appears in source (using normalized text matching)
    2. Content hash verification
    3. Numeric verification for market/competitive intelligence

    Previous issues fixed:
    - Phase 1 (2025-12-16): Check 3 now only verifies extraction_span contains numbers
    - Phase 2 (2025-12-16): Text normalization handles HTML entities, Unicode, markdown
    """

    def __init__(self):
        """Initialize the citation validator."""
        pass

    def verify(self, finding: Finding, source_text: str, source_hash: str) -> VerificationResult:
        """Verify that a finding's citation is valid.

        Args:
            finding: The research finding to verify
            source_text: The source document text
            source_hash: Hash of the source document

        Returns:
            VerificationResult indicating if citation is valid
        """
        # Normalize the extraction span for matching
        normalized_span = self._normalize_text(finding.extraction_span)
        normalized_source = self._normalize_text(source_text)

        # Check 1: Verify quote appears in source
        if normalized_span not in normalized_source:
            return VerificationResult(
                valid=False, reason="extraction_span not found in source document", confidence=0.95
            )

        # Check 2: Verify source hash matches
        if finding.source_hash and finding.source_hash != source_hash:
            return VerificationResult(
                valid=False, reason="source document hash mismatch", confidence=0.99
            )

        # Check 3: If numeric claim, validate extraction
        # Phase 1 fix applied: Only checks extraction_span contains numbers,
        # no longer validates content (which may legitimately paraphrase numbers)
        if finding.category in ["market_intelligence", "competitive_analysis"]:
            numeric_valid = self._verify_numeric_extraction(finding, normalized_span)
            if not numeric_valid:
                return VerificationResult(
                    valid=False,
                    reason="numeric claim does not match extraction_span",
                    confidence=0.9,
                )

        # Check 4: Semantic validation - verify content matches extraction_span semantically
        # This detects paraphrasing errors and hallucinations in the content field
        semantic_result = self._verify_semantic_accuracy(finding, normalized_span)
        if not semantic_result.valid:
            return semantic_result

        # All checks passed
        return VerificationResult(
            valid=True, reason="citation verified successfully", confidence=0.95
        )

    def _normalize_text(self, text: str) -> str:
        """Normalize text for matching using enhanced normalization.

        PHASE 2 ENHANCEMENT (2025-12-16):
        - Uses text_normalization.normalize_text() for comprehensive normalization
        - Handles HTML entities (e.g., &nbsp;, &#x27;, &quot;)
        - Unicode normalization (NFC - canonical composition)
        - Whitespace normalization
        - Zero-width character removal

        NOTE: Markdown stripping is DISABLED (strip_markdown=False) because:
        - GitHub READMEs often contain markdown formatting in the actual content
        - LLM extraction_span may preserve markdown syntax from source
        - Stripping markdown caused regression in Phase 2 testing (66.7% vs 72.2%)

        Args:
            text: Text to normalize

        Returns:
            Normalized text
        """
        if not text:
            return ""

        # Use selective normalization (HTML entities + Unicode + whitespace, but NOT markdown)
        return normalize_text(text, strip_markdown=False)

    def _verify_numeric_extraction(self, finding: Finding, normalized_span: str) -> bool:
        """Verify numeric values in extraction.

        PHASE 1 FIX APPLIED (2025-12-16):
        Only verifies that extraction_span contains numbers (no hallucination check needed for content).

        We only verify that extraction_span looks legitimate (has numbers if category suggests it).
        The content field is the LLM's interpretation and may legitimately paraphrase.

        Args:
            finding: The finding to verify
            normalized_span: Normalized extraction span

        Returns:
            True if numeric validation passes, False otherwise
        """
        # Extract numbers from span only
        span_numbers = re.findall(r"\d+(?:\.\d+)?", normalized_span)

        # For market/competitive intelligence, span should contain at least one number
        if finding.category in ["market_intelligence", "competitive_analysis"]:
            if not span_numbers:
                # Span claims to be about numbers but has none -> suspicious
                return False

        # If span has numbers (or category doesn't require them), it's valid
        # We trust the quote is from source, which Check 1 already verified
        return True

    def _verify_semantic_accuracy(
        self, finding: Finding, normalized_span: str
    ) -> VerificationResult:
        """Verify that content accurately reflects the extraction_span semantically.

        PHASE 3 ENHANCEMENT (2025-01-31):
        Adds semantic validation to detect:
        - Paraphrasing errors where content doesn't match the actual quote
        - Hallucinations where LLM invents interpretations
        - Content that misrepresents the source material

        Args:
            finding: The research finding to verify
            normalized_span: Normalized extraction span from source

        Returns:
            VerificationResult indicating if semantic validation passes
        """
        # Normalize content for comparison
        normalized_content = self._normalize_text(finding.content)

        # Check 1: Semantic similarity using sequence matching
        # Measures how similar the content is to the extraction_span
        similarity = SequenceMatcher(
            None, normalized_content.lower(), normalized_span.lower()
        ).ratio()

        if similarity < 0.3:
            return VerificationResult(
                valid=False,
                reason=f"Content doesn't match extraction_span semantically (similarity: {similarity:.1%})",
                confidence=0.85,
            )

        # Check 2: Key term preservation
        # Ensure important words from the span are preserved in the content
        span_terms = set(self._extract_key_terms(normalized_span))
        content_terms = set(self._extract_key_terms(normalized_content))

        if span_terms:
            overlap = len(span_terms & content_terms) / len(span_terms)

            if overlap < 0.5:
                return VerificationResult(
                    valid=False,
                    reason=f"Key terms not preserved in content (overlap: {overlap:.1%})",
                    confidence=0.8,
                )

        # Semantic validation passed
        return VerificationResult(
            valid=True,
            reason="Content semantically matches extraction_span",
            confidence=0.9,
        )

    def _extract_key_terms(self, text: str) -> list:
        """Extract key terms from text for semantic comparison.

        Filters out common stopwords that don't carry semantic meaning.

        Args:
            text: Text to extract terms from

        Returns:
            List of key terms (non-stopwords)
        """
        # Common English stopwords to filter out
        stopwords = {
            "a",
            "an",
            "and",
            "are",
            "as",
            "at",
            "be",
            "but",
            "by",
            "for",
            "if",
            "in",
            "into",
            "is",
            "it",
            "no",
            "not",
            "of",
            "on",
            "or",
            "such",
            "that",
            "the",
            "this",
            "to",
            "was",
            "will",
            "with",
            "from",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "would",
            "should",
            "could",
            "can",
            "may",
            "might",
            "must",
            "shall",
            "will",
        }

        # Split into words and filter
        words = text.lower().split()
        # Remove punctuation and filter stopwords
        terms = []
        for word in words:
            # Remove trailing punctuation
            clean_word = re.sub(r"[^\w\s]$", "", word)
            if clean_word and clean_word not in stopwords and len(clean_word) > 2:
                terms.append(clean_word)

        return terms
