"""
Build History Analyzer for Research Pipeline.

Analyzes build history to extract feasibility signals and cost-effectiveness
insights that inform research decisions. Feeds build outcomes into the
research pipeline to improve recommendations over time.

This module bridges build execution history with research analysis by:
1. Collecting and analyzing build outcomes and metrics
2. Extracting feasibility signals from historical builds
3. Feeding outcomes into cost-effectiveness analysis
4. Providing build history context for feasibility assessments
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BuildOutcome(Enum):
    """Possible build outcomes."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    ABANDONED = "abandoned"
    BLOCKED = "blocked"


class FeasibilitySignal(Enum):
    """Types of feasibility signals extracted from build history."""

    COMPLEXITY_INDICATOR = "complexity_indicator"
    TIME_ESTIMATE_ACCURACY = "time_estimate_accuracy"
    DEPENDENCY_RISK = "dependency_risk"
    TECH_STACK_MATURITY = "tech_stack_maturity"
    RESOURCE_UTILIZATION = "resource_utilization"
    ERROR_FREQUENCY = "error_frequency"


class MetricTrend(Enum):
    """Trend direction for metrics."""

    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass
class BuildMetrics:
    """Metrics collected from a single build."""

    build_id: str
    project_type: str
    outcome: BuildOutcome
    timestamp: datetime

    # Time metrics
    estimated_duration_hours: float = 0.0
    actual_duration_hours: float = 0.0

    # Complexity metrics
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    test_count: int = 0
    test_pass_rate: float = 0.0

    # Cost metrics
    estimated_cost: float = 0.0
    actual_cost: float = 0.0

    # Dependency metrics
    dependency_count: int = 0
    dependency_issues: int = 0

    # Error metrics
    error_count: int = 0
    warning_count: int = 0
    blocking_issues: int = 0

    # Tech stack
    tech_stack: List[str] = field(default_factory=list)

    # Metadata
    phase_id: Optional[str] = None
    category: Optional[str] = None
    notes: str = ""

    @property
    def time_estimate_accuracy(self) -> float:
        """Calculate time estimation accuracy (0-1, 1 = perfect)."""
        if self.estimated_duration_hours <= 0:
            return 0.0
        ratio = self.actual_duration_hours / self.estimated_duration_hours
        # Score: 1.0 if exact, decreases as ratio deviates from 1.0
        return max(0.0, 1.0 - abs(1.0 - ratio))

    @property
    def cost_estimate_accuracy(self) -> float:
        """Calculate cost estimation accuracy (0-1, 1 = perfect)."""
        if self.estimated_cost <= 0:
            return 0.0
        ratio = self.actual_cost / self.estimated_cost
        return max(0.0, 1.0 - abs(1.0 - ratio))

    @property
    def success_score(self) -> float:
        """Calculate overall success score (0-1)."""
        base_score = {
            BuildOutcome.SUCCESS: 1.0,
            BuildOutcome.PARTIAL: 0.6,
            BuildOutcome.FAILED: 0.0,
            BuildOutcome.ABANDONED: 0.1,
            BuildOutcome.BLOCKED: 0.2,
        }.get(self.outcome, 0.0)

        # Adjust for test pass rate
        if self.test_count > 0:
            test_factor = self.test_pass_rate
        else:
            test_factor = 1.0

        # Adjust for error rate
        total_issues = self.error_count + self.blocking_issues
        if total_issues > 0:
            error_factor = max(0.5, 1.0 - (total_issues * 0.1))
        else:
            error_factor = 1.0

        return base_score * test_factor * error_factor

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "build_id": self.build_id,
            "project_type": self.project_type,
            "outcome": self.outcome.value,
            "timestamp": self.timestamp.isoformat(),
            "estimated_duration_hours": self.estimated_duration_hours,
            "actual_duration_hours": self.actual_duration_hours,
            "files_changed": self.files_changed,
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
            "test_count": self.test_count,
            "test_pass_rate": self.test_pass_rate,
            "estimated_cost": self.estimated_cost,
            "actual_cost": self.actual_cost,
            "dependency_count": self.dependency_count,
            "dependency_issues": self.dependency_issues,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "blocking_issues": self.blocking_issues,
            "tech_stack": self.tech_stack,
            "phase_id": self.phase_id,
            "category": self.category,
            "notes": self.notes,
            "time_estimate_accuracy": self.time_estimate_accuracy,
            "cost_estimate_accuracy": self.cost_estimate_accuracy,
            "success_score": self.success_score,
        }


