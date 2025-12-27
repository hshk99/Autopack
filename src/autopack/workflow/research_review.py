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

import json

logger = logging.getLogger(__name__)

#
# ---------------------------------------------------------------------------
# Compatibility shims (legacy review workflow API)
# ---------------------------------------------------------------------------
#
# The existing implementation in this module is a review-record store that
# operates on (review_id, phase_id) and evaluates auto-approval based on a list
# of result dicts.
#
# Older tests expect a different surface:
#   - ReviewConfig, ReviewResult
#   - ResearchReviewWorkflow(config=ReviewConfig(...))
#   - review_research(research_result, context)
#   - load_review(session_id)
#   - submit_review(session_id, decision, reviewer, comments, approved_findings)
#   - internal _should_auto_approve + _generate_review_questions
#
# We keep the existing store implementation (renamed) and provide a thin
# compatibility wrapper exported as ResearchReviewWorkflow.
#

class ReviewDecision(Enum):
    """Review decision for research results."""
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"
    PENDING = "pending"


class ReviewPriority(Enum):
    """Priority for review."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class ReviewComment:
    """A comment on research results."""
    author: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchReview:
    """Review record for research phase results."""
    
    review_id: str
    phase_id: str
    decision: ReviewDecision = ReviewDecision.PENDING
    priority: ReviewPriority = ReviewPriority.MEDIUM
    reviewer: Optional[str] = None
    comments: List[ReviewComment] = field(default_factory=list)
    auto_approved: bool = False
    confidence_threshold: float = 0.8
    created_at: datetime = field(default_factory=datetime.now)
    reviewed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "review_id": self.review_id,
            "phase_id": self.phase_id,
            "decision": self.decision.value,
            "priority": self.priority.value,
            "reviewer": self.reviewer,
            "comments": [asdict(c) for c in self.comments],
            "auto_approved": self.auto_approved,
            "confidence_threshold": self.confidence_threshold,
            "created_at": self.created_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ResearchReview:
        """Create from dictionary."""
        return cls(
            review_id=data["review_id"],
            phase_id=data["phase_id"],
            decision=ReviewDecision(data.get("decision", "pending")),
            priority=ReviewPriority(data.get("priority", "medium")),
            reviewer=data.get("reviewer"),
            comments=[
                ReviewComment(
                    author=c["author"],
                    content=c["content"],
                    timestamp=datetime.fromisoformat(c["timestamp"]),
                    metadata=c.get("metadata", {}),
                )
                for c in data.get("comments", [])
            ],
            auto_approved=data.get("auto_approved", False),
            confidence_threshold=data.get("confidence_threshold", 0.8),
            created_at=datetime.fromisoformat(data["created_at"]),
            reviewed_at=datetime.fromisoformat(data["reviewed_at"]) if data.get("reviewed_at") else None,
            metadata=data.get("metadata", {}),
        )


class ResearchReviewStore:
    """Manages persisted review records (store implementation)."""
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize the review workflow.
        
        Args:
            storage_dir: Directory for storing review records
        """
        self.storage_dir = storage_dir or Path(".autopack/reviews")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._reviews: Dict[str, ResearchReview] = {}
        self._load_reviews()
    
    def create_review(
        self,
        phase_id: str,
        priority: ReviewPriority = ReviewPriority.MEDIUM,
        auto_approve_threshold: float = 0.8,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ResearchReview:
        """Create a new review for a research phase.
        
        Args:
            phase_id: ID of the research phase
            priority: Review priority
            auto_approve_threshold: Confidence threshold for auto-approval
            metadata: Additional metadata
            
        Returns:
            Created ResearchReview
        """
        review_id = f"review_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{phase_id}"
        
        review = ResearchReview(
            review_id=review_id,
            phase_id=phase_id,
            priority=priority,
            confidence_threshold=auto_approve_threshold,
            metadata=metadata or {},
        )
        
        self._reviews[review_id] = review
        self._save_review(review)
        
        logger.info(f"Created review {review_id} for phase {phase_id}")
        return review
    
    def evaluate_auto_approval(
        self,
        review_id: str,
        research_results: List[Dict[str, Any]],
    ) -> bool:
        """Evaluate if research results meet auto-approval criteria.
        
        Args:
            review_id: ID of the review
            research_results: Research results to evaluate
            
        Returns:
            True if auto-approved, False otherwise
        """
        review = self._reviews.get(review_id)
        if not review:
            raise ValueError(f"Review not found: {review_id}")
        
        if not research_results:
            logger.info(f"No results to evaluate for review {review_id}")
            return False
        
        # Calculate average confidence
        confidences = [
            result.get("confidence", 0.0)
            for result in research_results
        ]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        # Check if all results have minimum confidence
        min_confidence = min(confidences) if confidences else 0.0
        
        # Auto-approve if average confidence meets threshold and no result is too low
        should_auto_approve = (
            avg_confidence >= review.confidence_threshold
            and min_confidence >= review.confidence_threshold * 0.8
        )
        
        if should_auto_approve:
            review.decision = ReviewDecision.APPROVED
            review.auto_approved = True
            review.reviewed_at = datetime.now()
            review.comments.append(ReviewComment(
                author="system",
                content=f"Auto-approved: average confidence {avg_confidence:.1%} "
                        f"meets threshold {review.confidence_threshold:.1%}",
            ))
            self._save_review(review)
            logger.info(f"Auto-approved review {review_id}")
        
        return should_auto_approve
    
    def submit_review(
        self,
        review_id: str,
        decision: ReviewDecision,
        reviewer: str,
        comment: Optional[str] = None,
    ) -> None:
        """Submit a review decision.
        
        Args:
            review_id: ID of the review
            decision: Review decision
            reviewer: Name/ID of the reviewer
            comment: Optional review comment
        """
        review = self._reviews.get(review_id)
        if not review:
            raise ValueError(f"Review not found: {review_id}")
        
        review.decision = decision
        review.reviewer = reviewer
        review.reviewed_at = datetime.now()
        
        if comment:
            review.comments.append(ReviewComment(
                author=reviewer,
                content=comment,
            ))
        
        self._save_review(review)
        logger.info(f"Review {review_id} submitted: {decision.value} by {reviewer}")
    
    def add_comment(
        self,
        review_id: str,
        author: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a comment to a review.
        
        Args:
            review_id: ID of the review
            author: Comment author
            content: Comment content
            metadata: Additional metadata
        """
        review = self._reviews.get(review_id)
        if not review:
            raise ValueError(f"Review not found: {review_id}")
        
        review.comments.append(ReviewComment(
            author=author,
            content=content,
            metadata=metadata or {},
        ))
        
        self._save_review(review)
        logger.debug(f"Added comment to review {review_id}")
    
    def get_review(self, review_id: str) -> Optional[ResearchReview]:
        """Get a review by ID.
        
        Args:
            review_id: ID of the review
            
        Returns:
            ResearchReview if found, None otherwise
        """
        return self._reviews.get(review_id)
    
    def get_review_by_phase(self, phase_id: str) -> Optional[ResearchReview]:
        """Get review for a specific phase.
        
        Args:
            phase_id: ID of the research phase
            
        Returns:
            ResearchReview if found, None otherwise
        """
        for review in self._reviews.values():
            if review.phase_id == phase_id:
                return review
        return None
    
    def list_pending_reviews(
        self,
        priority: Optional[ReviewPriority] = None,
    ) -> List[ResearchReview]:
        """List pending reviews.
        
        Args:
            priority: Filter by priority
            
        Returns:
            List of pending ResearchReview objects
        """
        reviews = [
            r for r in self._reviews.values()
            if r.decision == ReviewDecision.PENDING
        ]
        
        if priority:
            reviews = [r for r in reviews if r.priority == priority]
        
        # Sort by priority (urgent first) then by created_at
        priority_order = {
            ReviewPriority.URGENT: 0,
            ReviewPriority.HIGH: 1,
            ReviewPriority.MEDIUM: 2,
            ReviewPriority.LOW: 3,
        }
        
        reviews.sort(
            key=lambda r: (priority_order[r.priority], r.created_at),
        )
        
        return reviews
    
    def export_review_history(
        self,
        output_path: Path,
        phase_id: Optional[str] = None,
    ) -> None:
        """Export review history to file.
        
        Args:
            output_path: Path to output file
            phase_id: Optional phase ID to filter by
        """
        reviews = list(self._reviews.values())
        
        if phase_id:
            reviews = [r for r in reviews if r.phase_id == phase_id]
        
        data = {
            "exported_at": datetime.now().isoformat(),
            "total_reviews": len(reviews),
            "reviews": [r.to_dict() for r in reviews],
        }
        
        output_path.write_text(json.dumps(data, indent=2))
        logger.info(f"Exported {len(reviews)} reviews to {output_path}")
    
    def _save_review(self, review: ResearchReview) -> None:
        """Save a review to disk."""
        review_file = self.storage_dir / f"{review.review_id}.json"
        try:
            review_file.write_text(json.dumps(review.to_dict(), indent=2))
        except Exception as e:
            logger.error(f"Error saving review {review.review_id}: {e}")
    
    def _load_reviews(self) -> None:
        """Load all reviews from disk."""
        if not self.storage_dir.exists():
            return
        
        for review_file in self.storage_dir.glob("*.json"):
            try:
                data = json.loads(review_file.read_text())
                review = ResearchReview.from_dict(data)
                self._reviews[review.review_id] = review
            except Exception as e:
                logger.error(f"Error loading review from {review_file}: {e}")
        
        logger.info(f"Loaded {len(self._reviews)} reviews")


def create_review_for_phase(
    phase_id: str,
    research_results: List[Dict[str, Any]],
    auto_approve_threshold: float = 0.8,
    priority: ReviewPriority = ReviewPriority.MEDIUM,
) -> tuple[ResearchReview, bool]:
    """Create and evaluate a review for a research phase.
    
    Args:
        phase_id: ID of the research phase
        research_results: Research results to review
        auto_approve_threshold: Confidence threshold for auto-approval
        priority: Review priority
        
    Returns:
        Tuple of (ResearchReview, was_auto_approved)
    """
    workflow = ResearchReviewStore()
    
    review = workflow.create_review(
        phase_id=phase_id,
        priority=priority,
        auto_approve_threshold=auto_approve_threshold,
    )
    
    auto_approved = workflow.evaluate_auto_approval(
        review_id=review.review_id,
        research_results=research_results,
    )
    
    return review, auto_approved


# ---------------------------------------------------------------------------
# Legacy review workflow API (expected by tests)
# ---------------------------------------------------------------------------


@dataclass
class ReviewConfig:
    auto_approve_threshold: float = 0.8
    require_human_review: bool = True
    review_timeout_seconds: int = 3600
    store_reviews: bool = False
    review_storage_dir: Optional[Path] = None


@dataclass
class ReviewResult:
    research_session_id: str
    decision: ReviewDecision
    reviewer: str
    comments: str = ""
    approved_findings: List[str] = field(default_factory=list)
    additional_questions: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "research_session_id": self.research_session_id,
            "decision": self.decision.value,
            "reviewer": self.reviewer,
            "comments": self.comments,
            "approved_findings": self.approved_findings,
            "additional_questions": self.additional_questions,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewResult":
        return cls(
            research_session_id=data["research_session_id"],
            decision=ReviewDecision(data["decision"]),
            reviewer=data.get("reviewer") or "unknown",
            comments=data.get("comments", ""),
            approved_findings=list(data.get("approved_findings", [])),
            additional_questions=list(data.get("additional_questions", [])),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else datetime.now(),
        )


class ResearchReviewWorkflow:
    """Compatibility wrapper matching the legacy test API."""

    def __init__(self, config: Optional[ReviewConfig] = None):
        self.config = config or ReviewConfig()
        self._storage_dir = self.config.review_storage_dir or Path(".autopack/reviews_compat")
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def _review_path(self, session_id: str) -> Path:
        return self._storage_dir / f"{session_id}_review.json"

    def _should_auto_approve(self, research_result: Any) -> bool:
        if not getattr(research_result, "success", False):
            return False
        confidence = float(getattr(research_result, "confidence_score", 0.0) or 0.0)
        findings = list(getattr(research_result, "findings", []) or [])
        if confidence < float(self.config.auto_approve_threshold):
            return False
        if len(findings) < 3:
            return False
        return True

    def _generate_review_questions(self, research_result: Any) -> List[str]:
        confidence = float(getattr(research_result, "confidence_score", 0.0) or 0.0)
        findings = list(getattr(research_result, "findings", []) or [])
        questions = []
        if confidence < float(self.config.auto_approve_threshold):
            questions.append(
                f"Confidence is {confidence:.2f}. What additional evidence would increase confidence?"
            )
        if len(findings) < 3:
            questions.append("Findings are limited. Are there missing key considerations or sources?")
        if not questions:
            questions.append("Do the findings and recommendations align with the project constraints?")
        return questions

    def review_research(self, research_result: Any, context: Dict[str, Any]) -> ReviewResult:
        session_id = getattr(research_result, "session_id", None) or "unknown_session"

        if self.config.require_human_review:
            decision = ReviewDecision.PENDING
            reviewer = "human_required"
            additional_questions = self._generate_review_questions(research_result)
            approved_findings: List[str] = []
            comments = "Human review required by configuration."
        else:
            if self._should_auto_approve(research_result):
                decision = ReviewDecision.APPROVED
                reviewer = "auto"
                approved_findings = list(getattr(research_result, "findings", []) or [])
                additional_questions = []
                comments = "Auto-approved based on confidence and findings criteria."
            else:
                decision = ReviewDecision.PENDING
                reviewer = "auto"
                approved_findings = []
                additional_questions = self._generate_review_questions(research_result)
                comments = "Not auto-approved; requires further review."

        review = ReviewResult(
            research_session_id=session_id,
            decision=decision,
            reviewer=reviewer,
            comments=comments,
            approved_findings=approved_findings,
            additional_questions=additional_questions,
        )

        if self.config.store_reviews:
            try:
                self._storage_dir.mkdir(parents=True, exist_ok=True)
                self._review_path(session_id).write_text(json.dumps(review.to_dict(), indent=2))
            except Exception as e:
                logger.debug("Failed to store compat review: %s", e)

        return review

    def load_review(self, session_id: str) -> Optional[ReviewResult]:
        path = self._review_path(session_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return ReviewResult.from_dict(data)
        except Exception as e:
            logger.debug("Failed to load compat review %s: %s", session_id, e)
            return None

    def submit_review(
        self,
        session_id: str,
        decision: ReviewDecision,
        reviewer: str,
        comments: str = "",
        approved_findings: Optional[List[str]] = None,
    ) -> ReviewResult:
        review = ReviewResult(
            research_session_id=session_id,
            decision=decision,
            reviewer=reviewer,
            comments=comments,
            approved_findings=list(approved_findings or []),
            additional_questions=[],
        )
        if self.config.store_reviews:
            try:
                self._storage_dir.mkdir(parents=True, exist_ok=True)
                self._review_path(session_id).write_text(json.dumps(review.to_dict(), indent=2))
            except Exception as e:
                logger.debug("Failed to store submitted compat review: %s", e)
        return review


# Backwards-compat alias for callers that still want the old store implementation.
LegacyResearchReviewWorkflow = ResearchReviewStore
