"""Verification module for validating extracted content against source documents.

This module provides utilities to verify that extracted content matches the source
material, with special handling for numeric values and text normalization.
"""

import logging
import re

from autopack.text_normalization import normalize_text

logger = logging.getLogger(__name__)


def extract_numbers(text: str) -> list[str]:
    """Extract all numeric values from text.

    Args:
        text: Input text to extract numbers from.

    Returns:
        List of numeric strings found in the text.
    """
    if not text:
        return []

    # Pattern matches integers and decimals, with optional commas and signs
    number_pattern = r"[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?"
    numbers = re.findall(number_pattern, text)

    # Normalize numbers by removing commas
    return [num.replace(",", "") for num in numbers]


def verify_numeric_values(extracted: str, source: str, tolerance: float = 0.0001) -> dict:
    """Verify that numeric values in extracted text match those in source.

    This function extracts numbers from both extracted and source text,
    then verifies that all numbers from extracted text appear in source.

    Args:
        extracted: The extracted text (e.g., extraction_span).
        source: The source document text to verify against.
        tolerance: Floating point comparison tolerance (default: 0.0001).

    Returns:
        dict with:
            - valid: bool - True if all numbers in extracted appear in source
            - extracted_numbers: list - Numbers found in extracted text
            - source_numbers: list - Numbers found in source text
            - missing_numbers: list - Numbers in extracted but not in source
            - details: str - Human-readable verification details
    """
    if not extracted:
        return {
            "valid": True,
            "extracted_numbers": [],
            "source_numbers": [],
            "missing_numbers": [],
            "details": "No extracted text to verify",
        }

    if not source:
        return {
            "valid": False,
            "extracted_numbers": extract_numbers(extracted),
            "source_numbers": [],
            "missing_numbers": extract_numbers(extracted),
            "details": "No source text provided",
        }

    extracted_nums = extract_numbers(extracted)
    source_nums = extract_numbers(source)

    # Convert to sets for comparison, handling floats with tolerance
    extracted_floats = set()
    source_floats = set()

    for num_str in extracted_nums:
        try:
            extracted_floats.add(float(num_str))
        except ValueError:
            logger.warning(f"Could not parse number: {num_str}")

    for num_str in source_nums:
        try:
            source_floats.add(float(num_str))
        except ValueError:
            logger.warning(f"Could not parse source number: {num_str}")

    # Check if all extracted numbers appear in source (with tolerance)
    missing = []
    for ext_num in extracted_floats:
        found = False
        for src_num in source_floats:
            if abs(ext_num - src_num) <= tolerance:
                found = True
                break
        if not found:
            missing.append(str(ext_num))

    valid = len(missing) == 0

    return {
        "valid": valid,
        "extracted_numbers": extracted_nums,
        "source_numbers": source_nums,
        "missing_numbers": missing,
        "details": f"{'✓' if valid else '✗'} Found {len(extracted_nums)} numbers in extraction, {len(missing)} not in source",
    }


def verify_citation_in_source(
    extracted: str, source: str, normalize: bool = True, min_match_length: int = 10
) -> dict:
    """Verify that extracted citation text appears in the source document.

    This function checks if the extracted text (or a normalized version of it)
    can be found in the source document, accounting for formatting differences.

    Args:
        extracted: The extracted citation text.
        source: The source document text to verify against.
        normalize: Whether to apply text normalization before matching.
        min_match_length: Minimum length of extracted text to require matching.

    Returns:
        dict with:
            - valid: bool - True if extracted text found in source
            - match_position: int - Character position of match in source (-1 if not found)
            - match_quality: str - Quality of match ('exact', 'normalized', 'none')
            - details: str - Human-readable verification details
    """
    if not extracted:
        return {
            "valid": True,
            "match_position": -1,
            "match_quality": "none",
            "details": "No extracted text to verify",
        }

    if not source:
        return {
            "valid": False,
            "match_position": -1,
            "match_quality": "none",
            "details": "No source text provided",
        }

    # Skip verification if extracted text is too short
    if len(extracted.strip()) < min_match_length:
        return {
            "valid": True,
            "match_position": -1,
            "match_quality": "skipped",
            "details": f"Extracted text too short ({len(extracted.strip())} < {min_match_length})",
        }

    # Try exact match first
    if extracted in source:
        position = source.index(extracted)
        return {
            "valid": True,
            "match_position": position,
            "match_quality": "exact",
            "details": f"✓ Exact match found at position {position}",
        }

    # Try normalized match if enabled
    if normalize:
        normalized_extracted = normalize_text(extracted).lower()
        normalized_source = normalize_text(source).lower()

        if normalized_extracted in normalized_source:
            position = normalized_source.index(normalized_extracted)
            return {
                "valid": True,
                "match_position": position,
                "match_quality": "normalized",
                "details": f"✓ Normalized match found at position {position}",
            }

    # No match found
    return {
        "valid": False,
        "match_position": -1,
        "match_quality": "none",
        "details": f'✗ No match found (extracted: "{extracted[:50]}...")',
    }


def verify_extraction(
    extraction_span: str,
    source_document: str,
    verify_numbers: bool = True,
    verify_text: bool = True,
) -> dict:
    """Complete verification of an extraction against source document.

    This combines numeric and text verification into a single check.

    Args:
        extraction_span: The extracted text span to verify.
        source_document: The source document text.
        verify_numbers: Whether to verify numeric values.
        verify_text: Whether to verify text presence.

    Returns:
        dict with:
            - valid: bool - True if all enabled verifications pass
            - numeric_check: dict - Results of numeric verification (if enabled)
            - text_check: dict - Results of text verification (if enabled)
            - details: str - Human-readable summary
    """
    result = {"valid": True, "details": []}

    if verify_numbers:
        numeric_result = verify_numeric_values(extraction_span, source_document)
        result["numeric_check"] = numeric_result
        result["valid"] = result["valid"] and numeric_result["valid"]
        result["details"].append(f"Numeric: {numeric_result['details']}")

    if verify_text:
        text_result = verify_citation_in_source(extraction_span, source_document)
        result["text_check"] = text_result
        result["valid"] = result["valid"] and text_result["valid"]
        result["details"].append(f"Text: {text_result['details']}")

    result["details"] = " | ".join(result["details"])

    return result
