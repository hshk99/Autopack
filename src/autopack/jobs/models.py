"""
Job Models - Data structures for job management.

BUILD-189 Phase 5 Skeleton.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class JobStatus(Enum):
    """Status of a job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class JobPriority(Enum):
    """Priority levels for jobs."""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Job:
    """Represents a background job."""

    id: str
    name: str
    handler: str  # Module.function path
    args: dict[str, Any] = field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    priority: JobPriority = JobPriority.NORMAL
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    checkpoint: Optional[dict[str, Any]] = None  # For resumability
    parent_job_id: Optional[str] = None  # For job hierarchies

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "handler": self.handler,
            "args": self.args,
            "status": self.status.value,
            "priority": self.priority.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error_message": self.error_message,
            "result": self.result,
            "checkpoint": self.checkpoint,
            "parent_job_id": self.parent_job_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            handler=data["handler"],
            args=data.get("args", {}),
            status=JobStatus(data.get("status", "pending")),
            priority=JobPriority(data.get("priority", 1)),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else datetime.now()
            ),
            started_at=(
                datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None
            ),
            completed_at=(
                datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
            ),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            error_message=data.get("error_message"),
            result=data.get("result"),
            checkpoint=data.get("checkpoint"),
            parent_job_id=data.get("parent_job_id"),
        )
