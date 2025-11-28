"""
Test classification service
"""
import pytest
from app.services.classification_service import ClassificationService
from app.models.category import Category


def test_classification_service_initialization():
    """Test classification service can be initialized"""
    service = ClassificationService()
    assert service is not None


def test_build_classification_prompt():
    """Test prompt building"""
    service = ClassificationService()

    categories = [
        Category(id=1, name="Income", description="Income documents", scenario_pack_id=1),
        Category(id=2, name="Expenses", description="Expense documents", scenario_pack_id=1),
    ]

    prompt = service._build_classification_prompt("Test document text", categories)

    assert "Income" in prompt
    assert "Expenses" in prompt
    assert "Test document text" in prompt


def test_parse_classification_result():
    """Test result parsing"""
    service = ClassificationService()

    categories = [
        Category(id=1, name="Income", description="Income documents", scenario_pack_id=1),
        Category(id=2, name="Expenses", description="Expense documents", scenario_pack_id=1),
    ]

    result_text = "Category: Income, Confidence: 85"
    category_id, confidence = service._parse_classification_result(result_text, categories)

    assert category_id == 1
    assert confidence == 85.0