@dataclass
class FeasibilityFeedback:
    """Feasibility feedback derived from build history."""

    signal_type: FeasibilitySignal
    signal_value: float  # 0-1 score
    confidence: float  # 0-1 confidence in the signal
    sample_size: int
    trend: MetricTrend
    supporting_evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "signal_type": self.signal_type.value,
            "signal_value": self.signal_value,
            "confidence": self.confidence,
            "sample_size": self.sample_size,
            "trend": self.trend.value,
            "supporting_evidence": self.supporting_evidence,
        }


@dataclass
class CostEffectivenessFeedback:
    """Cost-effectiveness feedback from build history."""

    estimation_accuracy: float  # 0-1
    cost_overrun_rate: float  # Percentage of builds with cost overrun
    avg_cost_deviation: float  # Average % deviation from estimates
    high_cost_factors: List[str]  # Factors correlated with high costs
    cost_optimization_opportunities: List[str]
    sample_size: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "estimation_accuracy": self.estimation_accuracy,
            "cost_overrun_rate": self.cost_overrun_rate,
            "avg_cost_deviation": self.avg_cost_deviation,
            "high_cost_factors": self.high_cost_factors,
            "cost_optimization_opportunities": self.cost_optimization_opportunities,
            "sample_size": self.sample_size,
        }


@dataclass
class BuildHistoryAnalysisResult:
    """Complete analysis result from build history."""

    project_type: Optional[str]
    analysis_timestamp: datetime
    total_builds_analyzed: int
    date_range_days: int

    # Aggregate metrics
    overall_success_rate: float
    avg_time_estimate_accuracy: float
    avg_cost_estimate_accuracy: float

    # Feasibility signals
    feasibility_signals: List[FeasibilityFeedback]

    # Cost-effectiveness feedback
    cost_effectiveness: CostEffectivenessFeedback

    # Recommendations
    recommendations: List[str]
    warnings: List[str]

    # Detailed metrics by category
    metrics_by_category: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    metrics_by_tech_stack: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "project_type": self.project_type,
            "analysis_timestamp": self.analysis_timestamp.isoformat(),
            "total_builds_analyzed": self.total_builds_analyzed,
            "date_range_days": self.date_range_days,
            "overall_success_rate": self.overall_success_rate,
            "avg_time_estimate_accuracy": self.avg_time_estimate_accuracy,
            "avg_cost_estimate_accuracy": self.avg_cost_estimate_accuracy,
            "feasibility_signals": [s.to_dict() for s in self.feasibility_signals],
            "cost_effectiveness": self.cost_effectiveness.to_dict(),
            "recommendations": self.recommendations,
            "warnings": self.warnings,
            "metrics_by_category": self.metrics_by_category,
            "metrics_by_tech_stack": self.metrics_by_tech_stack,
        }


