"""Citation validation for research findings.

This module validates that extracted research findings contain accurate citations
that match the source documents.

CURRENT STATUS: Contains known issues that will be fixed in citation validity improvement phases:
- Phase 1: Numeric verification is too strict (checks both content AND extraction_span)
- Phase 2: Text normalization is too basic (misses HTML entities, Unicode, markdown)
"""

import re
from dataclasses import dataclass
from typing import Optional


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

    KNOWN ISSUES (to be fixed in citation improvement phases):
    - Check 3 is too strict: compares numbers in content vs extraction_span
    - Text normalization is too basic: misses HTML entities, Unicode, markdown
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
                valid=False,
                reason="extraction_span not found in source document",
                confidence=0.95
            )

        # Check 2: Verify source hash matches
        if finding.source_hash and finding.source_hash != source_hash:
            return VerificationResult(
                valid=False,
                reason="source document hash mismatch",
                confidence=0.99
            )

        # Check 3: If numeric claim, validate extraction
        # BUG: This is too strict - checks BOTH content and span
        # Will be fixed in Phase 1 to only check extraction_span
        if finding.category in ["market_intelligence", "competitive_analysis"]:
            numeric_valid = self._verify_numeric_extraction(finding, normalized_span)
            if not numeric_valid:
                return VerificationResult(
                    valid=False,
                    reason="numeric claim does not match extraction_span",
                    confidence=0.9
                )

        # All checks passed
        return VerificationResult(
            valid=True,
            reason="citation verified successfully",
            confidence=0.95
        )

    def _normalize_text(self, text: str) -> str:
        """Normalize text for matching.

        CURRENT IMPLEMENTATION (Phase 0 - too basic):
        - Collapses whitespace
        - Converts to lowercase

        MISSING (will be added in Phase 2):
        - HTML entity decoding
        - Unicode normalization
        - Markdown artifact stripping
        - Zero-width character removal

        Args:
            text: Text to normalize

        Returns:
            Normalized text
        """
        if not text:
            return ""

        # Basic normalization: collapse whitespace and lowercase
        normalized = re.sub(r'\s+', ' ', text.strip())
        return normalized.lower()

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
        span_numbers = re.findall(r'\d+(?:\.\d+)?', normalized_span)

        # For market/competitive intelligence, span should contain at least one number
        if finding.category in ["market_intelligence", "competitive_analysis"]:
            if not span_numbers:
                # Span claims to be about numbers but has none -> suspicious
                return False

        # If span has numbers (or category doesn't require them), it's valid
        # We trust the quote is from source, which Check 1 already verified
        return True
