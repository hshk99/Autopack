"""
ROAD-D: Governance Integration for Generated PRs

Implements approval gating system for auto-generated followup PRs.
PRs require explicit human approval before merging.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ApprovalRequest:
    """Request for PR approval."""

    pr_number: int
    generated_from: str  # e.g., "COST-SINK-001"
    title: str
    description: str
    impact_assessment: str
    rollback_plan: str
    created_at: str
    status: str = "pending"  # pending, approved, rejected

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pr_number": self.pr_number,
            "generated_from": self.generated_from,
            "title": self.title,
            "description": self.description,
            "impact_assessment": self.impact_assessment,
            "rollback_plan": self.rollback_plan,
            "created_at": self.created_at,
            "status": self.status,
        }


class PrGovernanceGateway:
    """Governance gateway for auto-generated PRs."""

    def __init__(self):
        """Initialize gateway."""
        self.pending_approvals: Dict[int, ApprovalRequest] = {}
        self.approved_prs: set = set()
        self.rejected_prs: set = set()

    def create_approval_request(
        self,
        pr_number: int,
        generated_from: str,
        title: str,
        description: str,
        impact_assessment: str,
        rollback_plan: str,
    ) -> ApprovalRequest:
        """Create approval request for generated PR.

        Args:
            pr_number: GitHub PR number
            generated_from: ID of improvement/task that generated this PR
            title: PR title
            description: PR description
            impact_assessment: Assessment of potential impact
            rollback_plan: Plan for rolling back if issues arise

        Returns:
            ApprovalRequest
        """
        request = ApprovalRequest(
            pr_number=pr_number,
            generated_from=generated_from,
            title=title,
            description=description,
            impact_assessment=impact_assessment,
            rollback_plan=rollback_plan,
            created_at=datetime.now().isoformat(),
        )

        self.pending_approvals[pr_number] = request
        logger.info(f"Created approval request for PR #{pr_number}: {generated_from}")
        return request

    def approve_pr(self, pr_number: int, reviewer: str = "human") -> bool:
        """Approve PR for merging.

        Args:
            pr_number: GitHub PR number
            reviewer: Name of reviewer who approved

        Returns:
            True if approved, False if not found
        """
        if pr_number not in self.pending_approvals:
            logger.warning(f"PR #{pr_number} not found in pending approvals")
            return False

        request = self.pending_approvals[pr_number]
        request.status = "approved"
        self.approved_prs.add(pr_number)
        del self.pending_approvals[pr_number]

        logger.info(f"✅ PR #{pr_number} approved by {reviewer}")
        return True

    def reject_pr(self, pr_number: int, reason: str = "") -> bool:
        """Reject PR.

        Args:
            pr_number: GitHub PR number
            reason: Reason for rejection

        Returns:
            True if rejected, False if not found
        """
        if pr_number not in self.pending_approvals:
            logger.warning(f"PR #{pr_number} not found in pending approvals")
            return False

        request = self.pending_approvals[pr_number]
        request.status = "rejected"
        self.rejected_prs.add(pr_number)
        del self.pending_approvals[pr_number]

        logger.info(f"❌ PR #{pr_number} rejected: {reason}")
        return True

    def can_merge(self, pr_number: int) -> bool:
        """Check if PR can be merged.

        Args:
            pr_number: GitHub PR number

        Returns:
            True if PR is approved
        """
        return pr_number in self.approved_prs

    def get_pending_count(self) -> int:
        """Get count of pending approvals."""
        return len(self.pending_approvals)


# Global gateway instance
_gateway = None


def get_gateway() -> PrGovernanceGateway:
    """Get or create global gateway."""
    global _gateway
    if _gateway is None:
        _gateway = PrGovernanceGateway()
    return _gateway
