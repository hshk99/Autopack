"""
Document model for storing processed documents with metadata.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, JSON
from sqlalchemy.sql import func

from ..database import Base


class Document(Base):
    """
    Document model for storing processed documents.

    Attributes:
        id: Primary key
        filename: Original filename
        document_type: Type of document (invoice, receipt, contract, etc.)
        pack_name: Name of the pack this document belongs to
        confidence_score: Confidence score of extraction (0.0 to 1.0)
        extracted_text: Full extracted text content
        document_metadata: Additional metadata as JSON
        created_at: Timestamp when document was created
        updated_at: Timestamp when document was last updated
    """

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(500), nullable=False, index=True)
    document_type = Column(String(100), index=True)
    pack_name = Column(String(200), index=True)
    confidence_score = Column(Float, index=True)
    extracted_text = Column(Text)
    document_metadata = Column("metadata", JSON)  # "metadata" is reserved in SQLAlchemy
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True
    )
