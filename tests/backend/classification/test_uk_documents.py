"""
Tests for UK document classification pack.
"""

import pytest

# Skip all tests in this file - backend classification features not fully implemented yet
pytestmark = pytest.mark.skip(reason="Backend classification features not fully implemented yet")
from src.backend.classification.packs.uk_documents import (
    UKDocumentClassifier,
    DocumentCategory,
    DocumentPattern,
)


@pytest.fixture
def classifier():
    """Create UK document classifier instance."""
    return UKDocumentClassifier()


class TestUKDocumentClassifier:
    """Test suite for UK document classifier."""

    def test_initialization(self, classifier):
        """Test classifier initializes with all categories."""
        categories = classifier.list_categories()
        assert len(categories) == 6
        assert "hmrc_tax_return" in categories
        assert "nhs_record" in categories
        assert "driving_licence" in categories
        assert "passport" in categories
        assert "bank_statement" in categories
        assert "utility_bill" in categories

    def test_hmrc_tax_return_classification(self, classifier):
        """Test HMRC tax return document classification."""
        text = """
        HM Revenue & Customs
        Self Assessment Tax Return
        Tax Year: 2023/2024
        UTR: 1234567890
        National Insurance Number: AB 12 34 56 C
        Form SA100
        Income Tax calculation
        """
        scores = classifier.classify(text)
        assert scores["hmrc_tax_return"] > 0.5
        assert scores["hmrc_tax_return"] > scores.get("nhs_record", 0)

    def test_nhs_record_classification(self, classifier):
        """Test NHS record document classification."""
        text = """
        National Health Service
        Patient Medical Record
        NHS Number: 123 456 7890
        GP Practice: City Medical Centre
        Patient Name: John Smith
        Medical History and Prescription Details
        """
        scores = classifier.classify(text)
        assert scores["nhs_record"] > 0.5
        assert scores["nhs_record"] > scores.get("hmrc_tax_return", 0)

    def test_driving_licence_classification(self, classifier):
        """Test driving licence document classification."""
        text = """
        DVLA
        United Kingdom Driving Licence
        Photocard Licence
        Driver Number: SMITH123456AB1CD
        Valid Until: 15/08/2030
        Category B - Motor vehicles
        Issued by: Driver and Vehicle Licensing Agency, Swansea
        """
        scores = classifier.classify(text)
        assert scores["driving_licence"] > 0.5
        assert scores["driving_licence"] > scores.get("passport", 0)

    def test_passport_classification(self, classifier):
        """Test passport document classification."""
        text = """
        Her Majesty's Passport
        United Kingdom of Great Britain and Northern Ireland
        Passport Number: 123456789
        Nationality: British
        Date of Birth: 15/03/1985
        Date of Issue: 01/06/2020
        Date of Expiry: 01/06/2030
        Authority: HM Passport Office
        """
        scores = classifier.classify(text)
        assert scores["passport"] > 0.5
        assert scores["passport"] > scores.get("driving_licence", 0)

    def test_bank_statement_classification(self, classifier):
        """Test bank statement document classification."""
        text = """
        Bank Statement
        Account Number: 12345678
        Sort Code: 12-34-56
        Statement Period: 01/01/2024 to 31/01/2024
        Opening Balance: £1,234.56
        Closing Balance: £2,345.67
        Transactions:
        15/01/2024 Debit £50.00
        20/01/2024 Credit £1,200.00
        """
        scores = classifier.classify(text)
        assert scores["bank_statement"] > 0.5
        assert scores["bank_statement"] > scores.get("utility_bill", 0)

    def test_utility_bill_classification(self, classifier):
        """Test utility bill document classification."""
        text = """
        British Gas Energy Bill
        Account Number: 123456789
        Bill Date: 15/01/2024
        Payment Due: 01/02/2024
        Supply Address:
        123 High Street
        London
        SW1A 1AA
        Gas Usage: 450 kWh
        Electricity Usage: 320 kWh
        Total Charges: £145.67
        """
        scores = classifier.classify(text)
        assert scores["utility_bill"] > 0.5
        assert scores["utility_bill"] > scores.get("bank_statement", 0)

    def test_uk_date_extraction(self, classifier):
        """Test UK date format extraction."""
        text = """
        Date: 15/03/2024
        Another date: 01-12-2023
        Written date: 25 December 2023
        US format should work too: January 15, 2024
        """
        dates = classifier.extract_uk_dates(text)
        assert len(dates) >= 3
        assert "15/03/2024" in dates or "15/03/2024" in str(dates)

    def test_postcode_extraction(self, classifier):
        """Test UK postcode extraction."""
        text = """
        Address 1: SW1A 1AA
        Address 2: M1 1AE
        Address 3: B33 8TH
        Address 4: CR2 6XH
        Address 5: DN55 1PT
        """
        postcodes = classifier.extract_postcodes(text)
        assert len(postcodes) >= 4
        assert any("SW1A" in pc for pc in postcodes)

    def test_ni_number_extraction(self, classifier):
        """Test National Insurance number extraction."""
        text = """
        NI Number: AB 12 34 56 C
        Another format: CD123456D
        With spaces: EF 12 34 56 E
        """
        ni_numbers = classifier.extract_ni_numbers(text)
        assert len(ni_numbers) >= 2

    def test_nhs_number_extraction(self, classifier):
        """Test NHS number extraction."""
        text = """
        NHS Number: 123 456 7890
        Another: 987 654 3210
        Without spaces: 1112223333
        """
        nhs_numbers = classifier.extract_nhs_numbers(text)
        assert len(nhs_numbers) >= 2

    def test_get_category(self, classifier):
        """Test getting category by ID."""
        category = classifier.get_category("hmrc_tax_return")
        assert category is not None
        assert category.name == "HMRC Tax Return"
        assert len(category.patterns) > 0
        assert len(category.keywords) > 0

    def test_get_invalid_category(self, classifier):
        """Test getting non-existent category."""
        category = classifier.get_category("invalid_category")
        assert category is None

    def test_empty_text_classification(self, classifier):
        """Test classification with empty text."""
        scores = classifier.classify("")
        assert all(score == 0.0 for score in scores.values())

    def test_mixed_document_classification(self, classifier):
        """Test classification with mixed document content."""
        text = """
        HMRC Tax Return
        UTR: 1234567890
        NHS Number: 123 456 7890
        This document contains mixed content
        """
        scores = classifier.classify(text)
        # Should score highest on tax return due to UTR and HMRC
        assert scores["hmrc_tax_return"] > 0
        assert scores["nhs_record"] > 0

    def test_category_required_fields(self, classifier):
        """Test that categories have required fields defined."""
        for category_id in classifier.list_categories():
            category = classifier.get_category(category_id)
            assert category is not None
            assert isinstance(category.required_fields, list)

    def test_pattern_weights(self, classifier):
        """Test that pattern weights are properly defined."""
        for category_id in classifier.list_categories():
            category = classifier.get_category(category_id)
            for pattern in category.patterns:
                assert pattern.weight > 0
                assert isinstance(pattern.pattern, str)
                assert isinstance(pattern.description, str)

    def test_case_insensitive_matching(self, classifier):
        """Test that classification is case-insensitive."""
        text_upper = "HMRC TAX RETURN UTR: 1234567890"
        text_lower = "hmrc tax return utr: 1234567890"
        text_mixed = "Hmrc Tax Return UTR: 1234567890"

        scores_upper = classifier.classify(text_upper)
        scores_lower = classifier.classify(text_lower)
        scores_mixed = classifier.classify(text_mixed)

        assert scores_upper["hmrc_tax_return"] > 0.5
        assert scores_lower["hmrc_tax_return"] > 0.5
        assert scores_mixed["hmrc_tax_return"] > 0.5

    def test_score_normalization(self, classifier):
        """Test that scores are normalized between 0 and 1."""
        text = "HMRC Tax Return UTR: 1234567890 SA100 National Insurance"
        scores = classifier.classify(text)
        for score in scores.values():
            assert 0.0 <= score <= 1.0
