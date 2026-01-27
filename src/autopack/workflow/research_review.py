"""Research Review Workflow Integration.

Provides workflow integration for reviewing research results before
proceeding with implementation phases.

Design Principles:
- Human-in-the-loop review for critical decisions
- Automated approval for high-confidence research
- Clear approval/rejection workflow
- Integration with BUILD_HISTORY for tracking
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ReviewDecision(Enum):
    """Decision from a review."""

    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_MORE_RESEARCH = "needs_more_research"


@dataclass
class ReviewCriteria:
    """Criteria for reviewing research results."""

    auto_approve_confidence: float = 0.9
    auto_reject_confidence: float = 0.3
    require_human_review: bool = True
    min_findings_required: int = 1
    min_recommendations_required: int = 1


@dataclass
class ReviewResult:
    """Result from a review."""

    decision: ReviewDecision
    reviewer: str
    confidence: float
    comments: str
    timestamp: datetime = field(default_factory=datetime.now)
    approved_findings: List[Any] = field(default_factory=list)


class ResearchReviewWorkflow:
    """Manages research review workflow."""

    def __init__(self, criteria: Optional[ReviewCriteria] = None):
        """Initialize review workflow.

        Args:
            criteria: Review criteria (uses defaults if not provided)
        """
        self.criteria = criteria or ReviewCriteria()
        self._pending_reviews: Dict[str, Dict[str, Any]] = {}

    def submit_for_review(self, research_result: Any) -> str:
        """Submit research result for review.

        Args:
            research_result: Research result to review

        Returns:
            Review ID
        """
        review_id = f"review_{uuid.uuid4().hex[:12]}"

        # Check if can auto-review
        if self._can_auto_review(research_result):
            # Auto-review
            review = self._auto_review(research_result)
            self._pending_reviews[review_id] = {
                "status": "completed",
                "result": research_result,
                "review": review,
                "submitted_at": datetime.now(),
            }
        else:
            # Requires manual review
            self._pending_reviews[review_id] = {
                "status": "pending",
                "result": research_result,
                "review": None,
                "submitted_at": datetime.now(),
            }

        return review_id

    def _can_auto_review(self, result: Any) -> bool:
        """Check if result can be auto-reviewed.

        Args:
            result: Research result

        Returns:
            True if can auto-review
        """
        # If human review is required, can't auto-review
        if self.criteria.require_human_review:
            return False

        # Can auto-review if confidence is very high or very low
        return True

    def _auto_review(self, result: Any) -> ReviewResult:
        """Automatically review a result.

        Args:
            result: Research result

        Returns:
            ReviewResult
        """
        confidence = getattr(result, "confidence", 0.0)
        findings = getattr(result, "findings", [])
        recommendations = getattr(result, "recommendations", [])

        # Determine decision
        if confidence >= self.criteria.auto_approve_confidence:
            # High confidence - approve
            if (
                len(findings) >= self.criteria.min_findings_required
                and len(recommendations) >= self.criteria.min_recommendations_required
            ):
                return ReviewResult(
                    decision=ReviewDecision.APPROVED,
                    reviewer="auto",
                    confidence=confidence,
                    comments=f"Auto-approved: High confidence ({confidence:.1%})",
                    approved_findings=findings,
                )

        # Check if insufficient findings/recommendations
        if len(findings) < self.criteria.min_findings_required:
            return ReviewResult(
                decision=ReviewDecision.NEEDS_MORE_RESEARCH,
                reviewer="auto",
                confidence=confidence,
                comments=f"Insufficient findings: {len(findings)}/{self.criteria.min_findings_required} required",
            )

        if len(recommendations) < self.criteria.min_recommendations_required:
            return ReviewResult(
                decision=ReviewDecision.NEEDS_MORE_RESEARCH,
                reviewer="auto",
                confidence=confidence,
                comments=f"Insufficient recommendations: {len(recommendations)}/{self.criteria.min_recommendations_required} required",
            )

        # Low confidence - reject
        if confidence <= self.criteria.auto_reject_confidence:
            return ReviewResult(
                decision=ReviewDecision.REJECTED,
                reviewer="auto",
                confidence=confidence,
                comments=f"Auto-rejected: Low confidence ({confidence:.1%})",
            )

        # Middle ground - needs more research
        return ReviewResult(
            decision=ReviewDecision.NEEDS_MORE_RESEARCH,
            reviewer="auto",
            confidence=confidence,
            comments="Confidence in middle range, needs more research",
        )

    def manual_review(
        self,
        review_id: str,
        decision: ReviewDecision,
        reviewer: str,
        comments: Optional[str] = None,
    ) -> ReviewResult:
        """Perform manual review.

        Args:
            review_id: Review ID
            decision: Review decision
            reviewer: Reviewer name
            comments: Optional comments

        Returns:
            ReviewResult

        Raises:
            ValueError: If review_id not found
        """
        if review_id not in self._pending_reviews:
            raise ValueError(f"Review {review_id} not found")

        result = self._pending_reviews[review_id]["result"]
        confidence = getattr(result, "confidence", 0.0)
        findings = getattr(result, "findings", [])

        review = ReviewResult(
            decision=decision,
            reviewer=reviewer,
            confidence=confidence,
            comments=comments or "",
            approved_findings=findings if decision == ReviewDecision.APPROVED else [],
        )

        # Update status
        self._pending_reviews[review_id]["status"] = "completed"
        self._pending_reviews[review_id]["review"] = review

        return review

    def get_review_status(self, review_id: str) -> Dict[str, Any]:
        """Get status of a review.

        Args:
            review_id: Review ID

        Returns:
            Status dictionary

        Raises:
            ValueError: If review_id not found
        """
        if review_id not in self._pending_reviews:
            raise ValueError(f"Review {review_id} not found")

        review_data = self._pending_reviews[review_id]
        return {
            "review_id": review_id,
            "status": review_data["status"],
            "submitted_at": review_data["submitted_at"].isoformat(),
        }

    def list_pending_reviews(self) -> List[str]:
        """List all pending review IDs.

        Returns:
            List of pending review IDs
        """
        return [
            review_id
            for review_id, data in self._pending_reviews.items()
            if data["status"] == "pending"
        ]

    def export_review_to_build_history(self, review_id: str) -> str:
        """Export review to BUILD_HISTORY format.

        Args:
            review_id: Review ID

        Returns:
            Formatted markdown entry

        Raises:
            ValueError: If review_id not found or not completed
        """
        if review_id not in self._pending_reviews:
            raise ValueError(f"Review {review_id} not found")

        review_data = self._pending_reviews[review_id]

        if review_data["status"] != "completed":
            raise ValueError(f"Review {review_id} not completed")

        review = review_data["review"]
        result = review_data["result"]

        lines = [
            f"## Research Review: {review_id}",
            f"**Decision**: {review.decision.value}",
            f"**Reviewer**: {review.reviewer}",
            f"**Confidence**: {review.confidence:.1%}",
            f"**Timestamp**: {review.timestamp}",
            "",
        ]

        if review.comments:
            lines.append(f"**Comments**: {review.comments}")
            lines.append("")

        if hasattr(result, "query"):
            lines.append(f"**Query**: {result.query}")
            lines.append("")

        if review.approved_findings:
            lines.append("### Approved Findings")
            for finding in review.approved_findings:
                lines.append(f"- {finding}")
            lines.append("")

        return "\n".join(lines)


# Backward compatibility alias for tests
ReviewConfig = ReviewCriteria
