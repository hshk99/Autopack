"""Dry-run models.

Defines data structures for dry-run results, approvals, and execution.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class DryRunStatus(str, Enum):
    """Status of a dry-run result."""

    PENDING = "pending"  # Dry-run created, awaiting approval
    APPROVED = "approved"  # Approved for execution
    EXECUTED = "executed"  # Successfully executed
    REJECTED = "rejected"  # Rejected by operator
    EXPIRED = "expired"  # Approval window expired
    HASH_MISMATCH = "hash_mismatch"  # Execution payload didn't match


@dataclass
class PredictedSideEffect:
    """A predicted side effect of an action."""

    effect_type: str  # e.g., "create", "update", "delete", "publish"
    target: str  # e.g., "youtube:video", "etsy:listing"
    description: str
    reversible: bool = True
    estimated_cost: Optional[float] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "effect_type": self.effect_type,
            "target": self.target,
            "description": self.description,
            "reversible": self.reversible,
            "estimated_cost": self.estimated_cost,
            "metadata": self.metadata,
        }


@dataclass
class DryRunResult:
    """Result of a dry-run execution.

    Contains the fully-rendered payload and predicted side effects
    without actually executing the action.
    """

    dry_run_id: str
    provider: str
    action: str
    payload: dict
    payload_hash: str
    predicted_effects: list[PredictedSideEffect]
    created_at: datetime
    status: DryRunStatus = DryRunStatus.PENDING
    validation_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    estimated_duration_seconds: Optional[float] = None
    requires_confirmation: bool = True
    run_id: Optional[str] = None
    phase_number: Optional[int] = None

    @staticmethod
    def compute_payload_hash(payload: dict) -> str:
        """Compute canonical SHA-256 hash of payload."""
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def is_valid(self) -> bool:
        """Check if dry-run result is valid for execution."""
        return len(self.validation_errors) == 0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "dry_run_id": self.dry_run_id,
            "provider": self.provider,
            "action": self.action,
            "payload": self.payload,
            "payload_hash": self.payload_hash,
            "predicted_effects": [e.to_dict() for e in self.predicted_effects],
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
            "validation_errors": self.validation_errors,
            "warnings": self.warnings,
            "estimated_duration_seconds": self.estimated_duration_seconds,
            "requires_confirmation": self.requires_confirmation,
            "run_id": self.run_id,
            "phase_number": self.phase_number,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DryRunResult":
        """Create from dictionary."""
        return cls(
            dry_run_id=data["dry_run_id"],
            provider=data["provider"],
            action=data["action"],
            payload=data["payload"],
            payload_hash=data["payload_hash"],
            predicted_effects=[PredictedSideEffect(**e) for e in data.get("predicted_effects", [])],
            created_at=datetime.fromisoformat(data["created_at"]),
            status=DryRunStatus(data.get("status", "pending")),
            validation_errors=data.get("validation_errors", []),
            warnings=data.get("warnings", []),
            estimated_duration_seconds=data.get("estimated_duration_seconds"),
            requires_confirmation=data.get("requires_confirmation", True),
            run_id=data.get("run_id"),
            phase_number=data.get("phase_number"),
        )


@dataclass
class DryRunApproval:
    """Approval record for a dry-run result."""

    approval_id: str
    dry_run_id: str
    approved_payload_hash: str
    approved_by: str
    approved_at: datetime
    notes: str = ""
    expires_at: Optional[datetime] = None
    execution_window_hours: int = 24

    def is_expired(self, as_of: Optional[datetime] = None) -> bool:
        """Check if approval has expired."""
        if self.expires_at is None:
            return False
        now = as_of or datetime.now(timezone.utc)
        return now > self.expires_at

    def matches_payload(self, payload_hash: str) -> bool:
        """Check if payload hash matches approved hash."""
        return self.approved_payload_hash == payload_hash

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "approval_id": self.approval_id,
            "dry_run_id": self.dry_run_id,
            "approved_payload_hash": self.approved_payload_hash,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat(),
            "notes": self.notes,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "execution_window_hours": self.execution_window_hours,
        }


@dataclass
class ExecutionResult:
    """Result of executing an approved dry-run."""

    execution_id: str
    dry_run_id: str
    approval_id: str
    executed_at: datetime
    success: bool
    response_summary: str = ""
    error_message: Optional[str] = None
    actual_effects: list[dict] = field(default_factory=list)
    duration_seconds: Optional[float] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "execution_id": self.execution_id,
            "dry_run_id": self.dry_run_id,
            "approval_id": self.approval_id,
            "executed_at": self.executed_at.isoformat(),
            "success": self.success,
            "response_summary": self.response_summary,
            "error_message": self.error_message,
            "actual_effects": self.actual_effects,
            "duration_seconds": self.duration_seconds,
        }
