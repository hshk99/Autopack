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
from typing import Any, Dict, List, Optional, Set

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


class BuildHistoryIntegrator:
    """Integrates BUILD_HISTORY with research system."""
    
    def __init__(self, build_history_path: Optional[Path] = None):
        """Initialize integrator.
        
        Args:
            build_history_path: Path to BUILD_HISTORY.md (defaults to repo root)
        """
        self.build_history_path = build_history_path or Path("BUILD_HISTORY.md")
        self._cache: Optional[BuildHistoryInsight] = None
        self._cache_time: Optional[datetime] = None
        
    def get_insights_for_task(self, task_description: str, category: Optional[str] = None) -> BuildHistoryInsights:
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
        successful = sum(1 for p in phases if p.get("status") in ["SUCCESS", "success", "completed"])
        failed = sum(1 for p in phases if p.get("status") in ["FAILED", "failed", "error"])

        # Extract best practices
        best_practices = []
        for phase in phases:
            content = phase.get("content", "")
            # Find lessons learned
            lessons_match = re.findall(r"Lessons Learned:\n(.+?)(?=\n\n|Issues:|$)", content, re.DOTALL)
            for lessons in lessons_match:
                for line in lessons.split("\n"):
                    if line.strip().startswith("-"):
                        best_practices.append(line.strip()[1:].strip())

        # Extract common pitfalls
        common_pitfalls = []
        for phase in phases:
            content = phase.get("content", "")
            # Find issues
            issues_match = re.findall(r"Issues:\n(.+?)(?=\n\n|Lessons Learned:|$)", content, re.DOTALL)
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

            phases.append({
                "number": int(phase_num),
                "title": phase_title.strip(),
                "status": status,
                "category": category,
                "timestamp": timestamp,
                "content": phase_content,
            })

        return {"phases": phases, "patterns": {}}
    
    def _extract_patterns(self, history_data: Dict[str, Any], task_description: str, category: Optional[str]) -> List[HistoricalPattern]:
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
                patterns.append(HistoricalPattern(
                    pattern_type=status,
                    category=category or "all",
                    description=f"{status.capitalize()} pattern observed",
                    frequency=count,
                    last_seen=datetime.now(),
                    confidence=min(count / len(phases), 1.0) if phases else 0.0,
                ))
        
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
                patterns.append(HistoricalPattern(
                    pattern_type="recurring_issue",
                    category=category or "all",
                    description=f"Recurring {issue} pattern",
                    frequency=count,
                    last_seen=datetime.now(),
                    confidence=min(count / len(phases), 1.0) if phases else 0.0,
                ))
        
        return patterns
    
    def _calculate_success_rates(self, history_data: Dict[str, Any], category: Optional[str]) -> Dict[str, float]:
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
    
    def _identify_common_issues(self, history_data: Dict[str, Any], category: Optional[str]) -> List[str]:
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
    
    def _generate_recommendations(self, patterns: List[HistoricalPattern], success_rates: Dict[str, float]) -> List[str]:
        """Generate recommendations based on patterns and success rates."""
        recommendations = []
        
        # Recommend based on success rates
        for category, rate in success_rates.items():
            if rate > 0.8:
                recommendations.append(f"High success rate ({rate:.1%}) for {category} tasks - consider similar approach")
            elif rate < 0.5:
                recommendations.append(f"Low success rate ({rate:.1%}) for {category} tasks - consider alternative approach")
        
        # Recommend based on patterns
        high_confidence_patterns = [p for p in patterns if p.confidence > 0.7]
        for pattern in high_confidence_patterns:
            if pattern.pattern_type == "success":
                recommendations.append(f"Pattern suggests successful approach for {pattern.category}")
        
        return recommendations[:5]  # Top 5 recommendations
    
    def _generate_warnings(self, patterns: List[HistoricalPattern], common_issues: List[str]) -> List[str]:
        """Generate warnings based on patterns and issues."""
        warnings = []
        
        # Warn about recurring issues
        recurring_issues = [p for p in patterns if p.pattern_type == "recurring_issue" and p.frequency >= 3]
        for pattern in recurring_issues:
            warnings.append(f"Recurring issue detected: {pattern.description} (seen {pattern.frequency} times)")
        
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
                lines.append(f"- **{pattern.pattern_type}** ({pattern.frequency}x): {pattern.description}")
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

    def record_research_outcome(self, phase_id: str, outcome: str, insights: Dict[str, Any]) -> None:
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
