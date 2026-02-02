"""BUILD_HISTORY Integrator for Research System

Reads past build decisions from BUILD_HISTORY.md and autopack.db,
then injects research insights into build planning to inform decision-making.

This integrator bridges the research system with the autonomous executor by:
1. Extracting historical patterns from completed phases
2. Analyzing success/failure rates for different task categories
3. Identifying recurring issues and their resolutions
4. Providing context-aware recommendations for new phases
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from autopack.integrations.pattern_library import PatternLibrary, ReusablePattern
    from autopack.research.analysis.build_history_analyzer import (
        BuildHistoryAnalysisResult,
    )

logger = logging.getLogger(__name__)


@dataclass
class HistoricalPattern:
    """Represents a pattern extracted from build history."""

    pattern_type: str  # e.g., "success", "failure", "recurring_issue"
    category: str  # Task category
    description: str
    frequency: int
    last_seen: datetime
    related_phases: List[str] = field(default_factory=list)
    resolution: Optional[str] = None
    confidence: float = 0.0


@dataclass
class BuildHistoryInsights:
    """Insights extracted from build history (test-compatible interface)."""

    total_phases: int = 0
    successful_phases: int = 0
    failed_phases: int = 0
    best_practices: List[str] = field(default_factory=list)
    common_pitfalls: List[str] = field(default_factory=list)
    patterns: List[HistoricalPattern] = field(default_factory=list)


@dataclass
class BuildHistoryInsight:
    """Insights extracted from build history for research planning."""

    patterns: List[HistoricalPattern]
    success_rate: Dict[str, float]  # Category -> success rate
    common_issues: List[str]
    recommended_approaches: List[str]
    warnings: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchContextEnrichment:
    """Research context enriched with build history data.

    This class bridges build history insights with the research pipeline,
    providing historical context for research decisions.
    """

    feasibility_adjustment: float  # -1.0 to 1.0
    confidence: float  # 0.0 to 1.0
    historical_success_rate: float  # 0.0 to 1.0
    recommended_research_scope: str  # "minimal", "standard", "comprehensive"
    risk_factors: List[str] = field(default_factory=list)
    success_factors: List[str] = field(default_factory=list)
    cost_optimization_tips: List[str] = field(default_factory=list)
    time_estimate_adjustment_percent: float = 0.0
    research_focus_areas: List[str] = field(default_factory=list)


@dataclass
class BuildInformedMetrics:
    """Metrics tracking build-informed decisions."""

    total_research_sessions: int = 0
    sessions_using_build_history: int = 0
    avg_research_time_saved_percent: float = 0.0
    successful_pattern_applications: int = 0
    failed_pattern_applications: int = 0
    avg_feasibility_adjustment: float = 0.0
    recommendation_acceptance_rate: float = 0.0


class BuildHistoryIntegrator:
    """Integrates BUILD_HISTORY with research system.

    This integrator bridges build history with the research pipeline by:
    1. Extracting historical patterns and feasibility signals
    2. Wiring build data into research context for informed decisions
    3. Generating recommendations based on historical success patterns
    4. Tracking metrics for build-informed decision effectiveness
    """

    def __init__(
        self,
        build_history_path: Optional[Path] = None,
        pattern_library: Optional["PatternLibrary"] = None,
    ):
        """Initialize integrator.

        Args:
            build_history_path: Path to BUILD_HISTORY.md (defaults to repo root)
            pattern_library: Optional PatternLibrary for cross-project pattern extraction
        """
        self.build_history_path = build_history_path or Path("BUILD_HISTORY.md")
        self._cache: Optional[BuildHistoryInsight] = None
        self._cache_time: Optional[datetime] = None
        self._pattern_library = pattern_library
        self._metrics = BuildInformedMetrics()

        # Lazy-load BuildHistoryAnalyzer when needed
        self._analyzer: Optional[Any] = None

    def get_insights_for_task(
        self, task_description: str, category: Optional[str] = None
    ) -> BuildHistoryInsights:
        """Extract relevant insights from build history for a task.

        Args:
            task_description: Description of the task
            category: Optional task category for filtering

        Returns:
            BuildHistoryInsights with relevant patterns and recommendations
        """
        # Parse build history
        history_data = self._parse_build_history()

        # Filter phases by category
        phases = history_data.get("phases", [])
        if category:
            phases = [p for p in phases if p.get("category") == category]

        # Count phases
        total = len(phases)
        successful = sum(
            1 for p in phases if p.get("status") in ["SUCCESS", "success", "completed"]
        )
        failed = sum(1 for p in phases if p.get("status") in ["FAILED", "failed", "error"])

        # Extract best practices
        best_practices = []
        for phase in phases:
            content = phase.get("content", "")
            # Find lessons learned
            lessons_match = re.findall(
                r"Lessons Learned:\n(.+?)(?=\n\n|Issues:|$)", content, re.DOTALL
            )
            for lessons in lessons_match:
                for line in lessons.split("\n"):
                    if line.strip().startswith("-"):
                        best_practices.append(line.strip()[1:].strip())

        # Extract common pitfalls
        common_pitfalls = []
        for phase in phases:
            content = phase.get("content", "")
            # Find issues
            issues_match = re.findall(
                r"Issues:\n(.+?)(?=\n\n|Lessons Learned:|$)", content, re.DOTALL
            )
            for issues in issues_match:
                for line in issues.split("\n"):
                    if line.strip().startswith("-"):
                        common_pitfalls.append(line.strip()[1:].strip())

        # Extract patterns
        patterns = self._extract_patterns(history_data, task_description, category)

        return BuildHistoryInsights(
            total_phases=total,
            successful_phases=successful,
            failed_phases=failed,
            best_practices=list(set(best_practices)),  # Deduplicate
            common_pitfalls=list(set(common_pitfalls)),  # Deduplicate
            patterns=patterns,
        )

    def _parse_build_history(self) -> Dict[str, Any]:
        """Parse BUILD_HISTORY.md into structured data."""
        if not self.build_history_path.exists():
            logger.warning(f"BUILD_HISTORY not found at {self.build_history_path}")
            return {"phases": [], "patterns": {}}

        content = self.build_history_path.read_text(encoding="utf-8")

        # Extract phase entries
        phases = []
        phase_pattern = r"## Phase (\d+): (.+?)\n(.+?)(?=## Phase|$)"

        for match in re.finditer(phase_pattern, content, re.DOTALL):
            phase_num = match.group(1)
            phase_title = match.group(2)
            phase_content = match.group(3)

            # Extract status (handle both formats: "✓ SUCCESS" and "Status: SUCCESS")
            status = "unknown"
            status_match = re.search(r"\*\*Status\*\*:\s*([✓✗])\s*(\w+)", phase_content)
            if status_match:
                symbol = status_match.group(1)
                status_text = status_match.group(2)
                status = status_text if symbol == "✓" else "FAILED"
            else:
                status_match = re.search(r"Status:\s*(\w+)", phase_content)
                if status_match:
                    status = status_match.group(1)

            # Extract category
            category_match = re.search(r"\*\*Category\*\*:\s*(\w+)", phase_content)
            if not category_match:
                category_match = re.search(r"Category:\s*(\w+)", phase_content)
            category = category_match.group(1) if category_match else "unknown"

            # Extract timestamp
            time_match = re.search(r"Completed:\s*([\d-]+T[\d:]+)", phase_content)
            timestamp = time_match.group(1) if time_match else None

            phases.append(
                {
                    "number": int(phase_num),
                    "title": phase_title.strip(),
                    "status": status,
                    "category": category,
                    "timestamp": timestamp,
                    "content": phase_content,
                }
            )

        return {"phases": phases, "patterns": {}}

    def _extract_patterns(
        self, history_data: Dict[str, Any], task_description: str, category: Optional[str]
    ) -> List[HistoricalPattern]:
        """Extract relevant patterns from history data."""
        patterns = []
        phases = history_data.get("phases", [])

        # Filter by category if provided
        if category:
            phases = [p for p in phases if p.get("category") == category]

        # Group by status
        status_counts: Dict[str, int] = {}
        for phase in phases:
            status = phase.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        # Create patterns for success/failure rates
        for status, count in status_counts.items():
            if count >= 2:  # Only patterns with multiple occurrences
                patterns.append(
                    HistoricalPattern(
                        pattern_type=status,
                        category=category or "all",
                        description=f"{status.capitalize()} pattern observed",
                        frequency=count,
                        last_seen=datetime.now(),
                        confidence=min(count / len(phases), 1.0) if phases else 0.0,
                    )
                )

        # Extract recurring issues
        issue_keywords = ["error", "failed", "issue", "problem", "bug"]
        issue_counts: Dict[str, int] = {}

        for phase in phases:
            content = phase.get("content", "").lower()
            for keyword in issue_keywords:
                if keyword in content:
                    issue_counts[keyword] = issue_counts.get(keyword, 0) + 1

        for issue, count in issue_counts.items():
            if count >= 2:
                patterns.append(
                    HistoricalPattern(
                        pattern_type="recurring_issue",
                        category=category or "all",
                        description=f"Recurring {issue} pattern",
                        frequency=count,
                        last_seen=datetime.now(),
                        confidence=min(count / len(phases), 1.0) if phases else 0.0,
                    )
                )

        return patterns

    def _calculate_success_rates(
        self, history_data: Dict[str, Any], category: Optional[str]
    ) -> Dict[str, float]:
        """Calculate success rates by category."""
        phases = history_data.get("phases", [])

        if not phases:
            return {}

        # Group by category
        category_stats: Dict[str, Dict[str, int]] = {}

        for phase in phases:
            cat = phase.get("category", "unknown")
            status = phase.get("status", "unknown")

            if cat not in category_stats:
                category_stats[cat] = {"total": 0, "success": 0}

            category_stats[cat]["total"] += 1
            if status in ["completed", "success"]:
                category_stats[cat]["success"] += 1

        # Calculate rates
        success_rates = {}
        for cat, stats in category_stats.items():
            if stats["total"] > 0:
                success_rates[cat] = stats["success"] / stats["total"]

        return success_rates

    def _identify_common_issues(
        self, history_data: Dict[str, Any], category: Optional[str]
    ) -> List[str]:
        """Identify common issues from history."""
        phases = history_data.get("phases", [])

        if category:
            phases = [p for p in phases if p.get("category") == category]

        # Extract issues from failed phases
        issues = []
        for phase in phases:
            if phase.get("status") in ["failed", "error"]:
                content = phase.get("content", "")
                # Look for error messages or issue descriptions
                error_match = re.search(r"Error: (.+?)\n", content)
                if error_match:
                    issues.append(error_match.group(1).strip())

        # Return unique issues
        return list(set(issues))[:5]  # Top 5 unique issues

    def _generate_recommendations(
        self, patterns: List[HistoricalPattern], success_rates: Dict[str, float]
    ) -> List[str]:
        """Generate recommendations based on patterns and success rates."""
        recommendations = []

        # Recommend based on success rates
        for category, rate in success_rates.items():
            if rate > 0.8:
                recommendations.append(
                    f"High success rate ({rate:.1%}) for {category} tasks - consider similar approach"
                )
            elif rate < 0.5:
                recommendations.append(
                    f"Low success rate ({rate:.1%}) for {category} tasks - consider alternative approach"
                )

        # Recommend based on patterns
        high_confidence_patterns = [p for p in patterns if p.confidence > 0.7]
        for pattern in high_confidence_patterns:
            if pattern.pattern_type == "success":
                recommendations.append(
                    f"Pattern suggests successful approach for {pattern.category}"
                )

        return recommendations[:5]  # Top 5 recommendations

    def _generate_warnings(
        self, patterns: List[HistoricalPattern], common_issues: List[str]
    ) -> List[str]:
        """Generate warnings based on patterns and issues."""
        warnings = []

        # Warn about recurring issues
        recurring_issues = [
            p for p in patterns if p.pattern_type == "recurring_issue" and p.frequency >= 3
        ]
        for pattern in recurring_issues:
            warnings.append(
                f"Recurring issue detected: {pattern.description} (seen {pattern.frequency} times)"
            )

        # Warn about common failures
        if common_issues:
            warnings.append(f"Common issues in this category: {', '.join(common_issues[:3])}")

        return warnings

    def should_trigger_research(
        self,
        task_description: str,
        category: Optional[str] = None,
        threshold: float = 0.5,
    ) -> bool:
        """Determine if research should be triggered for a task.

        Args:
            task_description: Description of the task
            category: Optional task category
            threshold: Success rate threshold below which research is triggered

        Returns:
            True if research should be triggered
        """
        insights = self.get_insights_for_task(task_description, category)

        # No history - trigger research
        if insights.total_phases == 0:
            return True

        # Low success rate - trigger research
        if insights.total_phases > 0:
            success_rate = insights.successful_phases / insights.total_phases
            if success_rate < threshold:
                return True

        # Many pitfalls - trigger research
        if len(insights.common_pitfalls) >= 3:
            return True

        return False

    def format_insights_for_prompt(self, insights: BuildHistoryInsights) -> str:
        """Format insights for LLM prompt.

        Args:
            insights: Insights to format

        Returns:
            Formatted markdown string
        """
        lines = [
            "# Historical Context",
            "",
            f"**Total Phases**: {insights.total_phases}",
            f"**Successful**: {insights.successful_phases}",
            f"**Failed**: {insights.failed_phases}",
            "",
        ]

        if insights.best_practices:
            lines.append("## Best Practices")
            for practice in insights.best_practices:
                lines.append(f"- {practice}")
            lines.append("")

        if insights.common_pitfalls:
            lines.append("## Common Pitfalls")
            for pitfall in insights.common_pitfalls:
                lines.append(f"- {pitfall}")
            lines.append("")

        if insights.patterns:
            lines.append("## Patterns")
            for pattern in insights.patterns:
                lines.append(
                    f"- **{pattern.pattern_type}** ({pattern.frequency}x): {pattern.description}"
                )
            lines.append("")

        return "\n".join(lines)

    def _merge_insights(
        self,
        insights1: BuildHistoryInsights,
        insights2: BuildHistoryInsights,
    ) -> BuildHistoryInsights:
        """Merge insights from multiple sources.

        Args:
            insights1: First insights object
            insights2: Second insights object

        Returns:
            Merged insights
        """
        # Merge counts
        total = insights1.total_phases + insights2.total_phases
        successful = insights1.successful_phases + insights2.successful_phases
        failed = insights1.failed_phases + insights2.failed_phases

        # Deduplicate lists
        best_practices = list(set(insights1.best_practices + insights2.best_practices))
        common_pitfalls = list(set(insights1.common_pitfalls + insights2.common_pitfalls))

        # Merge patterns (deduplicate by description)
        patterns_dict = {}
        for pattern in insights1.patterns + insights2.patterns:
            key = (pattern.pattern_type, pattern.description)
            if key in patterns_dict:
                # Update frequency
                patterns_dict[key].frequency += pattern.frequency
            else:
                patterns_dict[key] = pattern
        patterns = list(patterns_dict.values())

        return BuildHistoryInsights(
            total_phases=total,
            successful_phases=successful,
            failed_phases=failed,
            best_practices=best_practices,
            common_pitfalls=common_pitfalls,
            patterns=patterns,
        )

    def record_research_outcome(
        self, phase_id: str, outcome: str, insights: Dict[str, Any]
    ) -> None:
        """Record research outcome back to BUILD_HISTORY.

        Args:
            phase_id: Phase identifier
            outcome: Outcome status (success/failure)
            insights: Research insights to record
        """
        logger.info(f"Recording research outcome for phase {phase_id}: {outcome}")
        # This would append to BUILD_HISTORY.md
        # Implementation depends on BUILD_HISTORY format
        pass

    def extract_reusable_patterns(self) -> List["ReusablePattern"]:
        """Extract reusable patterns from build history using PatternLibrary.

        Parses the build history and extracts patterns that can be reused
        across projects. Requires a PatternLibrary to be configured.

        Returns:
            List of ReusablePattern objects extracted from history
        """
        if self._pattern_library is None:
            logger.warning("PatternLibrary not configured, cannot extract patterns")
            return []

        history_data = self._parse_build_history()
        return self._pattern_library.extract_patterns_from_history(history_data)

    def get_applicable_patterns(
        self,
        task_description: str,
        category: Optional[str] = None,
        tech_stack: Optional[List[str]] = None,
    ) -> List["ReusablePattern"]:
        """Get patterns applicable to a task.

        Finds patterns from the library that are relevant to the given
        task context.

        Args:
            task_description: Description of the task
            category: Optional task category
            tech_stack: Optional list of technologies being used

        Returns:
            List of applicable ReusablePattern objects, sorted by relevance
        """
        if self._pattern_library is None:
            logger.warning("PatternLibrary not configured, cannot find patterns")
            return []

        # First ensure patterns are extracted
        if not self._pattern_library.get_all_patterns():
            self.extract_reusable_patterns()

        project_context = {
            "description": task_description,
            "category": category or "",
            "tech_stack": tech_stack or [],
        }

        return self._pattern_library.find_applicable_patterns(project_context)

    def record_pattern_usage(self, pattern_id: str, success: bool) -> None:
        """Record that a pattern was applied.

        Updates the pattern's success rate and application count.

        Args:
            pattern_id: ID of the pattern that was applied
            success: Whether the application was successful
        """
        if self._pattern_library is None:
            logger.warning("PatternLibrary not configured, cannot record usage")
            return

        self._pattern_library.record_pattern_application(pattern_id, success)

    def _get_analyzer(self) -> Any:
        """Get or create BuildHistoryAnalyzer instance."""
        if self._analyzer is None:
            try:
                from autopack.research.analysis.build_history_analyzer import BuildHistoryAnalyzer

                self._analyzer = BuildHistoryAnalyzer(build_history_path=self.build_history_path)
            except ImportError:
                logger.warning("BuildHistoryAnalyzer not available, some features will be limited")
                return None
        return self._analyzer

    def enrich_research_context(
        self,
        task_description: str,
        category: Optional[str] = None,
        project_type: Optional[str] = None,
        tech_stack: Optional[List[str]] = None,
    ) -> ResearchContextEnrichment:
        """Enrich research context with build history data.

        This method wires historical build patterns into the research pipeline
        to inform research scope, focus areas, and expectations.

        Args:
            task_description: Description of the task for research
            category: Optional task category for filtering
            project_type: Optional project type for feasibility assessment
            tech_stack: Optional list of technologies involved

        Returns:
            ResearchContextEnrichment with historical data
        """
        analyzer = self._get_analyzer()
        if analyzer is None:
            # Return neutral enrichment if analyzer unavailable
            return ResearchContextEnrichment(
                feasibility_adjustment=0.0,
                confidence=0.0,
                historical_success_rate=0.5,
                recommended_research_scope="standard",
            )

        # Get analysis from build history
        analysis_result = analyzer.analyze(project_type=project_type, tech_stack=tech_stack)

        # Get basic insights
        insights = self.get_insights_for_task(task_description, category)

        # Calculate feasibility adjustment from signals
        feasibility_adjustment = 0.0
        confidence = 0.0
        if analysis_result.feasibility_signals:
            total_weight = sum(s.confidence for s in analysis_result.feasibility_signals)
            if total_weight > 0:
                weighted_adjustment = sum(
                    (s.signal_value - 0.5) * s.confidence
                    for s in analysis_result.feasibility_signals
                )
                feasibility_adjustment = (weighted_adjustment / total_weight) * 0.3
                confidence = min(total_weight / len(analysis_result.feasibility_signals), 1.0)

        # Determine research scope
        recommended_scope = self._determine_research_scope(
            analysis_result.overall_success_rate, insights, feasibility_adjustment
        )

        # Extract risk and success factors
        risk_factors = [w for w in analysis_result.warnings[:3]]  # Top 3 warnings are risk factors
        success_factors = self._extract_success_factors(analysis_result)

        # Get cost optimization tips
        cost_tips = analysis_result.cost_effectiveness.cost_optimization_opportunities

        # Calculate time estimate adjustment
        time_adjustment = 0.0
        if analysis_result.avg_time_estimate_accuracy > 0:
            # If historical estimates are poor, we need more research time
            time_adjustment = max(-20.0, (1.0 - analysis_result.avg_time_estimate_accuracy) * 50)

        # Identify research focus areas
        focus_areas = self._identify_research_focus_areas(analysis_result, insights, category)

        self._metrics.sessions_using_build_history += 1
        self._metrics.avg_feasibility_adjustment = (
            self._metrics.avg_feasibility_adjustment
            * (self._metrics.sessions_using_build_history - 1)
            + feasibility_adjustment
        ) / self._metrics.sessions_using_build_history

        return ResearchContextEnrichment(
            feasibility_adjustment=feasibility_adjustment,
            confidence=confidence,
            historical_success_rate=analysis_result.overall_success_rate,
            recommended_research_scope=recommended_scope,
            risk_factors=risk_factors,
            success_factors=success_factors,
            cost_optimization_tips=cost_tips[:5],
            time_estimate_adjustment_percent=time_adjustment,
            research_focus_areas=focus_areas,
        )

    def _determine_research_scope(
        self,
        success_rate: float,
        insights: BuildHistoryInsights,
        feasibility_adjustment: float,
    ) -> str:
        """Determine recommended research scope based on history.

        Args:
            success_rate: Historical success rate (0-1)
            insights: Build history insights
            feasibility_adjustment: Feasibility adjustment factor (-1 to 1)

        Returns:
            Recommended scope: "minimal", "standard", or "comprehensive"
        """
        # Low success rate or many pitfalls = comprehensive
        if success_rate < 0.5 or len(insights.common_pitfalls) >= 3:
            return "comprehensive"

        # Negative adjustment = comprehensive
        if feasibility_adjustment < -0.1:
            return "comprehensive"

        # High success rate = minimal
        if success_rate > 0.8 and len(insights.common_pitfalls) < 2:
            return "minimal"

        # Default to standard
        return "standard"

    def _extract_success_factors(self, analysis_result: "BuildHistoryAnalysisResult") -> List[str]:
        """Extract factors that correlate with success.

        Args:
            analysis_result: Build history analysis result

        Returns:
            List of success factors
        """
        factors = []

        # Extract from recommendations
        if analysis_result.recommendations:
            for rec in analysis_result.recommendations[:2]:
                if any(
                    word in rec.lower()
                    for word in ["success", "high", "positive", "leverage", "prioritize"]
                ):
                    factors.append(rec)

        # Extract from signals
        for signal in analysis_result.feasibility_signals:
            if signal.signal_value > 0.7 and signal.confidence > 0.5:
                factors.append(f"{signal.signal_type.value}: {signal.supporting_evidence[0]}")

        return factors[:5]

    def _identify_research_focus_areas(
        self,
        analysis_result: "BuildHistoryAnalysisResult",
        insights: BuildHistoryInsights,
        category: Optional[str],
    ) -> List[str]:
        """Identify key research focus areas based on history.

        Args:
            analysis_result: Build history analysis result
            insights: Build history insights
            category: Task category

        Returns:
            List of recommended research focus areas
        """
        focus_areas = []

        # Focus on high-risk areas
        if analysis_result.warnings:
            focus_areas.append("Risk mitigation strategies")

        # Focus on common issues if many failures
        if insights.common_pitfalls:
            focus_areas.append("Avoiding common pitfalls")

        # Focus on optimization if cost issues
        if (
            analysis_result.cost_effectiveness.cost_overrun_rate > 0.3
            or analysis_result.cost_effectiveness.high_cost_factors
        ):
            focus_areas.append("Cost optimization approaches")

        # Focus on time estimation if poor accuracy
        if analysis_result.avg_time_estimate_accuracy < 0.6:
            focus_areas.append("Realistic timeline planning")

        # Add category-specific focus
        if category:
            focus_areas.append(f"Best practices for {category} tasks")

        return focus_areas[:5]

    def get_research_recommendations_from_history(
        self,
        task_description: str,
        category: Optional[str] = None,
        project_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get research recommendations informed by build history.

        This method generates recommendations for how to approach research
        based on patterns identified in the build history.

        Args:
            task_description: Description of the task
            category: Optional task category
            project_type: Optional project type

        Returns:
            Dictionary with research recommendations
        """
        insights = self.get_insights_for_task(task_description, category)
        analyzer = self._get_analyzer()

        if analyzer is None:
            return {
                "research_approach": "standard",
                "research_agents": [],
                "validation_requirements": [],
                "estimated_research_time_hours": 4,
            }

        analysis = analyzer.analyze(project_type=project_type)

        # Determine research agents to use based on history
        agents = self._recommend_research_agents(insights, analysis, category)

        # Determine validation requirements
        validation_reqs = self._determine_validation_requirements(insights, analysis)

        # Estimate research time
        estimated_time = self._estimate_research_time(insights, analysis)

        return {
            "research_approach": self._determine_research_scope(
                analysis.overall_success_rate, insights, 0.0
            ),
            "research_agents": agents,
            "validation_requirements": validation_reqs,
            "estimated_research_time_hours": estimated_time,
            "cost_research_priority": (
                "high" if analysis.cost_effectiveness.cost_overrun_rate > 0.3 else "standard"
            ),
            "feasibility_research_priority": (
                "high" if analysis.overall_success_rate < 0.6 else "standard"
            ),
        }

    def _recommend_research_agents(
        self,
        insights: BuildHistoryInsights,
        analysis: "BuildHistoryAnalysisResult",
        category: Optional[str],
    ) -> List[str]:
        """Recommend which research agents to prioritize.

        Args:
            insights: Build history insights
            analysis: Build history analysis result
            category: Task category

        Returns:
            List of recommended research agent types
        """
        agents = []

        # Add feasibility research if low success rate
        if analysis.overall_success_rate < 0.6:
            agents.append("product_feasibility_agent")

        # Add cost research if high overruns
        if analysis.cost_effectiveness.cost_overrun_rate > 0.3:
            agents.append("cost_effectiveness_analyzer")

        # Add competitive research if mentioned in warnings
        if any("compet" in w.lower() for w in analysis.warnings):
            agents.append("competitive_analysis_agent")

        # Add market research if category suggests
        if category and any(kw in category.lower() for kw in ["market", "demand", "trend"]):
            agents.append("market_research_agent")

        # Add tech stack research if issues detected
        if any(
            tech in " ".join(a for a in analysis.metrics_by_tech_stack.keys())
            for tech in ["deprecated", "experimental"]
        ):
            agents.append("technical_feasibility_agent")

        return agents[:5] if agents else ["general_research_agent"]

    def _determine_validation_requirements(
        self,
        insights: BuildHistoryInsights,
        analysis: "BuildHistoryAnalysisResult",
    ) -> List[str]:
        """Determine validation requirements based on history.

        Args:
            insights: Build history insights
            analysis: Build history analysis result

        Returns:
            List of validation requirements
        """
        requirements = []

        # Require citation validation if many common issues
        if len(insights.common_pitfalls) > 2:
            requirements.append("citation_validation")

        # Require evidence validation if low success rate
        if analysis.overall_success_rate < 0.5:
            requirements.append("evidence_validation")

        # Require quality validation if cost overruns
        if analysis.cost_effectiveness.cost_overrun_rate > 0.5:
            requirements.append("quality_validation")

        # Require recency validation for tech stack decisions
        if analysis.metrics_by_tech_stack:
            requirements.append("recency_validation")

        return requirements if requirements else ["standard_validation"]

    def _estimate_research_time(
        self,
        insights: BuildHistoryInsights,
        analysis: "BuildHistoryAnalysisResult",
    ) -> float:
        """Estimate research time needed based on history.

        Args:
            insights: Build history insights
            analysis: Build history analysis result

        Returns:
            Estimated research time in hours
        """
        base_time = 4.0  # Standard research is 4 hours

        # Increase if low success rate
        if analysis.overall_success_rate < 0.5:
            base_time += 4.0

        # Increase if many common pitfalls
        base_time += min(len(insights.common_pitfalls) * 0.5, 2.0)

        # Increase if cost overruns common
        if analysis.cost_effectiveness.cost_overrun_rate > 0.5:
            base_time += 2.0

        # Reduce if high success rate and no issues
        if analysis.overall_success_rate > 0.8 and len(insights.common_pitfalls) == 0:
            base_time = 2.0

        return base_time

    def get_metrics(self) -> BuildInformedMetrics:
        """Get current metrics for build-informed decisions.

        Returns:
            Current build-informed metrics
        """
        return self._metrics

    def record_decision_outcome(
        self,
        decision_id: str,
        was_successful: bool,
        pattern_applied: Optional[str] = None,
    ) -> None:
        """Record the outcome of a build-informed decision.

        Args:
            decision_id: Identifier for the decision
            was_successful: Whether the decision resulted in success
            pattern_applied: Optional pattern ID that was applied
        """
        if pattern_applied:
            if was_successful:
                self._metrics.successful_pattern_applications += 1
            else:
                self._metrics.failed_pattern_applications += 1

            total_apps = (
                self._metrics.successful_pattern_applications
                + self._metrics.failed_pattern_applications
            )
            if total_apps > 0:
                self._metrics.recommendation_acceptance_rate = (
                    self._metrics.successful_pattern_applications / total_apps
                )

        logger.info(
            f"Recorded build-informed decision outcome: {decision_id} "
            f"(success={was_successful}, pattern={pattern_applied})"
        )
