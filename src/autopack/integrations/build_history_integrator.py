"""BUILD_HISTORY Integrator for Research System

Reads past build decisions from BUILD_HISTORY.md and autopack.db,
then injects research insights into build planning to inform decision-making.

This integrator bridges the research system with the autonomous executor by:
1. Extracting historical patterns from completed phases
2. Analyzing success/failure rates for different task categories
3. Identifying recurring issues and their resolutions
4. Providing context-aware recommendations for new phases

Design Principles:
- Read-only access to BUILD_HISTORY.md and database
- No modifications to source files
- Provides advisory insights, not mandatory decisions
- Integrates with existing research orchestrator
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from autopack.database import SessionLocal
from autopack.models import Phase, Run, PhaseState

logger = logging.getLogger(__name__)


@dataclass
class BuildDecision:
    """Represents a historical build decision extracted from BUILD_HISTORY or database."""

    phase_id: str
    task_category: str
    complexity: str
    outcome: str  # success, failed, blocked
    tokens_used: int
    duration_seconds: Optional[float]
    issues_encountered: List[str] = field(default_factory=list)
    resolution_strategy: Optional[str] = None
    timestamp: Optional[datetime] = None


@dataclass
class ResearchInsight:
    """Research-derived insight for build planning."""

    insight_type: str  # pattern, recommendation, warning, opportunity
    category: str  # task category this applies to
    confidence: float  # 0.0-1.0
    description: str
    supporting_evidence: List[str] = field(default_factory=list)
    actionable_recommendation: Optional[str] = None


@dataclass
class BuildContext:
    """Aggregated context from build history for decision-making."""

    total_phases: int
    success_rate: float
    avg_tokens_per_phase: float
    category_stats: Dict[str, Dict[str, float]]  # category -> {success_rate, avg_tokens, count}
    common_issues: List[Tuple[str, int]]  # (issue_description, frequency)
    recent_trends: List[str]
    insights: List[ResearchInsight] = field(default_factory=list)


class BuildHistoryIntegrator:
    """Integrates BUILD_HISTORY analysis with research system for informed planning."""

    def __init__(self, project_root: Path, db_session: Optional[Session] = None):
        """
        Initialize the integrator.

        Args:
            project_root: Root directory of the project
            db_session: Optional database session (creates new if not provided)
        """
        self.project_root = project_root
        self.build_history_path = project_root / "docs" / "BUILD_HISTORY.md"
        self._db_session = db_session
        self._owns_session = db_session is None

    @property
    def db(self) -> Session:
        """Get database session (lazy initialization)."""
        if self._db_session is None:
            self._db_session = SessionLocal()
        return self._db_session

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._owns_session and self._db_session:
            self._db_session.close()

    def extract_decisions_from_markdown(self) -> List[BuildDecision]:
        """Extract build decisions from BUILD_HISTORY.md.

        Parses markdown structure to identify completed phases and their outcomes.
        """
        if not self.build_history_path.exists():
            logger.warning(f"BUILD_HISTORY.md not found at {self.build_history_path}")
            return []

        decisions = []
        content = self.build_history_path.read_text(encoding="utf-8")

        # Pattern: ## Phase: <phase_id> - <description>
        phase_pattern = re.compile(r"^##\s+Phase:\s+([\w-]+)\s+-\s+(.+)$", re.MULTILINE)
        # Pattern: **Status**: <status>
        status_pattern = re.compile(r"\*\*Status\*\*:\s+(\w+)")
        # Pattern: **Category**: <category>
        category_pattern = re.compile(r"\*\*Category\*\*:\s+(\w+)")
        # Pattern: **Complexity**: <complexity>
        complexity_pattern = re.compile(r"\*\*Complexity\*\*:\s+(\w+)")

        for match in phase_pattern.finditer(content):
            phase_id = match.group(1)
            start_pos = match.end()
            next_match = phase_pattern.search(content, start_pos)
            end_pos = next_match.start() if next_match else len(content)
            section = content[start_pos:end_pos]

            # Extract metadata
            status_match = status_pattern.search(section)
            category_match = category_pattern.search(section)
            complexity_match = complexity_pattern.search(section)

            if status_match:
                outcome = status_match.group(1).lower()
                decisions.append(
                    BuildDecision(
                        phase_id=phase_id,
                        task_category=category_match.group(1) if category_match else "unknown",
                        complexity=complexity_match.group(1) if complexity_match else "medium",
                        outcome=outcome,
                        tokens_used=0,  # Not available in markdown
                        duration_seconds=None,
                        issues_encountered=[],
                    )
                )

        logger.info(f"Extracted {len(decisions)} decisions from BUILD_HISTORY.md")
        return decisions

    def extract_decisions_from_database(self, limit: int = 100) -> List[BuildDecision]:
        """Extract build decisions from database (more detailed than markdown).

        Args:
            limit: Maximum number of recent phases to analyze
        """
        decisions = []

        try:
            phases = (
                self.db.query(Phase)
                .filter(Phase.state.in_([PhaseState.COMPLETED, PhaseState.FAILED]))
                .order_by(Phase.completed_at.desc())
                .limit(limit)
                .all()
            )

            for phase in phases:
                outcome = "success" if phase.state == PhaseState.COMPLETED else "failed"
                duration = None
                if phase.started_at and phase.completed_at:
                    duration = (phase.completed_at - phase.started_at).total_seconds()

                decisions.append(
                    BuildDecision(
                        phase_id=phase.phase_id,
                        task_category=phase.task_category or "unknown",
                        complexity=phase.complexity or "medium",
                        outcome=outcome,
                        tokens_used=phase.tokens_used,
                        duration_seconds=duration,
                        issues_encountered=[],  # Could parse from phase logs
                        timestamp=phase.completed_at,
                    )
                )

            logger.info(f"Extracted {len(decisions)} decisions from database")
        except Exception as e:
            logger.error(f"Failed to extract decisions from database: {e}")

        return decisions

    def analyze_build_context(self, decisions: List[BuildDecision]) -> BuildContext:
        """Analyze historical decisions to build context for planning.

        Args:
            decisions: List of historical build decisions

        Returns:
            BuildContext with aggregated statistics and insights
        """
        if not decisions:
            return BuildContext(
                total_phases=0,
                success_rate=0.0,
                avg_tokens_per_phase=0.0,
                category_stats={},
                common_issues=[],
                recent_trends=[],
            )

        # Overall statistics
        total = len(decisions)
        successful = sum(1 for d in decisions if d.outcome == "success")
        success_rate = successful / total if total > 0 else 0.0
        avg_tokens = sum(d.tokens_used for d in decisions) / total if total > 0 else 0.0

        # Category-specific statistics
        category_stats = {}
        for decision in decisions:
            cat = decision.task_category
            if cat not in category_stats:
                category_stats[cat] = {"total": 0, "success": 0, "tokens": 0}
            category_stats[cat]["total"] += 1
            if decision.outcome == "success":
                category_stats[cat]["success"] += 1
            category_stats[cat]["tokens"] += decision.tokens_used

        # Compute rates
        for cat, stats in category_stats.items():
            stats["success_rate"] = stats["success"] / stats["total"] if stats["total"] > 0 else 0.0
            stats["avg_tokens"] = stats["tokens"] / stats["total"] if stats["total"] > 0 else 0.0
            stats["count"] = stats["total"]

        # Recent trends (last 10 phases)
        recent = decisions[:10]
        recent_trends = []
        if len(recent) >= 3:
            recent_success_rate = sum(1 for d in recent if d.outcome == "success") / len(recent)
            if recent_success_rate > 0.8:
                recent_trends.append("High recent success rate (>80%)")
            elif recent_success_rate < 0.5:
                recent_trends.append("Low recent success rate (<50%) - may need intervention")

        return BuildContext(
            total_phases=total,
            success_rate=success_rate,
            avg_tokens_per_phase=avg_tokens,
            category_stats=category_stats,
            common_issues=[],  # TODO: Extract from logs
            recent_trends=recent_trends,
        )

    def generate_insights(self, context: BuildContext) -> List[ResearchInsight]:
        """Generate actionable insights from build context.

        Args:
            context: Analyzed build context

        Returns:
            List of research insights for planning
        """
        insights = []

        # Overall success rate insight
        if context.success_rate < 0.6:
            insights.append(
                ResearchInsight(
                    insight_type="warning",
                    category="all",
                    confidence=0.9,
                    description=f"Low overall success rate ({context.success_rate:.1%})",
                    supporting_evidence=[f"Only {int(context.success_rate * context.total_phases)} of {context.total_phases} phases succeeded"],
                    actionable_recommendation="Consider breaking down complex phases into smaller, more manageable tasks",
                )
            )

        # Category-specific insights
        for category, stats in context.category_stats.items():
            if stats["success_rate"] < 0.5 and stats["count"] >= 3:
                insights.append(
                    ResearchInsight(
                        insight_type="warning",
                        category=category,
                        confidence=0.8,
                        description=f"Low success rate for {category} tasks ({stats['success_rate']:.1%})",
                        supporting_evidence=[f"{stats['count']} attempts with {int(stats['success'] )} successes"],
                        actionable_recommendation=f"Review {category} task patterns and consider additional validation",
                    )
                )
            elif stats["success_rate"] > 0.8 and stats["count"] >= 5:
                insights.append(
                    ResearchInsight(
                        insight_type="pattern",
                        category=category,
                        confidence=0.9,
                        description=f"High success rate for {category} tasks ({stats['success_rate']:.1%})",
                        supporting_evidence=[f"{stats['count']} attempts with {int(stats['success'])} successes"],
                        actionable_recommendation=f"{category} tasks are well-understood - can proceed with confidence",
                    )
                )

        # Token usage insights
        if context.avg_tokens_per_phase > 50000:
            insights.append(
                ResearchInsight(
                    insight_type="recommendation",
                    category="all",
                    confidence=0.7,
                    description=f"High average token usage ({context.avg_tokens_per_phase:.0f} per phase)",
                    supporting_evidence=["May indicate overly complex phases or verbose outputs"],
                    actionable_recommendation="Consider phase decomposition or more focused scopes",
                )
            )

        return insights

    def get_build_context_for_planning(self) -> BuildContext:
        """Main entry point: Get comprehensive build context for planning.

        Returns:
            BuildContext with historical analysis and actionable insights
        """
        # Combine decisions from both sources
        db_decisions = self.extract_decisions_from_database()
        md_decisions = self.extract_decisions_from_markdown()

        # Prefer database decisions (more detailed), fall back to markdown
        all_decisions = db_decisions if db_decisions else md_decisions

        # Analyze and generate insights
        context = self.analyze_build_context(all_decisions)
        context.insights = self.generate_insights(context)

        logger.info(
            f"Generated build context: {context.total_phases} phases, "
            f"{context.success_rate:.1%} success rate, {len(context.insights)} insights"
        )

        return context

    def export_context_for_research(self, output_path: Path) -> None:
        """Export build context as JSON for research system integration.

        Args:
            output_path: Path to write JSON output
        """
        context = self.get_build_context_for_planning()

        export_data = {
            "generated_at": datetime.now().isoformat(),
            "total_phases": context.total_phases,
            "success_rate": context.success_rate,
            "avg_tokens_per_phase": context.avg_tokens_per_phase,
            "category_stats": context.category_stats,
            "recent_trends": context.recent_trends,
            "insights": [
                {
                    "type": insight.insight_type,
                    "category": insight.category,
                    "confidence": insight.confidence,
                    "description": insight.description,
                    "evidence": insight.supporting_evidence,
                    "recommendation": insight.actionable_recommendation,
                }
                for insight in context.insights
            ],
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(export_data, indent=2), encoding="utf-8")
        logger.info(f"Exported build context to {output_path}")
