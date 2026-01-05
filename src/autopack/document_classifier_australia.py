"""Australia-specific Document Classification Module

This module provides classification for Australia-specific documents:
- ATO Tax Returns
- Medicare Card
- Driver's License
- Passport
- Bank Statements
- Utility Bills

It includes support for Australian date formats and postcodes.
"""

import re
from datetime import datetime
from typing import Optional


class AustraliaDocumentClassifier:
    """Classifier for Australia-specific documents."""

    @staticmethod
    def classify_document(text: str) -> Optional[str]:
        """Classify the document based on its content.

        Args:
            text: The text content of the document.

        Returns:
            The document type if recognized, otherwise None.
        """
        if "ATO" in text and "tax return" in text.lower():
            return "ATO Tax Return"
        elif "medicare card" in text.lower():
            return "Medicare Card"
        elif "driver's license" in text.lower() or "driver licence" in text.lower():
            return "Driver's License"
        elif "passport" in text.lower():
            return "Passport"
        elif "account number" in text.lower() and "bsb" in text.lower():
            return "Bank Statement"
        elif (
            "utility bill" in text.lower()
            or "electricity" in text.lower()
            or "water" in text.lower()
        ):
            return "Utility Bill"
        return None

    @staticmethod
    def extract_australian_date(text: str) -> Optional[datetime]:
        """Extract Australian date from text.

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
    def extract_australian_postcode(text: str) -> Optional[str]:
        """Extract Australian postcode from text.

        Args:
            text: The text content of the document.

        Returns:
            A string representing the postcode if found, otherwise None.
        """
        postcode_pattern = r"\b\d{4}\b"
        match = re.search(postcode_pattern, text)
        return match.group() if match else None
