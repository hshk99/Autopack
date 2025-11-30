"""
Australia-specific document classification pack.

This pack provides document classification categories and validation rules
specific to Australian documents including tax returns, Medicare cards,
driver's licenses, passports, bank statements, and utility bills.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Pattern
import re

from pydantic import BaseModel, Field, field_validator


class AustralianDocumentType(str, Enum):
    """Australian document types."""
    
    ATO_TAX_RETURN = "ato_tax_return"
    MEDICARE_CARD = "medicare_card"
    DRIVERS_LICENSE = "drivers_license"
    PASSPORT = "passport"
    BANK_STATEMENT = "bank_statement"
    UTILITY_BILL = "utility_bill"


class AustralianState(str, Enum):
    """Australian states and territories."""
    
    NSW = "NSW"  # New South Wales
    VIC = "VIC"  # Victoria
    QLD = "QLD"  # Queensland
    SA = "SA"    # South Australia
    WA = "WA"    # Western Australia
    TAS = "TAS"  # Tasmania
    NT = "NT"    # Northern Territory
    ACT = "ACT"  # Australian Capital Territory


class AustralianDateFormat:
    """Australian date format utilities."""
    
    # Common Australian date formats
    FORMATS = [
        "%d/%m/%Y",      # 31/12/2023
        "%d-%m-%Y",      # 31-12-2023
        "%d %B %Y",      # 31 December 2023
        "%d %b %Y",      # 31 Dec 2023
        "%d.%m.%Y",      # 31.12.2023
    ]
    
    @classmethod
    def parse_date(cls, date_string: str) -> Optional[datetime]:
        """
        Parse Australian date string to datetime object.
        
        Args:
            date_string: Date string in Australian format
            
        Returns:
            Parsed datetime object or None if parsing fails
        """
        for fmt in cls.FORMATS:
            try:
                return datetime.strptime(date_string.strip(), fmt)
            except ValueError:
                continue
        return None
    
    @classmethod
    def format_date(cls, date: datetime, format_index: int = 0) -> str:
        """
        Format datetime to Australian date string.
        
        Args:
            date: Datetime object to format
            format_index: Index of format to use (default: 0 for DD/MM/YYYY)
            
        Returns:
            Formatted date string
        """
        return date.strftime(cls.FORMATS[format_index])


class PostcodeValidator:
    """Australian postcode validation utilities."""
    
    # Postcode ranges by state/territory
    POSTCODE_RANGES: Dict[AustralianState, List[tuple]] = {
        AustralianState.NSW: [(1000, 2599), (2619, 2899), (2921, 2999)],
        AustralianState.ACT: [(200, 299), (2600, 2618), (2900, 2920)],
        AustralianState.VIC: [(3000, 3999), (8000, 8999)],
        AustralianState.QLD: [(4000, 4999), (9000, 9999)],
        AustralianState.SA: [(5000, 5799), (5800, 5999)],
        AustralianState.WA: [(6000, 6797), (6800, 6999)],
        AustralianState.TAS: [(7000, 7799), (7800, 7999)],
        AustralianState.NT: [(800, 899), (900, 999)],
    }
    
    @classmethod
    def validate_postcode(cls, postcode: str) -> bool:
        """
        Validate Australian postcode format.
        
        Args:
            postcode: Postcode string to validate
            
        Returns:
            True if valid Australian postcode
        """
        if not re.match(r'^\d{4}$', postcode):
            return False
        
        code = int(postcode)
        for ranges in cls.POSTCODE_RANGES.values():
            for min_code, max_code in ranges:
                if min_code <= code <= max_code:
                    return True
        return False
    
    @classmethod
    def get_state_from_postcode(cls, postcode: str) -> Optional[AustralianState]:
        """
        Determine state/territory from postcode.
        
        Args:
            postcode: Postcode string
            
        Returns:
            State enum or None if invalid
        """
        if not cls.validate_postcode(postcode):
            return None
        
        code = int(postcode)
        for state, ranges in cls.POSTCODE_RANGES.items():
            for min_code, max_code in ranges:
                if min_code <= code <= max_code:
                    return state
        return None


class DocumentClassificationRule(BaseModel):
    """Rule for classifying Australian documents."""
    
    document_type: AustralianDocumentType
    keywords: List[str] = Field(description="Keywords that indicate this document type")
    patterns: List[str] = Field(description="Regex patterns for document identification")
    required_fields: List[str] = Field(description="Required fields for this document type")
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    
    @field_validator('patterns')
    @classmethod
    def validate_patterns(cls, v: List[str]) -> List[str]:
        """Validate that patterns are valid regex."""
        for pattern in v:
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern '{pattern}': {e}")
        return v


class AustralianDocumentPack:
    """Australian document classification pack."""
    
    CLASSIFICATION_RULES: List[DocumentClassificationRule] = [
        DocumentClassificationRule(
            document_type=AustralianDocumentType.ATO_TAX_RETURN,
            keywords=["tax return", "ato", "australian taxation office", "tfn", "tax file number", "notice of assessment"],
            patterns=[r"TFN\s*:?\s*\d{3}\s*\d{3}\s*\d{3}", r"ABN\s*:?\s*\d{2}\s*\d{3}\s*\d{3}\s*\d{3}"],
            required_fields=["tax_file_number", "financial_year", "taxable_income"],
        ),
        DocumentClassificationRule(
            document_type=AustralianDocumentType.MEDICARE_CARD,
            keywords=["medicare", "medicare card", "medicare number", "valid to"],
            patterns=[r"\d{4}\s*\d{5}\s*\d{1}", r"Valid\s+to:?\s+\d{2}/\d{4}"],
            required_fields=["medicare_number", "individual_reference_number", "expiry_date"],
        ),
        DocumentClassificationRule(
            document_type=AustralianDocumentType.DRIVERS_LICENSE,
            keywords=["driver", "licence", "license", "driver's licence", "dl number"],
            patterns=[r"Licence\s+No\.?\s*:?\s*\d+", r"Date\s+of\s+Birth\s*:?\s*\d{2}/\d{2}/\d{4}"],
            required_fields=["licence_number", "date_of_birth", "state", "expiry_date"],
        ),
        DocumentClassificationRule(
            document_type=AustralianDocumentType.PASSPORT,
            keywords=["passport", "australian passport", "nationality", "date of issue"],
            patterns=[r"Passport\s+No\.?\s*[A-Z]\d{7}", r"Nationality\s*:?\s*AUSTRALIA"],
            required_fields=["passport_number", "surname", "given_names", "date_of_birth", "expiry_date"],
        ),
        DocumentClassificationRule(
            document_type=AustralianDocumentType.BANK_STATEMENT,
            keywords=["bank statement", "account statement", "bsb", "account number", "balance"],
            patterns=[r"BSB\s*:?\s*\d{3}-?\d{3}", r"Account\s+Number\s*:?\s*\d+"],
            required_fields=["bsb", "account_number", "statement_period", "opening_balance", "closing_balance"],
        ),
        DocumentClassificationRule(
            document_type=AustralianDocumentType.UTILITY_BILL,
            keywords=["electricity", "gas", "water", "utility", "bill", "account number", "due date"],
            patterns=[r"Account\s+Number\s*:?\s*\d+", r"Due\s+Date\s*:?\s*\d{2}/\d{2}/\d{4}"],
            required_fields=["account_number", "billing_period", "amount_due", "due_date", "service_address"],
        ),
    ]
    
    @classmethod
    def classify_document(cls, text: str) -> Optional[AustralianDocumentType]:
        """
        Classify document based on content.
        
        Args:
            text: Document text content
            
        Returns:
            Classified document type or None if no match
        """
        text_lower = text.lower()
        best_match = None
        best_score = 0.0
        
        for rule in cls.CLASSIFICATION_RULES:
            score = 0.0
            
            # Check keywords
            keyword_matches = sum(1 for keyword in rule.keywords if keyword in text_lower)
            score += (keyword_matches / len(rule.keywords)) * 0.5
            
            # Check patterns
            pattern_matches = sum(1 for pattern in rule.patterns if re.search(pattern, text, re.IGNORECASE))
            score += (pattern_matches / len(rule.patterns)) * 0.5
            
            if score > best_score and score >= rule.confidence_threshold:
                best_score = score
                best_match = rule.document_type
        
        return best_match
