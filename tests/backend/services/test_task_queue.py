"""
Tests for task queue service.
"""

import base64
from unittest.mock import Mock, patch

import pytest

from src.backend.services.task_queue import (
    ProcessingResult,
    get_task_status,
    queue_batch_processing,
)


@pytest.fixture
def mock_celery_task():
    """Mock Celery task."""
    with patch("src.backend.services.task_queue.process_file_task") as mock:
        mock_result = Mock()
        mock_result.id = "test-task-id"
        mock.apply_async.return_value = mock_result
        yield mock


def test_processing_result_model():
    """Test ProcessingResult model."""
    result = ProcessingResult(
        file_id="file-123",
        filename="test.jpg",
        ocr_text="Sample text",
        classification={"type": "invoice"},
        confidence=0.95,
        processing_time=1.5,
    )

    assert result.file_id == "file-123"
    assert result.filename == "test.jpg"
    assert result.ocr_text == "Sample text"
    assert result.classification == {"type": "invoice"}
    assert result.confidence == 0.95
    assert result.processing_time == 1.5
    assert result.error is None


def test_processing_result_with_error():
    """Test ProcessingResult model with error."""
    result = ProcessingResult(
        file_id="file-123",
        filename="test.jpg",
        processing_time=0.5,
        error="Processing failed",
    )

    assert result.error == "Processing failed"
    assert result.ocr_text is None
    assert result.classification is None


def test_queue_batch_processing(mock_celery_task):
    """Test queuing a file for batch processing."""
    content = b"test file content"
    task_id = queue_batch_processing(
        batch_id="batch-123",
        file_id="file-456",
        job_id="job-789",
        filename="test.jpg",
        content=content,
        mime_type="image/jpeg",
    )

    assert task_id == "test-task-id"
    mock_celery_task.apply_async.assert_called_once()

    # Verify the task was called with correct arguments
    call_args = mock_celery_task.apply_async.call_args
    args = call_args[1]["args"]

    assert args[0] == "batch-123"  # batch_id
    assert args[1] == "file-456"  # file_id
    assert args[2] == "job-789"  # job_id
    assert args[3] == "test.jpg"  # filename
    assert base64.b64decode(args[4]) == content  # content_base64
    assert args[5] == "image/jpeg"  # mime_type


def test_get_task_status_pending():
    """Test getting status of a pending task."""
    with patch("src.backend.services.task_queue.AsyncResult") as mock_result:
        mock_result.return_value.state = "PENDING"

        status = get_task_status("task-123")

        assert status["task_id"] == "task-123"
        assert status["status"] == "queued"
        assert status["result"] is None
        assert status["error"] is None


def test_perform_ocr_placeholder():
    """Test OCR placeholder function."""
    from src.backend.services.task_queue import perform_ocr

    result = perform_ocr(b"test content", "image/jpeg")
    assert isinstance(result, str)
    assert len(result) > 0


def test_classify_document_placeholder():
    """Test classification placeholder function."""
    from src.backend.services.task_queue import classify_document

    result = classify_document("Sample text", "test.jpg")
    assert isinstance(result, dict)
    assert "classification" in result
    assert "confidence" in result
