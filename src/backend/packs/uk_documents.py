"""
UK-specific document classification pack.

This module provides document classification capabilities for common UK documents
including tax returns, NHS records, driving licences, passports, bank statements,
and utility bills. It includes UK-specific date format and postal code validation.
"""

import re
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Pattern

from pydantic import BaseModel, Field, validator


class UKDocumentType(str, Enum):
    """UK document types supported by this classification pack."""

    HMRC_TAX_RETURN = "hmrc_tax_return"
    NHS_RECORD = "nhs_record"
    DRIVING_LICENCE = "driving_licence"
    PASSPORT = "passport"
    BANK_STATEMENT = "bank_statement"
    UTILITY_BILL = "utility_bill"


class UKDateFormat(str, Enum):
    """Common UK date formats."""

    DD_MM_YYYY = "DD/MM/YYYY"
    DD_MM_YY = "DD/MM/YY"
    D_MMM_YYYY = "D MMM YYYY"
    DD_MONTH_YYYY = "DD Month YYYY"


class UKPostalCodeValidator:
    """Validator for UK postal codes."""

    # UK postcode regex pattern
    # Format: AA9A 9AA, A9A 9AA, A9 9AA, A99 9AA, AA9 9AA, AA99 9AA
    POSTCODE_PATTERN: Pattern = re.compile(
        r"^([A-Z]{1,2}\d{1,2}[A-Z]?)\s*(\d[A-Z]{2})$",
        re.IGNORECASE
    )

    @classmethod
    def validate(cls, postcode: str) -> bool:
        """
        Validate a UK postal code.

        Args:
            postcode: The postal code to validate

        Returns:
            True if valid, False otherwise
        """
        if not postcode:
            return False
        return bool(cls.POSTCODE_PATTERN.match(postcode.strip()))

    @classmethod
    def normalize(cls, postcode: str) -> Optional[str]:
        """
        Normalize a UK postal code to standard format.

        Args:
            postcode: The postal code to normalize

        Returns:
            Normalized postal code or None if invalid
        """
        if not postcode:
            return None

        match = cls.POSTCODE_PATTERN.match(postcode.strip())
        if not match:
            return None

        outward, inward = match.groups()
        return f"{outward.upper()} {inward.upper()}"


class UKDateParser:
    """Parser for UK date formats."""

    DATE_PATTERNS: List[tuple[Pattern, str]] = [
        (re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})"), "%d/%m/%Y"),
        (re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2})"), "%d/%m/%y"),
        (re.compile(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})"), "%d %B %Y"),
        (re.compile(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})"), "%d %b %Y"),
    ]

    @classmethod
    def parse(cls, date_str: str) -> Optional[datetime]:
        """
        Parse a UK date string.

        Args:
            date_str: The date string to parse

        Returns:
            Parsed datetime object or None if parsing fails
        """
        if not date_str:
            return None

        date_str = date_str.strip()

        for pattern, format_str in cls.DATE_PATTERNS:
            if pattern.match(date_str):
                try:
                    return datetime.strptime(date_str, format_str)
                except ValueError:
                    continue

        return None


class DocumentClassificationResult(BaseModel):
    """Result of document classification."""

    document_type: UKDocumentType
    confidence: float = Field(ge=0.0, le=1.0)
    extracted_data: Dict[str, str] = Field(default_factory=dict)
    validation_errors: List[str] = Field(default_factory=list)


class UKDocumentClassifier:
    """Classifier for UK documents."""

    # Keywords for each document type
    DOCUMENT_KEYWORDS: Dict[UKDocumentType, List[str]] = {
        UKDocumentType.HMRC_TAX_RETURN: [
            "hmrc", "tax return", "self assessment", "utr", "unique taxpayer reference",
            "national insurance", "income tax", "tax year"
        ],
        UKDocumentType.NHS_RECORD: [
            "nhs", "national health service", "nhs number", "gp", "general practitioner",
            "medical record", "prescription", "hospital"
        ],
        UKDocumentType.DRIVING_LICENCE: [
            "driving licence", "dvla", "driver number", "categories", "entitlement",
            "photocard", "counterpart"
        ],
        UKDocumentType.PASSPORT: [
            "passport", "her majesty", "his majesty", "united kingdom", "nationality",
            "passport number", "place of birth", "date of issue"
        ],
        UKDocumentType.BANK_STATEMENT: [
            "bank statement", "account number", "sort code", "balance", "transaction",
            "debit", "credit", "statement period"
        ],
        UKDocumentType.UTILITY_BILL: [
            "utility", "electricity", "gas", "water", "council tax", "meter reading",
            "usage", "tariff", "supply"
        ],
    }

    def classify(self, text: str) -> DocumentClassificationResult:
        """
        Classify a UK document based on its text content.

        Args:
            text: The document text to classify

        Returns:
            Classification result with document type and confidence
        """
        text_lower = text.lower()
        scores: Dict[UKDocumentType, float] = {}

        # Calculate keyword match scores
        for doc_type, keywords in self.DOCUMENT_KEYWORDS.items():
            matches = sum(1 for keyword in keywords if keyword in text_lower)
            scores[doc_type] = matches / len(keywords) if keywords else 0.0

        # Find best match
        if not scores or max(scores.values()) == 0:
            # Default to bank statement with low confidence if no matches
            return DocumentClassificationResult(
                document_type=UKDocumentType.BANK_STATEMENT,
                confidence=0.0,
                validation_errors=["No matching keywords found"]
            )

        best_type = max(scores, key=scores.get)
        confidence = scores[best_type]

        # Extract data based on document type
        extracted_data = self._extract_data(text, best_type)
        validation_errors = self._validate_extracted_data(extracted_data, best_type)

        return DocumentClassificationResult(
            document_type=best_type,
            confidence=confidence,
            extracted_data=extracted_data,
            validation_errors=validation_errors
        )

    def _extract_data(self, text: str, doc_type: UKDocumentType) -> Dict[str, str]:
        """Extract relevant data from document text."""
        extracted: Dict[str, str] = {}

        # Extract postal codes
        postcode_matches = re.findall(
            r"\b([A-Z]{1,2}\d{1,2}[A-Z]?)\s*(\d[A-Z]{2})\b",
            text,
            re.IGNORECASE
        )
        if postcode_matches:
            extracted["postal_code"] = UKPostalCodeValidator.normalize(
                f"{postcode_matches[0][0]} {postcode_matches[0][1]}"
            )

        # Extract dates
        date_matches = re.findall(
            r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
            text
        )
        if date_matches:
            extracted["date"] = date_matches[0]

        return extracted

    def _validate_extracted_data(
        self, data: Dict[str, str], doc_type: UKDocumentType
    ) -> List[str]:
        """Validate extracted data."""
        errors: List[str] = []

        # Validate postal code if present
        if "postal_code" in data:
            if not UKPostalCodeValidator.validate(data["postal_code"]):
                errors.append(f"Invalid postal code: {data['postal_code']}")

        # Validate date if present
        if "date" in data:
            if not UKDateParser.parse(data["date"]):
                errors.append(f"Invalid date format: {data['date']}")

        return errors
