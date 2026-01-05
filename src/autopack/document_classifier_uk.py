"""UK-specific Document Classification Module

This module provides classification for UK-specific documents:
- HMRC Tax Returns
- NHS Records
- Driving Licence
- Passport
- Bank Statements
- Utility Bills

It includes support for UK date formats and postal codes.
"""

import re
from datetime import datetime
from typing import Optional


class UKDocumentClassifier:
    """Classifier for UK-specific documents."""

    @staticmethod
    def classify_document(text: str) -> Optional[str]:
        """Classify the document based on its content.

        Args:
            text: The text content of the document.

        Returns:
            The document type if recognized, otherwise None.
        """
        if "HMRC" in text and "tax return" in text.lower():
            return "HMRC Tax Return"
        elif "NHS" in text and "patient" in text.lower():
            return "NHS Record"
        elif "driving licence" in text.lower():
            return "Driving Licence"
        elif "passport" in text.lower():
            return "Passport"
        elif "account number" in text.lower() and "sort code" in text.lower():
            return "Bank Statement"
        elif (
            "utility bill" in text.lower()
            or "electricity" in text.lower()
            or "water" in text.lower()
        ):
            return "Utility Bill"
        return None

    @staticmethod
    def extract_uk_date(text: str) -> Optional[datetime]:
        """Extract UK date from text.

        Args:
            text: The text content of the document.

        Returns:
            A datetime object if a date is found, otherwise None.
        """
        date_patterns = [
            r"\b\d{1,2}/\d{1,2}/\d{4}\b",  # DD/MM/YYYY
            r"\b\d{1,2}-\d{1,2}-\d{4}\b",  # DD-MM-YYYY
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return datetime.strptime(match.group(), "%d/%m/%Y")
                except ValueError:
                    continue
        return None

    @staticmethod
    def extract_uk_postcode(text: str) -> Optional[str]:
        """Extract UK postcode from text.

        Args:
            text: The text content of the document.

        Returns:
            A string representing the postcode if found, otherwise None.
        """
        postcode_pattern = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b"
        match = re.search(postcode_pattern, text, re.IGNORECASE)
        return match.group().upper() if match else None
