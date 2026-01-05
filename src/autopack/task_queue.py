"""Task queue for processing uploaded files."""

import uuid
from typing import Any
from fastapi import UploadFile
import logging

# Simulated task queue
task_queue = []

logger = logging.getLogger(__name__)


def queue_files_for_processing(file: UploadFile) -> str:
    """
    Queue a file for processing.

    Args:
        file: The uploaded file to process.

    Returns:
        A job ID for tracking the processing task.
    """
    job_id = str(uuid.uuid4())
    task = {"job_id": job_id, "file_name": file.filename, "status": "queued"}
    task_queue.append(task)

    # Simulate background processing
    logger.info(f"Queued file {file.filename} for processing with job ID {job_id}")
    process_file(task)

    return job_id


def process_file(task: Any):
    """
    Simulate file processing.

    Args:
        task: The task dictionary containing job details.
    """
    logger.info(f"Processing file {task['file_name']} with job ID {task['job_id']}")
    task["status"] = "completed"
