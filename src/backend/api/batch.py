"""
Batch upload API endpoint for processing multiple files.

This module provides endpoints for uploading multiple files for batch processing,
queuing them for OCR and classification, and tracking job status.
"""

from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from ..services.task_queue import queue_batch_processing
from ..services.file_validator import validate_file


router = APIRouter(prefix="/api/v1/batch", tags=["batch"])


class FileJobInfo(BaseModel):
    """Information about a single file job in a batch."""

    file_id: str = Field(..., description="Unique identifier for the file")
    filename: str = Field(..., description="Original filename")
    job_id: str = Field(..., description="Job ID for tracking processing status")
    status: str = Field(default="queued", description="Current processing status")


class BatchUploadResponse(BaseModel):
    """Response model for batch upload endpoint."""

    batch_id: str = Field(..., description="Unique identifier for the batch")
    total_files: int = Field(..., description="Total number of files in batch")
    accepted_files: int = Field(..., description="Number of files accepted for processing")
    rejected_files: int = Field(..., description="Number of files rejected")
    jobs: List[FileJobInfo] = Field(..., description="List of job information for each file")
    errors: List[dict] = Field(default_factory=list, description="List of errors for rejected files")


class JobStatus(BaseModel):
    """Status information for a processing job."""

    job_id: str = Field(..., description="Job identifier")
    status: str = Field(..., description="Current status: queued, processing, completed, failed")
    progress: Optional[int] = Field(None, description="Progress percentage (0-100)")
    result: Optional[dict] = Field(None, description="Processing result if completed")
    error: Optional[str] = Field(None, description="Error message if failed")


class BatchStatusResponse(BaseModel):
    """Response model for batch status endpoint."""

    batch_id: str = Field(..., description="Batch identifier")
    total_jobs: int = Field(..., description="Total number of jobs in batch")
    completed: int = Field(..., description="Number of completed jobs")
    failed: int = Field(..., description="Number of failed jobs")
    processing: int = Field(..., description="Number of jobs currently processing")
    queued: int = Field(..., description="Number of jobs still queued")
    jobs: List[JobStatus] = Field(..., description="Status of each job")


# Supported file types for batch processing
SUPPORTED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/bmp",
    "application/pdf",
}

# Maximum file size: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024

# Maximum number of files per batch
MAX_BATCH_SIZE = 50


@router.post(
    "/upload",
    response_model=BatchUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload multiple files for batch processing",
    description="Upload multiple files for OCR and classification. Files are queued for parallel processing.",
)
async def upload_batch(
    files: List[UploadFile] = File(..., description="List of files to process")
) -> BatchUploadResponse:
    """
    Upload multiple files for batch processing.

    Args:
        files: List of uploaded files

    Returns:
        BatchUploadResponse with batch ID and job information

    Raises:
        HTTPException: If batch size exceeds limit or no valid files provided
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided",
        )

    if len(files) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Batch size exceeds maximum of {MAX_BATCH_SIZE} files",
        )

    batch_id = str(uuid4())
    jobs: List[FileJobInfo] = []
    errors: List[dict] = []

    for file in files:
        try:
            # Read file content
            content = await file.read()
            await file.seek(0)

            # Validate file
            validation_result = validate_file(
                content=content,
                filename=file.filename or "unknown",
                max_size=MAX_FILE_SIZE,
                allowed_types=SUPPORTED_MIME_TYPES,
            )

            if not validation_result["valid"]:
                errors.append({
                    "filename": file.filename,
                    "error": validation_result["error"],
                })
                continue

            # Generate unique IDs
            file_id = str(uuid4())
            job_id = str(uuid4())

            # Queue for processing
            queue_batch_processing(
                batch_id=batch_id,
                file_id=file_id,
                job_id=job_id,
                filename=file.filename or "unknown",
                content=content,
                mime_type=validation_result["mime_type"],
            )

            jobs.append(
                FileJobInfo(
                    file_id=file_id,
                    filename=file.filename or "unknown",
                    job_id=job_id,
                    status="queued",
                )
            )

        except Exception as e:
            errors.append({
                "filename": file.filename,
                "error": f"Unexpected error: {str(e)}",
            })

    if not jobs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid files to process",
        )

    return BatchUploadResponse(
        batch_id=batch_id,
        total_files=len(files),
        accepted_files=len(jobs),
        rejected_files=len(errors),
        jobs=jobs,
        errors=errors,
    )


@router.get(
    "/{batch_id}/status",
    response_model=BatchStatusResponse,
    summary="Get batch processing status",
    description="Retrieve the current status of all jobs in a batch",
)
async def get_batch_status(batch_id: str) -> BatchStatusResponse:
    """Get the status of a batch processing job."""
    # Implementation will be added with task queue integration
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)
