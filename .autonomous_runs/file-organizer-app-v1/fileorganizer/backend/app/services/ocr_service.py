"""
OCR Service - Tesseract + PyMuPDF text extraction
"""
import pytesseract
import fitz  # PyMuPDF
from PIL import Image
from pathlib import Path
from typing import Tuple
from app.core.config import settings


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

                    # Run Tesseract OCR
                    ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                    page_text = " ".join([
                        word for word, conf in zip(ocr_data['text'], ocr_data['conf'])
                        if int(conf) > 0
                    ])
                    full_text.append(page_text)

                    # Calculate average confidence
                    confidences = [int(c) for c in ocr_data['conf'] if int(c) > 0]
                    avg_conf = sum(confidences) / len(confidences) if confidences else 0
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
            ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

            # Extract text with confidence filtering
            text_parts = []
            confidences = []

            for word, conf in zip(ocr_data['text'], ocr_data['conf']):
                conf_int = int(conf)
                if conf_int > 0:
                    text_parts.append(word)
                    confidences.append(conf_int)

            extracted_text = " ".join(text_parts)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0

            return extracted_text, avg_confidence

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