class BuildHistoryAnalyzer:
    """
    Analyzes build history to extract feasibility and cost-effectiveness signals.

    This analyzer:
    1. Collects build outcomes and metrics from BUILD_HISTORY.md
    2. Extracts feasibility signals for new project assessments
    3. Provides cost-effectiveness feedback from historical data
    4. Identifies patterns that inform research recommendations
    """

    def __init__(
        self,
        build_history_path: Optional[Path] = None,
        max_history_days: int = 365,
    ):
        """Initialize the analyzer.

        Args:
            build_history_path: Path to BUILD_HISTORY.md (defaults to repo root)
            max_history_days: Maximum age of builds to consider (default: 365)
        """
        self.build_history_path = build_history_path or Path("BUILD_HISTORY.md")
        self.max_history_days = max_history_days
        self._metrics_cache: List[BuildMetrics] = []
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_minutes = 30

    def collect_build_metrics(self, force_refresh: bool = False) -> List[BuildMetrics]:
        """Collect build metrics from BUILD_HISTORY.md.

        Args:
            force_refresh: Force re-parsing even if cache is valid

        Returns:
            List of BuildMetrics from history
        """
        # Check cache validity
        if (
            not force_refresh
            and self._metrics_cache
            and self._cache_timestamp
            and datetime.now() - self._cache_timestamp < timedelta(minutes=self._cache_ttl_minutes)
        ):
            return self._metrics_cache

        # Parse BUILD_HISTORY.md
        metrics = self._parse_build_history()

        # Filter by age
        cutoff_date = datetime.now() - timedelta(days=self.max_history_days)
        metrics = [m for m in metrics if m.timestamp >= cutoff_date]

        # Update cache
        self._metrics_cache = metrics
        self._cache_timestamp = datetime.now()

        logger.info(f"Collected {len(metrics)} build metrics from history")
        return metrics

    def _parse_build_history(self) -> List[BuildMetrics]:
        """Parse BUILD_HISTORY.md into BuildMetrics."""
        if not self.build_history_path.exists():
            logger.warning(f"BUILD_HISTORY not found at {self.build_history_path}")
            return []

        try:
            content = self.build_history_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Error reading BUILD_HISTORY: {e}")
            return []

        metrics = []
        phase_pattern = r"## Phase (\d+): (.+?)\n(.+?)(?=## Phase|$)"

        for match in re.finditer(phase_pattern, content, re.DOTALL):
            phase_num = match.group(1)
            phase_title = match.group(2)
            phase_content = match.group(3)

            build_metrics = self._extract_metrics_from_phase(phase_num, phase_title, phase_content)
            if build_metrics:
                metrics.append(build_metrics)

        return metrics

    def _extract_metrics_from_phase(
        self, phase_num: str, phase_title: str, content: str
    ) -> Optional[BuildMetrics]:
        """Extract metrics from a single phase entry."""
        # Extract status
        outcome = BuildOutcome.SUCCESS
        status_match = re.search(r"\*\*Status\*\*:\s*([✓✗])\s*(\w+)", content)
        if status_match:
            symbol = status_match.group(1)
            status_text = status_match.group(2).lower()
            if symbol == "✗" or "fail" in status_text:
                outcome = BuildOutcome.FAILED
            elif "partial" in status_text:
                outcome = BuildOutcome.PARTIAL
            elif "abandon" in status_text:
                outcome = BuildOutcome.ABANDONED
            elif "block" in status_text:
                outcome = BuildOutcome.BLOCKED
        else:
            status_match = re.search(r"Status:\s*(\w+)", content, re.IGNORECASE)
            if status_match:
                status_text = status_match.group(1).lower()
                if "fail" in status_text or "error" in status_text:
                    outcome = BuildOutcome.FAILED
                elif "partial" in status_text:
                    outcome = BuildOutcome.PARTIAL

        # Extract timestamp
        timestamp = datetime.now()
        time_match = re.search(r"Completed:\s*([\d-]+T[\d:]+)", content)
        if time_match:
            try:
                timestamp = datetime.fromisoformat(time_match.group(1))
            except ValueError:
                pass
        else:
            # Try alternative date formats
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", content)
            if date_match:
                try:
                    timestamp = datetime.fromisoformat(date_match.group(1))
                except ValueError:
                    pass

        # Extract category
        category_match = re.search(r"\*\*Category\*\*:\s*(\w+)", content)
        if not category_match:
            category_match = re.search(r"Category:\s*(\w+)", content, re.IGNORECASE)
        category = category_match.group(1) if category_match else "unknown"

        # Extract project type (infer from category or title)
        project_type = self._infer_project_type(phase_title, category, content)

        # Extract time metrics
        estimated_hours = 0.0
        actual_hours = 0.0
        est_match = re.search(r"Estimated.*?(\d+(?:\.\d+)?)\s*hours?", content, re.IGNORECASE)
        if est_match:
            estimated_hours = float(est_match.group(1))
        actual_match = re.search(r"Actual.*?(\d+(?:\.\d+)?)\s*hours?", content, re.IGNORECASE)
        if actual_match:
            actual_hours = float(actual_match.group(1))
        # Alternative: Duration format
        duration_match = re.search(r"Duration:\s*(\d+(?:\.\d+)?)\s*hours?", content, re.IGNORECASE)
        if duration_match and actual_hours == 0:
            actual_hours = float(duration_match.group(1))

        # Extract file changes
        files_changed = 0
        files_match = re.search(r"(\d+)\s*files?\s*changed", content, re.IGNORECASE)
        if files_match:
            files_changed = int(files_match.group(1))

        # Extract lines changed
        lines_added = 0
        lines_removed = 0
        lines_match = re.search(r"(\d+)\s*insertions?.*?(\d+)\s*deletions?", content, re.IGNORECASE)
        if lines_match:
            lines_added = int(lines_match.group(1))
            lines_removed = int(lines_match.group(2))

        # Extract test metrics
        test_count = 0
        test_pass_rate = 1.0
        test_match = re.search(r"(\d+)\s*tests?", content, re.IGNORECASE)
        if test_match:
            test_count = int(test_match.group(1))
        pass_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*pass", content, re.IGNORECASE)
        if pass_match:
            test_pass_rate = float(pass_match.group(1)) / 100.0
        else:
            # Check for pass/fail counts
            passed_match = re.search(r"(\d+)\s*passed", content, re.IGNORECASE)
            failed_match = re.search(r"(\d+)\s*failed", content, re.IGNORECASE)
            if passed_match and test_count > 0:
                test_pass_rate = int(passed_match.group(1)) / test_count

        # Extract error/warning counts
        error_count = len(re.findall(r"error", content, re.IGNORECASE))
        warning_count = len(re.findall(r"warning", content, re.IGNORECASE))
        blocking_issues = len(re.findall(r"block|critical", content, re.IGNORECASE))

        # Extract tech stack (look for common tech terms)
        tech_stack = self._extract_tech_stack(content)

        # Extract cost metrics
        estimated_cost = 0.0
        actual_cost = 0.0
        cost_match = re.search(
            r"(?:estimated\s*)?cost.*?\$?([\d,]+(?:\.\d+)?)", content, re.IGNORECASE
        )
        if cost_match:
            estimated_cost = float(cost_match.group(1).replace(",", ""))

        # Extract dependency info
        dependency_count = 0
        dependency_issues = 0
        dep_match = re.search(r"(\d+)\s*dependenc", content, re.IGNORECASE)
        if dep_match:
            dependency_count = int(dep_match.group(1))
        dep_issue_match = re.search(
            r"dependency.*?issue|issue.*?dependency", content, re.IGNORECASE
        )
        if dep_issue_match:
            dependency_issues = 1

        return BuildMetrics(
            build_id=f"phase_{phase_num}",
            project_type=project_type,
            outcome=outcome,
            timestamp=timestamp,
            estimated_duration_hours=estimated_hours,
            actual_duration_hours=actual_hours,
            files_changed=files_changed,
            lines_added=lines_added,
            lines_removed=lines_removed,
            test_count=test_count,
            test_pass_rate=test_pass_rate,
            estimated_cost=estimated_cost,
            actual_cost=actual_cost,
            dependency_count=dependency_count,
            dependency_issues=dependency_issues,
            error_count=error_count,
            warning_count=warning_count,
            blocking_issues=blocking_issues,
            tech_stack=tech_stack,
            phase_id=f"phase_{phase_num}",
            category=category,
            notes=phase_title.strip(),
        )

    def _infer_project_type(self, title: str, category: str, content: str) -> str:
        """Infer project type from phase information."""
        combined = f"{title} {category} {content}".lower()

        if any(kw in combined for kw in ["ecommerce", "shop", "store", "cart"]):
            return "ecommerce"
        elif any(kw in combined for kw in ["trading", "market", "stock", "crypto"]):
            return "trading"
        elif any(kw in combined for kw in ["content", "media", "video", "blog"]):
            return "content"
        elif any(kw in combined for kw in ["automation", "bot", "script", "cli"]):
            return "automation"
        elif any(kw in combined for kw in ["api", "backend", "service"]):
            return "api"
        elif any(kw in combined for kw in ["frontend", "ui", "web", "app"]):
            return "frontend"
        else:
            return "other"

    def _extract_tech_stack(self, content: str) -> List[str]:
        """Extract technology stack from content."""
        tech_keywords = [
            "python",
            "javascript",
            "typescript",
            "react",
            "vue",
            "angular",
            "node",
            "django",
            "flask",
            "fastapi",
            "express",
            "nextjs",
            "postgres",
            "mysql",
            "mongodb",
            "redis",
            "docker",
            "kubernetes",
            "aws",
            "gcp",
            "azure",
            "vercel",
            "netlify",
            "heroku",
        ]
        content_lower = content.lower()
        return [tech for tech in tech_keywords if tech in content_lower]

    def extract_feasibility_signals(
        self,
        project_type: Optional[str] = None,
        tech_stack: Optional[List[str]] = None,
    ) -> List[FeasibilityFeedback]:
        """Extract feasibility signals from build history.

        Args:
            project_type: Filter by project type
            tech_stack: Filter by tech stack components

        Returns:
            List of feasibility feedback signals
        """
        metrics = self.collect_build_metrics()

        # Filter by project type
        if project_type:
            metrics = [m for m in metrics if m.project_type == project_type]

        # Filter by tech stack
        if tech_stack:
            metrics = [m for m in metrics if any(t in m.tech_stack for t in tech_stack)]

        if not metrics:
            return []

        signals = []

        # 1. Complexity indicator
        avg_complexity = sum(m.files_changed + m.lines_added for m in metrics) / len(metrics)
        complexity_signal = FeasibilityFeedback(
            signal_type=FeasibilitySignal.COMPLEXITY_INDICATOR,
            signal_value=min(1.0, avg_complexity / 1000),  # Normalize
            confidence=self._calculate_confidence(len(metrics)),
            sample_size=len(metrics),
            trend=self._calculate_trend([m.files_changed + m.lines_added for m in metrics]),
            supporting_evidence=[
                f"Avg files changed: {sum(m.files_changed for m in metrics) / len(metrics):.1f}",
                f"Avg lines added: {sum(m.lines_added for m in metrics) / len(metrics):.1f}",
            ],
        )
        signals.append(complexity_signal)

        # 2. Time estimate accuracy
        time_accuracies = [
            m.time_estimate_accuracy for m in metrics if m.estimated_duration_hours > 0
        ]
        if time_accuracies:
            signals.append(
                FeasibilityFeedback(
                    signal_type=FeasibilitySignal.TIME_ESTIMATE_ACCURACY,
                    signal_value=sum(time_accuracies) / len(time_accuracies),
                    confidence=self._calculate_confidence(len(time_accuracies)),
                    sample_size=len(time_accuracies),
                    trend=self._calculate_trend(time_accuracies),
                    supporting_evidence=[
                        f"Avg estimate accuracy: {sum(time_accuracies) / len(time_accuracies):.1%}",
                        f"Builds with estimates: {len(time_accuracies)}/{len(metrics)}",
                    ],
                )
            )

        # 3. Dependency risk
        dep_issues = sum(m.dependency_issues for m in metrics)
        total_deps = sum(m.dependency_count for m in metrics)
        dep_risk = dep_issues / max(1, total_deps)
        signals.append(
            FeasibilityFeedback(
                signal_type=FeasibilitySignal.DEPENDENCY_RISK,
                signal_value=1.0 - dep_risk,  # Higher = lower risk
                confidence=self._calculate_confidence(len(metrics)),
                sample_size=len(metrics),
                trend=MetricTrend.STABLE,
                supporting_evidence=[
                    f"Dependency issues: {dep_issues}",
                    f"Total dependencies tracked: {total_deps}",
                ],
            )
        )

        # 4. Tech stack maturity
        success_by_tech: Dict[str, List[float]] = {}
        for m in metrics:
            for tech in m.tech_stack:
                if tech not in success_by_tech:
                    success_by_tech[tech] = []
                success_by_tech[tech].append(m.success_score)

        if success_by_tech:
            avg_tech_success = sum(
                sum(scores) / len(scores) for scores in success_by_tech.values()
            ) / len(success_by_tech)
            signals.append(
                FeasibilityFeedback(
                    signal_type=FeasibilitySignal.TECH_STACK_MATURITY,
                    signal_value=avg_tech_success,
                    confidence=self._calculate_confidence(len(success_by_tech)),
                    sample_size=len(success_by_tech),
                    trend=MetricTrend.STABLE,
                    supporting_evidence=[
                        f"Tech stacks analyzed: {list(success_by_tech.keys())}",
                        f"Avg success rate: {avg_tech_success:.1%}",
                    ],
                )
            )

        # 5. Error frequency
        avg_errors = sum(m.error_count for m in metrics) / len(metrics)
        error_score = max(0.0, 1.0 - (avg_errors / 10))  # Normalize to 0-1
        signals.append(
            FeasibilityFeedback(
                signal_type=FeasibilitySignal.ERROR_FREQUENCY,
                signal_value=error_score,
                confidence=self._calculate_confidence(len(metrics)),
                sample_size=len(metrics),
                trend=self._calculate_trend([m.error_count for m in metrics], inverse=True),
                supporting_evidence=[
                    f"Avg errors per build: {avg_errors:.1f}",
                    f"Total errors: {sum(m.error_count for m in metrics)}",
                ],
            )
        )

        return signals

    def analyze_cost_effectiveness(
        self,
        project_type: Optional[str] = None,
    ) -> CostEffectivenessFeedback:
        """Analyze cost-effectiveness from build history.

        Args:
            project_type: Filter by project type

        Returns:
            Cost-effectiveness feedback from history
        """
        metrics = self.collect_build_metrics()

        if project_type:
            metrics = [m for m in metrics if m.project_type == project_type]

        if not metrics:
            return CostEffectivenessFeedback(
                estimation_accuracy=0.0,
                cost_overrun_rate=0.0,
                avg_cost_deviation=0.0,
                high_cost_factors=[],
                cost_optimization_opportunities=[],
                sample_size=0,
            )

        # Calculate estimation accuracy
        cost_accuracies = [m.cost_estimate_accuracy for m in metrics if m.estimated_cost > 0]
        estimation_accuracy = (
            sum(cost_accuracies) / len(cost_accuracies) if cost_accuracies else 0.0
        )

        # Calculate cost overrun rate
        overruns = [m for m in metrics if m.estimated_cost > 0 and m.actual_cost > m.estimated_cost]
        cost_overrun_rate = len(overruns) / len(metrics) if metrics else 0.0

        # Calculate average cost deviation
        deviations = []
        for m in metrics:
            if m.estimated_cost > 0:
                deviation = abs(m.actual_cost - m.estimated_cost) / m.estimated_cost
                deviations.append(deviation)
        avg_cost_deviation = sum(deviations) / len(deviations) if deviations else 0.0

        # Identify high cost factors
        high_cost_factors = self._identify_high_cost_factors(metrics)

        # Identify optimization opportunities
        opportunities = self._identify_cost_optimization_opportunities(metrics)

        return CostEffectivenessFeedback(
            estimation_accuracy=estimation_accuracy,
            cost_overrun_rate=cost_overrun_rate,
            avg_cost_deviation=avg_cost_deviation,
            high_cost_factors=high_cost_factors,
            cost_optimization_opportunities=opportunities,
            sample_size=len(metrics),
        )

    def _identify_high_cost_factors(self, metrics: List[BuildMetrics]) -> List[str]:
        """Identify factors correlated with high costs."""
        factors = []

        # Check if high complexity correlates with high cost
        high_cost_builds = sorted(metrics, key=lambda m: m.actual_cost, reverse=True)[
            : len(metrics) // 3
        ]
        if high_cost_builds:
            avg_complexity = sum(m.files_changed for m in high_cost_builds) / len(high_cost_builds)
            overall_avg = sum(m.files_changed for m in metrics) / len(metrics)
            if avg_complexity > overall_avg * 1.5:
                factors.append("High file change count correlates with higher costs")

        # Check dependency issues
        dep_issue_builds = [m for m in metrics if m.dependency_issues > 0]
        if dep_issue_builds:
            avg_cost_with_issues = sum(m.actual_cost for m in dep_issue_builds) / len(
                dep_issue_builds
            )
            avg_cost_overall = sum(m.actual_cost for m in metrics) / len(metrics)
            if avg_cost_with_issues > avg_cost_overall * 1.2:
                factors.append("Dependency issues increase project costs")

        # Check error rates
        high_error_builds = [m for m in metrics if m.error_count > 3]
        if high_error_builds and len(high_error_builds) >= 2:
            factors.append("High error counts associated with cost overruns")

        return factors

    def _identify_cost_optimization_opportunities(self, metrics: List[BuildMetrics]) -> List[str]:
        """Identify opportunities for cost optimization."""
        opportunities = []

        # Check estimation patterns
        time_accuracies = [
            m.time_estimate_accuracy for m in metrics if m.estimated_duration_hours > 0
        ]
        if time_accuracies and sum(time_accuracies) / len(time_accuracies) < 0.6:
            opportunities.append(
                "Improve time estimation accuracy - current estimates deviate significantly"
            )

        # Check for common tech stack success
        success_by_tech: Dict[str, List[float]] = {}
        for m in metrics:
            for tech in m.tech_stack:
                if tech not in success_by_tech:
                    success_by_tech[tech] = []
                success_by_tech[tech].append(m.success_score)

        high_success_tech = [
            tech
            for tech, scores in success_by_tech.items()
            if len(scores) >= 2 and sum(scores) / len(scores) > 0.8
        ]
        if high_success_tech:
            opportunities.append(
                f"Leverage high-success tech stack: {', '.join(high_success_tech)}"
            )

        # Check for test coverage impact
        tested_builds = [m for m in metrics if m.test_count > 0]
        if tested_builds:
            avg_success_tested = sum(m.success_score for m in tested_builds) / len(tested_builds)
            untested = [m for m in metrics if m.test_count == 0]
            if untested:
                avg_success_untested = sum(m.success_score for m in untested) / len(untested)
                if avg_success_tested > avg_success_untested + 0.1:
                    opportunities.append(
                        "Testing correlates with higher success rates - prioritize test coverage"
                    )

        return opportunities

    def _calculate_confidence(self, sample_size: int) -> float:
        """Calculate confidence based on sample size."""
        if sample_size >= 20:
            return 0.9
        elif sample_size >= 10:
            return 0.7
        elif sample_size >= 5:
            return 0.5
        elif sample_size >= 2:
            return 0.3
        else:
            return 0.1

    def _calculate_trend(self, values: List[float], inverse: bool = False) -> MetricTrend:
        """Calculate trend direction for a series of values."""
        if len(values) < 3:
            return MetricTrend.INSUFFICIENT_DATA

        # Compare first half to second half
        mid = len(values) // 2
        first_half_avg = sum(values[:mid]) / mid if mid > 0 else 0
        second_half_avg = sum(values[mid:]) / (len(values) - mid)

        diff = second_half_avg - first_half_avg
        threshold = 0.1 * first_half_avg if first_half_avg > 0 else 0.1

        if inverse:
            diff = -diff

        if diff > threshold:
            return MetricTrend.IMPROVING
        elif diff < -threshold:
            return MetricTrend.DECLINING
        else:
            return MetricTrend.STABLE

    def analyze(
        self,
        project_type: Optional[str] = None,
        tech_stack: Optional[List[str]] = None,
    ) -> BuildHistoryAnalysisResult:
        """Perform complete build history analysis.

        Args:
            project_type: Filter by project type
            tech_stack: Filter by tech stack components

        Returns:
            Complete analysis result
        """
        metrics = self.collect_build_metrics()
        original_count = len(metrics)

        # Filter by project type
        if project_type:
            metrics = [m for m in metrics if m.project_type == project_type]

        # Filter by tech stack
        if tech_stack:
            metrics = [m for m in metrics if any(t in m.tech_stack for t in tech_stack)]

        if not metrics:
            logger.warning(
                f"No build metrics found for project_type={project_type}, tech_stack={tech_stack}"
            )
            return BuildHistoryAnalysisResult(
                project_type=project_type,
                analysis_timestamp=datetime.now(),
                total_builds_analyzed=0,
                date_range_days=0,
                overall_success_rate=0.0,
                avg_time_estimate_accuracy=0.0,
                avg_cost_estimate_accuracy=0.0,
                feasibility_signals=[],
                cost_effectiveness=CostEffectivenessFeedback(
                    estimation_accuracy=0.0,
                    cost_overrun_rate=0.0,
                    avg_cost_deviation=0.0,
                    high_cost_factors=[],
                    cost_optimization_opportunities=[],
                    sample_size=0,
                ),
                recommendations=["No historical data available for analysis"],
                warnings=[],
            )

        # Calculate date range
        timestamps = [m.timestamp for m in metrics]
        date_range = (max(timestamps) - min(timestamps)).days if timestamps else 0

        # Calculate aggregate metrics
        success_scores = [m.success_score for m in metrics]
        overall_success_rate = sum(success_scores) / len(success_scores)

        time_accuracies = [
            m.time_estimate_accuracy for m in metrics if m.estimated_duration_hours > 0
        ]
        avg_time_accuracy = sum(time_accuracies) / len(time_accuracies) if time_accuracies else 0.0

        cost_accuracies = [m.cost_estimate_accuracy for m in metrics if m.estimated_cost > 0]
        avg_cost_accuracy = sum(cost_accuracies) / len(cost_accuracies) if cost_accuracies else 0.0

        # Extract signals
        feasibility_signals = self.extract_feasibility_signals(project_type, tech_stack)

        # Analyze cost-effectiveness
        cost_effectiveness = self.analyze_cost_effectiveness(project_type)

        # Group metrics by category
        metrics_by_category: Dict[str, Dict[str, Any]] = {}
        for m in metrics:
            if m.category not in metrics_by_category:
                metrics_by_category[m.category] = {
                    "count": 0,
                    "success_rate": 0.0,
                    "avg_duration": 0.0,
                }
            cat_data = metrics_by_category[m.category]
            cat_data["count"] += 1
            cat_data["success_rate"] = (
                cat_data["success_rate"] * (cat_data["count"] - 1) + m.success_score
            ) / cat_data["count"]
            cat_data["avg_duration"] = (
                cat_data["avg_duration"] * (cat_data["count"] - 1) + m.actual_duration_hours
            ) / cat_data["count"]

        # Group by tech stack
        metrics_by_tech: Dict[str, Dict[str, Any]] = {}
        for m in metrics:
            for tech in m.tech_stack:
                if tech not in metrics_by_tech:
                    metrics_by_tech[tech] = {
                        "count": 0,
                        "success_rate": 0.0,
                    }
                tech_data = metrics_by_tech[tech]
                tech_data["count"] += 1
                tech_data["success_rate"] = (
                    tech_data["success_rate"] * (tech_data["count"] - 1) + m.success_score
                ) / tech_data["count"]

        # Generate recommendations
        recommendations = self._generate_recommendations(
            metrics, feasibility_signals, cost_effectiveness
        )

        # Generate warnings
        warnings = self._generate_warnings(metrics, cost_effectiveness)

        return BuildHistoryAnalysisResult(
            project_type=project_type,
            analysis_timestamp=datetime.now(),
            total_builds_analyzed=len(metrics),
            date_range_days=date_range,
            overall_success_rate=overall_success_rate,
            avg_time_estimate_accuracy=avg_time_accuracy,
            avg_cost_estimate_accuracy=avg_cost_accuracy,
            feasibility_signals=feasibility_signals,
            cost_effectiveness=cost_effectiveness,
            recommendations=recommendations,
            warnings=warnings,
            metrics_by_category=metrics_by_category,
            metrics_by_tech_stack=metrics_by_tech,
        )

    def _generate_recommendations(
        self,
        metrics: List[BuildMetrics],
        signals: List[FeasibilityFeedback],
        cost_feedback: CostEffectivenessFeedback,
    ) -> List[str]:
        """Generate recommendations based on analysis."""
        recommendations = []

        # Base recommendations on success rate
        success_rate = sum(m.success_score for m in metrics) / len(metrics)
        if success_rate < 0.5:
            recommendations.append(
                "Consider more thorough planning - historical success rate is below 50%"
            )

        # Add cost optimization opportunities
        recommendations.extend(cost_feedback.cost_optimization_opportunities[:3])

        # Add signal-based recommendations
        for signal in signals:
            if signal.signal_type == FeasibilitySignal.TIME_ESTIMATE_ACCURACY:
                if signal.signal_value < 0.5:
                    recommendations.append(
                        "Add buffer to time estimates - historical accuracy is low"
                    )
            elif signal.signal_type == FeasibilitySignal.DEPENDENCY_RISK:
                if signal.signal_value < 0.7:
                    recommendations.append(
                        "Review dependencies carefully - historical issues detected"
                    )

        return recommendations[:5]

    def _generate_warnings(
        self,
        metrics: List[BuildMetrics],
        cost_feedback: CostEffectivenessFeedback,
    ) -> List[str]:
        """Generate warnings based on analysis."""
        warnings = []

        # Warn about high failure rate
        failed = [m for m in metrics if m.outcome == BuildOutcome.FAILED]
        if len(failed) / len(metrics) > 0.3:
            warnings.append(f"High failure rate: {len(failed)}/{len(metrics)} builds failed")

        # Warn about cost overruns
        if cost_feedback.cost_overrun_rate > 0.5:
            warnings.append(
                f"Cost overruns common: {cost_feedback.cost_overrun_rate:.0%} of builds exceeded estimates"
            )

        # Warn about high cost factors
        warnings.extend(cost_feedback.high_cost_factors[:2])

        return warnings

    def get_feasibility_adjustment(
        self,
        base_feasibility_score: float,
        project_type: Optional[str] = None,
        tech_stack: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Get feasibility score adjustment based on build history.

        Args:
            base_feasibility_score: Initial feasibility score (0-1)
            project_type: Project type for filtering
            tech_stack: Tech stack for filtering

        Returns:
            Adjusted feasibility with explanation
        """
        signals = self.extract_feasibility_signals(project_type, tech_stack)

        if not signals:
            return {
                "original_score": base_feasibility_score,
                "adjusted_score": base_feasibility_score,
                "adjustment": 0.0,
                "confidence": 0.0,
                "explanation": "No historical data available for adjustment",
            }

        # Calculate weighted adjustment
        total_weight = 0.0
        weighted_sum = 0.0

        for signal in signals:
            weight = signal.confidence
            # Deviation from neutral (0.5)
            deviation = signal.signal_value - 0.5
            weighted_sum += deviation * weight
            total_weight += weight

        if total_weight > 0:
            adjustment = (weighted_sum / total_weight) * 0.3  # Max 30% adjustment
        else:
            adjustment = 0.0

        adjusted_score = max(0.0, min(1.0, base_feasibility_score + adjustment))

        return {
            "original_score": base_feasibility_score,
            "adjusted_score": adjusted_score,
            "adjustment": adjustment,
            "confidence": min(total_weight / len(signals), 1.0),
            "explanation": self._explain_adjustment(signals, adjustment),
            "signals": [s.to_dict() for s in signals],
        }

    def _explain_adjustment(self, signals: List[FeasibilityFeedback], adjustment: float) -> str:
        """Generate explanation for feasibility adjustment."""
        if abs(adjustment) < 0.05:
            return "Historical data suggests neutral feasibility outlook"

        direction = "positive" if adjustment > 0 else "negative"
        factors = []

        for signal in signals:
            if signal.signal_type == FeasibilitySignal.TIME_ESTIMATE_ACCURACY:
                if signal.signal_value > 0.7:
                    factors.append("good time estimation accuracy")
                elif signal.signal_value < 0.4:
                    factors.append("poor time estimation accuracy")

            elif signal.signal_type == FeasibilitySignal.ERROR_FREQUENCY:
                if signal.signal_value > 0.7:
                    factors.append("low error frequency")
                elif signal.signal_value < 0.4:
                    factors.append("high error frequency")

            elif signal.signal_type == FeasibilitySignal.TECH_STACK_MATURITY:
                if signal.signal_value > 0.7:
                    factors.append("mature tech stack")
                elif signal.signal_value < 0.4:
                    factors.append("less mature tech stack")

        if factors:
            return f"Historical data suggests {direction} adjustment based on: {', '.join(factors)}"
        else:
            return f"Historical data suggests {direction} feasibility adjustment"


def get_build_history_feedback(
    build_history_path: Optional[Path] = None,
    project_type: Optional[str] = None,
    tech_stack: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Convenience function to get build history feedback for research pipeline.

    Args:
        build_history_path: Path to BUILD_HISTORY.md
        project_type: Filter by project type
        tech_stack: Filter by tech stack components

    Returns:
        Dictionary with feasibility signals and cost-effectiveness feedback
    """
    analyzer = BuildHistoryAnalyzer(build_history_path=build_history_path)
    result = analyzer.analyze(project_type=project_type, tech_stack=tech_stack)
    return result.to_dict()
