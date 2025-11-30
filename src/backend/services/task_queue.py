"""
Background task queue for parallel OCR and classification processing.

This module provides Celery-based task queue functionality for processing
uploaded files in parallel with OCR and classification.
"""

import logging
from typing import Any, Dict, Optional

from celery import Celery, Task
from celery.result import AsyncResult
from pydantic import BaseModel

from ..config import get_settings


logger = logging.getLogger(__name__)
settings = get_settings()


# Initialize Celery app
celery_app = Celery(
    "autopack",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes
    task_soft_time_limit=270,  # 4.5 minutes
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,
)


class ProcessingResult(BaseModel):
    """Result of file processing."""

    file_id: str
    filename: str
    ocr_text: Optional[str] = None
    classification: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    processing_time: float
    error: Optional[str] = None


@celery_app.task(bind=True, name="autopack.process_file")
def process_file_task(
    self: Task,
    batch_id: str,
    file_id: str,
    job_id: str,
    filename: str,
    content_base64: str,
    mime_type: str,
) -> Dict[str, Any]:
    """
    Process a single file with OCR and classification.

    Args:
        self: Celery task instance
        batch_id: Batch identifier
        file_id: File identifier
        job_id: Job identifier
        filename: Original filename
        content_base64: Base64-encoded file content
        mime_type: MIME type of the file

    Returns:
        Dictionary containing processing results
    """
    import base64
    import time

    start_time = time.time()

    try:
        # Update task state
        self.update_state(
            state="PROCESSING",
            meta={
                "batch_id": batch_id,
                "file_id": file_id,
                "filename": filename,
                "progress": 0,
            },
        )

        # Decode content
        content = base64.b64decode(content_base64)

        # Perform OCR
        self.update_state(state="PROCESSING", meta={"progress": 30})
        ocr_text = perform_ocr(content, mime_type)

        # Perform classification
        self.update_state(state="PROCESSING", meta={"progress": 70})
        classification_result = classify_document(ocr_text, filename)

        processing_time = time.time() - start_time

        result = ProcessingResult(
            file_id=file_id,
            filename=filename,
            ocr_text=ocr_text,
            classification=classification_result.get("classification"),
            confidence=classification_result.get("confidence"),
            processing_time=processing_time,
        )

        logger.info(
            f"Successfully processed file {filename} in batch {batch_id} "
            f"(job_id: {job_id}, time: {processing_time:.2f}s)"
        )

        return result.model_dump()

    except Exception as e:
        processing_time = time.time() - start_time
        error_msg = f"Error processing file {filename}: {str(e)}"
        logger.error(error_msg, exc_info=True)

        result = ProcessingResult(
            file_id=file_id,
            filename=filename,
            processing_time=processing_time,
            error=error_msg,
        )

        return result.model_dump()


def perform_ocr(content: bytes, mime_type: str) -> str:
    """
    Perform OCR on file content.

    Args:
        content: File content as bytes
        mime_type: MIME type of the file

    Returns:
        Extracted text from OCR
    """
    # TODO: Implement actual OCR using Tesseract or cloud service
    # This is a placeholder implementation
    logger.info(f"Performing OCR on {mime_type} file")
    return "Sample OCR text extracted from document"


def classify_document(text: str, filename: str) -> Dict[str, Any]:
    """
    Classify document based on OCR text.

    Args:
        text: OCR-extracted text
        filename: Original filename

    Returns:
        Classification result with confidence score
    """
    # TODO: Implement actual classification using ML model or LLM
    # This is a placeholder implementation
    logger.info(f"Classifying document: {filename}")
    return {
        "classification": "invoice",
        "confidence": 0.85,
        "metadata": {
            "detected_fields": ["date", "amount", "vendor"],
        },
    }


def queue_batch_processing(
    batch_id: str,
    file_id: str,
    job_id: str,
    filename: str,
    content: bytes,
    mime_type: str,
) -> str:
    """
    Queue a file for batch processing.

    Args:
        batch_id: Batch identifier
        file_id: File identifier
        job_id: Job identifier
        filename: Original filename
        content: File content as bytes
        mime_type: MIME type of the file

    Returns:
        Task ID for tracking
    """
    import base64

    content_base64 = base64.b64encode(content).decode("utf-8")

    task = process_file_task.apply_async(
        args=[batch_id, file_id, job_id, filename, content_base64, mime_type],
        task_id=job_id,
    )

    logger.info(f"Queued file {filename} for processing (job_id: {job_id})")
    return task.id


def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    Get the status of a task.

    Args:
        task_id: Task identifier

    Returns:
        Dictionary containing task status and result
    """
    result = AsyncResult(task_id, app=celery_app)

    response = {
        "task_id": task_id,
        "status": result.state,
        "result": None,
        "error": None,
    }

    if result.state == "PENDING":
        response["status"] = "queued"
    elif result.state == "PROCESSING":
        response["progress"] = result.info.get("progress", 0)
    elif result.state == "SUCCESS":
        response["status"] = "completed"
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["status"] = "failed"
        response["error"] = str(result.info)

    return response
