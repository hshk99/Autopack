"""Automated telemetry analysis for issue prioritization."""

import os
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class RankedIssue:
    """A ranked issue from telemetry analysis."""

    rank: int
    issue_type: str  # cost_sink, failure_mode, retry_cause, flaky_test
    phase_id: str
    phase_type: Optional[str]
    metric_value: float  # tokens, count, rate depending on type
    details: Dict[str, Any]


@dataclass
class CostRecommendation:
    """Cost recommendation from telemetry analysis (IMP-COST-005)."""

    should_pause: bool
    reason: str
    current_spend: float  # Total tokens used (expressed as cost proxy)
    budget_remaining_pct: float  # Percentage of budget remaining
    severity: str  # "warning", "critical"


class TelemetryAnalyzer:
    """Analyze telemetry data and generate ranked issues."""

    def __init__(self, db_session: Session, memory_service=None):
        self.db = db_session
        self.memory_service = memory_service
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        # IMP-ARCH-018: Changed default to "true" to enable self-improvement loop
        self._telemetry_to_memory_enabled = (
            os.getenv("AUTOPACK_TELEMETRY_TO_MEMORY_ENABLED", "true").lower() == "true"
        )

    def aggregate_telemetry(self, window_days: int = 7) -> Dict[str, List[RankedIssue]]:
        """Analyze recent runs and generate ranked issue list.

        Args:
            window_days: Number of days to look back (default: 7)

        Returns:
            Dictionary containing ranked issue lists:
            - top_cost_sinks: Phases consuming the most tokens
            - top_failure_modes: Most common failure patterns
            - top_retry_causes: Phases that retry most frequently
            - phase_type_stats: Per-phase-type statistics for ROAD-L
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

        # Find ranked issues
        cost_sinks = self._find_cost_sinks(cutoff)
        failure_modes = self._find_failure_modes(cutoff)
        retry_causes = self._find_retry_causes(cutoff)
        phase_type_stats = self._compute_phase_type_stats(cutoff)

        # NEW: Persist to memory for future retrieval
        if self.memory_service and self.memory_service.enabled:
            from autopack.telemetry.telemetry_to_memory_bridge import TelemetryToMemoryBridge

            bridge = TelemetryToMemoryBridge(
                self.memory_service, enabled=self._telemetry_to_memory_enabled
            )
            # Convert RankedIssue objects to dicts for bridge
            flat_issues = []
            for issue in cost_sinks:
                flat_issues.append(
                    {
                        "issue_type": "cost_sink",
                        "insight_id": f"{issue.rank}",
                        "rank": issue.rank,
                        "phase_id": issue.phase_id,
                        "phase_type": issue.phase_type,
                        "severity": "high",
                        "description": f"Phase {issue.phase_id} consuming {issue.metric_value:,.0f} tokens",
                        "metric_value": issue.metric_value,
                        "occurrences": issue.details.get("count", 1),
                        "details": issue.details,
                        "suggested_action": f"Optimize token usage for {issue.phase_type}",
                    }
                )
            for issue in failure_modes:
                flat_issues.append(
                    {
                        "issue_type": "failure_mode",
                        "insight_id": f"{issue.rank}",
                        "rank": issue.rank,
                        "phase_id": issue.phase_id,
                        "phase_type": issue.phase_type,
                        "severity": "high",
                        "description": f"Failure: {issue.details.get('outcome', '')} - {issue.details.get('stop_reason', '')}",
                        "metric_value": issue.metric_value,
                        "occurrences": issue.details.get("count", 1),
                        "details": issue.details,
                        "suggested_action": f"Fix {issue.phase_type} failure pattern",
                    }
                )
            for issue in retry_causes:
                flat_issues.append(
                    {
                        "issue_type": "retry_cause",
                        "insight_id": f"{issue.rank}",
                        "rank": issue.rank,
                        "phase_id": issue.phase_id,
                        "phase_type": issue.phase_type,
                        "severity": "medium",
                        "description": f"Retry cause: {issue.details.get('stop_reason', '')}",
                        "metric_value": issue.metric_value,
                        "occurrences": issue.details.get("count", 1),
                        "details": issue.details,
                        "suggested_action": f"Increase timeout or optimize {issue.phase_type}",
                    }
                )
            bridge.persist_insights(
                flat_issues,
                run_id=self.run_id,
                project_id=None,
            )

        return {
            "top_cost_sinks": cost_sinks,
            "top_failure_modes": failure_modes,
            "top_retry_causes": retry_causes,
            "phase_type_stats": phase_type_stats,  # For ROAD-L
        }

    def _find_cost_sinks(self, cutoff: datetime) -> List[RankedIssue]:
        """Find phases consuming the most tokens.

        Args:
            cutoff: Only analyze events after this timestamp

        Returns:
            List of RankedIssue objects for top 10 cost sinks
        """
        result = self.db.execute(
            text("""
            SELECT phase_id, phase_type, SUM(tokens_used) as total_tokens,
                   AVG(tokens_used) as avg_tokens, COUNT(*) as count
            FROM phase_outcome_events
            WHERE timestamp >= :cutoff AND tokens_used IS NOT NULL
            GROUP BY phase_id, phase_type
            ORDER BY total_tokens DESC
            LIMIT 10
        """),
            {"cutoff": cutoff},
        )

        return [
            RankedIssue(
                rank=i + 1,
                issue_type="cost_sink",
                phase_id=row.phase_id,
                phase_type=row.phase_type,
                metric_value=row.total_tokens,
                details={"avg_tokens": row.avg_tokens, "count": row.count},
            )
            for i, row in enumerate(result)
        ]

    def _find_failure_modes(self, cutoff: datetime) -> List[RankedIssue]:
        """Find most common failure patterns.

        Args:
            cutoff: Only analyze events after this timestamp

        Returns:
            List of RankedIssue objects for top 10 failure modes
        """
        result = self.db.execute(
            text("""
            SELECT phase_id, phase_type, phase_outcome, stop_reason,
                   COUNT(*) as count
            FROM phase_outcome_events
            WHERE timestamp >= :cutoff AND phase_outcome != 'SUCCESS'
            GROUP BY phase_id, phase_type, phase_outcome, stop_reason
            ORDER BY count DESC
            LIMIT 10
        """),
            {"cutoff": cutoff},
        )

        return [
            RankedIssue(
                rank=i + 1,
                issue_type="failure_mode",
                phase_id=row.phase_id,
                phase_type=row.phase_type,
                metric_value=row.count,
                details={"outcome": row.phase_outcome, "stop_reason": row.stop_reason},
            )
            for i, row in enumerate(result)
        ]

    def _find_retry_causes(self, cutoff: datetime) -> List[RankedIssue]:
        """Find phases that retry most frequently.

        Args:
            cutoff: Only analyze events after this timestamp

        Returns:
            List of RankedIssue objects for top 10 retry causes
        """
        # Find phases with multiple attempts (retries)
        result = self.db.execute(
            text("""
            SELECT phase_id, phase_type, stop_reason,
                   COUNT(*) as retry_count,
                   SUM(CASE WHEN phase_outcome = 'SUCCESS' THEN 1 ELSE 0 END) as success_count
            FROM phase_outcome_events
            WHERE timestamp >= :cutoff
            GROUP BY phase_id, phase_type, stop_reason
            HAVING COUNT(*) > 1
            ORDER BY retry_count DESC
            LIMIT 10
        """),
            {"cutoff": cutoff},
        )

        return [
            RankedIssue(
                rank=i + 1,
                issue_type="retry_cause",
                phase_id=row.phase_id,
                phase_type=row.phase_type,
                metric_value=row.retry_count,
                details={
                    "stop_reason": row.stop_reason,
                    "success_count": row.success_count,
                    "retry_count": row.retry_count,
                },
            )
            for i, row in enumerate(result)
        ]

    def _compute_phase_type_stats(self, cutoff: datetime) -> Dict[str, Dict]:
        """Compute per-phase-type success rates and costs for ROAD-L.

        Args:
            cutoff: Only analyze events after this timestamp

        Returns:
            Dictionary mapping "phase_type:model_used" to statistics:
            - success_rate: Fraction of successful outcomes
            - avg_tokens: Average tokens used
            - sample_count: Number of samples
        """
        result = self.db.execute(
            text("""
            SELECT phase_type, model_used,
                   COUNT(*) as total,
                   SUM(CASE WHEN phase_outcome = 'SUCCESS' THEN 1 ELSE 0 END) as successes,
                   AVG(tokens_used) as avg_tokens
            FROM phase_outcome_events
            WHERE timestamp >= :cutoff AND phase_type IS NOT NULL
            GROUP BY phase_type, model_used
        """),
            {"cutoff": cutoff},
        )

        stats = {}
        for row in result:
            key = f"{row.phase_type}:{row.model_used}"
            stats[key] = {
                "success_rate": row.successes / row.total if row.total > 0 else 0,
                "avg_tokens": row.avg_tokens if row.avg_tokens else 0,
                "sample_count": row.total,
            }
        return stats

    def write_ranked_issues(self, issues: Dict, output_path: Path) -> None:
        """Write ranked issues to artifact file.

        Args:
            issues: Dictionary from aggregate_telemetry()
            output_path: Path to write markdown report
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            f.write("# Telemetry Analysis - Ranked Issues\n\n")
            f.write(f"**Generated**: {datetime.now(timezone.utc).isoformat()}\n\n")

            # Top Cost Sinks
            f.write("## Top Cost Sinks\n\n")
            if issues["top_cost_sinks"]:
                for issue in issues["top_cost_sinks"]:
                    f.write(
                        f"- [{issue.rank}] Phase: {issue.phase_id}, "
                        f"Tokens: {issue.metric_value:,.0f}, "
                        f"Avg: {issue.details['avg_tokens']:,.0f}, "
                        f"Count: {issue.details['count']}\n"
                    )
            else:
                f.write("*No cost sinks found in analysis window*\n")

            # Top Failure Modes
            f.write("\n## Top Failure Modes\n\n")
            if issues["top_failure_modes"]:
                for issue in issues["top_failure_modes"]:
                    f.write(
                        f"- [{issue.rank}] Phase: {issue.phase_id}, "
                        f"Count: {issue.metric_value:.0f}, "
                        f"Outcome: {issue.details['outcome']}, "
                        f"Reason: {issue.details['stop_reason']}\n"
                    )
            else:
                f.write("*No failure modes found in analysis window*\n")

            # Top Retry Causes
            f.write("\n## Top Retry Causes\n\n")
            if issues["top_retry_causes"]:
                for issue in issues["top_retry_causes"]:
                    f.write(
                        f"- [{issue.rank}] Phase: {issue.phase_id}, "
                        f"Retry Count: {issue.metric_value:.0f}, "
                        f"Success Count: {issue.details['success_count']}, "
                        f"Reason: {issue.details['stop_reason']}\n"
                    )
            else:
                f.write("*No retry patterns found in analysis window*\n")

            # Phase Type Stats (for ROAD-L)
            f.write("\n## Phase Type Statistics (for ROAD-L)\n\n")
            if issues["phase_type_stats"]:
                f.write("| Phase:Model | Success Rate | Avg Tokens | Samples |\n")
                f.write("|-------------|--------------|------------|----------|\n")
                for key, stats in sorted(
                    issues["phase_type_stats"].items(),
                    key=lambda x: x[1]["sample_count"],
                    reverse=True,
                ):
                    f.write(
                        f"| {key} | {stats['success_rate']:.1%} | "
                        f"{stats['avg_tokens']:,.0f} | {stats['sample_count']} |\n"
                    )
            else:
                f.write("*No phase type statistics available*\n")

        logger.info(f"[ROAD-B] Wrote ranked issues to: {output_path}")

    def get_recommendations_for_phase(
        self, phase_type: str, lookback_hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get actionable recommendations for a phase type based on recent telemetry.

        Queries recent analysis results for the given phase type and returns
        recommendations for mitigating detected issues.

        Args:
            phase_type: The type of phase to get recommendations for
            lookback_hours: Number of hours to look back for analysis (default: 24)

        Returns:
            List of recommendation dicts with:
            - severity: "CRITICAL" or "HIGH"
            - action: One of "reduce_context_size", "switch_to_smaller_model",
                      "increase_timeout", "optimize_prompt"
            - reason: Human-readable explanation
            - metric_value: The metric value that triggered this recommendation
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        recommendations: List[Dict[str, Any]] = []

        # Check for high failure rates (triggers model downgrade or prompt optimization)
        failure_result = self.db.execute(
            text("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN phase_outcome != 'SUCCESS' THEN 1 ELSE 0 END) as failures
            FROM phase_outcome_events
            WHERE timestamp >= :cutoff AND phase_type = :phase_type
            """),
            {"cutoff": cutoff, "phase_type": phase_type},
        )
        failure_row = failure_result.fetchone()
        if failure_row and failure_row.total > 0:
            failure_rate = failure_row.failures / failure_row.total
            if failure_rate >= 0.5:  # 50%+ failure rate is CRITICAL
                recommendations.append(
                    {
                        "severity": "CRITICAL",
                        "action": "switch_to_smaller_model",
                        "reason": f"High failure rate ({failure_rate:.0%}) for phase type '{phase_type}' - smaller model may be more reliable",
                        "metric_value": failure_rate,
                    }
                )
            elif failure_rate >= 0.3:  # 30%+ failure rate is HIGH
                recommendations.append(
                    {
                        "severity": "HIGH",
                        "action": "optimize_prompt",
                        "reason": f"Elevated failure rate ({failure_rate:.0%}) for phase type '{phase_type}'",
                        "metric_value": failure_rate,
                    }
                )

        # Check for high token usage (triggers context size reduction)
        token_result = self.db.execute(
            text("""
            SELECT AVG(tokens_used) as avg_tokens, MAX(tokens_used) as max_tokens
            FROM phase_outcome_events
            WHERE timestamp >= :cutoff AND phase_type = :phase_type AND tokens_used IS NOT NULL
            """),
            {"cutoff": cutoff, "phase_type": phase_type},
        )
        token_row = token_result.fetchone()
        if token_row and token_row.avg_tokens:
            # CRITICAL if average exceeds 100k tokens
            if token_row.avg_tokens > 100_000:
                recommendations.append(
                    {
                        "severity": "CRITICAL",
                        "action": "reduce_context_size",
                        "reason": f"Very high average token usage ({token_row.avg_tokens:,.0f}) for phase type '{phase_type}'",
                        "metric_value": token_row.avg_tokens,
                    }
                )
            # HIGH if average exceeds 50k tokens
            elif token_row.avg_tokens > 50_000:
                recommendations.append(
                    {
                        "severity": "HIGH",
                        "action": "reduce_context_size",
                        "reason": f"High average token usage ({token_row.avg_tokens:,.0f}) for phase type '{phase_type}'",
                        "metric_value": token_row.avg_tokens,
                    }
                )

        # Check for timeout patterns (triggers timeout increase)
        timeout_result = self.db.execute(
            text("""
            SELECT COUNT(*) as timeout_count
            FROM phase_outcome_events
            WHERE timestamp >= :cutoff AND phase_type = :phase_type
                  AND (stop_reason LIKE '%timeout%' OR stop_reason LIKE '%TIMEOUT%')
            """),
            {"cutoff": cutoff, "phase_type": phase_type},
        )
        timeout_row = timeout_result.fetchone()
        if timeout_row and timeout_row.timeout_count >= 3:  # 3+ timeouts is CRITICAL
            recommendations.append(
                {
                    "severity": "CRITICAL",
                    "action": "increase_timeout",
                    "reason": f"Frequent timeouts ({timeout_row.timeout_count}) for phase type '{phase_type}'",
                    "metric_value": timeout_row.timeout_count,
                }
            )
        elif timeout_row and timeout_row.timeout_count >= 1:  # 1-2 timeouts is HIGH
            recommendations.append(
                {
                    "severity": "HIGH",
                    "action": "increase_timeout",
                    "reason": f"Timeout detected ({timeout_row.timeout_count}) for phase type '{phase_type}'",
                    "metric_value": timeout_row.timeout_count,
                }
            )

        return recommendations

    def get_cost_recommendations(
        self,
        tokens_used: int,
        token_cap: int,
        warning_threshold_pct: float = 0.80,
        critical_threshold_pct: float = 0.95,
    ) -> CostRecommendation:
        """Get cost recommendations based on current token usage (IMP-COST-005).

        Analyzes current spend against budget and recommends whether to pause
        execution to prevent budget overruns.

        Args:
            tokens_used: Total tokens consumed so far in this run
            token_cap: Maximum token budget for this run
            warning_threshold_pct: Percentage at which to issue warning (default: 80%)
            critical_threshold_pct: Percentage at which to recommend pause (default: 95%)

        Returns:
            CostRecommendation with pause decision and details
        """
        if token_cap <= 0:
            # No cap set, don't recommend pause
            return CostRecommendation(
                should_pause=False,
                reason="No token cap configured",
                current_spend=float(tokens_used),
                budget_remaining_pct=100.0,
                severity="info",
            )

        usage_pct = tokens_used / token_cap
        budget_remaining_pct = max(0.0, (1.0 - usage_pct) * 100)

        # Critical: Above critical threshold - recommend pause
        if usage_pct >= critical_threshold_pct:
            return CostRecommendation(
                should_pause=True,
                reason=f"Token usage at {usage_pct:.1%} of budget ({tokens_used:,}/{token_cap:,} tokens). "
                f"Approaching budget exhaustion.",
                current_spend=float(tokens_used),
                budget_remaining_pct=budget_remaining_pct,
                severity="critical",
            )

        # Warning: Above warning threshold but below critical
        if usage_pct >= warning_threshold_pct:
            return CostRecommendation(
                should_pause=False,
                reason=f"Token usage at {usage_pct:.1%} of budget ({tokens_used:,}/{token_cap:,} tokens). "
                f"Consider wrapping up current work.",
                current_spend=float(tokens_used),
                budget_remaining_pct=budget_remaining_pct,
                severity="warning",
            )

        # Normal: Below warning threshold
        return CostRecommendation(
            should_pause=False,
            reason="Token usage within normal limits",
            current_spend=float(tokens_used),
            budget_remaining_pct=budget_remaining_pct,
            severity="info",
        )
