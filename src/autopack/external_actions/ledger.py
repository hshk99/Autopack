"""External action ledger service.

Provides durable idempotency and exactly-once semantics for external side effects.
Implements gap analysis items 6.1 and 6.9.

Key features:
- Check-before-execute: prevents duplicate actions on restart
- Payload hash verification: ensures approved payload matches execution payload
- Audit trail: queryable history of all external actions
- Artifact export: run-local JSON export for offline analysis
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from .models import ExternalAction, ExternalActionStatus

logger = logging.getLogger(__name__)


class ExternalActionLedger:
    """Service for managing external action ledger.

    Usage:
        ledger = ExternalActionLedger(db_session)

        # Check if action already completed (idempotency check)
        if ledger.is_completed("publish-video-123"):
            return ledger.get_action("publish-video-123").response_summary

        # Register new action intent
        action = ledger.register_action(
            idempotency_key="publish-video-123",
            provider="youtube",
            action="publish",
            payload={"title": "My Video", ...},
            run_id="run-abc",
        )

        # Mark as approved (with approval reference)
        ledger.approve_action("publish-video-123", approval_id="approval-xyz")

        # Execute and record outcome
        try:
            result = execute_youtube_publish(...)
            ledger.complete_action("publish-video-123", response_summary=redact(result))
        except Exception as e:
            ledger.fail_action("publish-video-123", error_message=str(e))
    """

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def compute_payload_hash(payload: dict) -> str:
        """Compute canonical SHA-256 hash of payload.

        Normalizes JSON to ensure consistent hashing regardless of key order.
        """
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def get_action(self, idempotency_key: str) -> Optional[ExternalAction]:
        """Get an external action by idempotency key."""
        return (
            self.db.query(ExternalAction)
            .filter(ExternalAction.idempotency_key == idempotency_key)
            .first()
        )

    def is_completed(self, idempotency_key: str) -> bool:
        """Check if an action with this key has already completed."""
        action = self.get_action(idempotency_key)
        return action is not None and action.status == ExternalActionStatus.COMPLETED

    def is_in_progress(self, idempotency_key: str) -> bool:
        """Check if an action is currently executing."""
        action = self.get_action(idempotency_key)
        return action is not None and action.status == ExternalActionStatus.EXECUTING

    def register_action(
        self,
        idempotency_key: str,
        provider: str,
        action: str,
        payload: dict,
        run_id: Optional[str] = None,
        phase_number: Optional[int] = None,
        request_summary: Optional[str] = None,
        max_retries: int = 3,
        metadata: Optional[dict] = None,
    ) -> ExternalAction:
        """Register a new external action intent.

        If an action with this idempotency_key already exists, returns the existing action.
        This is the idempotency guarantee: calling register twice with the same key
        does not create a duplicate.

        Args:
            idempotency_key: Unique identifier for this action intent
            provider: External service (youtube, etsy, shopify, trading)
            action: Action type (publish, list, update, trade)
            payload: Request payload (will be hashed)
            run_id: Associated run ID (optional)
            phase_number: Phase that triggered this action (optional)
            request_summary: Human-readable summary (optional)
            max_retries: Maximum retry attempts
            metadata: Additional provider-specific data

        Returns:
            ExternalAction record (existing or newly created)
        """
        # Check for existing action with this key
        existing = self.get_action(idempotency_key)
        if existing is not None:
            logger.info(
                f"External action {idempotency_key} already exists with status {existing.status}"
            )
            return existing

        # Compute payload hash
        payload_hash = self.compute_payload_hash(payload)

        # Create new action
        new_action = ExternalAction(
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            provider=provider,
            action=action,
            run_id=run_id,
            phase_number=phase_number,
            request_summary=request_summary or json.dumps(payload, indent=2)[:1000],
            max_retries=max_retries,
            extra_data=metadata,
            status=ExternalActionStatus.PENDING,
        )

        self.db.add(new_action)
        self.db.commit()
        self.db.refresh(new_action)

        logger.info(
            f"Registered external action: {idempotency_key} "
            f"(provider={provider}, action={action}, hash={payload_hash[:16]}...)"
        )

        return new_action

    def approve_action(
        self,
        idempotency_key: str,
        approval_id: str,
        payload_hash: Optional[str] = None,
    ) -> ExternalAction:
        """Mark an action as approved and ready for execution.

        Args:
            idempotency_key: Action to approve
            approval_id: Reference to approval record
            payload_hash: Optional hash to verify (ensures approved payload matches)

        Returns:
            Updated action record

        Raises:
            ValueError: If action not found or payload hash mismatch
        """
        action = self.get_action(idempotency_key)
        if action is None:
            raise ValueError(f"External action not found: {idempotency_key}")

        # Verify payload hash if provided (ensures approval matches execution)
        if payload_hash is not None and action.payload_hash != payload_hash:
            raise ValueError(
                f"Payload hash mismatch for {idempotency_key}: "
                f"expected {action.payload_hash}, got {payload_hash}"
            )

        action.approval_id = approval_id
        action.status = ExternalActionStatus.APPROVED

        self.db.commit()
        self.db.refresh(action)

        logger.info(f"Approved external action: {idempotency_key} (approval={approval_id})")

        return action

    def start_execution(self, idempotency_key: str) -> ExternalAction:
        """Mark an action as currently executing.

        Returns:
            Updated action record

        Raises:
            ValueError: If action not found or not in executable state
        """
        action = self.get_action(idempotency_key)
        if action is None:
            raise ValueError(f"External action not found: {idempotency_key}")

        if not action.can_execute():
            raise ValueError(
                f"Action {idempotency_key} cannot be executed (status={action.status})"
            )

        action.status = ExternalActionStatus.EXECUTING
        action.started_at = datetime.now(timezone.utc)
        action.retry_count += 1

        self.db.commit()
        self.db.refresh(action)

        logger.info(
            f"Started execution: {idempotency_key} (attempt {action.retry_count}/{action.max_retries})"
        )

        return action

    def complete_action(
        self,
        idempotency_key: str,
        response_summary: str,
        metadata_update: Optional[dict] = None,
    ) -> ExternalAction:
        """Mark an action as successfully completed.

        Args:
            idempotency_key: Action that completed
            response_summary: Redacted summary of response (no raw tokens)
            metadata_update: Additional metadata to merge

        Returns:
            Updated action record
        """
        action = self.get_action(idempotency_key)
        if action is None:
            raise ValueError(f"External action not found: {idempotency_key}")

        action.status = ExternalActionStatus.COMPLETED
        action.completed_at = datetime.now(timezone.utc)
        action.response_summary = response_summary

        if metadata_update:
            action.extra_data = {**(action.extra_data or {}), **metadata_update}

        self.db.commit()
        self.db.refresh(action)

        logger.info(f"Completed external action: {idempotency_key}")

        return action

    def fail_action(
        self,
        idempotency_key: str,
        error_message: str,
    ) -> ExternalAction:
        """Mark an action as failed.

        If retries remain, the action can be retried via start_execution().

        Args:
            idempotency_key: Action that failed
            error_message: Error description

        Returns:
            Updated action record
        """
        action = self.get_action(idempotency_key)
        if action is None:
            raise ValueError(f"External action not found: {idempotency_key}")

        action.status = ExternalActionStatus.FAILED
        action.completed_at = datetime.now(timezone.utc)
        action.error_message = error_message

        self.db.commit()
        self.db.refresh(action)

        logger.warning(
            f"Failed external action: {idempotency_key} "
            f"(retries={action.retry_count}/{action.max_retries}, error={error_message[:100]})"
        )

        return action

    def cancel_action(
        self, idempotency_key: str, reason: str = "cancelled by operator"
    ) -> ExternalAction:
        """Cancel a pending or approved action.

        Args:
            idempotency_key: Action to cancel
            reason: Cancellation reason

        Returns:
            Updated action record
        """
        action = self.get_action(idempotency_key)
        if action is None:
            raise ValueError(f"External action not found: {idempotency_key}")

        if action.is_complete():
            raise ValueError(
                f"Cannot cancel completed action: {idempotency_key} (status={action.status})"
            )

        action.status = ExternalActionStatus.CANCELLED
        action.completed_at = datetime.now(timezone.utc)
        action.error_message = reason

        self.db.commit()
        self.db.refresh(action)

        logger.info(f"Cancelled external action: {idempotency_key} ({reason})")

        return action

    def query_actions(
        self,
        provider: Optional[str] = None,
        action_type: Optional[str] = None,
        status: Optional[ExternalActionStatus] = None,
        run_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[ExternalAction]:
        """Query external actions with filters.

        Args:
            provider: Filter by provider
            action_type: Filter by action type
            status: Filter by status
            run_id: Filter by run ID
            limit: Maximum results

        Returns:
            List of matching actions
        """
        query = self.db.query(ExternalAction)

        if provider:
            query = query.filter(ExternalAction.provider == provider)
        if action_type:
            query = query.filter(ExternalAction.action == action_type)
        if status:
            query = query.filter(ExternalAction.status == status)
        if run_id:
            query = query.filter(ExternalAction.run_id == run_id)

        return query.order_by(ExternalAction.created_at.desc()).limit(limit).all()

    def export_run_actions(self, run_id: str, output_dir: Path) -> Path:
        """Export all actions for a run to a JSON artifact.

        Args:
            run_id: Run to export
            output_dir: Directory for artifact

        Returns:
            Path to exported JSON file
        """
        actions = self.query_actions(run_id=run_id, limit=10000)

        export_data = {
            "run_id": run_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "action_count": len(actions),
            "actions": [
                {
                    "idempotency_key": a.idempotency_key,
                    "provider": a.provider,
                    "action": a.action,
                    "payload_hash": a.payload_hash,
                    "approval_id": a.approval_id,
                    "status": a.status.value if a.status else None,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "started_at": a.started_at.isoformat() if a.started_at else None,
                    "completed_at": a.completed_at.isoformat() if a.completed_at else None,
                    "retry_count": a.retry_count,
                    "request_summary": a.request_summary,
                    "response_summary": a.response_summary,
                    "error_message": a.error_message,
                }
                for a in actions
            ],
        }

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"external_actions_{run_id}.json"
        output_path.write_text(json.dumps(export_data, indent=2), encoding="utf-8")

        logger.info(f"Exported {len(actions)} actions to {output_path}")

        return output_path
