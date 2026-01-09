"""Database models for external action ledger.

Implements gap analysis items 6.1 (durable idempotency) and 6.9 (external action ledger):
- Append-only ledger keyed by idempotency_key
- Stores payload_hash, provider, action, approval reference
- Tracks status, timestamps, retry count
- Redacted response summary (never raw tokens)
"""

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    JSON,
    Index,
)
from sqlalchemy import Enum as SQLEnum

from ..database import Base


class ExternalActionStatus(str, Enum):
    """Status of an external action."""

    PENDING = "PENDING"  # Created but not yet executed
    APPROVED = "APPROVED"  # Approval received, ready to execute
    EXECUTING = "EXECUTING"  # Currently executing
    COMPLETED = "COMPLETED"  # Successfully completed
    FAILED = "FAILED"  # Failed after all retries
    CANCELLED = "CANCELLED"  # Cancelled by operator


class ExternalAction(Base):
    """External action ledger entry.

    This table implements exactly-once intent tracking for external side effects.
    Keyed by idempotency_key to prevent duplicate actions across restarts.

    Fields match gap analysis 6.9 requirements:
    - idempotency_key: unique identifier for this action intent
    - payload_hash: SHA-256 of canonical normalized request
    - provider: external service (youtube, etsy, shopify, trading, etc.)
    - action: specific action type (publish, list, update, trade, etc.)
    - approval_id: reference to approval record (if applicable)
    - status: current state of the action
    - timestamps: created_at, started_at, completed_at
    - retry_count: number of execution attempts
    - response_summary: redacted response (no raw tokens)
    """

    __tablename__ = "external_actions"

    # Primary key is the idempotency key itself
    idempotency_key = Column(String(255), primary_key=True, index=True)

    # Request identity
    payload_hash = Column(String(64), nullable=False, index=True)  # SHA-256 hex
    provider = Column(String(50), nullable=False, index=True)  # youtube, etsy, shopify, trading
    action = Column(String(50), nullable=False, index=True)  # publish, list, update, trade

    # Context
    run_id = Column(String(255), nullable=True, index=True)  # Link to run if applicable
    phase_number = Column(Integer, nullable=True)  # Phase that triggered this action
    approval_id = Column(String(255), nullable=True, index=True)  # Reference to approval record

    # Status and lifecycle
    status = Column(
        SQLEnum(ExternalActionStatus),
        nullable=False,
        default=ExternalActionStatus.PENDING,
        index=True,
    )
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    started_at = Column(DateTime, nullable=True)  # When execution began
    completed_at = Column(DateTime, nullable=True)  # When execution finished (success or fail)

    # Execution tracking
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)

    # Request/response (redacted - never contains raw tokens)
    request_summary = Column(Text, nullable=True)  # Human-readable request summary
    response_summary = Column(Text, nullable=True)  # Redacted response summary
    error_message = Column(Text, nullable=True)  # Error message if failed

    # Extra data (extensible JSON for provider-specific data)
    # Note: "metadata" is reserved in SQLAlchemy, so we use "extra_data"
    extra_data = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_external_actions_provider_action", "provider", "action"),
        Index("ix_external_actions_run_phase", "run_id", "phase_number"),
        Index("ix_external_actions_status_created", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ExternalAction(key={self.idempotency_key}, "
            f"provider={self.provider}, action={self.action}, "
            f"status={self.status})>"
        )

    def is_complete(self) -> bool:
        """Check if action has reached a terminal state."""
        return self.status in (
            ExternalActionStatus.COMPLETED,
            ExternalActionStatus.FAILED,
            ExternalActionStatus.CANCELLED,
        )

    def can_execute(self) -> bool:
        """Check if action is eligible for execution."""
        return self.status in (
            ExternalActionStatus.APPROVED,
            ExternalActionStatus.PENDING,  # If no approval required
        )

    def can_retry(self) -> bool:
        """Check if action can be retried."""
        return self.status == ExternalActionStatus.FAILED and self.retry_count < self.max_retries
