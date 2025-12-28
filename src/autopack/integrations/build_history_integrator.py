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

try:
    import sqlite3
except ImportError:
    sqlite3 = None

logger = logging.getLogger(__name__)


@dataclass
class HistoricalPattern:
    """Represents a pattern extracted from build history."""
    
    pattern_type: str  # 'success', 'failure', 'recurring_issue'
    category: str  # Task category (e.g., 'IMPLEMENT_FEATURE', 'FIX_BUG')
    description: str
    frequency: int
    examples: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class BuildHistoryInsights:
    """Aggregated insights from build history."""
    
    total_phases: int = 0
    successful_phases: int = 0
    failed_phases: int = 0
    patterns: List[HistoricalPattern] = field(default_factory=list)
    common_pitfalls: List[str] = field(default_factory=list)
    best_practices: List[str] = field(default_factory=list)
    related_research: List[str] = field(default_factory=list)


class BuildHistoryIntegrator:
    """Integrates BUILD_HISTORY data with research system."""
    
    def __init__(
        self,
        build_history_path: Optional[Path] = None,
        db_path: Optional[Path] = None,
    ):
        """Initialize the integrator.
        
        Args:
            build_history_path: Path to BUILD_HISTORY.md file
            db_path: Path to autopack.db database
        """
        self.build_history_path = build_history_path or Path("BUILD_HISTORY.md")
        self.db_path = db_path or Path("autopack.db")
        self._cache: Optional[BuildHistoryInsights] = None
        self._cache_timestamp: Optional[datetime] = None
    
    def get_insights_for_task(
        self,
        task_description: str,
        category: Optional[str] = None,
    ) -> BuildHistoryInsights:
        """Get historical insights relevant to a task.
        
        Args:
            task_description: Description of the task
            category: Task category (e.g., 'IMPLEMENT_FEATURE')
            
        Returns:
            BuildHistoryInsights with relevant patterns and recommendations
        """
        insights = BuildHistoryInsights()
        
        # Extract from BUILD_HISTORY.md
        if self.build_history_path.exists():
            md_insights = self._extract_from_markdown(task_description, category)
            insights = self._merge_insights(insights, md_insights)
        
        # Extract from database
        if self.db_path.exists() and sqlite3:
            db_insights = self._extract_from_database(task_description, category)
            insights = self._merge_insights(insights, db_insights)
        
        # Identify patterns
        insights.patterns = self._identify_patterns(insights)
        
        return insights
    
    def _extract_from_markdown(
        self,
        task_description: str,
        category: Optional[str],
    ) -> BuildHistoryInsights:
        """Extract insights from BUILD_HISTORY.md."""
        insights = BuildHistoryInsights()
        
        try:
            content = self.build_history_path.read_text()
            
            # Parse phase entries
            phase_pattern = r"## Phase \d+: (.+?)\n(.+?)(?=## Phase|$)"
            phases = re.findall(phase_pattern, content, re.DOTALL)
            
            insights.total_phases = len(phases)
            
            for title, body in phases:
                # Check if relevant to current task
                if category and category.lower() not in body.lower():
                    continue
                
                # Extract status
                if "✓" in body or "SUCCESS" in body.upper():
                    insights.successful_phases += 1
                elif "✗" in body or "FAILED" in body.upper():
                    insights.failed_phases += 1
                
                # Extract lessons learned
                lessons_match = re.search(
                    r"Lessons Learned:(.+?)(?=\n##|$)",
                    body,
                    re.DOTALL | re.IGNORECASE,
                )
                if lessons_match:
                    lessons = lessons_match.group(1).strip()
                    for line in lessons.split("\n"):
                        line = line.strip("- ").strip()
                        if line:
                            insights.best_practices.append(line)
                
                # Extract issues
                issues_match = re.search(
                    r"Issues:(.+?)(?=\n##|$)",
                    body,
                    re.DOTALL | re.IGNORECASE,
                )
                if issues_match:
                    issues = issues_match.group(1).strip()
                    for line in issues.split("\n"):
                        line = line.strip("- ").strip()
                        if line:
                            insights.common_pitfalls.append(line)
        
        except Exception as e:
            logger.warning(f"Failed to extract from BUILD_HISTORY.md: {e}")
        
        return insights
    
    def _extract_from_database(
        self,
        task_description: str,
        category: Optional[str],
    ) -> BuildHistoryInsights:
        """Extract insights from autopack.db."""
        insights = BuildHistoryInsights()
        
        if not sqlite3:
            return insights
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Query phase history
            query = """
                SELECT phase_type, status, metadata
                FROM phases
                WHERE 1=1
            """
            params = []
            
            if category:
                query += " AND phase_type = ?"
                params.append(category)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            insights.total_phases = len(rows)
            
            for phase_type, status, metadata in rows:
                if status == "completed":
                    insights.successful_phases += 1
                elif status == "failed":
                    insights.failed_phases += 1
            
            conn.close()
        
        except Exception as e:
            logger.warning(f"Failed to extract from database: {e}")
        
        return insights
    
    def _merge_insights(
        self,
        base: BuildHistoryInsights,
        new: BuildHistoryInsights,
    ) -> BuildHistoryInsights:
        """Merge two insight objects."""
        base.total_phases += new.total_phases
        base.successful_phases += new.successful_phases
        base.failed_phases += new.failed_phases
        base.patterns.extend(new.patterns)
        base.common_pitfalls.extend(new.common_pitfalls)
        base.best_practices.extend(new.best_practices)
        base.related_research.extend(new.related_research)
        
        # Deduplicate
        base.common_pitfalls = list(set(base.common_pitfalls))
        base.best_practices = list(set(base.best_practices))
        base.related_research = list(set(base.related_research))
        
        return base
    
    def _identify_patterns(
        self,
        insights: BuildHistoryInsights,
    ) -> List[HistoricalPattern]:
        """Identify patterns from aggregated insights."""
        patterns = []
        
        # Success rate pattern
        if insights.total_phases > 0:
            success_rate = insights.successful_phases / insights.total_phases
            if success_rate > 0.8:
                patterns.append(
                    HistoricalPattern(
                        pattern_type="success",
                        category="general",
                        description=f"High success rate ({success_rate:.1%}) for similar tasks",
                        frequency=insights.successful_phases,
                        confidence=success_rate,
                    )
                )
            elif success_rate < 0.5:
                patterns.append(
                    HistoricalPattern(
                        pattern_type="failure",
                        category="general",
                        description=f"Low success rate ({success_rate:.1%}) - extra caution needed",
                        frequency=insights.failed_phases,
                        confidence=1.0 - success_rate,
                        recommendations=[
                            "Consider conducting research before implementation",
                            "Review past failures for common issues",
                        ],
                    )
                )
        
        # Recurring issues pattern
        issue_counts: Dict[str, int] = {}
        for issue in insights.common_pitfalls:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
        
        for issue, count in issue_counts.items():
            if count >= 2:
                patterns.append(
                    HistoricalPattern(
                        pattern_type="recurring_issue",
                        category="general",
                        description=issue,
                        frequency=count,
                        confidence=min(count / 5.0, 1.0),
                        recommendations=[
                            f"This issue has occurred {count} times before",
                            "Review past resolutions before proceeding",
                        ],
                    )
                )
        
        return patterns
    
    def should_trigger_research(
        self,
        task_description: str,
        category: Optional[str] = None,
        threshold: float = 0.5,
    ) -> bool:
        """Determine if research should be triggered based on history.
        
        Args:
            task_description: Description of the task
            category: Task category
            threshold: Success rate threshold below which research is recommended
            
        Returns:
            True if research is recommended
        """
        insights = self.get_insights_for_task(task_description, category)
        
        if insights.total_phases == 0:
            # No history - research might be helpful
            return True
        
        success_rate = insights.successful_phases / insights.total_phases
        
        # Trigger research if success rate is low
        if success_rate < threshold:
            return True
        
        # Trigger if there are recurring issues
        recurring_issues = [
            p for p in insights.patterns
            if p.pattern_type == "recurring_issue" and p.frequency >= 2
        ]
        if recurring_issues:
            return True
        
        return False
    
    def format_insights_for_prompt(
        self,
        insights: BuildHistoryInsights,
    ) -> str:
        """Format insights for inclusion in LLM prompts.
        
        Args:
            insights: Insights to format
            
        Returns:
            Formatted string for prompt injection
        """
        lines = ["# Historical Context from BUILD_HISTORY\n"]
        
        if insights.total_phases > 0:
            success_rate = insights.successful_phases / insights.total_phases
            lines.append(
                f"Past Performance: {insights.successful_phases}/{insights.total_phases} "
                f"phases successful ({success_rate:.1%})\n"
            )
        
        if insights.patterns:
            lines.append("\n## Identified Patterns:")
            for pattern in insights.patterns:
                lines.append(f"- [{pattern.pattern_type.upper()}] {pattern.description}")
                if pattern.recommendations:
                    for rec in pattern.recommendations:
                        lines.append(f"  → {rec}")
        
        if insights.common_pitfalls:
            lines.append("\n## Common Pitfalls to Avoid:")
            for pitfall in insights.common_pitfalls[:5]:  # Top 5
                lines.append(f"- {pitfall}")
        
        if insights.best_practices:
            lines.append("\n## Recommended Best Practices:")
            for practice in insights.best_practices[:5]:  # Top 5
                lines.append(f"- {practice}")
        
        return "\n".join(lines)
