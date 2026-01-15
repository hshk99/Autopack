"""ROAD-I: Regression Protection - Prevent already-fixed issues from reoccurring.

Tracks:
- Issue fix history (what was fixed, when, how)
- Issue recurrence detection
- Regression alerts with root cause analysis
- Fix stability metrics

Key capabilities:
- Record fixes with context (commit SHA, fix description, affected phases)
- Detect when previously-fixed issues reoccur
- Alert on regressions with actionable recommendations
- Track fix stability over time (how often fixes hold)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class IssueType(Enum):
    """Type of issue that was fixed."""

    COST_SINK = "cost_sink"  # High token usage
    FAILURE_MODE = "failure_mode"  # Recurring failures
    RETRY_CAUSE = "retry_cause"  # Excessive retries
    PERFORMANCE = "performance"  # Slow execution
    QUALITY = "quality"  # Low quality outputs


class RegressionSeverity(Enum):
    """Severity of regression detection."""

    CRITICAL = "critical"  # Exact same issue recurred
    HIGH = "high"  # Similar issue with high confidence
    MEDIUM = "medium"  # Potential regression, needs investigation
    LOW = "low"  # Minor deviation, may not be regression


@dataclass
class IssueFix:
    """Record of an issue that was fixed."""

    issue_id: str  # Unique identifier for the issue
    issue_type: IssueType
    phase_id: str  # Which phase had the issue
    description: str  # Human-readable description
    fix_timestamp: datetime
    commit_sha: Optional[str] = None  # Git commit that fixed it
    fix_pr_number: Optional[int] = None  # PR number if applicable
    baseline_metric_value: float = 0.0  # Metric value before fix
    improved_metric_value: float = 0.0  # Metric value after fix
    fix_context: Dict[str, Any] = field(default_factory=dict)  # Additional context


@dataclass
class RegressionDetection:
    """Detection of a regression (issue recurring)."""

    regression_id: str
    original_fix: IssueFix
    detection_timestamp: datetime
    current_metric_value: float
    severity: RegressionSeverity
    confidence: float  # 0.0-1.0
    evidence: List[str]  # Evidence supporting regression claim
    recommendations: List[str]  # What to do about it
    affected_runs: List[str] = field(default_factory=list)  # Run IDs showing regression


@dataclass
class FixStabilityReport:
    """Report on how stable fixes are over time."""

    total_fixes: int
    stable_fixes: int  # Fixes that haven't regressed
    regressed_fixes: int  # Fixes that have regressed
    average_fix_duration: timedelta  # How long fixes typically hold
    stability_rate: float  # Percentage of fixes that remain stable
    most_unstable_phases: List[str]  # Phases with most regressions
    recommendations: List[str]


class RegressionProtector:
    """Tracks fixed issues and detects regressions.

    Usage:
        protector = RegressionProtector(storage_path="telemetry/fixes.json")

        # Record a fix
        fix = IssueFix(
            issue_id="COST_phase_build_1",
            issue_type=IssueType.COST_SINK,
            phase_id="phase_build",
            description="Reduced token usage by optimizing prompts",
            fix_timestamp=datetime.now(),
            commit_sha="abc123",
            baseline_metric_value=5000,
            improved_metric_value=3000,
        )
        protector.record_fix(fix)

        # Check for regressions
        current_metrics = {"phase_build": {"token_usage": 4800}}
        regressions = protector.check_for_regressions(current_metrics)
        for regression in regressions:
            logger.warning(f"Regression detected: {regression.original_fix.description}")
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        regression_threshold: float = 0.15,  # 15% degradation triggers alert
        lookback_window_days: int = 90,  # Consider fixes from last 90 days
        min_samples_for_detection: int = 3,  # Need 3+ samples to confirm regression
    ):
        """Initialize regression protector.

        Args:
            storage_path: Path to JSON file for persisting fix history
            regression_threshold: Percentage degradation that triggers regression alert
            lookback_window_days: How many days back to track fixes
            min_samples_for_detection: Minimum samples needed to confirm regression
        """
        self.storage_path = Path(storage_path) if storage_path else None
        self.regression_threshold = regression_threshold
        self.lookback_window_days = lookback_window_days
        self.min_samples_for_detection = min_samples_for_detection

        # In-memory storage
        self.fixes: Dict[str, IssueFix] = {}  # issue_id -> IssueFix
        self.regressions: Dict[str, RegressionDetection] = (
            {}
        )  # regression_id -> RegressionDetection

        # Load from storage if available
        if self.storage_path and self.storage_path.exists():
            self._load_from_storage()

    def record_fix(self, fix: IssueFix) -> None:
        """Record that an issue has been fixed.

        Args:
            fix: IssueFix record with fix details
        """
        self.fixes[fix.issue_id] = fix
        logger.info(
            f"[ROAD-I] Recorded fix for {fix.issue_id}: {fix.description} "
            f"({fix.baseline_metric_value:.0f} -> {fix.improved_metric_value:.0f})"
        )

        # Persist to storage
        if self.storage_path:
            self._save_to_storage()

    def check_for_regressions(
        self, current_metrics: Dict[str, Dict[str, float]]
    ) -> List[RegressionDetection]:
        """Check if any previously-fixed issues have regressed.

        Args:
            current_metrics: Dict of {phase_id: {metric_name: value}}

        Returns:
            List of detected regressions
        """
        regressions = []
        now = datetime.now()
        cutoff_date = now - timedelta(days=self.lookback_window_days)

        for fix in self.fixes.values():
            # Only check recent fixes (within lookback window)
            if fix.fix_timestamp < cutoff_date:
                continue

            # Get current metric for this phase
            phase_metrics = current_metrics.get(fix.phase_id, {})
            if not phase_metrics:
                continue

            # Map issue type to metric name
            metric_name = self._get_metric_name_for_issue_type(fix.issue_type)
            current_value = phase_metrics.get(metric_name)

            if current_value is None:
                continue

            # Check if regression occurred
            regression = self._detect_regression(fix, current_value, now)
            if regression:
                regressions.append(regression)
                self.regressions[regression.regression_id] = regression
                logger.warning(
                    f"[ROAD-I] Regression detected: {regression.original_fix.description} "
                    f"(severity: {regression.severity.value})"
                )

        # Persist regressions
        if self.storage_path and regressions:
            self._save_to_storage()

        return regressions

    def _detect_regression(
        self, fix: IssueFix, current_value: float, timestamp: datetime
    ) -> Optional[RegressionDetection]:
        """Detect if a fix has regressed based on current metric value.

        Args:
            fix: The original fix record
            current_value: Current metric value
            timestamp: Timestamp of measurement

        Returns:
            RegressionDetection if regression detected, None otherwise
        """
        # Calculate degradation from improved value
        if fix.improved_metric_value == 0:
            return None

        # For metrics where lower is better (tokens, cost, failures, retries)
        is_lower_better = fix.issue_type in [
            IssueType.COST_SINK,
            IssueType.FAILURE_MODE,
            IssueType.RETRY_CAUSE,
        ]

        if is_lower_better:
            # Check if current value increased significantly from improved value
            degradation = (current_value - fix.improved_metric_value) / abs(
                fix.improved_metric_value
            )
        else:
            # For metrics where higher is better (performance, quality)
            degradation = (fix.improved_metric_value - current_value) / abs(
                fix.improved_metric_value
            )

        # Determine if this is a regression
        if degradation < self.regression_threshold:
            return None  # No significant degradation

        # Classify severity
        severity = self._classify_regression_severity(degradation, fix, current_value)
        confidence = min(degradation / self.regression_threshold, 1.0)

        # Build evidence
        evidence = [
            f"Metric value degraded by {degradation:.1%}",
            f"Original fix reduced metric from {fix.baseline_metric_value:.0f} to {fix.improved_metric_value:.0f}",
            f"Current value is {current_value:.0f}",
        ]

        if fix.commit_sha:
            evidence.append(f"Original fix was in commit {fix.commit_sha}")

        # Generate recommendations
        recommendations = self._generate_regression_recommendations(fix, degradation)

        regression_id = f"REG_{fix.issue_id}_{timestamp.strftime('%Y%m%d_%H%M%S')}"

        return RegressionDetection(
            regression_id=regression_id,
            original_fix=fix,
            detection_timestamp=timestamp,
            current_metric_value=current_value,
            severity=severity,
            confidence=confidence,
            evidence=evidence,
            recommendations=recommendations,
        )

    def _classify_regression_severity(
        self, degradation: float, fix: IssueFix, current_value: float
    ) -> RegressionSeverity:
        """Classify the severity of a regression.

        Args:
            degradation: Percentage degradation from improved value
            fix: Original fix record
            current_value: Current metric value

        Returns:
            RegressionSeverity classification
        """
        # Critical: Very close to baseline or worse
        if current_value >= fix.baseline_metric_value * 0.95:
            return RegressionSeverity.CRITICAL

        # High: >=50% degradation from improved value
        if degradation >= 0.5:
            return RegressionSeverity.HIGH

        # Medium: 25-50% degradation
        if degradation >= 0.25:
            return RegressionSeverity.MEDIUM

        # Low: 15-25% degradation
        return RegressionSeverity.LOW

    def _generate_regression_recommendations(self, fix: IssueFix, degradation: float) -> List[str]:
        """Generate actionable recommendations for a regression.

        Args:
            fix: Original fix record
            degradation: Percentage degradation

        Returns:
            List of recommendations
        """
        recommendations = []

        if degradation > 0.5:
            recommendations.append(
                f"High-severity regression detected - consider reverting recent changes to {fix.phase_id}"
            )
        else:
            recommendations.append(
                f"Investigate recent changes to {fix.phase_id} that may have reintroduced the issue"
            )

        if fix.commit_sha:
            recommendations.append(
                f"Review the original fix in commit {fix.commit_sha} to understand what regressed"
            )

        if fix.fix_pr_number:
            recommendations.append(f"Reference original fix PR #{fix.fix_pr_number} for context")

        recommendations.append("Run A-B validation to confirm regression and quantify impact")

        return recommendations

    def _get_metric_name_for_issue_type(self, issue_type: IssueType) -> str:
        """Map issue type to metric name.

        Args:
            issue_type: Type of issue

        Returns:
            Metric name string
        """
        mapping = {
            IssueType.COST_SINK: "token_usage",
            IssueType.FAILURE_MODE: "failure_count",
            IssueType.RETRY_CAUSE: "retry_count",
            IssueType.PERFORMANCE: "duration_ms",
            IssueType.QUALITY: "quality_score",
        }
        return mapping.get(issue_type, "unknown")

    def get_fix_stability_report(self) -> FixStabilityReport:
        """Generate report on fix stability over time.

        Returns:
            FixStabilityReport with stability metrics
        """
        total_fixes = len(self.fixes)
        regressed_fix_ids = {r.original_fix.issue_id for r in self.regressions.values()}
        regressed_fixes = len(regressed_fix_ids)
        stable_fixes = total_fixes - regressed_fixes

        # Calculate average fix duration (time until regression or now)
        now = datetime.now()
        fix_durations = []
        for fix in self.fixes.values():
            if fix.issue_id in regressed_fix_ids:
                # Find first regression for this fix
                regression = next(
                    r for r in self.regressions.values() if r.original_fix.issue_id == fix.issue_id
                )
                duration = regression.detection_timestamp - fix.fix_timestamp
            else:
                # Still stable, use current time
                duration = now - fix.fix_timestamp

            fix_durations.append(duration)

        avg_duration = (
            sum(fix_durations, timedelta()) / len(fix_durations) if fix_durations else timedelta()
        )

        # Calculate stability rate
        stability_rate = stable_fixes / total_fixes if total_fixes > 0 else 1.0

        # Find most unstable phases
        phase_regression_counts: Dict[str, int] = {}
        for regression in self.regressions.values():
            phase_id = regression.original_fix.phase_id
            phase_regression_counts[phase_id] = phase_regression_counts.get(phase_id, 0) + 1

        most_unstable_phases = sorted(
            phase_regression_counts.keys(), key=lambda p: phase_regression_counts[p], reverse=True
        )[:5]

        # Generate recommendations
        recommendations = []
        if stability_rate < 0.7:
            recommendations.append(
                f"Low fix stability ({stability_rate:.1%}) - review fix quality and test coverage"
            )
        if most_unstable_phases:
            recommendations.append(
                f"Focus on stabilizing {', '.join(most_unstable_phases[:3])} - these have the most regressions"
            )
        if avg_duration < timedelta(days=7):
            recommendations.append(
                "Fixes are regressing quickly - consider more thorough testing before merging"
            )

        return FixStabilityReport(
            total_fixes=total_fixes,
            stable_fixes=stable_fixes,
            regressed_fixes=regressed_fixes,
            average_fix_duration=avg_duration,
            stability_rate=stability_rate,
            most_unstable_phases=most_unstable_phases,
            recommendations=recommendations,
        )

    def clear_old_fixes(self, days: int = 180) -> int:
        """Clear fix records older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of fixes cleared
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        old_fixes = [fid for fid, fix in self.fixes.items() if fix.fix_timestamp < cutoff_date]

        for fid in old_fixes:
            del self.fixes[fid]

        logger.info(f"[ROAD-I] Cleared {len(old_fixes)} old fix records (older than {days} days)")

        if self.storage_path:
            self._save_to_storage()

        return len(old_fixes)

    def _save_to_storage(self) -> None:
        """Save fix history to persistent storage."""
        if not self.storage_path:
            return

        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "fixes": {
                fid: {
                    "issue_id": fix.issue_id,
                    "issue_type": fix.issue_type.value,
                    "phase_id": fix.phase_id,
                    "description": fix.description,
                    "fix_timestamp": fix.fix_timestamp.isoformat(),
                    "commit_sha": fix.commit_sha,
                    "fix_pr_number": fix.fix_pr_number,
                    "baseline_metric_value": fix.baseline_metric_value,
                    "improved_metric_value": fix.improved_metric_value,
                    "fix_context": fix.fix_context,
                }
                for fid, fix in self.fixes.items()
            },
            "regressions": {
                rid: {
                    "regression_id": reg.regression_id,
                    "original_fix_id": reg.original_fix.issue_id,
                    "detection_timestamp": reg.detection_timestamp.isoformat(),
                    "current_metric_value": reg.current_metric_value,
                    "severity": reg.severity.value,
                    "confidence": reg.confidence,
                    "evidence": reg.evidence,
                    "recommendations": reg.recommendations,
                    "affected_runs": reg.affected_runs,
                }
                for rid, reg in self.regressions.items()
            },
        }

        with open(self.storage_path, "w") as f:
            json.dump(data, f, indent=2)

    def _load_from_storage(self) -> None:
        """Load fix history from persistent storage."""
        if not self.storage_path or not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, "r") as f:
                data = json.load(f)

            # Load fixes
            for fid, fix_data in data.get("fixes", {}).items():
                self.fixes[fid] = IssueFix(
                    issue_id=fix_data["issue_id"],
                    issue_type=IssueType(fix_data["issue_type"]),
                    phase_id=fix_data["phase_id"],
                    description=fix_data["description"],
                    fix_timestamp=datetime.fromisoformat(fix_data["fix_timestamp"]),
                    commit_sha=fix_data.get("commit_sha"),
                    fix_pr_number=fix_data.get("fix_pr_number"),
                    baseline_metric_value=fix_data.get("baseline_metric_value", 0.0),
                    improved_metric_value=fix_data.get("improved_metric_value", 0.0),
                    fix_context=fix_data.get("fix_context", {}),
                )

            # Load regressions (need to link back to fixes)
            for rid, reg_data in data.get("regressions", {}).items():
                original_fix_id = reg_data["original_fix_id"]
                if original_fix_id in self.fixes:
                    self.regressions[rid] = RegressionDetection(
                        regression_id=reg_data["regression_id"],
                        original_fix=self.fixes[original_fix_id],
                        detection_timestamp=datetime.fromisoformat(reg_data["detection_timestamp"]),
                        current_metric_value=reg_data["current_metric_value"],
                        severity=RegressionSeverity(reg_data["severity"]),
                        confidence=reg_data["confidence"],
                        evidence=reg_data["evidence"],
                        recommendations=reg_data["recommendations"],
                        affected_runs=reg_data.get("affected_runs", []),
                    )

            logger.info(
                f"[ROAD-I] Loaded {len(self.fixes)} fixes and {len(self.regressions)} regressions from storage"
            )

        except Exception as e:
            logger.error(f"[ROAD-I] Failed to load from storage: {e}")
