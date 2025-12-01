"""
UK-specific document classification pack.

This module provides document classification categories and patterns
specific to United Kingdom documents, including HMRC tax returns,
NHS records, driving licences, passports, bank statements, and utility bills.
"""

from typing import Dict, List, Optional
from datetime import datetime
import re
from pydantic import BaseModel, Field


class DocumentPattern(BaseModel):
    """Pattern definition for document classification."""

    pattern: str = Field(..., description="Regex pattern to match")
    weight: float = Field(default=1.0, description="Pattern matching weight")
    description: str = Field(..., description="Pattern description")


class DocumentCategory(BaseModel):
    """UK document category definition."""

    name: str = Field(..., description="Category name")
    description: str = Field(..., description="Category description")
    patterns: List[DocumentPattern] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    required_fields: List[str] = Field(default_factory=list)


class UKDocumentClassifier:
    """Classifier for UK-specific documents."""

    # UK date format patterns
    UK_DATE_PATTERNS = [
        r'\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b',  # DD/MM/YYYY or DD-MM-YYYY
        r'\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b',  # DD Month YYYY
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b',  # Month DD, YYYY
    ]

    # UK postcode pattern
    UK_POSTCODE_PATTERN = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'

    # National Insurance Number pattern
    NI_NUMBER_PATTERN = r'\b[A-Z]{2}\s*\d{2}\s*\d{2}\s*\d{2}\s*[A-Z]\b'

    # NHS Number pattern (10 digits)
    NHS_NUMBER_PATTERN = r'\b\d{3}\s*\d{3}\s*\d{4}\b'

    # UK Driving Licence Number pattern
    DRIVING_LICENCE_PATTERN = r'\b[A-Z]{5}\d{6}[A-Z]{2}\d[A-Z]{2}\b'

    # UK Passport Number pattern
    PASSPORT_NUMBER_PATTERN = r'\b\d{9}\b'

    # UK Bank Account patterns
    SORT_CODE_PATTERN = r'\b\d{2}[-\s]?\d{2}[-\s]?\d{2}\b'
    ACCOUNT_NUMBER_PATTERN = r'\b\d{8}\b'

    def __init__(self):
        """Initialize UK document classifier with predefined categories."""
        self.categories = self._initialize_categories()

    def _initialize_categories(self) -> Dict[str, DocumentCategory]:
        """Initialize UK document categories with patterns and keywords."""
        return {
            "hmrc_tax_return": DocumentCategory(
                name="HMRC Tax Return",
                description="HM Revenue & Customs tax return documents",
                patterns=[
                    DocumentPattern(
                        pattern=r'\bSA\d{3}\b',
                        weight=2.0,
                        description="Self Assessment form reference"
                    ),
                    DocumentPattern(
                        pattern=r'\bUTR\s*:?\s*\d{10}\b',
                        weight=2.0,
                        description="Unique Taxpayer Reference"
                    ),
                    DocumentPattern(
                        pattern=self.NI_NUMBER_PATTERN,
                        weight=1.5,
                        description="National Insurance Number"
                    ),
                ],
                keywords=[
                    "HMRC", "HM Revenue", "Customs", "Self Assessment",
                    "Tax Return", "UTR", "Income Tax", "National Insurance",
                    "P60", "P45", "PAYE", "Tax Year"
                ],
                required_fields=["tax_year", "utr_number"]
            ),
            "nhs_record": DocumentCategory(
                name="NHS Record",
                description="National Health Service medical records",
                patterns=[
                    DocumentPattern(
                        pattern=self.NHS_NUMBER_PATTERN,
                        weight=2.0,
                        description="NHS Number"
                    ),
                    DocumentPattern(
                        pattern=r'\bGP\s+Practice\b',
                        weight=1.5,
                        description="GP Practice reference"
                    ),
                ],
                keywords=[
                    "NHS", "National Health Service", "GP", "General Practitioner",
                    "Medical Record", "Patient", "Prescription", "Hospital",
                    "Surgery", "Health Centre", "Medical History"
                ],
                required_fields=["nhs_number", "patient_name"]
            ),
            "driving_licence": DocumentCategory(
                name="Driving Licence",
                description="UK Driving Licence documents",
                patterns=[
                    DocumentPattern(
                        pattern=self.DRIVING_LICENCE_PATTERN,
                        weight=2.5,
                        description="Driving Licence Number"
                    ),
                    DocumentPattern(
                        pattern=r'\bDVLA\b',
                        weight=2.0,
                        description="DVLA reference"
                    ),
                ],
                keywords=[
                    "DVLA", "Driving Licence", "Driver Number", "Photocard",
                    "Category", "Entitlement", "Valid Until", "Issue Date",
                    "Swansea", "Vehicle Licensing"
                ],
                required_fields=["licence_number", "holder_name"]
            ),
            "passport": DocumentCategory(
                name="Passport",
                description="UK Passport documents",
                patterns=[
                    DocumentPattern(
                        pattern=self.PASSPORT_NUMBER_PATTERN,
                        weight=2.0,
                        description="Passport Number"
                    ),
                    DocumentPattern(
                        pattern=r'\bHer\s+Majesty\'?s\s+Passport\b',
                        weight=2.5,
                        description="Passport title"
                    ),
                    DocumentPattern(
                        pattern=r'\bUnited\s+Kingdom\s+of\s+Great\s+Britain\b',
                        weight=2.0,
                        description="UK full name"
                    ),
                ],
                keywords=[
                    "Passport", "British Passport", "United Kingdom",
                    "Nationality", "Date of Birth", "Place of Birth",
                    "Date of Issue", "Date of Expiry", "Authority",
                    "Her Majesty", "HM Passport Office"
                ],
                required_fields=["passport_number", "holder_name", "nationality"]
            ),
            "bank_statement": DocumentCategory(
                name="Bank Statement",
                description="UK Bank Statement documents",
                patterns=[
                    DocumentPattern(
                        pattern=self.SORT_CODE_PATTERN,
                        weight=2.0,
                        description="Sort Code"
                    ),
                    DocumentPattern(
                        pattern=self.ACCOUNT_NUMBER_PATTERN,
                        weight=1.5,
                        description="Account Number"
                    ),
                    DocumentPattern(
                        pattern=r'\b(?:GBP|£)\s*[\d,]+\.\d{2}\b',
                        weight=1.0,
                        description="GBP currency amounts"
                    ),
                ],
                keywords=[
                    "Bank Statement", "Account Number", "Sort Code",
                    "Balance", "Transaction", "Debit", "Credit",
                    "Opening Balance", "Closing Balance", "Statement Period",
                    "IBAN", "BIC", "SWIFT"
                ],
                required_fields=["account_number", "sort_code", "statement_date"]
            ),
            "utility_bill": DocumentCategory(
                name="Utility Bill",
                description="UK Utility Bill documents (gas, electricity, water, council tax)",
                patterns=[
                    DocumentPattern(
                        pattern=self.UK_POSTCODE_PATTERN,
                        weight=1.5,
                        description="UK Postcode"
                    ),
                    DocumentPattern(
                        pattern=r'\bAccount\s+Number\s*:?\s*\d+\b',
                        weight=1.5,
                        description="Account Number"
                    ),
                    DocumentPattern(
                        pattern=r'\b(?:kWh|m³|litres)\b',
                        weight=1.0,
                        description="Utility units"
                    ),
                ],
                keywords=[
                    "Utility Bill", "Gas", "Electricity", "Water", "Council Tax",
                    "Energy", "Supply", "Meter Reading", "Usage", "Charges",
                    "Bill Date", "Payment Due", "Account Number", "Customer Number",
                    "British Gas", "EDF", "Scottish Power", "Thames Water"
                ],
                required_fields=["account_number", "bill_date", "address"]
            ),
        }

    def classify(self, text: str) -> Dict[str, float]:
        """
        Classify document text against UK document categories.

        Args:
            text: Document text to classify

        Returns:
            Dictionary mapping category names to confidence scores (0-1)
        """
        scores = {}

        for category_id, category in self.categories.items():
            score = 0.0
            max_score = 0.0

            # Check patterns
            for pattern_def in category.patterns:
                max_score += pattern_def.weight
                if re.search(pattern_def.pattern, text, re.IGNORECASE):
                    score += pattern_def.weight

            # Check keywords
            keyword_weight = 0.5
            max_score += len(category.keywords) * keyword_weight
            for keyword in category.keywords:
                if re.search(r'\b' + re.escape(keyword) + r'\b', text, re.IGNORECASE):
                    score += keyword_weight

            # Normalize score
            if max_score > 0:
                scores[category_id] = min(score / max_score, 1.0)
            else:
                scores[category_id] = 0.0

        return scores

    def get_category(self, category_id: str) -> Optional[DocumentCategory]:
        """Get category definition by ID."""
        return self.categories.get(category_id)

    def list_categories(self) -> List[str]:
        """List all available category IDs."""
        return list(self.categories.keys())

    def extract_uk_dates(self, text: str) -> List[str]:
        """Extract UK-formatted dates from text."""
        dates = []
        for pattern in self.UK_DATE_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            dates.extend(matches)
        return dates

    def extract_postcodes(self, text: str) -> List[str]:
        """Extract UK postcodes from text."""
        return re.findall(self.UK_POSTCODE_PATTERN, text, re.IGNORECASE)

    def extract_ni_numbers(self, text: str) -> List[str]:
        """Extract National Insurance numbers from text."""
        return re.findall(self.NI_NUMBER_PATTERN, text, re.IGNORECASE)

    def extract_nhs_numbers(self, text: str) -> List[str]:
        """Extract NHS numbers from text."""
        return re.findall(self.NHS_NUMBER_PATTERN, text)
