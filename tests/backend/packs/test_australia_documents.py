"""
Tests for Australian document classification pack.
"""

from datetime import datetime
import pytest

from src.backend.packs.australia_documents import (
    AustralianDocumentType,
    AustralianState,
    AustralianDateFormat,
    PostcodeValidator,
    DocumentClassificationRule,
    AustralianDocumentPack,
)


class TestAustralianDateFormat:
    """Test Australian date format utilities."""
    
    def test_parse_date_slash_format(self):
        """Test parsing DD/MM/YYYY format."""
        date = AustralianDateFormat.parse_date("31/12/2023")
        assert date is not None
        assert date.day == 31
        assert date.month == 12
        assert date.year == 2023
    
    def test_parse_date_dash_format(self):
        """Test parsing DD-MM-YYYY format."""
        date = AustralianDateFormat.parse_date("15-06-2023")
        assert date is not None
        assert date.day == 15
        assert date.month == 6
        assert date.year == 2023
    
    def test_parse_date_full_month(self):
        """Test parsing DD Month YYYY format."""
        date = AustralianDateFormat.parse_date("25 December 2023")
        assert date is not None
        assert date.day == 25
        assert date.month == 12
        assert date.year == 2023
    
    def test_parse_date_abbreviated_month(self):
        """Test parsing DD Mon YYYY format."""
        date = AustralianDateFormat.parse_date("10 Jan 2023")
        assert date is not None
        assert date.day == 10
        assert date.month == 1
        assert date.year == 2023
    
    def test_parse_date_invalid(self):
        """Test parsing invalid date returns None."""
        date = AustralianDateFormat.parse_date("invalid date")
        assert date is None
    
    def test_format_date_default(self):
        """Test formatting date to DD/MM/YYYY."""
        date = datetime(2023, 12, 31)
        formatted = AustralianDateFormat.format_date(date)
        assert formatted == "31/12/2023"
    
    def test_format_date_dash(self):
        """Test formatting date to DD-MM-YYYY."""
        date = datetime(2023, 6, 15)
        formatted = AustralianDateFormat.format_date(date, format_index=1)
        assert formatted == "15-06-2023"


class TestPostcodeValidator:
    """Test Australian postcode validation."""
    
    def test_validate_postcode_nsw_valid(self):
        """Test valid NSW postcode."""
        assert PostcodeValidator.validate_postcode("2000") is True
        assert PostcodeValidator.validate_postcode("2500") is True
    
    def test_validate_postcode_vic_valid(self):
        """Test valid VIC postcode."""
        assert PostcodeValidator.validate_postcode("3000") is True
        assert PostcodeValidator.validate_postcode("3999") is True
    
    def test_validate_postcode_qld_valid(self):
        """Test valid QLD postcode."""
        assert PostcodeValidator.validate_postcode("4000") is True
        assert PostcodeValidator.validate_postcode("4999") is True
    
    def test_validate_postcode_sa_valid(self):
        """Test valid SA postcode."""
        assert PostcodeValidator.validate_postcode("5000") is True
    
    def test_validate_postcode_wa_valid(self):
        """Test valid WA postcode."""
        assert PostcodeValidator.validate_postcode("6000") is True
    
    def test_validate_postcode_tas_valid(self):
        """Test valid TAS postcode."""
        assert PostcodeValidator.validate_postcode("7000") is True
    
    def test_validate_postcode_nt_valid(self):
        """Test valid NT postcode."""
        assert PostcodeValidator.validate_postcode("0800") is True
    
    def test_validate_postcode_act_valid(self):
        """Test valid ACT postcode."""
        assert PostcodeValidator.validate_postcode("2600") is True
    
    def test_validate_postcode_invalid_format(self):
        """Test invalid postcode format."""
        assert PostcodeValidator.validate_postcode("123") is False
        assert PostcodeValidator.validate_postcode("12345") is False
        assert PostcodeValidator.validate_postcode("abcd") is False
    
    def test_validate_postcode_invalid_range(self):
        """Test postcode outside valid ranges."""
        assert PostcodeValidator.validate_postcode("0000") is False
        assert PostcodeValidator.validate_postcode("9999") is False
    
    def test_get_state_from_postcode_nsw(self):
        """Test getting NSW from postcode."""
        state = PostcodeValidator.get_state_from_postcode("2000")
        assert state == AustralianState.NSW
    
    def test_get_state_from_postcode_vic(self):
        """Test getting VIC from postcode."""
        state = PostcodeValidator.get_state_from_postcode("3000")
        assert state == AustralianState.VIC
    
    def test_get_state_from_postcode_qld(self):
        """Test getting QLD from postcode."""
        state = PostcodeValidator.get_state_from_postcode("4000")
        assert state == AustralianState.QLD
    
    def test_get_state_from_postcode_invalid(self):
        """Test getting state from invalid postcode."""
        state = PostcodeValidator.get_state_from_postcode("0000")
        assert state is None


