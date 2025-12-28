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
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ReviewStatus(Enum):
    """Status of a research review."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"


# BUILD-146: Compatibility API for tests
class ReviewDecisionEnum(Enum):
    """Review decision enum for compatibility with tests."""

    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_MORE_RESEARCH = "needs_more_research"


# Export as ReviewDecision for test compatibility
ReviewDecision = ReviewDecisionEnum


@dataclass
class ReviewCriteria:
    """Criteria for automatic review decisions."""

    auto_approve_confidence: float = 0.9
    auto_reject_confidence: float = 0.3
    require_human_review: bool = True
    min_findings_required: int = 1
    min_recommendations_required: int = 1


@dataclass
class ReviewResult:
    """Result of a review process."""

    decision: ReviewDecisionEnum
    reviewer: str
    confidence: float = 0.0
    comments: str = ""
    approved_findings: List[str] = field(default_factory=list)
    rejected_findings: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ReviewComment:
    """A comment on research results."""
    
    author: str
    comment: str
    timestamp: datetime = field(default_factory=datetime.now)
    query_index: Optional[int] = None  # Which query this comment refers to


@dataclass
class ReviewDecisionData:
    """Decision from a research review (renamed from ReviewDecision to avoid conflict)."""

    status: ReviewStatus
    reviewer: str
    comments: List[ReviewComment] = field(default_factory=list)
    approved_queries: List[int] = field(default_factory=list)  # Indices of approved queries
    rejected_queries: List[int] = field(default_factory=list)  # Indices of rejected queries
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchReview:
    """Represents a review of research results."""

    review_id: str
    phase_id: str
    phase_description: str
    status: ReviewStatus = ReviewStatus.PENDING
    decisions: List[ReviewDecisionData] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "review_id": self.review_id,
            "phase_id": self.phase_id,
            "phase_description": self.phase_description,
            "status": self.status.value,
            "decisions": [
                {
                    "status": d.status.value,
                    "reviewer": d.reviewer,
                    "comments": [
                        {
                            "author": c.author,
                            "comment": c.comment,
                            "timestamp": c.timestamp.isoformat(),
                            "query_index": c.query_index,
                        }
                        for c in d.comments
                    ],
                    "approved_queries": d.approved_queries,
                    "rejected_queries": d.rejected_queries,
                    "timestamp": d.timestamp.isoformat(),
                    "metadata": d.metadata,
                }
                for d in self.decisions
            ],
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class ResearchReviewWorkflow:
    """Manages research review workflow."""

    def __init__(
        self,
        criteria: Optional[ReviewCriteria] = None,
        review_storage_path: Optional[Path] = None,
        auto_approve_threshold: float = 0.8,
    ):
        """Initialize the workflow.

        Args:
            criteria: Review criteria (for test compatibility)
            review_storage_path: Path to store review data
            auto_approve_threshold: Confidence threshold for auto-approval
        """
        # BUILD-146: Support both old and new API
        self.criteria = criteria or ReviewCriteria()
        self.review_storage_path = review_storage_path or Path(".autopack/reviews")
        self.review_storage_path.mkdir(parents=True, exist_ok=True)
        self.auto_approve_threshold = auto_approve_threshold
        self._pending_reviews: Dict[str, Dict[str, Any]] = {}
    
    def create_review(
        self,
        phase: Any,  # ResearchPhase
    ) -> ResearchReview:
        """Create a new review for a research phase.
        
        Args:
            phase: Research phase to review
            
        Returns:
            New research review
        """
        review = ResearchReview(
            review_id=f"review_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            phase_id=phase.phase_id,
            phase_description=phase.description,
        )
        
        # Check if auto-approval is possible
        if self._can_auto_approve(phase):
            decision = ReviewDecisionData(
                status=ReviewStatus.APPROVED,
                reviewer="system",
                comments=[
                    ReviewComment(
                        author="system",
                        comment="Auto-approved based on high confidence scores",
                    )
                ],
                approved_queries=list(range(len(phase.results))),
            )
            review.decisions.append(decision)
            review.status = ReviewStatus.APPROVED
            review.completed_at = datetime.now()
            
            logger.info(f"Research phase auto-approved: {phase.phase_id}")
        
        # Save review
        self._save_review(review)
        
        return review
    
    def submit_decision(
        self,
        review: ResearchReview,
        decision: ReviewDecisionData,
    ) -> ResearchReview:
        """Submit a review decision.

        Args:
            review: Review to update
            decision: Decision to add

        Returns:
            Updated review
        """
        review.decisions.append(decision)
        review.status = decision.status
        
        if decision.status in (ReviewStatus.APPROVED, ReviewStatus.REJECTED):
            review.completed_at = datetime.now()
        
        # Save updated review
        self._save_review(review)
        
        logger.info(
            f"Review decision submitted: {review.review_id} - {decision.status.value}"
        )
        
        return review
    
    def get_review(self, review_id: str) -> Optional[ResearchReview]:
        """Get a review by ID.
        
        Args:
            review_id: Review ID
            
        Returns:
            Review if found, None otherwise
        """
        review_file = self.review_storage_path / f"{review_id}.json"
        
        if not review_file.exists():
            return None
        
        try:
            import json
            data = json.loads(review_file.read_text())
            
            # Reconstruct review object
            review = ResearchReview(
                review_id=data["review_id"],
                phase_id=data["phase_id"],
                phase_description=data["phase_description"],
                status=ReviewStatus(data["status"]),
                created_at=datetime.fromisoformat(data["created_at"]),
                completed_at=datetime.fromisoformat(data["completed_at"]) if data["completed_at"] else None,
            )
            
            # Reconstruct decisions
            for d in data["decisions"]:
                comments = [
                    ReviewComment(
                        author=c["author"],
                        comment=c["comment"],
                        timestamp=datetime.fromisoformat(c["timestamp"]),
                        query_index=c["query_index"],
                    )
                    for c in d["comments"]
                ]

                decision = ReviewDecisionData(
                    status=ReviewStatus(d["status"]),
                    reviewer=d["reviewer"],
                    comments=comments,
                    approved_queries=d["approved_queries"],
                    rejected_queries=d["rejected_queries"],
                    timestamp=datetime.fromisoformat(d["timestamp"]),
                    metadata=d["metadata"],
                )
                review.decisions.append(decision)
            
            return review
        
        except Exception as e:
            logger.error(f"Failed to load review {review_id}: {e}")
            return None
    
    def list_pending_reviews(self) -> List[ResearchReview]:
        """List all pending reviews.
        
        Returns:
            List of pending reviews
        """
        reviews = []
        
        for review_file in self.review_storage_path.glob("review_*.json"):
            review = self.get_review(review_file.stem)
            if review and review.status == ReviewStatus.PENDING:
                reviews.append(review)
        
        return reviews
    
    def _can_auto_approve(self, phase: Any) -> bool:
        """Check if phase can be auto-approved.
        
        Args:
            phase: Research phase
            
        Returns:
            True if auto-approval is possible
        """
        if not phase.results:
            return False
        
        # Check average confidence
        avg_confidence = sum(r.confidence for r in phase.results) / len(phase.results)
        
        return avg_confidence >= self.auto_approve_threshold
    
    def _save_review(self, review: ResearchReview) -> None:
        """Save review to storage.
        
        Args:
            review: Review to save
        """
        import json
        
        review_file = self.review_storage_path / f"{review.review_id}.json"
        review_file.write_text(json.dumps(review.to_dict(), indent=2))
    
    def format_for_display(self, review: ResearchReview) -> str:
        """Format review for display.
        
        Args:
            review: Review to format
            
        Returns:
            Formatted string
        """
        lines = [
            f"# Research Review: {review.phase_description}",
            "",
            f"**Review ID**: {review.review_id}",
            f"**Phase ID**: {review.phase_id}",
            f"**Status**: {review.status.value}",
            f"**Created**: {review.created_at.isoformat()}",
        ]
        
        if review.completed_at:
            lines.append(f"**Completed**: {review.completed_at.isoformat()}")
        
        if review.decisions:
            lines.append("\n## Decisions\n")
            for i, decision in enumerate(review.decisions, 1):
                lines.extend([
                    f"### Decision {i}",
                    f"**Reviewer**: {decision.reviewer}",
                    f"**Status**: {decision.status.value}",
                    f"**Timestamp**: {decision.timestamp.isoformat()}",
                ])
                
                if decision.comments:
                    lines.append("\n**Comments**:")
                    for comment in decision.comments:
                        lines.append(f"- {comment.author}: {comment.comment}")

                lines.append("")

        return "\n".join(lines)

    # BUILD-146: Test compatibility methods
    def submit_for_review(self, result: Any) -> str:
        """Submit research result for review (test compatibility API).

        Args:
            result: ResearchPhaseResult to review

        Returns:
            Review ID
        """
        review_id = f"review_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        # Determine if we can auto-review
        can_auto = self._can_auto_review(result)

        if can_auto:
            # Auto-review
            review_result = self._auto_review(result)
            status = "completed" if review_result.decision in [ReviewDecisionEnum.APPROVED, ReviewDecisionEnum.REJECTED] else "pending"
        else:
            # Manual review required
            review_result = None
            status = "pending"

        self._pending_reviews[review_id] = {
            "result": result,
            "review_result": review_result,
            "status": status,
            "submitted_at": datetime.now().isoformat()
        }

        return review_id

    def _can_auto_review(self, result: Any) -> bool:
        """Check if result can be auto-reviewed (test compatibility).

        Args:
            result: ResearchPhaseResult

        Returns:
            True if auto-review is possible
        """
        # If human review is required, cannot auto-review
        if self.criteria.require_human_review:
            return False

        # Otherwise can auto-review
        return True

    def _auto_review(self, result: Any) -> ReviewResult:
        """Automatically review research result (test compatibility).

        Args:
            result: ResearchPhaseResult

        Returns:
            ReviewResult with decision
        """
        # Check minimum requirements first (regardless of confidence)
        findings_ok = len(result.findings) >= self.criteria.min_findings_required
        recs_ok = len(result.recommendations) >= self.criteria.min_recommendations_required

        if not findings_ok or not recs_ok:
            # Insufficient data - needs more research
            return ReviewResult(
                decision=ReviewDecisionEnum.NEEDS_MORE_RESEARCH,
                reviewer="auto",
                confidence=result.confidence,
                comments=f"Insufficient findings: {len(result.findings)}/{self.criteria.min_findings_required} or recommendations: {len(result.recommendations)}/{self.criteria.min_recommendations_required}"
            )

        # Check confidence thresholds
        if result.confidence >= self.criteria.auto_approve_confidence:
            return ReviewResult(
                decision=ReviewDecisionEnum.APPROVED,
                reviewer="auto",
                confidence=result.confidence,
                approved_findings=result.findings,
                comments="Auto-approved based on high confidence and sufficient findings"
            )

        elif result.confidence <= self.criteria.auto_reject_confidence:
            return ReviewResult(
                decision=ReviewDecisionEnum.REJECTED,
                reviewer="auto",
                confidence=result.confidence,
                rejected_findings=result.findings,
                comments="Auto-rejected based on low confidence"
            )

        else:
            # Middle range - needs more research
            return ReviewResult(
                decision=ReviewDecisionEnum.NEEDS_MORE_RESEARCH,
                reviewer="auto",
                confidence=result.confidence,
                comments="Confidence in middle range, needs more research"
            )

    def manual_review(
        self,
        review_id: str,
        decision: ReviewDecisionEnum,
        reviewer: str,
        comments: str = ""
    ) -> ReviewResult:
        """Submit manual review decision (test compatibility).

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

        result_data = self._pending_reviews[review_id]["result"]

        review_result = ReviewResult(
            decision=decision,
            reviewer=reviewer,
            confidence=result_data.confidence if hasattr(result_data, 'confidence') else 0.0,
            comments=comments,
            approved_findings=result_data.findings if decision == ReviewDecisionEnum.APPROVED else [],
            rejected_findings=result_data.findings if decision == ReviewDecisionEnum.REJECTED else []
        )

        self._pending_reviews[review_id]["review_result"] = review_result
        self._pending_reviews[review_id]["status"] = "completed"

        return review_result

    def get_review_status(self, review_id: str) -> Dict[str, Any]:
        """Get review status (test compatibility).

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
            "submitted_at": review_data["submitted_at"]
        }

    def export_review_to_build_history(self, review_id: str) -> str:
        """Export review to BUILD_HISTORY format (test compatibility).

        Args:
            review_id: Review ID

        Returns:
            Formatted entry

        Raises:
            ValueError: If review not found or not completed
        """
        if review_id not in self._pending_reviews:
            raise ValueError(f"Review {review_id} not found")

        review_data = self._pending_reviews[review_id]

        if review_data["status"] != "completed":
            raise ValueError(f"Review {review_id} is not completed")

        review_result = review_data["review_result"]

        return f"""## Research Review

**Decision**: {review_result.decision.value}
**Reviewer**: {review_result.reviewer}
**Confidence**: {review_result.confidence:.2f}
**Comments**: {review_result.comments}
"""
