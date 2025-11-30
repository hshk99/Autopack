"""
Tests for Canada document classification pack.
"""

import pytest
from datetime import datetime
from src.backend.packs.canada_documents import (
    CanadaDocumentPack,
    CanadianPostalCode,
    CanadianDateFormat,
    DocumentCategory
)


class TestCanadianPostalCode:
    """Tests for Canadian postal code validation."""
    
    def test_valid_postal_codes(self):
        """Test validation of valid postal codes."""
        valid_codes = [
            "K1A 0B1",  # Ottawa
            "M5H 2N2",  # Toronto
            "H3Z 2Y7",  # Montreal
            "V6B 4Y8",  # Vancouver
            "T2P 2M5",  # Calgary
        ]
        
        for code in valid_codes:
            postal = CanadianPostalCode(code=code)
            assert postal.code == code.upper().replace(' ', '')[:3] + ' ' + code.upper().replace(' ', '')[3:]
    
    def test_valid_postal_codes_no_space(self):
        """Test validation of postal codes without spaces."""
        postal = CanadianPostalCode(code="K1A0B1")
        assert postal.code == "K1A 0B1"
    
    def test_invalid_postal_codes(self):
        """Test rejection of invalid postal codes."""
        invalid_codes = [
            "12345",        # US ZIP
            "A1A 1A",       # Too short
            "D1A 1A1",      # Invalid first letter (D)
            "A1D 1A1",      # Invalid third letter (D)
            "A1A 1D1",      # Invalid fifth letter (D)
            "AAA 111",      # Wrong pattern
            "111 AAA",      # Wrong pattern
        ]
        
        for code in invalid_codes:
            with pytest.raises(ValueError):
                CanadianPostalCode(code=code)
    
    def test_postal_code_formatting(self):
        """Test postal code formatting."""
        postal = CanadianPostalCode(code="k1a0b1")
        assert postal.code == "K1A 0B1"


class TestCanadianDateFormat:
    """Tests for Canadian date format handling."""
    
    def test_parse_iso_date(self):
        """Test parsing ISO format dates."""
        date = CanadianDateFormat.parse_date("2024-01-15")
        assert date is not None
        assert date.year == 2024
        assert date.month == 1
        assert date.day == 15
    
    def test_parse_dd_mm_yyyy(self):
        """Test parsing DD/MM/YYYY format."""
        date = CanadianDateFormat.parse_date("15/01/2024")
        assert date is not None
        assert date.year == 2024
        assert date.month == 1
        assert date.day == 15
    
    def test_parse_long_format(self):
        """Test parsing long format dates."""
        date = CanadianDateFormat.parse_date("January 15, 2024")
        assert date is not None
        assert date.year == 2024
        assert date.month == 1
        assert date.day == 15
    
    def test_parse_invalid_date(self):
        """Test parsing invalid date returns None."""
        date = CanadianDateFormat.parse_date("invalid date")
        assert date is None
    
    def test_format_date_iso(self):
        """Test formatting date as ISO."""
        date = datetime(2024, 1, 15)
        formatted = CanadianDateFormat.format_date(date, "iso")
        assert formatted == "2024-01-15"
    
    def test_format_date_short(self):
        """Test formatting date as short format."""
        date = datetime(2024, 1, 15)
        formatted = CanadianDateFormat.format_date(date, "short")
        assert formatted == "15/01/2024"
    
    def test_format_date_long(self):
        """Test formatting date as long format."""
        date = datetime(2024, 1, 15)
        formatted = CanadianDateFormat.format_date(date, "long")
        assert formatted == "January 15, 2024"


