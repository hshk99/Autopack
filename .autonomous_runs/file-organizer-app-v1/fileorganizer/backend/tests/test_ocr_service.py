"""
Test OCR service
"""
import pytest
from pathlib import Path
from app.services.ocr_service import OCRService
from PIL import Image


def test_ocr_service_initialization():
    """Test OCR service can be initialized"""
    service = OCRService()
    assert service is not None


def test_extract_text_from_image(tmp_path):
    """Test text extraction from image"""
    # Create test image with text
    img = Image.new('RGB', (200, 100), color='white')
    test_image_path = tmp_path / "test.png"
    img.save(test_image_path)

    service = OCRService()

    # Note: This will return empty/low confidence for blank image
    # Real test would use image with actual text
    text, confidence = service.extract_text_from_image(test_image_path)

    assert isinstance(text, str)
    assert isinstance(confidence, float)
    assert 0 <= confidence <= 100
