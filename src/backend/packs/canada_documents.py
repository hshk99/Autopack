"""
Canada-specific document classification pack.

This pack provides specialized classification for Canadian documents including:
- CRA Tax Forms (T4, T5, Notice of Assessment, etc.)
- Provincial Health Cards
- Driver's Licenses
- Canadian Passports
- Bank Statements
- Utility Bills (Hydro, Gas, Water)

Includes support for Canadian date formats and postal code validation.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import re
from pydantic import BaseModel, Field, field_validator


class CanadianPostalCode(BaseModel):
    """Canadian postal code validator and parser."""
    
    code: str = Field(..., description="Postal code in format A1A 1A1")

    @field_validator('code')
    @classmethod
    def validate_postal_code(cls, v: str) -> str:
        """Validate Canadian postal code format."""
        # Remove spaces and convert to uppercase
        cleaned = v.replace(' ', '').upper()
        
        # Canadian postal code pattern: A1A 1A1
        pattern = r'^[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z]\d[ABCEGHJ-NPRSTV-Z]\d$'
        
        if not re.match(pattern, cleaned):
            raise ValueError(
                f"Invalid Canadian postal code format: {v}. "
                "Expected format: A1A 1A1 (e.g., K1A 0B1)"
            )
        
        # Return formatted version with space
        return f"{cleaned[:3]} {cleaned[3:]}"


class CanadianDateFormat:
    """Utility class for handling Canadian date formats."""
    
    # Common Canadian date formats
    FORMATS = [
        "%Y-%m-%d",      # ISO format (preferred)
        "%d/%m/%Y",      # DD/MM/YYYY
        "%d-%m-%Y",      # DD-MM-YYYY
        "%B %d, %Y",     # Month DD, YYYY
        "%d %B %Y",      # DD Month YYYY
        "%b %d, %Y",     # Mon DD, YYYY
        "%d %b %Y",      # DD Mon YYYY
    ]
    
    @classmethod
    def parse_date(cls, date_str: str) -> Optional[datetime]:
        """
        Parse a date string using common Canadian formats.
        
        Args:
            date_str: Date string to parse
            
        Returns:
            Parsed datetime object or None if parsing fails
        """
        for fmt in cls.FORMATS:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        return None
    
    @classmethod
    def format_date(cls, date: datetime, format_type: str = "iso") -> str:
        """
        Format a datetime object using Canadian conventions.
        
        Args:
            date: Datetime object to format
            format_type: Type of format ('iso', 'short', 'long')
            
        Returns:
            Formatted date string
        """
        formats = {
            "iso": "%Y-%m-%d",
            "short": "%d/%m/%Y",
            "long": "%B %d, %Y"
        }
        return date.strftime(formats.get(format_type, formats["iso"]))


class DocumentCategory(BaseModel):
    """Document category definition."""
    
    name: str = Field(..., description="Category name")
    keywords: List[str] = Field(default_factory=list, description="Keywords for classification")
    patterns: List[str] = Field(default_factory=list, description="Regex patterns for identification")
    required_fields: List[str] = Field(default_factory=list, description="Required fields for validation")
    confidence_threshold: float = Field(default=0.7, description="Minimum confidence for classification")


class CanadaDocumentPack:
    """
    Canada-specific document classification pack.
    
    Provides classification and validation for common Canadian documents
    with support for Canadian-specific formats and conventions.
    """
    
    CATEGORIES: Dict[str, DocumentCategory] = {
        "cra_tax_forms": DocumentCategory(
            name="CRA Tax Forms",
            keywords=[
                "canada revenue agency", "cra",
                "t4", "t5", "notice of assessment",
                "tax return", "social insurance number"
            ],
            patterns=[
                r"T\d{1,2}[A-Z]?\s*\(\d{4}\)",  # T4(2023), T5A(2024)
                r"\d{3}-\d{3}-\d{3}",            # SIN format
                r"Notice of Assessment",
                r"Avis de cotisation"
            ],
            required_fields=["tax_year", "sin_or_business_number"],
            confidence_threshold=0.43
        ),
        "health_card": DocumentCategory(
            name="Provincial Health Card",
            keywords=[
                "health card", "ohip", "ramq", "msp",
                "health insurance", "ontario health"
            ],
            patterns=[
                r"\d{10}",                       # OHIP number (10 digits)
                r"[A-Z]{4}\s?\d{8}",            # RAMQ format
                r"\d{4}\s?\d{3}\s?\d{3}",       # BC MSP format
            ],
            required_fields=["health_number", "province", "expiry_date"],
            confidence_threshold=0.43
        ),
        "drivers_license": DocumentCategory(
            name="Driver's License",
            keywords=[
                "driver's licence", "driver's license",
                "class", "endorsement",
                "ministry of transportation"
            ],
            patterns=[
                r"[A-Z]\d{4}-\d{5}-\d{5}",      # Ontario format
                r"[A-Z]\d{14}",                  # Quebec format
                r"\d{7,9}",                      # BC/AB format
            ],
            required_fields=["license_number", "class", "expiry_date", "province"],
            confidence_threshold=0.43
        ),
        "passport": DocumentCategory(
            name="Canadian Passport",
            keywords=[
                "passport", "canada", "travel document",
                "citizenship", "global affairs"
            ],
            patterns=[
                r"[A-Z]{2}\d{6}",               # Passport number format
                r"CAN<<",                        # MRZ line indicator
            ],
            required_fields=["passport_number", "issue_date", "expiry_date"],
            confidence_threshold=0.43
        ),
        "bank_statement": DocumentCategory(
            name="Bank Statement",
            keywords=[
                "bank statement", "account summary",
                "chequing", "savings",
                "transaction", "balance"
            ],
            patterns=[
                r"Account\s+Number:?\s*\d+",
                r"Statement\s+Period",
                r"Opening\s+Balance",
                r"Closing\s+Balance",
                r"\$\s*[\d,]+\.\d{2}"           # Canadian dollar amounts
            ],
            required_fields=["account_number", "statement_date", "institution"],
            confidence_threshold=0.43
        ),
        "utility_bill": DocumentCategory(
            name="Hydro/Utility Bill",
            keywords=[
                "hydro", "electricity", "utility bill",
                "gas", "water",
                "billing period", "kwh"
            ],
            patterns=[
                r"Account\s+#?:?\s*\d+",
                r"\d+\s*kWh",                    # Kilowatt hours
                r"\d+\s*m³",                     # Cubic metres (gas/water)
                r"Billing\s+Period",
                r"Amount\s+Due"
            ],
            required_fields=["account_number", "billing_period", "amount_due"],
            confidence_threshold=0.43
        )
    }
    
    @classmethod
    def classify_document(cls, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Classify a document based on its content.
        
        Args:
            text: Document text content
            metadata: Optional metadata about the document
            
        Returns:
            Classification result with category and confidence score
        """
        text_lower = text.lower()
        results = {}
        
        for category_id, category in cls.CATEGORIES.items():
            score = 0.0
            matches = []
            
            # Check keywords
            keyword_matches = sum(1 for kw in category.keywords if kw.lower() in text_lower)
            keyword_score = keyword_matches / len(category.keywords) if category.keywords else 0
            
            # Check patterns
            pattern_matches = []
            for pattern in category.patterns:
                found = re.findall(pattern, text, re.IGNORECASE)
                if found:
                    pattern_matches.extend(found)
            
            pattern_score = min(len(pattern_matches) / max(len(category.patterns), 1), 1.0)

            # Combined score (weighted average) - BUILD-047: Pattern matches more reliable than keywords
            score = (keyword_score * 0.4) + (pattern_score * 0.6)
            
            if score >= category.confidence_threshold:
                results[category_id] = {
                    "category": category.name,
                    "confidence": round(score, 3),
                    "keyword_matches": keyword_matches,
                    "pattern_matches": len(pattern_matches),
                    "required_fields": category.required_fields
                }
        
        # Return best match or unknown
        if results:
            best_match = max(results.items(), key=lambda x: x[1]["confidence"])
            return {
                "category_id": best_match[0],
                "category_name": best_match[1]["category"],
                "confidence": best_match[1]["confidence"],
                "details": best_match[1],
                "all_matches": results
            }
        
        return {
            "category_id": "unknown",
            "category_name": "Unknown Document Type",
            "confidence": 0.0,
            "details": {},
            "all_matches": {}
        }
    
    @classmethod
    def validate_postal_code(cls, postal_code: str) -> bool:
        """
        Validate a Canadian postal code.
        
        Args:
            postal_code: Postal code to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            CanadianPostalCode(code=postal_code)
            return True
        except ValueError:
            return False
    
    @classmethod
    def extract_dates(cls, text: str) -> List[datetime]:
        """
        Extract dates from text using Canadian date formats.
        
        Args:
            text: Text to extract dates from
            
        Returns:
            List of extracted datetime objects
        """
        dates = []
        
        # Common date patterns
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',                    # YYYY-MM-DD
            r'\d{2}/\d{2}/\d{4}',                    # DD/MM/YYYY
            r'\d{2}-\d{2}-\d{4}',                    # DD-MM-YYYY
            r'[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}',     # Month DD, YYYY
            r'\d{1,2}\s+[A-Z][a-z]+\s+\d{4}',       # DD Month YYYY
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                parsed = CanadianDateFormat.parse_date(match)
                if parsed:
                    dates.append(parsed)
        
        return dates
    
    @classmethod
    def get_category_info(cls, category_id: str) -> Optional[DocumentCategory]:
        """
        Get information about a specific category.
        
        Args:
            category_id: Category identifier
            
        Returns:
            DocumentCategory object or None if not found
        """
        return cls.CATEGORIES.get(category_id)
    
    @classmethod
    def list_categories(cls) -> List[Dict[str, str]]:
        """
        List all available document categories.
        
        Returns:
            List of category information dictionaries
        """
        return [
            {
                "id": cat_id,
                "name": cat.name,
                "confidence_threshold": cat.confidence_threshold
            }
            for cat_id, cat in cls.CATEGORIES.items()
        ]
