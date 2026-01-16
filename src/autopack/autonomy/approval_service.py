"""IMP-AUTOPILOT-002: Approval workflow for autopilot proposals.

This module provides human-in-the-loop approval workflow for autopilot
improvement proposals that require manual review before execution.

Workflow:
1. Autopilot generates proposals, some marked "requires_approval"
2. ApprovalService queues these for human review
3. Human reviews via CLI/API and approves/rejects
4. ApprovalService executes approved proposals through autopilot controller

Storage:
- Pending approvals: .autonomous_runs/<run_id>/autopilot/pending_approvals.json
- Approval decisions: .autonomous_runs/<run_id>/autopilot/approval_decisions.json
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


# IMP-AUTOPILOT-002: Approval decision model
class ApprovalDecision(BaseModel):
    """Human decision on an approval request.

    Attributes:
        action_id: Action identifier from the proposal
        session_id: Autopilot session that generated this request
        decision: approve, reject, or defer (decide later)
        decided_at: Timestamp of decision
        decided_by: Optional identifier of approver (user, system, etc.)
        notes: Optional notes from approver
    """

    model_config = ConfigDict(extra="forbid")

    action_id: str
    session_id: str
    decision: Literal["approve", "reject", "defer"]
    decided_at: datetime
    decided_by: Optional[str] = None
    notes: Optional[str] = None


class PendingApproval(BaseModel):
    """Pending approval request with proposal context.

    Attributes:
        action_id: Action identifier
        session_id: Autopilot session that generated this
        approval_status: requires_approval or blocked
        reason: Why approval is needed
        action_type: Type of action (e.g., write_file, run_command)
        action_description: Human-readable description
        created_at: When this was created
        proposal_summary: Brief summary of what this accomplishes
    """

    model_config = ConfigDict(extra="forbid")

    action_id: str
    session_id: str
    approval_status: Literal["requires_approval", "blocked"]
    reason: str
    action_type: Optional[str] = None
    action_description: Optional[str] = None
    created_at: datetime
    proposal_summary: Optional[str] = None


@dataclass
class ApprovalQueue:
    """In-memory representation of pending approvals.

    Attributes:
        pending: List of pending approval requests
        decisions: List of approval decisions
    """

    pending: List[PendingApproval] = field(default_factory=list)
    decisions: List[ApprovalDecision] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to JSON-serializable dict."""
        return {
            "pending": [p.model_dump(mode="json") for p in self.pending],
            "decisions": [d.model_dump(mode="json") for d in self.decisions],
        }

    @classmethod
    def from_dict(cls, data: Dict) -> ApprovalQueue:
        """Create from JSON dict."""
        return cls(
            pending=[PendingApproval.model_validate(p) for p in data.get("pending", [])],
            decisions=[ApprovalDecision.model_validate(d) for d in data.get("decisions", [])],
        )


