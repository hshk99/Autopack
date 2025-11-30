"""
Tests for UK document classification pack.
"""

import pytest
from datetime import datetime

from src.backend.packs.uk_documents import (
    UKDocumentClassifier,
    UKDocumentType,
    UKPostalCodeValidator,
    UKDateParser,
)


class TestUKPostalCodeValidator:
    """Tests for UK postal code validation."""

    def test_valid_postcodes(self):
        """Test validation of valid UK postal codes."""
        valid_postcodes = [
            "SW1A 1AA",
            "M1 1AE",
            "B33 8TH",
            "CR2 6XH",
            "DN55 1PT",
            "W1A 0AX",
            "EC1A 1BB",
        ]

        for postcode in valid_postcodes:
            assert UKPostalCodeValidator.validate(postcode), f"Failed for {postcode}"

    def test_valid_postcodes_without_space(self):
        """Test validation of valid postcodes without space."""
        assert UKPostalCodeValidator.validate("SW1A1AA")
        assert UKPostalCodeValidator.validate("M11AE")
        assert UKPostalCodeValidator.validate("B338TH")

    def test_invalid_postcodes(self):
        """Test validation of invalid postal codes."""
        invalid_postcodes = [
            "INVALID",
            "12345",
            "A1 1",
            "AA AA",
            "",
            "SW1A 1AAA",
        ]

        for postcode in invalid_postcodes:
            assert not UKPostalCodeValidator.validate(postcode), f"Should fail for {postcode}"

    def test_normalize_postcode(self):
        """Test postal code normalization."""
        assert UKPostalCodeValidator.normalize("sw1a1aa") == "SW1A 1AA"
        assert UKPostalCodeValidator.normalize("m1  1ae") == "M1 1AE"
        assert UKPostalCodeValidator.normalize("B33 8TH") == "B33 8TH"
        assert UKPostalCodeValidator.normalize("invalid") is None


class TestUKDateParser:
    """Tests for UK date parsing."""

    def test_parse_dd_mm_yyyy(self):
        """Test parsing DD/MM/YYYY format."""
        date = UKDateParser.parse("25/12/2023")
        assert date is not None
        assert date.day == 25
        assert date.month == 12
        assert date.year == 2023

    def test_parse_dd_mm_yy(self):
        """Test parsing DD/MM/YY format."""
        date = UKDateParser.parse("25/12/23")
        assert date is not None
        assert date.day == 25
        assert date.month == 12
        assert date.year == 2023

    def test_parse_d_month_yyyy(self):
        """Test parsing D Month YYYY format."""
        date = UKDateParser.parse("25 December 2023")
        assert date is not None
        assert date.day == 25
        assert date.month == 12
        assert date.year == 2023

    def test_parse_d_mmm_yyyy(self):
        """Test parsing D MMM YYYY format."""
        date = UKDateParser.parse("25 Dec 2023")
        assert date is not None
        assert date.day == 25
        assert date.month == 12
        assert date.year == 2023

    def test_parse_invalid_date(self):
        """Test parsing invalid dates."""
        assert UKDateParser.parse("invalid") is None
        assert UKDateParser.parse("32/13/2023") is None
        assert UKDateParser.parse("") is None


class TestUKDocumentClassifier:
    """Tests for UK document classification."""

    def test_classify_hmrc_tax_return(self):
        """Test classification of HMRC tax return."""
        text = """
        HMRC Self Assessment Tax Return
        Tax Year: 2022/2023
        Unique Taxpayer Reference: 1234567890
        National Insurance Number: AB123456C
        Income Tax: £5,000
        Address: 123 Main Street, London, SW1A 1AA
        """

        classifier = UKDocumentClassifier()
        result = classifier.classify(text)

        assert result.document_type == UKDocumentType.HMRC_TAX_RETURN
        assert result.confidence > 0.5
        assert "postal_code" in result.extracted_data
        assert result.extracted_data["postal_code"] == "SW1A 1AA"

    def test_classify_nhs_record(self):
        """Test classification of NHS record."""
        text = """
        NHS Medical Record
        NHS Number: 123 456 7890
        GP Practice: City Medical Centre
        Prescription Details
        Hospital: Royal London Hospital
        Address: 456 Health Road, Manchester, M1 1AE
        """

        classifier = UKDocumentClassifier()
        result = classifier.classify(text)

        assert result.document_type == UKDocumentType.NHS_RECORD
        assert result.confidence > 0.5
        assert "postal_code" in result.extracted_data

    def test_classify_driving_licence(self):
        """Test classification of driving licence."""
        text = """
        UK Driving Licence
        DVLA Driver Number: SMITH123456AB1CD
        Categories: B, C1
        Entitlement: Full Licence
        Photocard Valid Until: 25/12/2033
        Address: 789 Drive Lane, Birmingham, B33 8TH
        """

        classifier = UKDocumentClassifier()
        result = classifier.classify(text)

        assert result.document_type == UKDocumentType.DRIVING_LICENCE
        assert result.confidence > 0.5

    def test_classify_passport(self):
        """Test classification of passport."""
        text = """
        United Kingdom of Great Britain and Northern Ireland
        Passport
        Passport Number: 123456789
        Nationality: British
        Date of Birth: 01/01/1990
        Place of Birth: London
        Date of Issue: 15/06/2023
        """

        classifier = UKDocumentClassifier()
        result = classifier.classify(text)

        assert result.document_type == UKDocumentType.PASSPORT
        assert result.confidence > 0.5

    def test_classify_bank_statement(self):
        """Test classification of bank statement."""
        text = """
        Bank Statement
        Account Number: 12345678
        Sort Code: 12-34-56
        Statement Period: 01/01/2023 - 31/01/2023
        Opening Balance: £1,000.00
        Closing Balance: £1,500.00
        Transactions: Debit, Credit
        """

        classifier = UKDocumentClassifier()
        result = classifier.classify(text)

        assert result.document_type == UKDocumentType.BANK_STATEMENT
        assert result.confidence > 0.5

    def test_classify_utility_bill(self):
        """Test classification of utility bill."""
        text = """
        Electricity Bill
        Meter Reading: 12345
        Usage: 500 kWh
        Tariff: Standard
        Supply Address: 321 Power Street, Leeds, LS1 1AB
        """

        classifier = UKDocumentClassifier()
        result = classifier.classify(text)

        assert result.document_type == UKDocumentType.UTILITY_BILL
        assert result.confidence > 0.5
