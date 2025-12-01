"""Canada-specific Document Classification Module

This module provides classification for Canada-specific documents:
- CRA Tax Forms
- Health Card
- Driver's License
- Passport
- Bank Statements
- Hydro/Utility Bills

It includes support for Canadian date formats and postal codes.
"""

import re
from datetime import datetime
from typing import Optional


class CanadaDocumentClassifier:
    """Classifier for Canada-specific documents."""

    @staticmethod
    def classify_document(text: str) -> Optional[str]:
        """Classify the document based on its content.

        Args:
            text: The text content of the document.

        Returns:
            The document type if recognized, otherwise None.
        """
        if "CRA" in text and "tax" in text.lower():
            return "CRA Tax Form"
        elif "health card" in text.lower():
            return "Health Card"
        elif "driver's license" in text.lower():
            return "Driver's License"
        elif "passport" in text.lower():
            return "Passport"
        elif "account number" in text.lower() and "transit number" in text.lower():
            return "Bank Statement"
        elif "hydro bill" in text.lower() or "utility bill" in text.lower():
            return "Hydro/Utility Bill"
        return None

    @staticmethod
    def extract_canadian_date(text: str) -> Optional[datetime]:
        """Extract Canadian date from text.

        Args:
            text: The text content of the document.

        Returns:
            A datetime object if a date is found, otherwise None.
        """
        date_patterns = [
            r"\b\d{1,2}/\d{1,2}/\d{4}\b",  # DD/MM/YYYY
            r"\b\d{4}-\d{1,2}-\d{1,2}\b",  # YYYY-MM-DD
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return datetime.strptime(match.group(), "%d/%m/%Y")
                except ValueError:
                    try:
                        return datetime.strptime(match.group(), "%Y-%m-%d")
                    except ValueError:
                        continue
        return None

    @staticmethod
    def extract_canadian_postal_code(text: str) -> Optional[str]:
        """Extract Canadian postal code from text.

        Args:
            text: The text content of the document.

        Returns:
            A string representing the postal code if found, otherwise None.
        """
        postal_code_pattern = r"\b[A-Z]\d[A-Z] \d[A-Z]\d\b"
        match = re.search(postal_code_pattern, text, re.IGNORECASE)
        return match.group().upper() if match else None