class ApprovalService:
    """Service for managing autopilot approval workflow.

    IMP-AUTOPILOT-002: Provides human-in-the-loop approval for high-impact
    autopilot proposals.

    Responsibilities:
    - Queue approval requests from autopilot sessions
    - Load and persist approval queue
    - Accept human decisions (approve/reject/defer)
    - Execute approved actions through autopilot

    Attributes:
        run_id: Run identifier
        project_id: Project identifier
        storage_dir: Directory for approval artifacts
    """

    def __init__(self, run_id: str, project_id: str, workspace_root: Path):
        """Initialize approval service.

        Args:
            run_id: Run identifier
            project_id: Project identifier
            workspace_root: Workspace root directory
        """
        self.run_id = run_id
        self.project_id = project_id
        self.workspace_root = workspace_root

        # Storage paths
        self.storage_dir = workspace_root / ".autonomous_runs" / run_id / "autopilot"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.pending_path = self.storage_dir / "pending_approvals.json"
        self.decisions_path = self.storage_dir / "approval_decisions.json"

        # Load existing queue
        self.queue = self._load_queue()

    def _load_queue(self) -> ApprovalQueue:
        """Load approval queue from storage.

        Returns:
            Loaded ApprovalQueue or empty queue if not found
        """
        if not self.pending_path.exists():
            logger.debug(f"[ApprovalService] No pending approvals found at {self.pending_path}")
            return ApprovalQueue()

        try:
            data = json.loads(self.pending_path.read_text(encoding="utf-8"))
            queue = ApprovalQueue.from_dict(data)
            logger.info(
                f"[ApprovalService] Loaded {len(queue.pending)} pending approvals, "
                f"{len(queue.decisions)} decisions"
            )
            return queue
        except Exception as e:
            logger.warning(f"[ApprovalService] Failed to load approval queue: {e}")
            return ApprovalQueue()

    def _save_queue(self) -> None:
        """Persist approval queue to storage."""
        try:
            data = self.queue.to_dict()
            self.pending_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            logger.debug(f"[ApprovalService] Saved approval queue to {self.pending_path}")
        except Exception as e:
            logger.error(f"[ApprovalService] Failed to save approval queue: {e}")

    def queue_approvals(
        self, session_id: str, approval_requests: List, proposal_summary: Optional[str] = None
    ) -> int:
        """Queue approval requests from an autopilot session.

        IMP-AUTOPILOT-002: Called by autopilot when proposals need approval.

        Args:
            session_id: Autopilot session identifier
            approval_requests: List of ApprovalRequest objects from session
            proposal_summary: Optional summary of the proposal

        Returns:
            Number of requests queued
        """
        queued = 0

        for req in approval_requests:
            # Skip if already queued
            if any(p.action_id == req.action_id for p in self.queue.pending):
                logger.debug(f"[ApprovalService] Action {req.action_id} already queued")
                continue

            # Create pending approval
            pending = PendingApproval(
                action_id=req.action_id,
                session_id=session_id,
                approval_status=req.approval_status,
                reason=req.reason,
                action_type=getattr(req, "action_type", None),
                action_description=getattr(req, "description", None),
                created_at=datetime.now(timezone.utc),
                proposal_summary=proposal_summary,
            )

            self.queue.pending.append(pending)
            queued += 1

        if queued > 0:
            self._save_queue()
            logger.info(
                f"[ApprovalService] Queued {queued} approval requests from session {session_id}"
            )

        return queued

    def get_pending_approvals(self, include_blocked: bool = False) -> List[PendingApproval]:
        """Get list of pending approval requests.

        Args:
            include_blocked: If True, include blocked actions (default: False)

        Returns:
            List of pending approvals
        """
        if include_blocked:
            return self.queue.pending

        # Filter out blocked actions (only show requires_approval)
        return [p for p in self.queue.pending if p.approval_status == "requires_approval"]

    def record_decision(
        self,
        action_id: str,
        decision: Literal["approve", "reject", "defer"],
        decided_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """Record an approval decision.

        IMP-AUTOPILOT-002: Human provides approve/reject/defer decision.

        Args:
            action_id: Action identifier
            decision: approve, reject, or defer
            decided_by: Optional identifier of approver
            notes: Optional notes from approver

        Returns:
            True if decision recorded, False if action not found
        """
        # Find pending approval
        pending = next((p for p in self.queue.pending if p.action_id == action_id), None)
        if not pending:
            logger.warning(f"[ApprovalService] Action {action_id} not found in pending queue")
            return False

        # Create decision
        decision_obj = ApprovalDecision(
            action_id=action_id,
            session_id=pending.session_id,
            decision=decision,
            decided_at=datetime.now(timezone.utc),
            decided_by=decided_by,
            notes=notes,
        )

        self.queue.decisions.append(decision_obj)

        # Remove from pending if approved or rejected (keep deferred)
        if decision in ["approve", "reject"]:
            self.queue.pending = [p for p in self.queue.pending if p.action_id != action_id]

        self._save_queue()

        logger.info(
            f"[ApprovalService] Decision recorded for {action_id}: {decision} "
            f"(by: {decided_by or 'unknown'})"
        )

        return True

    def get_approved_actions(self, session_id: Optional[str] = None) -> List[str]:
        """Get list of approved action IDs.

        Args:
            session_id: Optional filter by session ID

        Returns:
            List of approved action IDs
        """
        approved = [d.action_id for d in self.queue.decisions if d.decision == "approve"]

        if session_id:
            # Filter by session
            approved = [
                d.action_id
                for d in self.queue.decisions
                if d.decision == "approve" and d.session_id == session_id
            ]

        return approved

    def bulk_approve(
        self, action_ids: List[str], decided_by: Optional[str] = None, notes: Optional[str] = None
    ) -> int:
        """Approve multiple actions at once.

        Args:
            action_ids: List of action IDs to approve
            decided_by: Optional identifier of approver
            notes: Optional notes (applied to all)

        Returns:
            Number of actions approved
        """
        approved = 0
        for action_id in action_ids:
            if self.record_decision(action_id, "approve", decided_by, notes):
                approved += 1

        logger.info(f"[ApprovalService] Bulk approved {approved}/{len(action_ids)} actions")
        return approved

    def bulk_reject(
        self, action_ids: List[str], decided_by: Optional[str] = None, notes: Optional[str] = None
    ) -> int:
        """Reject multiple actions at once.

        Args:
            action_ids: List of action IDs to reject
            decided_by: Optional identifier of approver
            notes: Optional notes (applied to all)

        Returns:
            Number of actions rejected
        """
        rejected = 0
        for action_id in action_ids:
            if self.record_decision(action_id, "reject", decided_by, notes):
                rejected += 1

        logger.info(f"[ApprovalService] Bulk rejected {rejected}/{len(action_ids)} actions")
        return rejected

    def get_statistics(self) -> Dict[str, int]:
        """Get approval queue statistics.

        Returns:
            Dictionary with counts:
            - pending: Total pending approvals
            - requires_approval: Pending requiring approval
            - blocked: Pending blocked actions
            - approved: Total approved decisions
            - rejected: Total rejected decisions
            - deferred: Total deferred decisions
        """
        requires_approval = sum(
            1 for p in self.queue.pending if p.approval_status == "requires_approval"
        )
        blocked = sum(1 for p in self.queue.pending if p.approval_status == "blocked")
        approved = sum(1 for d in self.queue.decisions if d.decision == "approve")
        rejected = sum(1 for d in self.queue.decisions if d.decision == "reject")
        deferred = sum(1 for d in self.queue.decisions if d.decision == "defer")

        return {
            "pending": len(self.queue.pending),
            "requires_approval": requires_approval,
            "blocked": blocked,
            "approved": approved,
            "rejected": rejected,
            "deferred": deferred,
        }
