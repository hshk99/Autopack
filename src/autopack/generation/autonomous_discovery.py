"""Autonomous Phase 1 discovery for improvement identification."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from feedback.optimization_detector import OptimizationDetector
    from memory.failure_analyzer import FailureAnalyzer
    from memory.metrics_db import MetricsDatabase


@dataclass
class DiscoveredIMP:
    """Represents an automatically discovered improvement opportunity."""

    imp_id: str
    title: str
    category: str  # 'security', 'performance', 'reliability', 'feature', 'refactor'
    priority: str  # 'critical', 'high', 'medium', 'low'
    description: str
    files_affected: List[str]
    discovery_source: str  # 'failure_pattern', 'optimization', 'code_analysis', 'metrics'
    confidence: float  # 0.0 to 1.0
    dependencies: List[str] = field(default_factory=list)
    discovered_at: str = field(default_factory=lambda: datetime.now().isoformat())


class AutonomousDiscovery:
    """Discovers improvement opportunities automatically."""

    CATEGORY_PREFIXES: Dict[str, str] = {
        "security": "SEC",
        "performance": "PERF",
        "reliability": "REL",
        "feature": "FEAT",
        "refactor": "REF",
        "telemetry": "TEL",
        "memory": "MEM",
        "generation": "GEN",
        "feedback": "LOOP",
    }

    def __init__(
        self,
        metrics_db: Optional["MetricsDatabase"] = None,
        failure_analyzer: Optional["FailureAnalyzer"] = None,
        optimization_detector: Optional["OptimizationDetector"] = None,
    ) -> None:
        """Initialize with optional dependencies."""
        self.metrics_db = metrics_db
        self.failure_analyzer = failure_analyzer
        self.optimization_detector = optimization_detector
        self._imp_counter: Dict[str, int] = {}
        self._discovered: List[DiscoveredIMP] = []

    def discover_all(self) -> List[DiscoveredIMP]:
        """Run all discovery methods and return found IMPs."""
        self._discovered = []

        # Discover from failure patterns
        if self.failure_analyzer:
            self._discovered.extend(self._discover_from_failures())

        # Discover from optimization suggestions
        if self.optimization_detector:
            self._discovered.extend(self._discover_from_optimizations())

        # Discover from metrics anomalies
        if self.metrics_db:
            self._discovered.extend(self._discover_from_metrics())

        return self._discovered

    def _discover_from_failures(self) -> List[DiscoveredIMP]:
        """Discover IMPs from recurring failure patterns."""
        imps: List[DiscoveredIMP] = []
        stats = self.failure_analyzer.get_failure_statistics()

        for pattern in stats.get("top_patterns", []):
            if pattern.get("occurrence_count", 0) >= 3 and not pattern.get("resolution"):
                category = self._map_failure_to_category(pattern.get("failure_type", "unknown"))
                imps.append(
                    DiscoveredIMP(
                        imp_id=self._generate_imp_id(category),
                        title=f"Fix recurring {pattern.get('failure_type', 'unknown')} failures",
                        category=category,
                        priority="high" if pattern.get("occurrence_count", 0) >= 5 else "medium",
                        description=(
                            f"Recurring failure pattern detected "
                            f"{pattern.get('occurrence_count')} times with no resolution. "
                            f"Pattern hash: {pattern.get('pattern_hash')}"
                        ),
                        files_affected=[],
                        discovery_source="failure_pattern",
                        confidence=min(0.9, 0.5 + pattern.get("occurrence_count", 0) * 0.1),
                    )
                )

        return imps

    def _discover_from_optimizations(self) -> List[DiscoveredIMP]:
        """Discover IMPs from optimization detector suggestions."""
        imps: List[DiscoveredIMP] = []
        suggestions = self.optimization_detector.detect_all()

        for suggestion in suggestions:
            category = self._map_optimization_to_category(suggestion.category)
            imps.append(
                DiscoveredIMP(
                    imp_id=self._generate_imp_id(category),
                    title=f"Optimize {suggestion.category.replace('_', ' ')}",
                    category=category,
                    priority=suggestion.severity,
                    description=f"{suggestion.description}. {suggestion.implementation_hint}",
                    files_affected=[],
                    discovery_source="optimization",
                    confidence=0.7 if suggestion.severity in ["high", "critical"] else 0.5,
                )
            )

        return imps

    def _discover_from_metrics(self) -> List[DiscoveredIMP]:
        """Discover IMPs from metrics anomalies."""
        imps: List[DiscoveredIMP] = []
        metrics = self.metrics_db.get_daily_metrics(days=7)

        if not metrics:
            return imps

        # Detect declining trends
        if len(metrics) >= 3:
            recent_success = sum(m.get("tasks_completed", 0) for m in metrics[:3])
            older_success = (
                sum(m.get("tasks_completed", 0) for m in metrics[3:6])
                if len(metrics) >= 6
                else recent_success
            )

            if older_success > 0 and recent_success < older_success * 0.7:
                decline_pct = ((older_success - recent_success) / older_success) * 100
                imps.append(
                    DiscoveredIMP(
                        imp_id=self._generate_imp_id("reliability"),
                        title="Investigate declining task completion rate",
                        category="reliability",
                        priority="high",
                        description=(
                            f"Task completion rate declined by {decline_pct:.0f}% "
                            f"over the last week"
                        ),
                        files_affected=[],
                        discovery_source="metrics",
                        confidence=0.6,
                    )
                )

        return imps

    def _map_failure_to_category(self, failure_type: str) -> str:
        """Map failure type to IMP category."""
        mapping: Dict[str, str] = {
            "ci_test_failure": "reliability",
            "ci_build_failure": "reliability",
            "merge_conflict": "refactor",
            "stagnation": "performance",
            "connection_error": "reliability",
            "permission_denied": "security",
            "rate_limit": "performance",
            "lint_failure": "refactor",
            "type_error": "reliability",
        }
        return mapping.get(failure_type, "reliability")

    def _map_optimization_to_category(self, opt_category: str) -> str:
        """Map optimization category to IMP category."""
        mapping: Dict[str, str] = {
            "slot_utilization": "performance",
            "ci_efficiency": "reliability",
            "stagnation": "reliability",
            "pr_merge_time": "performance",
        }
        return mapping.get(opt_category, "performance")

    def _generate_imp_id(self, category: str) -> str:
        """Generate unique IMP ID."""
        prefix = self.CATEGORY_PREFIXES.get(category, "IMP")
        self._imp_counter[prefix] = self._imp_counter.get(prefix, 0) + 1
        return f"IMP-{prefix}-{self._imp_counter[prefix]:03d}"

    def export_to_json(self, output_path: str) -> None:
        """Export discovered IMPs to JSON file."""
        output: Dict[str, Any] = {
            "discovered_at": datetime.now().isoformat(),
            "total_imps": len(self._discovered),
            "imps": [
                {
                    "imp_id": imp.imp_id,
                    "title": imp.title,
                    "category": imp.category,
                    "priority": imp.priority,
                    "description": imp.description,
                    "files_affected": imp.files_affected,
                    "discovery_source": imp.discovery_source,
                    "confidence": imp.confidence,
                    "dependencies": imp.dependencies,
                    "discovered_at": imp.discovered_at,
                }
                for imp in self._discovered
            ],
        }
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)

    def get_summary(self) -> str:
        """Get human-readable summary of discovered IMPs."""
        if not self._discovered:
            return "No improvements discovered. Run discover_all() first."

        lines = [f"Discovered {len(self._discovered)} potential improvements:\n"]
        by_priority: Dict[str, List[DiscoveredIMP]] = {
            "critical": [],
            "high": [],
            "medium": [],
            "low": [],
        }

        for imp in self._discovered:
            by_priority.get(imp.priority, by_priority["medium"]).append(imp)

        for priority in ["critical", "high", "medium", "low"]:
            if by_priority[priority]:
                lines.append(f"\n{priority.upper()} ({len(by_priority[priority])}):")
                for imp in by_priority[priority]:
                    lines.append(f"  [{imp.imp_id}] {imp.title} (confidence: {imp.confidence:.0%})")

        return "\n".join(lines)
