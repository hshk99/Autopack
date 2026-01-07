"""
Job Scheduling and Resumable Pipelines (BUILD-189 Phase 5 Skeleton)

This module provides durable background job execution:
- Job queue with persistence
- Retry with configurable policies
- Checkpointing for resumability
- Worker process management

Goals:
- Don't rely on a single long-running process
- Support graceful shutdown and restart
- Enable pipeline resumption from last checkpoint
"""

from .models import Job, JobStatus
from .queue import JobQueue

__all__ = ["Job", "JobStatus", "JobQueue"]
