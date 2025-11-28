"""
Test document service
"""
import pytest
from app.services.document_service import DocumentService
from app.models.document import ProcessingStatus


def test_upload_document(db):
    """Test document upload"""
    service = DocumentService(db)

    # Create test file data
    test_filename = "test.pdf"
    test_data = b"fake pdf content"

    document = service.upload_document(test_filename, test_data)

    assert document.id is not None
    assert document.filename == test_filename
    assert document.status == ProcessingStatus.PENDING
    assert document.file_type == ".pdf"


def test_upload_document_size_limit(db):
    """Test file size validation"""
    service = DocumentService(db)

    # Create oversized file (> 50 MB)
    large_data = b"x" * (51 * 1024 * 1024)

    with pytest.raises(ValueError, match="File too large"):
        service.upload_document("large.pdf", large_data)


def test_upload_unsupported_format(db):
    """Test unsupported file type validation"""
    service = DocumentService(db)

    with pytest.raises(ValueError, match="Unsupported file type"):
        service.upload_document("test.exe", b"data")
