"""Research Phase Implementation for Autonomous Build System.

This module implements the RESEARCH phase type, which enables the autonomous
executor to conduct research sessions before making implementation decisions.

Research phases are used when:
- A task requires external knowledge gathering
- Multiple implementation approaches need evaluation
- Domain-specific context is needed for decision-making
- Evidence collection is required before proceeding

Design Principles:
- Research phases are non-destructive (read-only operations)
- Results are persisted for audit and reuse
- Integrates with existing phase lifecycle
- Supports iterative refinement of research goals
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ResearchPhaseState(str, Enum):
    """States specific to research phases."""

    INITIALIZING = "initializing"  # Setting up research context
    GATHERING = "gathering"  # Collecting evidence from sources
    ANALYZING = "analyzing"  # Processing collected evidence
    SYNTHESIZING = "synthesizing"  # Combining findings into insights
    VALIDATING = "validating"  # Verifying research quality
    COMPLETED = "completed"  # Research finished successfully
    FAILED = "failed"  # Research could not be completed
    BLOCKED = "blocked"  # Waiting for external input


class ResearchSourceType(str, Enum):
    """Types of research sources."""

    CODEBASE = "codebase"  # Local code analysis
    DOCUMENTATION = "documentation"  # Project docs
    BUILD_HISTORY = "build_history"  # Past build decisions
    EXTERNAL_API = "external_api"  # External service queries
    WEB_SEARCH = "web_search"  # Web-based research
    GITHUB = "github"  # GitHub repositories/issues
    STACK_OVERFLOW = "stack_overflow"  # Q&A sites


@dataclass
class ResearchGoal:
    """A specific goal for the research phase."""

    goal_id: str
    description: str
    priority: int = 1  # 1 = highest priority
    required: bool = True
    success_criteria: List[str] = field(default_factory=list)
    evidence_needed: List[str] = field(default_factory=list)
    status: str = "pending"  # pending, in_progress, achieved, failed
    findings: List[str] = field(default_factory=list)


@dataclass
class ResearchEvidence:
    """Evidence collected during research."""

    evidence_id: str
    source_type: ResearchSourceType
    source_url: Optional[str]
    content: str
    relevance_score: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    collected_at: datetime = field(default_factory=datetime.now)
    goal_ids: List[str] = field(default_factory=list)  # Goals this supports
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchInsight:
    """Synthesized insight from research evidence."""

    insight_id: str
    insight_type: str  # recommendation, warning, pattern, opportunity
    description: str
    confidence: float  # 0.0 to 1.0
    supporting_evidence: List[str] = field(default_factory=list)  # evidence_ids
    actionable: bool = True
    recommendation: Optional[str] = None


@dataclass
class ResearchSession:
    """Complete research session with all collected data."""

    session_id: str
    phase_id: str
    run_id: str
    state: ResearchPhaseState = ResearchPhaseState.INITIALIZING
    goals: List[ResearchGoal] = field(default_factory=list)
    evidence: List[ResearchEvidence] = field(default_factory=list)
    insights: List[ResearchInsight] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    iteration_count: int = 0
    max_iterations: int = 5
    quality_score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "phase_id": self.phase_id,
            "run_id": self.run_id,
            "state": self.state.value,
            "goals": [
                {
                    "goal_id": g.goal_id,
                    "description": g.description,
                    "priority": g.priority,
                    "required": g.required,
                    "success_criteria": g.success_criteria,
                    "evidence_needed": g.evidence_needed,
                    "status": g.status,
                    "findings": g.findings,
                }
                for g in self.goals
            ],
            "evidence": [
                {
                    "evidence_id": e.evidence_id,
                    "source_type": e.source_type.value,
                    "source_url": e.source_url,
                    "content": e.content[:500] + "..." if len(e.content) > 500 else e.content,
                    "relevance_score": e.relevance_score,
                    "confidence": e.confidence,
                    "collected_at": e.collected_at.isoformat(),
                    "goal_ids": e.goal_ids,
                }
                for e in self.evidence
            ],
            "insights": [
                {
                    "insight_id": i.insight_id,
                    "insight_type": i.insight_type,
                    "description": i.description,
                    "confidence": i.confidence,
                    "supporting_evidence": i.supporting_evidence,
                    "actionable": i.actionable,
                    "recommendation": i.recommendation,
                }
                for i in self.insights
            ],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "iteration_count": self.iteration_count,
            "max_iterations": self.max_iterations,
            "quality_score": self.quality_score,
        }


class ResearchPhaseExecutor:
    """Executes research phases within the autonomous build system."""

    def __init__(
        self,
        project_root: Path,
        db_session: Optional[Session] = None,
        max_iterations: int = 5,
    ):
        """
        Initialize the research phase executor.

        Args:
            project_root: Root directory of the project
            db_session: Optional database session for persistence
            max_iterations: Maximum research iterations before stopping
        """
        self.project_root = project_root
        self._db_session = db_session
        self.max_iterations = max_iterations
        self._active_session: Optional[ResearchSession] = None

    def create_session(
        self,
        phase_id: str,
        run_id: str,
        goals: List[Dict[str, Any]],
    ) -> ResearchSession:
        """
        Create a new research session.

        Args:
            phase_id: ID of the phase this research belongs to
            run_id: ID of the run this phase belongs to
            goals: List of research goals with descriptions

        Returns:
            New ResearchSession instance
        """
        session_id = f"research-{phase_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        research_goals = [
            ResearchGoal(
                goal_id=f"goal-{i}",
                description=g.get("description", ""),
                priority=g.get("priority", 1),
                required=g.get("required", True),
                success_criteria=g.get("success_criteria", []),
                evidence_needed=g.get("evidence_needed", []),
            )
            for i, g in enumerate(goals)
        ]

        session = ResearchSession(
            session_id=session_id,
            phase_id=phase_id,
            run_id=run_id,
            goals=research_goals,
            max_iterations=self.max_iterations,
        )

        self._active_session = session
        logger.info(f"Created research session: {session_id} with {len(goals)} goals")

        return session

    def add_evidence(
        self,
        source_type: ResearchSourceType,
        content: str,
        relevance_score: float,
        confidence: float,
        source_url: Optional[str] = None,
        goal_ids: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ResearchEvidence:
        """
        Add evidence to the active research session.

        Args:
            source_type: Type of source the evidence came from
            content: The evidence content
            relevance_score: How relevant this is (0.0-1.0)
            confidence: Confidence in the evidence (0.0-1.0)
            source_url: Optional URL of the source
            goal_ids: Optional list of goal IDs this supports
            metadata: Optional additional metadata

        Returns:
            The created ResearchEvidence instance
        """
        if not self._active_session:
            raise RuntimeError("No active research session")

        evidence_id = f"evidence-{len(self._active_session.evidence)}"

        evidence = ResearchEvidence(
            evidence_id=evidence_id,
            source_type=source_type,
            source_url=source_url,
            content=content,
            relevance_score=relevance_score,
            confidence=confidence,
            goal_ids=goal_ids or [],
            metadata=metadata or {},
        )

        self._active_session.evidence.append(evidence)
        self._active_session.updated_at = datetime.now()

        logger.debug(f"Added evidence {evidence_id} from {source_type.value}")

        return evidence

    def synthesize_insights(self) -> List[ResearchInsight]:
        """
        Synthesize insights from collected evidence.

        Returns:
            List of synthesized insights
        """
        if not self._active_session:
            raise RuntimeError("No active research session")

        self._active_session.state = ResearchPhaseState.SYNTHESIZING
        insights = []

        # Group evidence by goal
        goal_evidence: Dict[str, List[ResearchEvidence]] = {}
        for evidence in self._active_session.evidence:
            for goal_id in evidence.goal_ids:
                if goal_id not in goal_evidence:
                    goal_evidence[goal_id] = []
                goal_evidence[goal_id].append(evidence)

        # Generate insights for each goal
        for goal in self._active_session.goals:
            evidence_for_goal = goal_evidence.get(goal.goal_id, [])

            if not evidence_for_goal:
                # No evidence found for this goal
                insight = ResearchInsight(
                    insight_id=f"insight-{len(insights)}",
                    insight_type="warning",
                    description=f"No evidence found for goal: {goal.description}",
                    confidence=0.0,
                    actionable=True,
                    recommendation="Consider alternative research sources or refine the goal",
                )
                insights.append(insight)
                goal.status = "failed"
            else:
                # Calculate aggregate confidence
                avg_confidence = sum(e.confidence for e in evidence_for_goal) / len(
                    evidence_for_goal
                )
                avg_relevance = sum(e.relevance_score for e in evidence_for_goal) / len(
                    evidence_for_goal
                )

                if avg_confidence >= 0.7 and avg_relevance >= 0.6:
                    insight = ResearchInsight(
                        insight_id=f"insight-{len(insights)}",
                        insight_type="recommendation",
                        description=f"Strong evidence supports goal: {goal.description}",
                        confidence=avg_confidence,
                        supporting_evidence=[e.evidence_id for e in evidence_for_goal],
                        actionable=True,
                        recommendation="Proceed with implementation based on gathered evidence",
                    )
                    goal.status = "achieved"
                else:
                    insight = ResearchInsight(
                        insight_id=f"insight-{len(insights)}",
                        insight_type="pattern",
                        description=f"Partial evidence for goal: {goal.description}",
                        confidence=avg_confidence,
                        supporting_evidence=[e.evidence_id for e in evidence_for_goal],
                        actionable=True,
                        recommendation="Consider gathering additional evidence before proceeding",
                    )
                    goal.status = "in_progress"

                insights.append(insight)
                goal.findings = [e.content[:200] for e in evidence_for_goal[:3]]

        self._active_session.insights = insights
        self._active_session.updated_at = datetime.now()

        logger.info(f"Synthesized {len(insights)} insights from research")

        return insights

    def calculate_quality_score(self) -> float:
        """
        Calculate overall quality score for the research session.

        Returns:
            Quality score between 0.0 and 1.0
        """
        if not self._active_session:
            raise RuntimeError("No active research session")

        self._active_session.state = ResearchPhaseState.VALIDATING

        # Factors for quality score
        factors = []

        # 1. Goal achievement rate
        achieved_goals = sum(
            1 for g in self._active_session.goals if g.status == "achieved"
        )
        required_goals = sum(1 for g in self._active_session.goals if g.required)
        if required_goals > 0:
            goal_rate = achieved_goals / required_goals
            factors.append((goal_rate, 0.4))  # 40% weight

        # 2. Evidence coverage
        if self._active_session.goals:
            goals_with_evidence = len(
                set(
                    goal_id
                    for e in self._active_session.evidence
                    for goal_id in e.goal_ids
                )
            )
            coverage = goals_with_evidence / len(self._active_session.goals)
            factors.append((coverage, 0.3))  # 30% weight

        # 3. Average confidence
        if self._active_session.evidence:
            avg_confidence = sum(
                e.confidence for e in self._active_session.evidence
            ) / len(self._active_session.evidence)
            factors.append((avg_confidence, 0.2))  # 20% weight

        # 4. Insight actionability
        if self._active_session.insights:
            actionable_rate = sum(
                1 for i in self._active_session.insights if i.actionable
            ) / len(self._active_session.insights)
            factors.append((actionable_rate, 0.1))  # 10% weight

        # Calculate weighted score
        if factors:
            quality_score = sum(score * weight for score, weight in factors)
        else:
            quality_score = 0.0

        self._active_session.quality_score = quality_score
        self._active_session.updated_at = datetime.now()

        logger.info(f"Research quality score: {quality_score:.2f}")

        return quality_score

    def complete_session(self) -> ResearchSession:
        """
        Complete the research session and return final results.

        Returns:
            The completed ResearchSession
        """
        if not self._active_session:
            raise RuntimeError("No active research session")

        # Ensure insights are synthesized
        if not self._active_session.insights:
            self.synthesize_insights()

        # Calculate quality score
        if self._active_session.quality_score is None:
            self.calculate_quality_score()

        self._active_session.state = ResearchPhaseState.COMPLETED
        self._active_session.completed_at = datetime.now()
        self._active_session.updated_at = datetime.now()

        logger.info(
            f"Completed research session {self._active_session.session_id} "
            f"with quality score {self._active_session.quality_score:.2f}"
        )

        return self._active_session

    def save_session(self, output_dir: Path) -> Path:
        """
        Save the research session to disk.

        Args:
            output_dir: Directory to save the session

        Returns:
            Path to the saved session file
        """
        if not self._active_session:
            raise RuntimeError("No active research session")

        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{self._active_session.session_id}.json"

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self._active_session.to_dict(), f, indent=2)

        logger.info(f"Saved research session to {output_file}")

        return output_file

    def get_decision_context(self) -> Dict[str, Any]:
        """
        Get context for decision-making based on research results.

        Returns:
            Dictionary with decision-relevant context
        """
        if not self._active_session:
            raise RuntimeError("No active research session")

        # Determine overall recommendation
        high_confidence_insights = [
            i for i in self._active_session.insights if i.confidence >= 0.7
        ]
        warnings = [
            i for i in self._active_session.insights if i.insight_type == "warning"
        ]

        if self._active_session.quality_score and self._active_session.quality_score >= 0.7:
            recommendation = "PROCEED"
            risk_level = "LOW"
        elif self._active_session.quality_score and self._active_session.quality_score >= 0.4:
            recommendation = "PROCEED_WITH_CAUTION"
            risk_level = "MEDIUM"
        else:
            recommendation = "GATHER_MORE_EVIDENCE"
            risk_level = "HIGH"

        return {
            "session_id": self._active_session.session_id,
            "recommendation": recommendation,
            "risk_level": risk_level,
            "quality_score": self._active_session.quality_score,
            "goals_achieved": sum(
                1 for g in self._active_session.goals if g.status == "achieved"
            ),
            "total_goals": len(self._active_session.goals),
            "evidence_count": len(self._active_session.evidence),
            "high_confidence_insights": len(high_confidence_insights),
            "warnings": len(warnings),
            "key_findings": [
                i.description
                for i in self._active_session.insights
                if i.confidence >= 0.6
            ][:5],
        }
