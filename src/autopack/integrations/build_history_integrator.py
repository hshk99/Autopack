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
    last_seen: datetime
    related_phases: List[str] = field(default_factory=list)
    resolution: Optional[str] = None
    confidence: float = 0.0


@dataclass
class BuildHistoryInsight:
    """Insights extracted from build history for research planning."""
    
    patterns: List[HistoricalPattern]
    success_rate: Dict[str, float]  # Category -> success rate
    common_issues: List[str]
    recommended_approaches: List[str]
    relevant_context: Dict[str, Any]
    extracted_at: datetime = field(default_factory=datetime.now)


class BuildHistoryIntegrator:
    """Integrates BUILD_HISTORY data with research system."""
    
    def __init__(
        self,
        build_history_path: Optional[Path] = None,
        db_path: Optional[Path] = None,
        min_pattern_frequency: int = 2,
    ):
        """Initialize the integrator.
        
        Args:
            build_history_path: Path to BUILD_HISTORY.md file
            db_path: Path to autopack.db database
            min_pattern_frequency: Minimum occurrences to consider a pattern
        """
        self.build_history_path = build_history_path or Path("BUILD_HISTORY.md")
        self.db_path = db_path or Path("autopack.db")
        self.min_pattern_frequency = min_pattern_frequency
        self._cache: Optional[BuildHistoryInsight] = None
        self._cache_timestamp: Optional[datetime] = None
    
    def extract_insights(
        self,
        task_category: Optional[str] = None,
        force_refresh: bool = False,
    ) -> BuildHistoryInsight:
        """Extract insights from build history.
        
        Args:
            task_category: Filter insights for specific task category
            force_refresh: Force refresh of cached insights
            
        Returns:
            BuildHistoryInsight with extracted patterns and recommendations
        """
        # Check cache
        if not force_refresh and self._cache and self._cache_timestamp:
            cache_age = (datetime.now() - self._cache_timestamp).total_seconds()
            if cache_age < 300:  # 5 minute cache
                logger.debug("Using cached build history insights")
                return self._filter_insights(self._cache, task_category)
        
        logger.info("Extracting insights from build history")
        
        # Extract from BUILD_HISTORY.md
        md_patterns = self._extract_from_markdown()
        
        # Extract from database if available
        db_patterns = self._extract_from_database()
        
        # Merge and analyze patterns
        all_patterns = md_patterns + db_patterns
        patterns = self._analyze_patterns(all_patterns)
        
        # Calculate success rates
        success_rate = self._calculate_success_rates(patterns)
        
        # Identify common issues
        common_issues = self._identify_common_issues(patterns)
        
        # Generate recommendations
        recommended_approaches = self._generate_recommendations(patterns)
        
        # Build insight object
        insight = BuildHistoryInsight(
            patterns=patterns,
            success_rate=success_rate,
            common_issues=common_issues,
            recommended_approaches=recommended_approaches,
            relevant_context=self._extract_context(patterns),
        )
        
        # Update cache
        self._cache = insight
        self._cache_timestamp = datetime.now()
        
        return self._filter_insights(insight, task_category)

    # ---------------------------------------------------------------------
    # Compatibility shims (legacy public API used by integration tests)
    # ---------------------------------------------------------------------

    def load_history(self) -> List[Dict[str, Any]]:
        """Legacy helper: load BUILD_HISTORY.md and return a list of entries.

        The integration tests use a lightweight BUILD_HISTORY format:
          `## Phase: <CATEGORY> - <Title> (SUCCESS|FAILED) [timestamp]`
        """
        entries: List[Dict[str, Any]] = []
        if not self.build_history_path.exists():
            return entries

        try:
            content = self.build_history_path.read_text(encoding="utf-8")
        except Exception:
            content = self.build_history_path.read_text()

        line_re = re.compile(
            r"^## Phase:\s*(?P<category>[A-Z0-9_]+)\s*-\s*(?P<title>.+?)\s*\((?P<status>SUCCESS|FAILED)\)\s*\[(?P<ts>[^\]]+)\]\s*$"
        )
        for line in content.splitlines():
            m = line_re.match(line.strip())
            if not m:
                continue
            raw_status = m.group("status")
            status = "COMPLETED" if raw_status == "SUCCESS" else "FAILED"
            ts_raw = m.group("ts")
            try:
                ts = datetime.fromisoformat(ts_raw)
            except Exception:
                ts = datetime.now()
            entries.append(
                {
                    "category": m.group("category"),
                    "title": m.group("title"),
                    "status": status,
                    "timestamp": ts,
                    "raw": line.strip(),
                }
            )
        return entries

    def analyze_patterns(self) -> List[HistoricalPattern]:
        """Legacy helper: return analyzed patterns from the available history."""
        # Prefer the existing insight extractor (uses both markdown + DB when possible).
        try:
            insight = self.extract_insights(force_refresh=True)
            if insight.patterns:
                return insight.patterns
        except Exception:
            pass

        # Fallback: analyze the test-friendly BUILD_HISTORY format.
        #
        # NOTE: The legacy tests expect patterns even when each (category, status)
        # bucket has frequency=1. Our main analyzer uses `min_pattern_frequency`
        # (default=2) which would otherwise filter everything out. For this legacy
        # method we intentionally return patterns for frequency>=1.
        entries = self.load_history()
        counts: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
        for i, entry in enumerate(entries, start=1):
            category = entry.get("category", "UNKNOWN")
            status = entry.get("status", "UNKNOWN")
            key = (category, status)
            counts.setdefault(key, []).append(
                {
                    "phase_id": f"phase_{i}",
                    "timestamp": entry.get("timestamp", datetime.now()),
                    "raw": entry.get("raw", ""),
                }
            )

        patterns: List[HistoricalPattern] = []
        for (category, status), items in counts.items():
            timestamps = [it.get("timestamp", datetime.now()) for it in items]
            last_seen = max(timestamps) if timestamps else datetime.now()
            pattern_type = "success" if status == "COMPLETED" else "failure"
            patterns.append(
                HistoricalPattern(
                    pattern_type=pattern_type,
                    category=category,
                    description=f"{len(items)} {status} phases in {category}",
                    frequency=len(items),
                    last_seen=last_seen,
                    related_phases=[it.get("phase_id", "") for it in items],
                    confidence=min(len(items) / 10.0, 1.0),
                )
            )

        return patterns

    def get_research_recommendations(self, task_description: str) -> List[str]:
        """Legacy helper: return recommended research prompts/approaches."""
        try:
            insight = self.extract_insights(force_refresh=True)
            recs = list(insight.recommended_approaches)
        except Exception:
            recs = []

        # Always provide at least one actionable recommendation.
        if not recs:
            recs = [
                f"Research best practices and common pitfalls for: {task_description}",
            ]
        return recs
    
    def _extract_from_markdown(self) -> List[Dict[str, Any]]:
        """Extract patterns from BUILD_HISTORY.md."""
        if not self.build_history_path.exists():
            logger.warning(f"BUILD_HISTORY.md not found at {self.build_history_path}")
            return []
        
        patterns = []
        try:
            content = self.build_history_path.read_text()
            
            # Extract phase entries
            phase_pattern = r"## Phase (\d+): (.+?)\n(.+?)(?=\n## Phase|\Z)"
            matches = re.finditer(phase_pattern, content, re.DOTALL)
            
            for match in matches:
                phase_num = match.group(1)
                phase_title = match.group(2)
                phase_content = match.group(3)
                
                # Extract category
                category_match = re.search(r"Category: (\w+)", phase_content)
                category = category_match.group(1) if category_match else "UNKNOWN"
                
                # Extract status
                status_match = re.search(r"Status: (\w+)", phase_content)
                status = status_match.group(1) if status_match else "UNKNOWN"
                
                # Extract timestamp
                timestamp_match = re.search(r"Completed: ([\d-]+ [\d:]+)", phase_content)
                timestamp = None
                if timestamp_match:
                    try:
                        timestamp = datetime.strptime(
                            timestamp_match.group(1), "%Y-%m-%d %H:%M:%S"
                        )
                    except ValueError:
                        pass
                
                patterns.append({
                    "phase_id": f"phase_{phase_num}",
                    "title": phase_title,
                    "category": category,
                    "status": status,
                    "timestamp": timestamp or datetime.now(),
                    "content": phase_content,
                })
            
            logger.info(f"Extracted {len(patterns)} patterns from BUILD_HISTORY.md")
        except Exception as e:
            logger.error(f"Error extracting from BUILD_HISTORY.md: {e}")
        
        return patterns
    
    def _extract_from_database(self) -> List[Dict[str, Any]]:
        """Extract patterns from autopack.db."""
        if not sqlite3:
            logger.debug("sqlite3 not available, skipping database extraction")
            return []
        
        if not self.db_path.exists():
            logger.debug(f"Database not found at {self.db_path}")
            return []
        
        patterns = []
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Query phase history
            cursor.execute("""
                SELECT phase_id, category, status, created_at, completed_at, metadata
                FROM phases
                WHERE completed_at IS NOT NULL
                ORDER BY completed_at DESC
                LIMIT 100
            """)
            
            for row in cursor.fetchall():
                phase_id, category, status, created_at, completed_at, metadata = row
                
                patterns.append({
                    "phase_id": phase_id,
                    "category": category,
                    "status": status,
                    "timestamp": datetime.fromisoformat(completed_at),
                    "metadata": metadata,
                })
            
            conn.close()
            logger.info(f"Extracted {len(patterns)} patterns from database")
        except Exception as e:
            logger.error(f"Error extracting from database: {e}")
        
        return patterns
    
    def _analyze_patterns(self, raw_patterns: List[Dict[str, Any]]) -> List[HistoricalPattern]:
        """Analyze raw patterns and create HistoricalPattern objects."""
        # Group by category and status
        category_status: Dict[tuple, List[Dict]] = {}
        for pattern in raw_patterns:
            key = (pattern.get("category", "UNKNOWN"), pattern.get("status", "UNKNOWN"))
            if key not in category_status:
                category_status[key] = []
            category_status[key].append(pattern)
        
        # Create HistoricalPattern objects
        patterns = []
        for (category, status), items in category_status.items():
            if len(items) < self.min_pattern_frequency:
                continue
            
            pattern_type = "success" if status == "COMPLETED" else "failure"
            
            # Get most recent timestamp
            timestamps = [item["timestamp"] for item in items if "timestamp" in item]
            last_seen = max(timestamps) if timestamps else datetime.now()
            
            # Extract phase IDs
            phase_ids = [item.get("phase_id", "") for item in items]
            
            patterns.append(HistoricalPattern(
                pattern_type=pattern_type,
                category=category,
                description=f"{len(items)} {status} phases in {category}",
                frequency=len(items),
                last_seen=last_seen,
                related_phases=phase_ids,
                confidence=min(len(items) / 10.0, 1.0),  # Max confidence at 10 occurrences
            ))
        
        return patterns
    
    def _calculate_success_rates(self, patterns: List[HistoricalPattern]) -> Dict[str, float]:
        """Calculate success rates by category."""
        category_stats: Dict[str, Dict[str, int]] = {}
        
        for pattern in patterns:
            if pattern.category not in category_stats:
                category_stats[pattern.category] = {"success": 0, "failure": 0}
            
            if pattern.pattern_type == "success":
                category_stats[pattern.category]["success"] += pattern.frequency
            else:
                category_stats[pattern.category]["failure"] += pattern.frequency
        
        success_rates = {}
        for category, stats in category_stats.items():
            total = stats["success"] + stats["failure"]
            if total > 0:
                success_rates[category] = stats["success"] / total
        
        return success_rates
    
    def _identify_common_issues(self, patterns: List[HistoricalPattern]) -> List[str]:
        """Identify common issues from failure patterns."""
        issues = []
        
        failure_patterns = [p for p in patterns if p.pattern_type == "failure"]
        failure_patterns.sort(key=lambda p: p.frequency, reverse=True)
        
        for pattern in failure_patterns[:5]:  # Top 5 issues
            issues.append(
                f"{pattern.category}: {pattern.frequency} failures "
                f"(last seen: {pattern.last_seen.strftime('%Y-%m-%d')})"
            )
        
        return issues
    
    def _generate_recommendations(self, patterns: List[HistoricalPattern]) -> List[str]:
        """Generate recommendations based on patterns."""
        recommendations = []
        
        # Recommend research for categories with low success rates
        category_success = {}
        for pattern in patterns:
            if pattern.category not in category_success:
                category_success[pattern.category] = {"success": 0, "total": 0}
            
            category_success[pattern.category]["total"] += pattern.frequency
            if pattern.pattern_type == "success":
                category_success[pattern.category]["success"] += pattern.frequency
        
        for category, stats in category_success.items():
            if stats["total"] >= 3:  # Minimum sample size
                success_rate = stats["success"] / stats["total"]
                if success_rate < 0.6:
                    recommendations.append(
                        f"Consider research phase for {category} tasks "
                        f"(current success rate: {success_rate:.1%})"
                    )
        
        # Recommend caution for categories with recent failures
        recent_failures = [
            p for p in patterns 
            if p.pattern_type == "failure" 
            and (datetime.now() - p.last_seen).days < 7
        ]
        
        for pattern in recent_failures:
            recommendations.append(
                f"Recent failures in {pattern.category} - "
                f"review past issues before proceeding"
            )
        
        return recommendations
    
    def _extract_context(self, patterns: List[HistoricalPattern]) -> Dict[str, Any]:
        """Extract relevant context from patterns."""
        return {
            "total_phases": sum(p.frequency for p in patterns),
            "categories": list(set(p.category for p in patterns)),
            "analysis_timestamp": datetime.now().isoformat(),
        }
    
    def _filter_insights(
        self, 
        insight: BuildHistoryInsight, 
        category: Optional[str],
    ) -> BuildHistoryInsight:
        """Filter insights for specific category."""
        if not category:
            return insight
        
        filtered_patterns = [
            p for p in insight.patterns 
            if p.category == category
        ]
        
        return BuildHistoryInsight(
            patterns=filtered_patterns,
            success_rate={category: insight.success_rate.get(category, 0.0)},
            common_issues=[
                issue for issue in insight.common_issues 
                if category in issue
            ],
            recommended_approaches=[
                rec for rec in insight.recommended_approaches 
                if category in rec
            ],
            relevant_context=insight.relevant_context,
            extracted_at=insight.extracted_at,
        )
    
    def should_trigger_research(
        self,
        task_description: str,
        task_category: str,
        threshold: float = 0.7,
    ) -> tuple[bool, str]:
        """Determine if research should be triggered for a task.
        
        Args:
            task_description: Description of the task
            task_category: Category of the task
            threshold: Success rate threshold below which to trigger research
            
        Returns:
            Tuple of (should_trigger, reason)
        """
        insights = self.extract_insights(task_category=task_category)
        
        # Check success rate
        success_rate = insights.success_rate.get(task_category, 1.0)
        if success_rate < threshold:
            return (
                True,
                f"Low success rate for {task_category}: {success_rate:.1%} "
                f"(threshold: {threshold:.1%})"
            )
        
        # Check for recent failures
        recent_failures = [
            p for p in insights.patterns
            if p.pattern_type == "failure"
            and (datetime.now() - p.last_seen).days < 7
        ]
        
        if recent_failures:
            return (
                True,
                f"Recent failures detected in {task_category} "
                f"({len(recent_failures)} in past week)"
            )
        
        # Check for complexity indicators in description
        complexity_keywords = [
            "complex", "multiple", "integration", "architecture",
            "design", "evaluate", "compare", "research"
        ]
        
        if any(keyword in task_description.lower() for keyword in complexity_keywords):
            return (
                True,
                "Task description indicates complexity requiring research"
            )
        
        return (False, "No research trigger conditions met")
