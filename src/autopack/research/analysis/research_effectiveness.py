"""
Research Cycle Outcome Tracking and Effectiveness Analysis.

IMP-SEG-002: Measures if follow-up research improved decision quality.
Tracks research cycle outcomes and enables continuous improvement through
feedback loops.

Provides:
- Research cycle effectiveness metrics
- Decision quality measurement
- Outcome tracking vs expected improvements
- Feedback loops for continuous improvement
- Outcome reporting and analysis
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ResearchOutcomeType(Enum):
    """Types of research cycle outcomes."""

    DECISION_MADE = "decision_made"  # Research led to a clear decision
    CONFIDENCE_IMPROVED = "confidence_improved"  # Confidence in decision increased
    RISK_IDENTIFIED = "risk_identified"  # Research identified new risks
    OPPORTUNITY_DISCOVERED = "opportunity_discovered"  # New opportunities found
    QUESTION_RESOLVED = "question_resolved"  # Research answered key questions
    BLOCKED = "blocked"  # Research could not progress further
    INCONCLUSIVE = "inconclusive"  # Research findings were inconclusive


class DecisionQualityLevel(Enum):
    """Assessment of decision quality after research."""

    EXCELLENT = "excellent"  # High confidence, comprehensive information
    GOOD = "good"  # Adequate confidence, sufficient information
    FAIR = "fair"  # Moderate confidence, some gaps remain
    POOR = "poor"  # Low confidence, significant gaps remain
    UNKNOWN = "unknown"  # Quality not yet assessed


class FeedbackCategory(Enum):
    """Categories of feedback for loop improvement."""

    RESEARCH_QUALITY = "research_quality"  # Quality of research findings
    DECISION_IMPACT = "decision_impact"  # Impact of decisions made
    TIME_EFFICIENCY = "time_efficiency"  # Time spent vs value gained
    COST_EFFICIENCY = "cost_efficiency"  # Cost spent vs value gained
    TRIGGER_EFFECTIVENESS = "trigger_effectiveness"  # Quality of trigger detection
    PATTERN_REUSE = "pattern_reuse"  # Reuse of successful patterns


@dataclass
class ResearchCycleOutcome:
    """Record of a complete research cycle outcome.

    IMP-SEG-002: Tracks what happened as a result of a research cycle,
    including decision quality improvements and follow-up research effectiveness.

    Attributes:
        cycle_id: Unique identifier for this research cycle
        research_session_id: Associated research session ID
        outcome_type: Type of outcome achieved
        decision_quality_before: Quality assessment before research
        decision_quality_after: Quality assessment after research
        confidence_before: Confidence level before research (0-100)
        confidence_after: Confidence level after research (0-100)
        time_spent_seconds: Total time spent on this cycle
        research_cost: Cost of research (in API tokens or units)
        key_findings: List of important findings from research
        decisions_made: Decisions that resulted from research
        risks_identified: Risks discovered during research
        questions_resolved: Questions answered by research
        follow_up_triggers_executed: Number of follow-up triggers executed
        follow_up_triggers_successful: Number of successful follow-up triggers
        created_at: When the cycle started
        completed_at: When the cycle completed
        improvement_notes: Notes on how to improve future cycles
    """

    cycle_id: str
    research_session_id: str
    outcome_type: ResearchOutcomeType
    decision_quality_before: DecisionQualityLevel = DecisionQualityLevel.UNKNOWN
    decision_quality_after: DecisionQualityLevel = DecisionQualityLevel.UNKNOWN
    confidence_before: int = 0  # 0-100
    confidence_after: int = 0  # 0-100
    time_spent_seconds: int = 0
    research_cost: float = 0.0
    key_findings: List[str] = field(default_factory=list)
    decisions_made: List[str] = field(default_factory=list)
    risks_identified: List[str] = field(default_factory=list)
    questions_resolved: List[str] = field(default_factory=list)
    follow_up_triggers_executed: int = 0
    follow_up_triggers_successful: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    improvement_notes: str = ""

    def calculate_quality_improvement(self) -> int:
        """Calculate quality improvement from before to after research.

        Returns:
            Quality improvement score (0-100).
        """
        quality_scores = {
            DecisionQualityLevel.EXCELLENT: 100,
            DecisionQualityLevel.GOOD: 75,
            DecisionQualityLevel.FAIR: 50,
            DecisionQualityLevel.POOR: 25,
            DecisionQualityLevel.UNKNOWN: 0,
        }
        before = quality_scores.get(self.decision_quality_before, 0)
        after = quality_scores.get(self.decision_quality_after, 0)
        return after - before

    def calculate_confidence_improvement(self) -> int:
        """Calculate confidence improvement from before to after research.

        Returns:
            Confidence improvement percentage points (-100 to 100).
        """
        return self.confidence_after - self.confidence_before

    def calculate_roi(self) -> float:
        """Calculate return on investment for this research cycle.

        Returns:
            ROI as a ratio (1.0 = break even, 2.0 = double value).
        """
        if self.research_cost == 0:
            return float("inf")

        # Value is measured as combination of quality improvement and decisions made
        quality_value = self.calculate_quality_improvement()
        decision_value = len(self.decisions_made) * 10
        findings_value = len(self.key_findings) * 5
        total_value = quality_value + decision_value + findings_value

        return total_value / self.research_cost if self.research_cost > 0 else 1.0

    def is_successful(self) -> bool:
        """Determine if this research cycle was successful.

        Returns:
            True if quality or confidence improved, or findings were made.
        """
        return (
            self.calculate_quality_improvement() > 0
            or self.calculate_confidence_improvement() > 0
            or len(self.key_findings) > 0
            or self.outcome_type
            in (
                ResearchOutcomeType.DECISION_MADE,
                ResearchOutcomeType.CONFIDENCE_IMPROVED,
                ResearchOutcomeType.OPPORTUNITY_DISCOVERED,
                ResearchOutcomeType.QUESTION_RESOLVED,
            )
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "cycle_id": self.cycle_id,
            "research_session_id": self.research_session_id,
            "outcome_type": self.outcome_type.value,
            "decision_quality_before": self.decision_quality_before.value,
            "decision_quality_after": self.decision_quality_after.value,
            "confidence_before": self.confidence_before,
            "confidence_after": self.confidence_after,
            "confidence_improvement": self.calculate_confidence_improvement(),
            "quality_improvement": self.calculate_quality_improvement(),
            "time_spent_seconds": self.time_spent_seconds,
            "research_cost": self.research_cost,
            "roi": round(self.calculate_roi(), 2),
            "key_findings_count": len(self.key_findings),
            "decisions_made_count": len(self.decisions_made),
            "risks_identified_count": len(self.risks_identified),
            "questions_resolved_count": len(self.questions_resolved),
            "follow_up_triggers_executed": self.follow_up_triggers_executed,
            "follow_up_triggers_successful": self.follow_up_triggers_successful,
            "was_successful": self.is_successful(),
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "improvement_notes": self.improvement_notes,
        }


@dataclass
class ResearchEffectivenessMetrics:
    """Aggregated metrics for research cycle effectiveness.

    IMP-SEG-002: Measures overall effectiveness of research cycles,
    including success rates, quality improvements, and ROI metrics.

    Attributes:
        total_cycles: Total number of research cycles tracked
        successful_cycles: Number of cycles that improved decisions
        confidence_improvement_avg: Average confidence improvement
        quality_improvement_avg: Average quality improvement
        roi_avg: Average return on investment
        follow_up_trigger_success_rate: Percentage of successful follow-up triggers
        cost_per_successful_decision: Average cost to achieve a successful outcome
        time_per_successful_decision: Average time to achieve a successful outcome
        outcome_distribution: Breakdown of outcome types
        decision_quality_distribution: Distribution of decision quality assessments
        tracked_since: When metrics collection started
    """

    total_cycles: int = 0
    successful_cycles: int = 0
    confidence_improvement_avg: float = 0.0
    quality_improvement_avg: float = 0.0
    roi_avg: float = 0.0
    follow_up_trigger_success_rate: float = 0.0
    cost_per_successful_decision: float = 0.0
    time_per_successful_decision: float = 0.0
    outcome_distribution: Dict[str, int] = field(default_factory=dict)
    decision_quality_distribution: Dict[str, int] = field(default_factory=dict)
    tracked_since: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def success_rate(self) -> float:
        """Calculate the success rate of research cycles.

        Returns:
            Success rate as a percentage (0-100).
        """
        if self.total_cycles == 0:
            return 0.0
        return (self.successful_cycles / self.total_cycles) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_cycles": self.total_cycles,
            "successful_cycles": self.successful_cycles,
            "success_rate_percent": round(self.success_rate(), 2),
            "confidence_improvement_avg": round(self.confidence_improvement_avg, 2),
            "quality_improvement_avg": round(self.quality_improvement_avg, 2),
            "roi_avg": round(self.roi_avg, 2),
            "follow_up_trigger_success_rate": round(
                self.follow_up_trigger_success_rate, 4
            ),
            "cost_per_successful_decision": round(
                self.cost_per_successful_decision, 2
            ),
            "time_per_successful_decision": round(
                self.time_per_successful_decision, 2
            ),
            "outcome_distribution": self.outcome_distribution,
            "decision_quality_distribution": self.decision_quality_distribution,
            "tracked_since": self.tracked_since.isoformat(),
        }


@dataclass
class ResearchEffectivenessFeedback:
    """Feedback for improving research effectiveness.

    IMP-SEG-002: Captures feedback about research cycles that can be used
    to improve future research.

    Attributes:
        cycle_id: Associated research cycle ID
        category: Category of feedback
        feedback_text: Detailed feedback
        priority: Priority of this feedback item (1-10)
        action_suggested: Suggested action to improve
        created_at: When feedback was created
    """

    cycle_id: str
    category: FeedbackCategory
    feedback_text: str
    priority: int = 5  # 1-10
    action_suggested: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "cycle_id": self.cycle_id,
            "category": self.category.value,
            "feedback_text": self.feedback_text,
            "priority": self.priority,
            "action_suggested": self.action_suggested,
            "created_at": self.created_at.isoformat(),
        }


class ResearchEffectivenessAnalyzer:
    """Analyzes and tracks research cycle effectiveness.

    IMP-SEG-002: Measures if follow-up research improved decision quality
    and provides feedback loops for continuous improvement.

    This analyzer tracks:
    - Research cycle outcomes and their impact
    - Decision quality improvements
    - Follow-up research effectiveness
    - Cost and time efficiency
    - Feedback for future improvements
    """

    def __init__(self):
        """Initialize the research effectiveness analyzer."""
        self.outcomes: List[ResearchCycleOutcome] = []
        self.feedback: List[ResearchEffectivenessFeedback] = []
        self.metrics = ResearchEffectivenessMetrics()
        logger.info("ResearchEffectivenessAnalyzer initialized")

    def record_outcome(self, outcome: ResearchCycleOutcome) -> None:
        """Record a research cycle outcome.

        IMP-SEG-002: Tracks research cycle outcomes for analysis and feedback.

        Args:
            outcome: The research cycle outcome to record.
        """
        self.outcomes.append(outcome)
        self._update_metrics()
        logger.info(
            f"Recorded research cycle outcome: {outcome.cycle_id} "
            f"(type={outcome.outcome_type.value}, "
            f"quality={outcome.decision_quality_after.value})"
        )

    def record_feedback(self, feedback: ResearchEffectivenessFeedback) -> None:
        """Record feedback about a research cycle.

        Args:
            feedback: The feedback to record.
        """
        self.feedback.append(feedback)
        logger.info(
            f"Recorded feedback for cycle {feedback.cycle_id}: "
            f"{feedback.category.value}"
        )

    def _update_metrics(self) -> None:
        """Update aggregated effectiveness metrics based on recorded outcomes."""
        if not self.outcomes:
            return

        # Basic counts
        self.metrics.total_cycles = len(self.outcomes)
        self.metrics.successful_cycles = sum(
            1 for o in self.outcomes if o.is_successful()
        )

        # Average improvements
        confidence_improvements = [o.calculate_confidence_improvement() for o in self.outcomes]
        quality_improvements = [o.calculate_quality_improvement() for o in self.outcomes]
        rois = [o.calculate_roi() for o in self.outcomes]

        if confidence_improvements:
            self.metrics.confidence_improvement_avg = sum(confidence_improvements) / len(
                confidence_improvements
            )
        if quality_improvements:
            self.metrics.quality_improvement_avg = sum(quality_improvements) / len(
                quality_improvements
            )
        if rois:
            self.metrics.roi_avg = sum(rois) / len(rois)

        # Follow-up trigger success rate
        total_triggers = sum(o.follow_up_triggers_executed for o in self.outcomes)
        successful_triggers = sum(
            o.follow_up_triggers_successful for o in self.outcomes
        )
        if total_triggers > 0:
            self.metrics.follow_up_trigger_success_rate = successful_triggers / total_triggers

        # Cost and time per successful decision
        successful_outcomes = [o for o in self.outcomes if o.is_successful()]
        if successful_outcomes:
            total_cost = sum(o.research_cost for o in successful_outcomes)
            total_time = sum(o.time_spent_seconds for o in successful_outcomes)
            self.metrics.cost_per_successful_decision = (
                total_cost / len(successful_outcomes)
            )
            self.metrics.time_per_successful_decision = (
                total_time / len(successful_outcomes)
            )

        # Outcome distribution
        self.metrics.outcome_distribution = {}
        for outcome_type in ResearchOutcomeType:
            count = sum(1 for o in self.outcomes if o.outcome_type == outcome_type)
            if count > 0:
                self.metrics.outcome_distribution[outcome_type.value] = count

        # Decision quality distribution
        self.metrics.decision_quality_distribution = {}
        for quality_level in DecisionQualityLevel:
            count = sum(
                1 for o in self.outcomes
                if o.decision_quality_after == quality_level
            )
            if count > 0:
                self.metrics.decision_quality_distribution[quality_level.value] = count

    def get_metrics(self) -> ResearchEffectivenessMetrics:
        """Get current aggregated effectiveness metrics.

        Returns:
            Current research effectiveness metrics.
        """
        return self.metrics

    def get_outcome(self, cycle_id: str) -> Optional[ResearchCycleOutcome]:
        """Get a specific research cycle outcome by ID.

        Args:
            cycle_id: The cycle ID to look up.

        Returns:
            The outcome if found, None otherwise.
        """
        for outcome in self.outcomes:
            if outcome.cycle_id == cycle_id:
                return outcome
        return None

    def get_outcomes_by_type(
        self, outcome_type: ResearchOutcomeType
    ) -> List[ResearchCycleOutcome]:
        """Get all outcomes of a specific type.

        Args:
            outcome_type: The outcome type to filter by.

        Returns:
            List of matching outcomes.
        """
        return [o for o in self.outcomes if o.outcome_type == outcome_type]

    def get_recent_outcomes(self, limit: int = 10) -> List[ResearchCycleOutcome]:
        """Get the most recent research cycle outcomes.

        Args:
            limit: Maximum number of outcomes to return.

        Returns:
            List of recent outcomes (newest first).
        """
        return sorted(self.outcomes, key=lambda o: o.created_at, reverse=True)[
            :limit
        ]

    def get_high_priority_feedback(self) -> List[ResearchEffectivenessFeedback]:
        """Get high priority feedback items for improvement.

        Returns:
            List of feedback items sorted by priority (highest first).
        """
        return sorted(self.feedback, key=lambda f: f.priority, reverse=True)

    def generate_improvement_report(self) -> Dict[str, Any]:
        """Generate a comprehensive improvement report.

        IMP-SEG-002: Provides actionable insights for improving research effectiveness.

        Returns:
            Dictionary containing improvement insights and recommendations.
        """
        report = {
            "report_generated_at": datetime.now(timezone.utc).isoformat(),
            "metrics": self.metrics.to_dict(),
            "recent_outcomes": [o.to_dict() for o in self.get_recent_outcomes(5)],
            "high_priority_feedback": [
                f.to_dict() for f in self.get_high_priority_feedback()[:5]
            ],
            "insights": [],
            "recommendations": [],
        }

        # Generate insights
        if self.metrics.success_rate() < 50:
            report["insights"].append(
                "Research cycle success rate is below 50%. Investigate root causes."
            )

        if self.metrics.roi_avg < 1.0:
            report["insights"].append(
                "Average ROI is below break-even. Research may be too expensive relative to value."
            )

        if self.metrics.follow_up_trigger_success_rate < 0.5:
            report["insights"].append(
                "Follow-up trigger success rate is low. Consider refining trigger detection."
            )

        if self.metrics.confidence_improvement_avg > 30:
            report["insights"].append(
                "Strong confidence improvements. Research is effectively reducing uncertainty."
            )

        # Generate recommendations
        if self.metrics.roi_avg < 1.0:
            report["recommendations"].append(
                "Optimize research budgets to improve cost-effectiveness."
            )

        if self.metrics.follow_up_trigger_success_rate < 0.5:
            report["recommendations"].append(
                "Improve follow-up trigger detection mechanism."
            )

        if len(self.feedback) > 0:
            report["recommendations"].append(
                f"Address {len(self.feedback)} feedback items for improvement."
            )

        # Outcome distribution analysis
        if self.metrics.outcome_distribution:
            most_common_outcome = max(
                self.metrics.outcome_distribution.items(), key=lambda x: x[1]
            )
            report["insights"].append(
                f"Most common outcome type: {most_common_outcome[0]} "
                f"({most_common_outcome[1]} cycles)"
            )

        return report

    def export_outcomes(self) -> List[Dict[str, Any]]:
        """Export all recorded outcomes as dictionaries.

        Returns:
            List of outcomes in dictionary format.
        """
        return [o.to_dict() for o in self.outcomes]

    def export_feedback(self) -> List[Dict[str, Any]]:
        """Export all recorded feedback as dictionaries.

        Returns:
            List of feedback items in dictionary format.
        """
        return [f.to_dict() for f in self.feedback]
