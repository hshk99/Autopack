"""Review Workflow for Research Results.

Provides approval/rejection workflow for research results before proceeding
to implementation phases. Integrates with autonomous executor to gate
risky decisions based on research quality and confidence.

Design Principles:
- Non-blocking: workflow can be bypassed in high-confidence scenarios
- Auditable: all decisions logged with reasoning
- Configurable: thresholds and rules can be adjusted
- Integration-ready: works with existing phase lifecycle
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ReviewDecision(str, Enum):
    """Possible review decisions."""

    APPROVED = "approved"  # Research approved, proceed to implementation
    REJECTED = "rejected"  # Research rejected, needs revision
    NEEDS_REVISION = "needs_revision"  # Research needs improvement
    DEFERRED = "deferred"  # Decision deferred to human reviewer
    AUTO_APPROVED = "auto_approved"  # Automatically approved (high confidence)


class ReviewReason(str, Enum):
    """Reasons for review decisions."""

    HIGH_QUALITY = "high_quality"  # Quality score above threshold
    LOW_QUALITY = "low_quality"  # Quality score below threshold
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"  # Not enough evidence
    CONFLICTING_EVIDENCE = "conflicting_evidence"  # Evidence contradicts
    HIGH_RISK = "high_risk"  # Implementation risk too high
    MISSING_GOALS = "missing_goals"  # Required goals not achieved
    CONFIDENCE_TOO_LOW = "confidence_too_low"  # Confidence below threshold
    MANUAL_REVIEW_REQUIRED = "manual_review_required"  # Human review needed


@dataclass
class ReviewCriteria:
    """Criteria for evaluating research results."""

    min_quality_score: float = 0.7  # Minimum quality score (0.0-1.0)
    min_confidence: float = 0.6  # Minimum average confidence
    min_evidence_count: int = 3  # Minimum evidence items
    required_goal_achievement_rate: float = 0.8  # % of required goals achieved
    max_conflicting_evidence_ratio: float = 0.3  # Max ratio of conflicting evidence
    auto_approve_threshold: float = 0.9  # Auto-approve above this quality
    require_human_review_below: float = 0.5  # Require human review below this


@dataclass
class ReviewResult:
    """Result of research review."""

    review_id: str
    session_id: str
    decision: ReviewDecision
    reasons: List[ReviewReason] = field(default_factory=list)
    quality_score: float = 0.0
    confidence_score: float = 0.0
    evidence_count: int = 0
    goal_achievement_rate: float = 0.0
    reviewer: str = "automated"  # "automated" or human identifier
    reviewed_at: datetime = field(default_factory=datetime.now)
    notes: Optional[str] = None
    recommendations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "review_id": self.review_id,
            "session_id": self.session_id,
            "decision": self.decision.value,
            "reasons": [r.value for r in self.reasons],
            "quality_score": self.quality_score,
            "confidence_score": self.confidence_score,
            "evidence_count": self.evidence_count,
            "goal_achievement_rate": self.goal_achievement_rate,
            "reviewer": self.reviewer,
            "reviewed_at": self.reviewed_at.isoformat(),
            "notes": self.notes,
            "recommendations": self.recommendations,
            "metadata": self.metadata,
        }


class ResearchReviewWorkflow:
    """Workflow for reviewing research results before implementation."""

    def __init__(
        self,
        project_root: Path,
        db_session: Optional[Session] = None,
        criteria: Optional[ReviewCriteria] = None,
    ):
        """
        Initialize review workflow.

        Args:
            project_root: Root directory of the project
            db_session: Optional database session
            criteria: Review criteria (uses defaults if not provided)
        """
        self.project_root = project_root
        self._db_session = db_session
        self.criteria = criteria or ReviewCriteria()
        self.review_dir = project_root / ".autonomous_runs" / "reviews"
        self.review_dir.mkdir(parents=True, exist_ok=True)

    def review_research_session(
        self, session_data: Dict[str, Any]
    ) -> ReviewResult:
        """
        Review a research session and make approval decision.

        Args:
            session_data: Research session data dictionary

        Returns:
            ReviewResult with decision and reasoning
        """
        session_id = session_data.get("session_id", "unknown")
        review_id = f"review-{session_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        logger.info(f"Starting review for session {session_id}")

        # Extract metrics
        quality_score = session_data.get("quality_score", 0.0)
        evidence = session_data.get("evidence", [])
        insights = session_data.get("insights", [])
        goals = session_data.get("goals", [])

        # Calculate metrics
        evidence_count = len(evidence)
        avg_confidence = self._calculate_average_confidence(evidence)
        goal_achievement_rate = self._calculate_goal_achievement_rate(goals)
        conflicting_ratio = self._detect_conflicting_evidence(evidence)

        # Initialize result
        result = ReviewResult(
            review_id=review_id,
            session_id=session_id,
            decision=ReviewDecision.APPROVED,  # Default, will be updated
            quality_score=quality_score,
            confidence_score=avg_confidence,
            evidence_count=evidence_count,
            goal_achievement_rate=goal_achievement_rate,
        )

        # Apply review criteria
        reasons = []

        # Check for auto-approval
        if quality_score >= self.criteria.auto_approve_threshold:
            result.decision = ReviewDecision.AUTO_APPROVED
            reasons.append(ReviewReason.HIGH_QUALITY)
            result.notes = f"Auto-approved: quality score {quality_score:.2f} exceeds threshold {self.criteria.auto_approve_threshold}"
            logger.info(f"Auto-approved session {session_id} (quality: {quality_score:.2f})")
        # Check for mandatory human review
        elif quality_score < self.criteria.require_human_review_below:
            result.decision = ReviewDecision.DEFERRED
            reasons.append(ReviewReason.LOW_QUALITY)
            reasons.append(ReviewReason.MANUAL_REVIEW_REQUIRED)
            result.notes = f"Deferred to human review: quality score {quality_score:.2f} below threshold {self.criteria.require_human_review_below}"
            logger.warning(f"Session {session_id} requires human review (quality: {quality_score:.2f})")
        else:
            # Apply detailed criteria
            if quality_score < self.criteria.min_quality_score:
                reasons.append(ReviewReason.LOW_QUALITY)
                result.recommendations.append(
                    f"Improve research quality (current: {quality_score:.2f}, required: {self.criteria.min_quality_score})"
                )

            if avg_confidence < self.criteria.min_confidence:
                reasons.append(ReviewReason.CONFIDENCE_TOO_LOW)
                result.recommendations.append(
                    f"Increase evidence confidence (current: {avg_confidence:.2f}, required: {self.criteria.min_confidence})"
                )

            if evidence_count < self.criteria.min_evidence_count:
                reasons.append(ReviewReason.INSUFFICIENT_EVIDENCE)
                result.recommendations.append(
                    f"Collect more evidence (current: {evidence_count}, required: {self.criteria.min_evidence_count})"
                )

            if goal_achievement_rate < self.criteria.required_goal_achievement_rate:
                reasons.append(ReviewReason.MISSING_GOALS)
                result.recommendations.append(
                    f"Achieve more research goals (current: {goal_achievement_rate:.1%}, required: {self.criteria.required_goal_achievement_rate:.1%})"
                )

            if conflicting_ratio > self.criteria.max_conflicting_evidence_ratio:
                reasons.append(ReviewReason.CONFLICTING_EVIDENCE)
                result.recommendations.append(
                    f"Resolve conflicting evidence (ratio: {conflicting_ratio:.1%})"
                )

            # Make final decision
            if reasons:
                if len(reasons) >= 3 or ReviewReason.LOW_QUALITY in reasons:
                    result.decision = ReviewDecision.REJECTED
                    result.notes = "Research rejected due to multiple quality issues"
                else:
                    result.decision = ReviewDecision.NEEDS_REVISION
                    result.notes = "Research needs minor improvements before approval"
            else:
                result.decision = ReviewDecision.APPROVED
                reasons.append(ReviewReason.HIGH_QUALITY)
                result.notes = "Research approved: meets all quality criteria"

        result.reasons = reasons

        # Persist review result
        self._save_review_result(result)

        logger.info(
            f"Review complete for {session_id}: {result.decision.value} "
            f"(quality: {quality_score:.2f}, confidence: {avg_confidence:.2f})"
        )

        return result

    def _calculate_average_confidence(self, evidence: List[Dict[str, Any]]) -> float:
        """Calculate average confidence across all evidence."""
        if not evidence:
            return 0.0
        confidences = [e.get("confidence", 0.0) for e in evidence]
        return sum(confidences) / len(confidences)

    def _calculate_goal_achievement_rate(self, goals: List[Dict[str, Any]]) -> float:
        """Calculate percentage of required goals achieved."""
        if not goals:
            return 0.0
        required_goals = [g for g in goals if g.get("required", True)]
        if not required_goals:
            return 1.0  # No required goals = 100% achievement
        achieved = sum(1 for g in required_goals if g.get("status") == "achieved")
        return achieved / len(required_goals)

    def _detect_conflicting_evidence(self, evidence: List[Dict[str, Any]]) -> float:
        """Detect ratio of potentially conflicting evidence."""
        if len(evidence) < 2:
            return 0.0

        # Simple heuristic: evidence with low relevance scores might conflict
        low_relevance = sum(
            1 for e in evidence if e.get("relevance_score", 1.0) < 0.5
        )
        return low_relevance / len(evidence)

    def _save_review_result(self, result: ReviewResult) -> None:
        """Save review result to disk."""
        review_file = self.review_dir / f"{result.review_id}.json"
        review_file.write_text(
            json.dumps(result.to_dict(), indent=2), encoding="utf-8"
        )
        logger.debug(f"Saved review result to {review_file}")

    def get_review_history(self, session_id: str) -> List[ReviewResult]:
        """Get all reviews for a session."""
        reviews = []
        for review_file in self.review_dir.glob(f"review-{session_id}-*.json"):
            try:
                data = json.loads(review_file.read_text(encoding="utf-8"))
                reviews.append(
                    ReviewResult(
                        review_id=data["review_id"],
                        session_id=data["session_id"],
                        decision=ReviewDecision(data["decision"]),
                        reasons=[ReviewReason(r) for r in data["reasons"]],
                        quality_score=data["quality_score"],
                        confidence_score=data["confidence_score"],
                        evidence_count=data["evidence_count"],
                        goal_achievement_rate=data["goal_achievement_rate"],
                        reviewer=data["reviewer"],
                        reviewed_at=datetime.fromisoformat(data["reviewed_at"]),
                        notes=data.get("notes"),
                        recommendations=data.get("recommendations", []),
                        metadata=data.get("metadata", {}),
                    )
                )
            except Exception as e:
                logger.error(f"Failed to load review {review_file}: {e}")
        return sorted(reviews, key=lambda r: r.reviewed_at, reverse=True)

    def should_proceed_to_implementation(
        self, session_id: str
    ) -> tuple[bool, Optional[ReviewResult]]:
        """
        Check if research session is approved for implementation.

        Args:
            session_id: Research session ID

        Returns:
            Tuple of (should_proceed, latest_review_result)
        """
        reviews = self.get_review_history(session_id)
        if not reviews:
            logger.warning(f"No reviews found for session {session_id}")
            return False, None

        latest_review = reviews[0]
        should_proceed = latest_review.decision in [
            ReviewDecision.APPROVED,
            ReviewDecision.AUTO_APPROVED,
        ]

        return should_proceed, latest_review