class TestCanadaDocumentPack:
    """Tests for Canada document classification pack."""
    
    def test_classify_cra_tax_form(self):
        """Test classification of CRA tax forms."""
        text = """
        CANADA REVENUE AGENCY
        Statement of Remuneration Paid
        T4 (2023)
        Social Insurance Number: 123-456-789
        Employment Income: $50,000.00
        """
        
        result = CanadaDocumentPack.classify_document(text)
        assert result["category_id"] == "cra_tax_forms"
        assert result["confidence"] > 0.7
    
    def test_classify_health_card(self):
        """Test classification of health cards."""
        text = """
        ONTARIO HEALTH INSURANCE PLAN
        Health Card / Carte Santé
        OHIP Number: 1234567890
        Expiry Date: 2025-12-31
        """
        
        result = CanadaDocumentPack.classify_document(text)
        assert result["category_id"] == "health_card"
        assert result["confidence"] > 0.7
    
    def test_classify_drivers_license(self):
        """Test classification of driver's licenses."""
        text = """
        ONTARIO
        Driver's Licence / Permis de conduire
        License Number: A1234-12345-12345
        Class: G
        Expiry Date: 2026-03-15
        Ministry of Transportation
        """
        
        result = CanadaDocumentPack.classify_document(text)
        assert result["category_id"] == "drivers_license"
        assert result["confidence"] > 0.7
    
    def test_classify_passport(self):
        """Test classification of Canadian passports."""
        text = """
        CANADA
        PASSPORT / PASSEPORT
        Passport No: AB123456
        Date of Issue: 2020-01-15
        Date of Expiry: 2030-01-14
        Global Affairs Canada
        """
        
        result = CanadaDocumentPack.classify_document(text)
        assert result["category_id"] == "passport"
        assert result["confidence"] > 0.7
    
    def test_classify_bank_statement(self):
        """Test classification of bank statements."""
        text = """
        ROYAL BANK OF CANADA
        Bank Statement / Relevé bancaire
        Account Number: 12345-6789012
        Statement Period: January 1 - January 31, 2024
        Opening Balance: $1,234.56
        Closing Balance: $2,345.67
        """
        
        result = CanadaDocumentPack.classify_document(text)
        assert result["category_id"] == "bank_statement"
        assert result["confidence"] > 0.6
    
    def test_classify_utility_bill(self):
        """Test classification of utility bills."""
        text = """
        HYDRO ONE
        Electricity Bill / Facture d'électricité
        Account Number: 123456789
        Billing Period: Dec 1, 2023 - Dec 31, 2023
        Total Usage: 450 kWh
        Amount Due: $125.50
        """
        
        result = CanadaDocumentPack.classify_document(text)
        assert result["category_id"] == "utility_bill"
        assert result["confidence"] > 0.6
    
    def test_classify_unknown_document(self):
        """Test classification of unknown documents."""
        text = """
        This is some random text that doesn't match
        any of the known Canadian document categories.
        """
        
        result = CanadaDocumentPack.classify_document(text)
        assert result["category_id"] == "unknown"
        assert result["confidence"] == 0.0
    
    def test_validate_postal_code_valid(self):
        """Test postal code validation with valid codes."""
        assert CanadaDocumentPack.validate_postal_code("K1A 0B1") is True
        assert CanadaDocumentPack.validate_postal_code("M5H2N2") is True
    
    def test_validate_postal_code_invalid(self):
        """Test postal code validation with invalid codes."""
        assert CanadaDocumentPack.validate_postal_code("12345") is False
        assert CanadaDocumentPack.validate_postal_code("D1A 1A1") is False
    
    def test_extract_dates(self):
        """Test date extraction from text."""
        text = """
        Issue Date: 2024-01-15
        Expiry Date: 15/01/2025
        Statement Period: January 1, 2024 to January 31, 2024
        """
        
        dates = CanadaDocumentPack.extract_dates(text)
        assert len(dates) >= 3
        assert any(d.year == 2024 and d.month == 1 and d.day == 15 for d in dates)
    
    def test_get_category_info(self):
        """Test retrieving category information."""
        category = CanadaDocumentPack.get_category_info("cra_tax_forms")
        assert category is not None
        assert category.name == "CRA Tax Forms"
        assert "cra" in [kw.lower() for kw in category.keywords]
    
    def test_get_category_info_invalid(self):
        """Test retrieving invalid category returns None."""
        category = CanadaDocumentPack.get_category_info("invalid_category")
        assert category is None
    
    def test_list_categories(self):
        """Test listing all categories."""
        categories = CanadaDocumentPack.list_categories()
        assert len(categories) == 6
        
        category_ids = [cat["id"] for cat in categories]
        assert "cra_tax_forms" in category_ids
        assert "health_card" in category_ids
        assert "drivers_license" in category_ids
        assert "passport" in category_ids
        assert "bank_statement" in category_ids
        assert "utility_bill" in category_ids
    
    def test_all_matches_returned(self):
        """Test that all matching categories are returned."""
        text = """
        CANADA REVENUE AGENCY
        T4 Statement
        Bank Account Information
        """
        
        result = CanadaDocumentPack.classify_document(text)
        assert "all_matches" in result
        # Should match CRA tax forms strongly
        assert "cra_tax_forms" in result["all_matches"]
