"""Dry-run executor service.

Manages dry-run creation, approval, and execution with hash verification.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from .models import (DryRunApproval, DryRunResult, DryRunStatus,
                     ExecutionResult, PredictedSideEffect)

logger = logging.getLogger(__name__)


# Type alias for action executors
ActionExecutor = Callable[[str, str, dict], dict]


class DryRunExecutor:
    """Service for managing dry-run execution flow.

    Usage:
        executor = DryRunExecutor(storage_dir=Path(".dry_runs"))

        # Create a dry-run
        result = executor.create_dry_run(
            provider="youtube",
            action="publish",
            payload={"title": "My Video", "description": "..."},
            predicted_effects=[
                PredictedSideEffect(
                    effect_type="create",
                    target="youtube:video",
                    description="Creates a new YouTube video",
                ),
            ],
        )

        # Approve the dry-run
        approval = executor.approve(result.dry_run_id, approved_by="admin")

        # Execute with hash verification
        execution = executor.execute(
            result.dry_run_id,
            approval.approval_id,
            payload=original_payload,  # Must match hash
            executor_fn=youtube_publish,
        )
    """

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        default_expiry_hours: int = 24,
    ):
        """Initialize the dry-run executor.

        Args:
            storage_dir: Directory for storing dry-run artifacts
            default_expiry_hours: Default approval expiry window
        """
        self.storage_dir = storage_dir or Path(".dry_runs")
        self.default_expiry_hours = default_expiry_hours
        self._dry_runs: dict[str, DryRunResult] = {}
        self._approvals: dict[str, DryRunApproval] = {}
        self._executions: dict[str, ExecutionResult] = {}

        # Load existing dry-runs
        self._load_state()

    def _load_state(self) -> None:
        """Load existing state from storage."""
        if not self.storage_dir.exists():
            return

        # Load dry-runs
        dry_runs_file = self.storage_dir / "dry_runs.json"
        if dry_runs_file.exists():
            try:
                data = json.loads(dry_runs_file.read_text(encoding="utf-8"))
                for dr_id, dr_data in data.items():
                    self._dry_runs[dr_id] = DryRunResult.from_dict(dr_data)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load dry-runs: {e}")

        # Load approvals
        approvals_file = self.storage_dir / "approvals.json"
        if approvals_file.exists():
            try:
                data = json.loads(approvals_file.read_text(encoding="utf-8"))
                for ap_id, ap_data in data.items():
                    self._approvals[ap_id] = DryRunApproval(
                        approval_id=ap_data["approval_id"],
                        dry_run_id=ap_data["dry_run_id"],
                        approved_payload_hash=ap_data["approved_payload_hash"],
                        approved_by=ap_data["approved_by"],
                        approved_at=datetime.fromisoformat(ap_data["approved_at"]),
                        notes=ap_data.get("notes", ""),
                        expires_at=(
                            datetime.fromisoformat(ap_data["expires_at"])
                            if ap_data.get("expires_at")
                            else None
                        ),
                        execution_window_hours=ap_data.get("execution_window_hours", 24),
                    )
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load approvals: {e}")

    def _save_state(self) -> None:
        """Save state to storage."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Save dry-runs
        dry_runs_file = self.storage_dir / "dry_runs.json"
        dry_runs_file.write_text(
            json.dumps(
                {dr_id: dr.to_dict() for dr_id, dr in self._dry_runs.items()},
                indent=2,
            ),
            encoding="utf-8",
        )

        # Save approvals
        approvals_file = self.storage_dir / "approvals.json"
        approvals_file.write_text(
            json.dumps(
                {ap_id: ap.to_dict() for ap_id, ap in self._approvals.items()},
                indent=2,
            ),
            encoding="utf-8",
        )

    def create_dry_run(
        self,
        provider: str,
        action: str,
        payload: dict,
        predicted_effects: Optional[list[PredictedSideEffect]] = None,
        validation_errors: Optional[list[str]] = None,
        warnings: Optional[list[str]] = None,
        run_id: Optional[str] = None,
        phase_number: Optional[int] = None,
        requires_confirmation: bool = True,
    ) -> DryRunResult:
        """Create a new dry-run result.

        Args:
            provider: Provider name (youtube, etsy, shopify, etc.)
            action: Action type (publish, list, update, etc.)
            payload: Fully-rendered request payload
            predicted_effects: List of predicted side effects
            validation_errors: Any validation errors found
            warnings: Any warnings to surface
            run_id: Associated run ID
            phase_number: Associated phase number
            requires_confirmation: Whether operator confirmation is required

        Returns:
            DryRunResult with computed payload hash
        """
        dry_run_id = f"dryrun-{uuid.uuid4().hex[:12]}"
        payload_hash = DryRunResult.compute_payload_hash(payload)
        now = datetime.now(timezone.utc)

        result = DryRunResult(
            dry_run_id=dry_run_id,
            provider=provider,
            action=action,
            payload=payload,
            payload_hash=payload_hash,
            predicted_effects=predicted_effects or [],
            created_at=now,
            status=DryRunStatus.PENDING,
            validation_errors=validation_errors or [],
            warnings=warnings or [],
            requires_confirmation=requires_confirmation,
            run_id=run_id,
            phase_number=phase_number,
        )

        self._dry_runs[dry_run_id] = result
        self._save_state()

        logger.info(
            f"Created dry-run: {dry_run_id} "
            f"(provider={provider}, action={action}, hash={payload_hash[:16]}...)"
        )

        return result

    def get_dry_run(self, dry_run_id: str) -> Optional[DryRunResult]:
        """Get a dry-run by ID."""
        return self._dry_runs.get(dry_run_id)

    def approve(
        self,
        dry_run_id: str,
        approved_by: str,
        notes: str = "",
        expiry_hours: Optional[int] = None,
    ) -> DryRunApproval:
        """Approve a dry-run for execution.

        Args:
            dry_run_id: ID of dry-run to approve
            approved_by: Operator approving
            notes: Optional approval notes
            expiry_hours: Hours until approval expires (defaults to default_expiry_hours)

        Returns:
            DryRunApproval record

        Raises:
            ValueError: If dry-run not found or has validation errors
        """
        dry_run = self.get_dry_run(dry_run_id)
        if dry_run is None:
            raise ValueError(f"Dry-run not found: {dry_run_id}")

        if not dry_run.is_valid():
            raise ValueError(
                f"Cannot approve dry-run with validation errors: {dry_run.validation_errors}"
            )

        if dry_run.status != DryRunStatus.PENDING:
            raise ValueError(f"Dry-run is not pending approval (status={dry_run.status})")

        now = datetime.now(timezone.utc)
        hours = expiry_hours or self.default_expiry_hours

        approval = DryRunApproval(
            approval_id=f"approval-{uuid.uuid4().hex[:12]}",
            dry_run_id=dry_run_id,
            approved_payload_hash=dry_run.payload_hash,
            approved_by=approved_by,
            approved_at=now,
            notes=notes,
            expires_at=now + timedelta(hours=hours),
            execution_window_hours=hours,
        )

        dry_run.status = DryRunStatus.APPROVED
        self._approvals[approval.approval_id] = approval
        self._save_state()

        logger.info(f"Approved dry-run: {dry_run_id} by {approved_by} (expires in {hours}h)")

        return approval

    def reject(
        self,
        dry_run_id: str,
        rejected_by: str,
        reason: str = "",
    ) -> DryRunResult:
        """Reject a dry-run.

        Args:
            dry_run_id: ID of dry-run to reject
            rejected_by: Operator rejecting
            reason: Rejection reason

        Returns:
            Updated DryRunResult

        Raises:
            ValueError: If dry-run not found
        """
        dry_run = self.get_dry_run(dry_run_id)
        if dry_run is None:
            raise ValueError(f"Dry-run not found: {dry_run_id}")

        dry_run.status = DryRunStatus.REJECTED
        self._save_state()

        logger.info(f"Rejected dry-run: {dry_run_id} by {rejected_by}: {reason}")

        return dry_run

    def get_approval(self, approval_id: str) -> Optional[DryRunApproval]:
        """Get an approval by ID."""
        return self._approvals.get(approval_id)

    def get_approval_for_dry_run(self, dry_run_id: str) -> Optional[DryRunApproval]:
        """Get the approval for a dry-run."""
        for approval in self._approvals.values():
            if approval.dry_run_id == dry_run_id:
                return approval
        return None

    def execute(
        self,
        dry_run_id: str,
        approval_id: str,
        payload: dict,
        executor_fn: ActionExecutor,
    ) -> ExecutionResult:
        """Execute an approved dry-run with hash verification.

        Args:
            dry_run_id: ID of dry-run to execute
            approval_id: ID of approval
            payload: Payload to execute (must match approved hash)
            executor_fn: Function to execute the action

        Returns:
            ExecutionResult

        Raises:
            ValueError: If dry-run/approval not found, expired, or hash mismatch
        """
        dry_run = self.get_dry_run(dry_run_id)
        if dry_run is None:
            raise ValueError(f"Dry-run not found: {dry_run_id}")

        approval = self.get_approval(approval_id)
        if approval is None:
            raise ValueError(f"Approval not found: {approval_id}")

        if approval.dry_run_id != dry_run_id:
            raise ValueError(f"Approval {approval_id} does not match dry-run {dry_run_id}")

        if approval.is_expired():
            dry_run.status = DryRunStatus.EXPIRED
            self._save_state()
            raise ValueError(f"Approval has expired: {approval_id}")

        # Verify payload hash matches
        current_hash = DryRunResult.compute_payload_hash(payload)
        if not approval.matches_payload(current_hash):
            dry_run.status = DryRunStatus.HASH_MISMATCH
            self._save_state()
            raise ValueError(
                f"Payload hash mismatch: approved={approval.approved_payload_hash[:16]}..., "
                f"current={current_hash[:16]}..."
            )

        # Execute the action
        now = datetime.now(timezone.utc)
        start_time = now

        try:
            result = executor_fn(dry_run.provider, dry_run.action, payload)

            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()

            execution = ExecutionResult(
                execution_id=f"exec-{uuid.uuid4().hex[:12]}",
                dry_run_id=dry_run_id,
                approval_id=approval_id,
                executed_at=now,
                success=True,
                response_summary=str(result)[:1000],
                duration_seconds=duration,
            )

            dry_run.status = DryRunStatus.EXECUTED
            self._executions[execution.execution_id] = execution
            self._save_state()

            logger.info(f"Executed dry-run: {dry_run_id} (duration={duration:.2f}s)")

            return execution

        except Exception as e:
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()

            execution = ExecutionResult(
                execution_id=f"exec-{uuid.uuid4().hex[:12]}",
                dry_run_id=dry_run_id,
                approval_id=approval_id,
                executed_at=now,
                success=False,
                error_message=str(e),
                duration_seconds=duration,
            )

            self._executions[execution.execution_id] = execution
            self._save_state()

            logger.error(f"Failed to execute dry-run {dry_run_id}: {e}")

            return execution

    def get_pending_dry_runs(self, provider: Optional[str] = None) -> list[DryRunResult]:
        """Get all pending dry-runs.

        Args:
            provider: Optional provider filter

        Returns:
            List of pending dry-runs
        """
        results = []
        for dr in self._dry_runs.values():
            if dr.status == DryRunStatus.PENDING:
                if provider is None or dr.provider == provider:
                    results.append(dr)
        return results

    def get_approved_dry_runs(
        self, provider: Optional[str] = None
    ) -> list[tuple[DryRunResult, DryRunApproval]]:
        """Get all approved (not yet executed) dry-runs.

        Args:
            provider: Optional provider filter

        Returns:
            List of (dry-run, approval) tuples
        """
        results = []
        for dr in self._dry_runs.values():
            if dr.status == DryRunStatus.APPROVED:
                if provider is None or dr.provider == provider:
                    approval = self.get_approval_for_dry_run(dr.dry_run_id)
                    if approval and not approval.is_expired():
                        results.append((dr, approval))
        return results

    def save_artifact(self, dry_run_id: str, output_dir: Optional[Path] = None) -> Path:
        """Save a dry-run as a JSON artifact.

        Args:
            dry_run_id: ID of dry-run to save
            output_dir: Directory for output (defaults to storage_dir)

        Returns:
            Path to saved artifact

        Raises:
            ValueError: If dry-run not found
        """
        dry_run = self.get_dry_run(dry_run_id)
        if dry_run is None:
            raise ValueError(f"Dry-run not found: {dry_run_id}")

        output_dir = output_dir or self.storage_dir / "artifacts"
        output_dir.mkdir(parents=True, exist_ok=True)

        artifact_data = {
            "dry_run": dry_run.to_dict(),
            "approval": None,
        }

        approval = self.get_approval_for_dry_run(dry_run_id)
        if approval:
            artifact_data["approval"] = approval.to_dict()

        artifact_path = output_dir / f"{dry_run_id}.json"
        artifact_path.write_text(json.dumps(artifact_data, indent=2), encoding="utf-8")

        logger.info(f"Saved dry-run artifact: {artifact_path}")

        return artifact_path
