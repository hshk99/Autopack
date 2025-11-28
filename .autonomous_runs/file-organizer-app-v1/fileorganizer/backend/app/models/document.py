"""
Document model - Uploaded files and their processing state
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Enum
from sqlalchemy.sql import func
from app.db.session import Base
import enum


class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)  # bytes
    file_type = Column(String(50), nullable=False)  # .pdf, .jpg, etc.

    # Processing
    status = Column(Enum(ProcessingStatus), default=ProcessingStatus.PENDING)
    extracted_text = Column(Text, nullable=True)
    ocr_confidence = Column(Float, nullable=True)

    # Classification
    assigned_category_id = Column(Integer, nullable=True)
    classification_confidence = Column(Float, nullable=True)
    embedding_vector = Column(Text, nullable=True)  # JSON-serialized vector

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Document(id={self.id}, filename='{self.filename}', status='{self.status}')>"
