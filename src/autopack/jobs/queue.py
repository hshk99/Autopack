"""
Job Queue - Simple in-memory job queue with persistence support.

BUILD-189 Phase 5 Skeleton - Minimal implementation for bootstrap.
Future: Add SQLite/PostgreSQL persistence, Redis backend, etc.
"""

from __future__ import annotations

import heapq
import uuid
from datetime import datetime
from threading import Lock
from typing import Optional

from .models import Job, JobPriority, JobStatus


class JobQueue:
    """
    Simple priority-based job queue.

    Features:
    - Priority ordering (CRITICAL > HIGH > NORMAL > LOW)
    - Thread-safe operations
    - Basic persistence hooks (implement in subclass)
    """

    def __init__(self):
        self._queue: list[tuple[int, float, Job]] = []  # (priority, timestamp, job)
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()

    def enqueue(
        self,
        name: str,
        handler: str,
        args: Optional[dict] = None,
        priority: JobPriority = JobPriority.NORMAL,
        max_retries: int = 3,
    ) -> Job:
        """Add a job to the queue."""
        job = Job(
            id=str(uuid.uuid4()),
            name=name,
            handler=handler,
            args=args or {},
            priority=priority,
            max_retries=max_retries,
        )

        with self._lock:
            self._jobs[job.id] = job
            # Use negative priority for max-heap behavior (higher priority = lower number)
            heapq.heappush(
                self._queue,
                (-priority.value, job.created_at.timestamp(), job),
            )

        return job

    def dequeue(self) -> Optional[Job]:
        """Get the next job from the queue."""
        with self._lock:
            while self._queue:
                _, _, job = heapq.heappop(self._queue)
                if job.status == JobStatus.PENDING:
                    job.status = JobStatus.RUNNING
                    job.started_at = datetime.now()
                    return job
            return None

    def get(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    def complete(self, job_id: str, result: Optional[dict] = None) -> None:
        """Mark a job as completed."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.now()
                job.result = result

    def fail(self, job_id: str, error: str) -> None:
        """Mark a job as failed."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.error_message = error
                if job.retry_count < job.max_retries:
                    job.retry_count += 1
                    job.status = JobStatus.RETRYING
                    # Re-queue for retry
                    heapq.heappush(
                        self._queue,
                        (-job.priority.value, datetime.now().timestamp(), job),
                    )
                else:
                    job.status = JobStatus.FAILED
                    job.completed_at = datetime.now()

    def cancel(self, job_id: str) -> bool:
        """Cancel a pending job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status == JobStatus.PENDING:
                job.status = JobStatus.CANCELLED
                return True
            return False

    def checkpoint(self, job_id: str, data: dict) -> None:
        """Save a checkpoint for resumability."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.checkpoint = data

    def pending_count(self) -> int:
        """Count of pending jobs."""
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status == JobStatus.PENDING)

    def running_count(self) -> int:
        """Count of running jobs."""
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status == JobStatus.RUNNING)
