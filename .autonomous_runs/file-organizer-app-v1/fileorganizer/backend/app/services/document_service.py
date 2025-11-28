"""
Document Processing Service - Orchestrates upload and text extraction
"""
from pathlib import Path
from sqlalchemy.orm import Session
from app.models.document import Document, ProcessingStatus
from app.services.ocr_service import OCRService
import shutil
from app.core.config import settings


class DocumentService:
    def __init__(self, db: Session):
        self.db = db
        self.ocr_service = OCRService()
        self.upload_dir = Path("uploads")
        self.upload_dir.mkdir(exist_ok=True)

    def upload_document(self, filename: str, file_data: bytes) -> Document:
        """
        Save uploaded file and create database record
        """
        # Validate file size
        file_size = len(file_data)
        max_size_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        if file_size > max_size_bytes:
            raise ValueError(f"File too large: {file_size} bytes (max: {max_size_bytes})")

        # Validate file type
        file_type = Path(filename).suffix.lower()
        if file_type not in settings.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported file type: {file_type}")

        # Save file
        file_path = self.upload_dir / filename
        with open(file_path, "wb") as f:
            f.write(file_data)

        # Create database record
        document = Document(
            filename=filename,
            original_path=str(file_path),
            file_size=file_size,
            file_type=file_type,
            status=ProcessingStatus.PENDING
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)

        return document

    def process_document(self, document_id: int) -> Document:
        """
        Extract text from document using OCR
        """
        document = self.db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise ValueError(f"Document not found: {document_id}")

        try:
            # Update status
            document.status = ProcessingStatus.PROCESSING
            self.db.commit()

            # Extract text
            file_path = Path(document.original_path)
            extracted_text, confidence = self.ocr_service.extract_text(
                file_path,
                document.file_type
            )

            # Update document
            document.extracted_text = extracted_text
            document.ocr_confidence = confidence
            document.status = ProcessingStatus.COMPLETED
            self.db.commit()
            self.db.refresh(document)

            return document

        except Exception as e:
            document.status = ProcessingStatus.FAILED
            self.db.commit()
            raise Exception(f"Document processing failed: {str(e)}")

    def get_document(self, document_id: int) -> Document:
        """Get document by ID"""
        return self.db.query(Document).filter(Document.id == document_id).first()

    def list_documents(self) -> list[Document]:
        """List all documents"""
        return self.db.query(Document).all()
