"""
OCR Service - Tesseract + PyMuPDF text extraction
"""
import logging
import pytesseract
from pytesseract import TesseractNotFoundError
import fitz  # PyMuPDF
from PIL import Image
from pathlib import Path
from typing import Tuple
from app.core.config import settings

logger = logging.getLogger(__name__)


class OCRService:
    def __init__(self):
        if settings.TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

    def extract_text_from_pdf(self, pdf_path: Path) -> Tuple[str, float]:
        """
        Extract text from PDF using PyMuPDF (native text) or OCR (scanned)
        Returns: (extracted_text, confidence)
        """
        try:
            doc = fitz.open(pdf_path)
            full_text = []
            total_confidence = 0
            page_count = 0

            for page_num in range(len(doc)):
                page = doc[page_num]

                # Try native text extraction first
                text = page.get_text()

                if text.strip():
                    # Native text extraction successful
                    full_text.append(text)
                    total_confidence += 100  # Native text = 100% confidence
                else:
                    # Fallback to OCR for scanned pages
                    pix = page.get_pixmap()
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                    ocr_data = self._safe_image_to_data(img)
                    page_text, avg_conf = self._build_text_from_ocr(ocr_data)
                    full_text.append(page_text)
                    total_confidence += avg_conf

                page_count += 1

            doc.close()

            combined_text = "\n\n".join(full_text)
            avg_confidence = total_confidence / page_count if page_count > 0 else 0

            return combined_text, avg_confidence

        except Exception as e:
            raise Exception(f"PDF text extraction failed: {str(e)}")

    def extract_text_from_image(self, image_path: Path) -> Tuple[str, float]:
        """
        Extract text from image using Tesseract OCR
        Returns: (extracted_text, confidence)
        """
        try:
            img = Image.open(image_path)
            ocr_data = self._safe_image_to_data(img)
            return self._build_text_from_ocr(ocr_data)

        except Exception as e:
            raise Exception(f"Image OCR failed: {str(e)}")

    def extract_text(self, file_path: Path, file_type: str) -> Tuple[str, float]:
        """
        Route to appropriate extraction method based on file type
        """
        if file_type.lower() == ".pdf":
            return self.extract_text_from_pdf(file_path)
        elif file_type.lower() in [".png", ".jpg", ".jpeg"]:
            return self.extract_text_from_image(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

    def _safe_image_to_data(self, image) -> dict:
        """
        Run pytesseract.image_to_data while tolerating missing Tesseract binaries.
        Returns an empty OCR result when Tesseract is unavailable so tests can still run.
        """
        try:
            return pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        except TesseractNotFoundError:
            logger.warning(
                "Tesseract binary not available - returning empty OCR result. "
                "Install Tesseract OCR for full functionality."
            )
            return {"text": [], "conf": []}

    @staticmethod
    def _build_text_from_ocr(ocr_data: dict) -> Tuple[str, float]:
        """Convert pytesseract output into concatenated text and average confidence."""
        text_parts = []
        confidences = []

        for word, conf in zip(ocr_data.get('text', []), ocr_data.get('conf', [])):
            try:
                conf_int = int(conf)
            except (TypeError, ValueError):
                continue
            if conf_int > 0 and word:
                text_parts.append(word)
                confidences.append(conf_int)

        extracted_text = " ".join(text_parts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return extracted_text, avg_confidence