class TestDocumentClassificationRule:
    """Test document classification rule model."""
    
    def test_create_valid_rule(self):
        """Test creating valid classification rule."""
        rule = DocumentClassificationRule(
            document_type=AustralianDocumentType.ATO_TAX_RETURN,
            keywords=["tax", "ato"],
            patterns=[r"\d{3}\s*\d{3}\s*\d{3}"],
            required_fields=["tfn"],
        )
        assert rule.document_type == AustralianDocumentType.ATO_TAX_RETURN
        assert len(rule.keywords) == 2
        assert rule.confidence_threshold == 0.7
    
    def test_invalid_regex_pattern(self):
        """Test that invalid regex pattern raises error."""
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            DocumentClassificationRule(
                document_type=AustralianDocumentType.MEDICARE_CARD,
                keywords=["medicare"],
                patterns=["[invalid(regex"],
                required_fields=["number"],
            )


class TestAustralianDocumentPack:
    """Test Australian document classification pack."""
    
    def test_classify_ato_tax_return(self):
        """Test classifying ATO tax return document."""
        text = """
        Australian Taxation Office
        Notice of Assessment
        Tax File Number: 123 456 789
        Financial Year: 2022-2023
        Taxable Income: $75,000
        """
        doc_type = AustralianDocumentPack.classify_document(text)
        assert doc_type == AustralianDocumentType.ATO_TAX_RETURN
    
    def test_classify_medicare_card(self):
        """Test classifying Medicare card."""
        text = """
        Medicare Card
        Medicare Number: 1234 56789 1
        Valid to: 12/2025
        """
        doc_type = AustralianDocumentPack.classify_document(text)
        assert doc_type == AustralianDocumentType.MEDICARE_CARD
    
    def test_classify_drivers_license(self):
        """Test classifying driver's license."""
        text = """
        Driver's Licence
        Licence No: 12345678
        Date of Birth: 15/06/1990
        Expiry Date: 31/12/2025
        """
        doc_type = AustralianDocumentPack.classify_document(text)
        assert doc_type == AustralianDocumentType.DRIVERS_LICENSE
    
    def test_classify_passport(self):
        """Test classifying Australian passport."""
        text = """
        Australian Passport
        Passport No: N1234567
        Nationality: AUSTRALIA
        Date of Issue: 01/01/2020
        """
        doc_type = AustralianDocumentPack.classify_document(text)
        assert doc_type == AustralianDocumentType.PASSPORT
    
    def test_classify_bank_statement(self):
        """Test classifying bank statement."""
        text = """
        Bank Statement
        BSB: 123-456
        Account Number: 12345678
        Opening Balance: $5,000.00
        Closing Balance: $5,500.00
        """
        doc_type = AustralianDocumentPack.classify_document(text)
        assert doc_type == AustralianDocumentType.BANK_STATEMENT
    
    def test_classify_utility_bill(self):
        """Test classifying utility bill."""
        text = """
        Electricity Bill
        Account Number: 123456789
        Billing Period: 01/01/2024 - 31/01/2024
        Amount Due: $150.00
        Due Date: 15/02/2024
        """
        doc_type = AustralianDocumentPack.classify_document(text)
        assert doc_type == AustralianDocumentType.UTILITY_BILL
    
    def test_classify_unknown_document(self):
        """Test classifying unknown document returns None."""
        text = "This is some random text with no document markers."
        doc_type = AustralianDocumentPack.classify_document(text)
        assert doc_type is None
