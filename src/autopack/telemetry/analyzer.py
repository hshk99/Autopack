"""Automated telemetry analysis for issue prioritization."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from autopack.diagnostics.probes import ProbeRunResult

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


@dataclass
class TaskGenerationStats:
    """Task generation statistics from telemetry (IMP-LOOP-004)."""

    total_runs: int  # Total generation attempts
    successful_runs: int  # Successful generation attempts
    failed_runs: int  # Failed generation attempts
    success_rate: float  # Success rate (0.0 - 1.0)
    total_tasks_generated: int  # Total tasks generated
    total_insights_processed: int  # Total insights processed
    total_patterns_detected: int  # Total patterns detected
    avg_generation_time_ms: float  # Average generation time in milliseconds
    avg_tasks_per_run: float  # Average tasks per successful run
    common_error_types: Dict[str, int]  # Error type -> count


@dataclass
class TaskEffectivenessStats:
    """Task effectiveness statistics from completion telemetry (IMP-LOOP-012).

    Tracks how well improvement tasks achieve their intended targets,
    enabling measurement of the self-improvement loop's effectiveness.
    """

    total_completed: int  # Total tasks completed (success or failure)
    successful_tasks: int  # Tasks that completed successfully
    failed_tasks: int  # Tasks that failed
    success_rate: float  # Success rate (0.0 - 1.0)
    targets_achieved: int  # Tasks that met their improvement targets
    targets_missed: int  # Tasks that didn't meet targets
    target_achievement_rate: float  # Rate of target achievement (0.0 - 1.0)
    avg_improvement_pct: float  # Average improvement percentage achieved
    avg_execution_duration_ms: float  # Average task execution time
    effectiveness_by_type: Dict[str, Dict[str, float]]  # type -> {success_rate, target_rate}
    effectiveness_by_priority: Dict[
        str, Dict[str, float]
    ]  # priority -> {success_rate, target_rate}


@dataclass
class ContextInjectionImpact:
    """Context injection impact analysis result (IMP-LOOP-021).

    Compares success rates between phases with and without context injection
    to measure the effectiveness of memory-based context retrieval.
    """

    with_context_success_rate: float  # Success rate for phases with context injection
    without_context_success_rate: float  # Success rate for phases without context injection
    delta: float  # Success rate difference (with - without)
    with_context_count: int  # Number of phases with context injection
    without_context_count: int  # Number of phases without context injection
    avg_context_item_count: float  # Average items injected (when context was injected)
    impact_significant: bool  # True if delta is statistically meaningful (>5% with n>=10)


@dataclass
class ModelCategoryStats:
    """Per-model statistics for a specific task category (IMP-LOOP-032).

    Tracks effectiveness metrics for a single model within a task category
    to enable data-driven model selection.
    """

    model_id: str  # Model identifier (e.g., "claude-sonnet-4-5", "claude-opus-4-5")
    task_category: str  # Task category (e.g., "test_generation", "code_review")
    success_rate: float  # Success rate (0.0 - 1.0)
    avg_latency_ms: float  # Average latency in milliseconds
    avg_tokens_used: float  # Average tokens used per phase
    cost_per_success: float  # Estimated cost per successful phase (tokens / success_rate)
    sample_count: int  # Number of samples


@dataclass
class RegressionPreventionReport:
    """Report measuring whether a task prevented regressions (IMP-LOOP-033).

    Long-term impact tracking requires measuring whether improvements
    prevent future regressions. This report compares test failure rates
    before and after task completion to quantify regression prevention.

    Attributes:
        task_id: The task identifier being measured.
        since_date: The date from which to measure (task completion date).
        related_test_count: Number of tests related to this task.
        failures_before: Number of test failures before task completion.
        failures_after: Number of test failures after task completion.
        regressions_prevented: Estimated number of regressions prevented.
        confidence: Confidence level in the measurement (0.0-1.0).
        measurement_window_days: Number of days in the measurement window.
        notes: Additional notes about the measurement.
    """

    task_id: str
    since_date: datetime
    related_test_count: int = 0
    failures_before: int = 0
    failures_after: int = 0
    regressions_prevented: int = 0
    confidence: float = 0.0
    measurement_window_days: int = 0
    notes: str = ""


@dataclass
class ModelEffectivenessReport:
    """Model effectiveness analysis report (IMP-LOOP-032).

    Tracks per-model success rates by task category to enable data-driven
    model selection. Builder currently uses Claude Sonnet 4.5 -> Opus 4 -> GPT-4o
    but this is hardcoded. This report provides the data to make selection adaptive.
    """

    # Stats grouped by model_id and task_category
    stats_by_model_category: Dict[str, Dict[str, ModelCategoryStats]]
    # Best model for each category (model_id with highest success_rate given sufficient samples)
    best_model_by_category: Dict[str, str]
    # Overall model rankings (model_id -> weighted success score)
    overall_model_rankings: Dict[str, float]
    # Analysis metadata
    analysis_window_days: int
    total_phases_analyzed: int
    generated_at: str  # ISO timestamp

    def best_model_for(self, task_category: str, min_samples: int = 5) -> Optional[str]:
        """Get the best model for a specific task category.

        Args:
            task_category: The task category to find the best model for
            min_samples: Minimum samples required for a model to be considered

        Returns:
            Model ID with highest success rate, or None if insufficient data
        """
        if task_category in self.best_model_by_category:
            return self.best_model_by_category[task_category]

        # Fallback: find model with highest overall ranking
        if self.overall_model_rankings:
            return max(self.overall_model_rankings.items(), key=lambda x: x[1])[0]

        return None


class TelemetryAnalyzer:
    """Analyze telemetry data and generate ranked issues."""

    def __init__(self, db_session: Session, memory_service=None):
        self.db = db_session
        self.memory_service = memory_service
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        # IMP-LOOP-020: Telemetry-to-memory persistence is MANDATORY and cannot be disabled
        # The feedback loop requires telemetry to flow to memory for self-improvement

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
            from autopack.telemetry.telemetry_to_memory_bridge import \
                TelemetryToMemoryBridge

            bridge = TelemetryToMemoryBridge(self.memory_service)
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

    def get_task_generation_stats(self, window_days: int = 7) -> TaskGenerationStats:
        """Get task generation success metrics (IMP-LOOP-004).

        Aggregates task generation telemetry to provide visibility into
        the health and effectiveness of the self-improvement loop.

        Args:
            window_days: Number of days to look back (default: 7)

        Returns:
            TaskGenerationStats with aggregated metrics
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

        # Query overall stats
        overall_result = self.db.execute(
            text("""
            SELECT
                COUNT(*) as total_runs,
                SUM(CASE WHEN success = true THEN 1 ELSE 0 END) as successful_runs,
                SUM(CASE WHEN success = false THEN 1 ELSE 0 END) as failed_runs,
                SUM(tasks_generated) as total_tasks_generated,
                SUM(insights_processed) as total_insights_processed,
                SUM(patterns_detected) as total_patterns_detected,
                AVG(generation_time_ms) as avg_generation_time_ms
            FROM task_generation_events
            WHERE timestamp >= :cutoff
            """),
            {"cutoff": cutoff},
        )
        row = overall_result.fetchone()

        total_runs = row.total_runs or 0
        successful_runs = row.successful_runs or 0
        failed_runs = row.failed_runs or 0
        total_tasks_generated = row.total_tasks_generated or 0
        total_insights_processed = row.total_insights_processed or 0
        total_patterns_detected = row.total_patterns_detected or 0
        avg_generation_time_ms = row.avg_generation_time_ms or 0.0

        # Calculate derived metrics
        success_rate = successful_runs / total_runs if total_runs > 0 else 0.0
        avg_tasks_per_run = total_tasks_generated / successful_runs if successful_runs > 0 else 0.0

        # Query common error types
        error_result = self.db.execute(
            text("""
            SELECT error_type, COUNT(*) as count
            FROM task_generation_events
            WHERE timestamp >= :cutoff AND success = false AND error_type IS NOT NULL
            GROUP BY error_type
            ORDER BY count DESC
            LIMIT 10
            """),
            {"cutoff": cutoff},
        )
        common_error_types = {row.error_type: row.count for row in error_result}

        logger.debug(
            f"[IMP-LOOP-004] Task generation stats: {total_runs} runs, "
            f"{success_rate:.1%} success rate, {total_tasks_generated} tasks generated"
        )

        return TaskGenerationStats(
            total_runs=total_runs,
            successful_runs=successful_runs,
            failed_runs=failed_runs,
            success_rate=success_rate,
            total_tasks_generated=total_tasks_generated,
            total_insights_processed=total_insights_processed,
            total_patterns_detected=total_patterns_detected,
            avg_generation_time_ms=avg_generation_time_ms,
            avg_tasks_per_run=avg_tasks_per_run,
            common_error_types=common_error_types,
        )

    def write_task_generation_report(self, stats: TaskGenerationStats, output_path: Path) -> None:
        """Write task generation stats to artifact file (IMP-LOOP-004).

        Args:
            stats: TaskGenerationStats from get_task_generation_stats()
            output_path: Path to write markdown report
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            f.write("# Task Generation Metrics Report\n\n")
            f.write(f"**Generated**: {datetime.now(timezone.utc).isoformat()}\n\n")

            f.write("## Summary\n\n")
            f.write("| Metric | Value |\n")
            f.write("|--------|-------|\n")
            f.write(f"| Total Runs | {stats.total_runs} |\n")
            f.write(f"| Successful Runs | {stats.successful_runs} |\n")
            f.write(f"| Failed Runs | {stats.failed_runs} |\n")
            f.write(f"| Success Rate | {stats.success_rate:.1%} |\n")
            f.write(f"| Total Tasks Generated | {stats.total_tasks_generated} |\n")
            f.write(f"| Avg Tasks per Run | {stats.avg_tasks_per_run:.1f} |\n")
            f.write(f"| Avg Generation Time | {stats.avg_generation_time_ms:.0f}ms |\n")

            f.write("\n## Insights Processing\n\n")
            f.write("| Metric | Value |\n")
            f.write("|--------|-------|\n")
            f.write(f"| Total Insights Processed | {stats.total_insights_processed} |\n")
            f.write(f"| Total Patterns Detected | {stats.total_patterns_detected} |\n")

            if stats.common_error_types:
                f.write("\n## Common Error Types\n\n")
                f.write("| Error Type | Count |\n")
                f.write("|------------|-------|\n")
                for error_type, count in stats.common_error_types.items():
                    f.write(f"| {error_type} | {count} |\n")
            else:
                f.write("\n## Error Types\n\n")
                f.write("*No errors recorded in analysis window*\n")

        logger.info(f"[IMP-LOOP-004] Wrote task generation report to: {output_path}")

    def receive_task_completion(
        self,
        task_id: str,
        success: bool,
        target_metric: Optional[float] = None,
        actual_metric: Optional[float] = None,
        task_type: Optional[str] = None,
        task_priority: Optional[str] = None,
        execution_duration_ms: Optional[float] = None,
        run_id: Optional[str] = None,
        failure_reason: Optional[str] = None,
        retry_count: int = 0,
    ) -> None:
        """Receive and record a task completion event (IMP-LOOP-012).

        This method is called when a ROAD-C improvement task completes,
        recording the outcome for effectiveness tracking.

        Args:
            task_id: Unique identifier for the task
            success: Whether the task completed successfully
            target_metric: Expected improvement target value
            actual_metric: Actual measured result after task execution
            task_type: Type of task (cost_sink, failure_mode, retry_cause)
            task_priority: Priority level (critical, high, medium, low)
            execution_duration_ms: How long the task took to execute
            run_id: Run ID that executed the task
            failure_reason: Reason for failure if task failed
            retry_count: Number of retries needed
        """
        from ..models import TaskCompletionEvent as TaskCompletionEventModel

        try:
            # Determine if target was achieved
            target_achieved = None
            improvement_percentage = None

            if target_metric is not None and actual_metric is not None:
                # For cost sinks and retry causes, lower is better
                # For success rates, higher is better
                # We'll use a simple heuristic: actual >= target means achieved
                # (callers should normalize metrics appropriately)
                target_achieved = actual_metric >= target_metric

                if target_metric != 0:
                    improvement_percentage = (
                        (actual_metric - target_metric) / abs(target_metric)
                    ) * 100

            db_event = TaskCompletionEventModel(
                task_id=task_id,
                run_id=run_id,
                success=success,
                failure_reason=failure_reason,
                target_metric=target_metric,
                actual_metric=actual_metric,
                target_achieved=target_achieved,
                improvement_percentage=improvement_percentage,
                task_type=task_type,
                task_priority=task_priority,
                execution_duration_ms=execution_duration_ms,
                retry_count=retry_count,
                timestamp=datetime.now(timezone.utc),
            )
            self.db.add(db_event)
            self.db.commit()
            logger.info(
                f"[IMP-LOOP-012] Recorded task completion: task_id={task_id}, "
                f"success={success}, target_achieved={target_achieved}"
            )
        except Exception as e:
            self.db.rollback()
            logger.warning(f"[IMP-LOOP-012] Failed to record task completion: {e}")

    def get_task_effectiveness_stats(self, window_days: int = 7) -> TaskEffectivenessStats:
        """Get task effectiveness statistics (IMP-LOOP-012).

        Aggregates task completion telemetry to measure how effectively
        the self-improvement loop achieves its intended improvements.

        Args:
            window_days: Number of days to look back (default: 7)

        Returns:
            TaskEffectivenessStats with aggregated effectiveness metrics
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

        # Query overall stats
        overall_result = self.db.execute(
            text("""
            SELECT
                COUNT(*) as total_completed,
                SUM(CASE WHEN success = true THEN 1 ELSE 0 END) as successful_tasks,
                SUM(CASE WHEN success = false THEN 1 ELSE 0 END) as failed_tasks,
                SUM(CASE WHEN target_achieved = true THEN 1 ELSE 0 END) as targets_achieved,
                SUM(CASE WHEN target_achieved = false THEN 1 ELSE 0 END) as targets_missed,
                AVG(improvement_percentage) as avg_improvement_pct,
                AVG(execution_duration_ms) as avg_execution_duration_ms
            FROM task_completion_events
            WHERE timestamp >= :cutoff
            """),
            {"cutoff": cutoff},
        )
        row = overall_result.fetchone()

        total_completed = row.total_completed or 0
        successful_tasks = row.successful_tasks or 0
        failed_tasks = row.failed_tasks or 0
        targets_achieved = row.targets_achieved or 0
        targets_missed = row.targets_missed or 0
        avg_improvement_pct = row.avg_improvement_pct or 0.0
        avg_execution_duration_ms = row.avg_execution_duration_ms or 0.0

        # Calculate rates
        success_rate = successful_tasks / total_completed if total_completed > 0 else 0.0
        targets_with_metrics = targets_achieved + targets_missed
        target_achievement_rate = (
            targets_achieved / targets_with_metrics if targets_with_metrics > 0 else 0.0
        )

        # Query effectiveness by task type
        type_result = self.db.execute(
            text("""
            SELECT
                task_type,
                COUNT(*) as total,
                SUM(CASE WHEN success = true THEN 1 ELSE 0 END) as successes,
                SUM(CASE WHEN target_achieved = true THEN 1 ELSE 0 END) as achieved
            FROM task_completion_events
            WHERE timestamp >= :cutoff AND task_type IS NOT NULL
            GROUP BY task_type
            """),
            {"cutoff": cutoff},
        )
        effectiveness_by_type: Dict[str, Dict[str, float]] = {}
        for type_row in type_result:
            total = type_row.total or 1
            effectiveness_by_type[type_row.task_type] = {
                "success_rate": (type_row.successes or 0) / total,
                "target_rate": (type_row.achieved or 0) / total,
                "total": total,
            }

        # Query effectiveness by priority
        priority_result = self.db.execute(
            text("""
            SELECT
                task_priority,
                COUNT(*) as total,
                SUM(CASE WHEN success = true THEN 1 ELSE 0 END) as successes,
                SUM(CASE WHEN target_achieved = true THEN 1 ELSE 0 END) as achieved
            FROM task_completion_events
            WHERE timestamp >= :cutoff AND task_priority IS NOT NULL
            GROUP BY task_priority
            """),
            {"cutoff": cutoff},
        )
        effectiveness_by_priority: Dict[str, Dict[str, float]] = {}
        for prio_row in priority_result:
            total = prio_row.total or 1
            effectiveness_by_priority[prio_row.task_priority] = {
                "success_rate": (prio_row.successes or 0) / total,
                "target_rate": (prio_row.achieved or 0) / total,
                "total": total,
            }

        logger.debug(
            f"[IMP-LOOP-012] Task effectiveness stats: {total_completed} completed, "
            f"{success_rate:.1%} success rate, {target_achievement_rate:.1%} target achievement"
        )

        return TaskEffectivenessStats(
            total_completed=total_completed,
            successful_tasks=successful_tasks,
            failed_tasks=failed_tasks,
            success_rate=success_rate,
            targets_achieved=targets_achieved,
            targets_missed=targets_missed,
            target_achievement_rate=target_achievement_rate,
            avg_improvement_pct=avg_improvement_pct,
            avg_execution_duration_ms=avg_execution_duration_ms,
            effectiveness_by_type=effectiveness_by_type,
            effectiveness_by_priority=effectiveness_by_priority,
        )

    def write_task_effectiveness_report(
        self, stats: TaskEffectivenessStats, output_path: Path
    ) -> None:
        """Write task effectiveness stats to artifact file (IMP-LOOP-012).

        Args:
            stats: TaskEffectivenessStats from get_task_effectiveness_stats()
            output_path: Path to write markdown report
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            f.write("# Task Effectiveness Report\n\n")
            f.write(f"**Generated**: {datetime.now(timezone.utc).isoformat()}\n\n")

            f.write("## Summary\n\n")
            f.write("| Metric | Value |\n")
            f.write("|--------|-------|\n")
            f.write(f"| Total Completed | {stats.total_completed} |\n")
            f.write(f"| Successful Tasks | {stats.successful_tasks} |\n")
            f.write(f"| Failed Tasks | {stats.failed_tasks} |\n")
            f.write(f"| Success Rate | {stats.success_rate:.1%} |\n")
            f.write(f"| Targets Achieved | {stats.targets_achieved} |\n")
            f.write(f"| Targets Missed | {stats.targets_missed} |\n")
            f.write(f"| Target Achievement Rate | {stats.target_achievement_rate:.1%} |\n")
            f.write(f"| Avg Improvement | {stats.avg_improvement_pct:.1f}% |\n")
            f.write(f"| Avg Execution Time | {stats.avg_execution_duration_ms:.0f}ms |\n")

            if stats.effectiveness_by_type:
                f.write("\n## Effectiveness by Task Type\n\n")
                f.write("| Task Type | Success Rate | Target Rate | Count |\n")
                f.write("|-----------|--------------|-------------|-------|\n")
                for task_type, metrics in sorted(stats.effectiveness_by_type.items()):
                    f.write(
                        f"| {task_type} | {metrics['success_rate']:.1%} | "
                        f"{metrics['target_rate']:.1%} | {int(metrics['total'])} |\n"
                    )

            if stats.effectiveness_by_priority:
                f.write("\n## Effectiveness by Priority\n\n")
                f.write("| Priority | Success Rate | Target Rate | Count |\n")
                f.write("|----------|--------------|-------------|-------|\n")
                for priority, metrics in sorted(stats.effectiveness_by_priority.items()):
                    f.write(
                        f"| {priority} | {metrics['success_rate']:.1%} | "
                        f"{metrics['target_rate']:.1%} | {int(metrics['total'])} |\n"
                    )

        logger.info(f"[IMP-LOOP-012] Wrote task effectiveness report to: {output_path}")

    def analyze_context_injection_impact(self, window_days: int = 7) -> ContextInjectionImpact:
        """Analyze the impact of context injection on phase success rates (IMP-LOOP-021).

        Compares success rates between phases with and without context injection
        to measure the effectiveness of memory-based context retrieval.

        Args:
            window_days: Number of days to look back (default: 7)

        Returns:
            ContextInjectionImpact with A/B comparison metrics
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

        # Query phases with context injection
        with_context_result = self.db.execute(
            text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN phase_outcome = 'SUCCESS' THEN 1 ELSE 0 END) as successes,
                AVG(context_item_count) as avg_items
            FROM phase_outcome_events
            WHERE timestamp >= :cutoff
                AND context_injected = true
            """),
            {"cutoff": cutoff},
        )
        with_row = with_context_result.fetchone()

        # Query phases without context injection
        without_context_result = self.db.execute(
            text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN phase_outcome = 'SUCCESS' THEN 1 ELSE 0 END) as successes
            FROM phase_outcome_events
            WHERE timestamp >= :cutoff
                AND (context_injected = false OR context_injected IS NULL)
            """),
            {"cutoff": cutoff},
        )
        without_row = without_context_result.fetchone()

        # Extract values with defaults
        with_count = with_row.total or 0 if with_row else 0
        with_successes = with_row.successes or 0 if with_row else 0
        avg_items = with_row.avg_items or 0.0 if with_row else 0.0

        without_count = without_row.total or 0 if without_row else 0
        without_successes = without_row.successes or 0 if without_row else 0

        # Calculate success rates
        with_success_rate = with_successes / max(with_count, 1)
        without_success_rate = without_successes / max(without_count, 1)
        delta = with_success_rate - without_success_rate

        # Determine if the impact is statistically significant
        # Simple heuristic: delta > 5% and at least 10 samples in each group
        impact_significant = abs(delta) > 0.05 and with_count >= 10 and without_count >= 10

        impact = ContextInjectionImpact(
            with_context_success_rate=with_success_rate,
            without_context_success_rate=without_success_rate,
            delta=delta,
            with_context_count=with_count,
            without_context_count=without_count,
            avg_context_item_count=avg_items,
            impact_significant=impact_significant,
        )

        logger.info(
            f"[IMP-LOOP-021] Context injection impact analysis: "
            f"with_context={with_success_rate:.1%} ({with_count} phases), "
            f"without_context={without_success_rate:.1%} ({without_count} phases), "
            f"delta={delta:+.1%}, significant={impact_significant}"
        )

        return impact

    def get_model_effectiveness_by_category(
        self, window_days: int = 7, min_samples: int = 5
    ) -> ModelEffectivenessReport:
        """Analyze success rates per model per task category (IMP-LOOP-032).

        Enables data-driven model selection by tracking which models perform best
        for which task categories. Builder uses Claude Sonnet 4.5 -> Opus 4 -> GPT-4o
        but this is currently hardcoded. This method provides the data to make
        model selection adaptive.

        Args:
            window_days: Number of days to look back (default: 7)
            min_samples: Minimum samples required for a model-category pair to be
                         considered for "best model" selection (default: 5)

        Returns:
            ModelEffectivenessReport with per-model-category statistics
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

        # Query model effectiveness grouped by model and task category
        result = self.db.execute(
            text("""
            SELECT
                model_used,
                phase_type as task_category,
                COUNT(*) as total,
                SUM(CASE WHEN phase_outcome = 'SUCCESS' THEN 1 ELSE 0 END) as successes,
                AVG(duration_seconds) as avg_duration_seconds,
                AVG(tokens_used) as avg_tokens
            FROM phase_outcome_events
            WHERE timestamp >= :cutoff
                AND model_used IS NOT NULL
                AND phase_type IS NOT NULL
            GROUP BY model_used, phase_type
            ORDER BY model_used, phase_type
            """),
            {"cutoff": cutoff},
        )

        # Build stats by model and category
        stats_by_model_category: Dict[str, Dict[str, ModelCategoryStats]] = {}
        total_phases = 0

        for row in result:
            model_id = row.model_used
            task_category = row.task_category
            total = row.total or 0
            successes = row.successes or 0
            avg_duration_seconds = row.avg_duration_seconds or 0.0
            avg_tokens = row.avg_tokens or 0.0

            total_phases += total

            # Calculate metrics
            success_rate = successes / max(total, 1)
            avg_latency_ms = avg_duration_seconds * 1000
            # Cost per success: tokens used / success_rate (higher = more expensive)
            cost_per_success = avg_tokens / max(success_rate, 0.01)

            stats = ModelCategoryStats(
                model_id=model_id,
                task_category=task_category,
                success_rate=success_rate,
                avg_latency_ms=avg_latency_ms,
                avg_tokens_used=avg_tokens,
                cost_per_success=cost_per_success,
                sample_count=total,
            )

            if model_id not in stats_by_model_category:
                stats_by_model_category[model_id] = {}
            stats_by_model_category[model_id][task_category] = stats

        # Determine best model for each category
        best_model_by_category: Dict[str, str] = {}
        category_candidates: Dict[str, List[ModelCategoryStats]] = {}

        # Group all stats by category
        for model_id, categories in stats_by_model_category.items():
            for task_category, stats in categories.items():
                if task_category not in category_candidates:
                    category_candidates[task_category] = []
                category_candidates[task_category].append(stats)

        # Find best model for each category (highest success rate with sufficient samples)
        for task_category, candidates in category_candidates.items():
            # Filter to models with sufficient samples
            qualified = [c for c in candidates if c.sample_count >= min_samples]
            if qualified:
                # Sort by success rate (descending), then by cost_per_success (ascending)
                qualified.sort(key=lambda x: (-x.success_rate, x.cost_per_success))
                best_model_by_category[task_category] = qualified[0].model_id

        # Calculate overall model rankings (weighted by sample count)
        overall_model_rankings: Dict[str, float] = {}
        for model_id, categories in stats_by_model_category.items():
            total_successes = 0
            total_samples = 0
            for stats in categories.values():
                total_successes += stats.success_rate * stats.sample_count
                total_samples += stats.sample_count
            if total_samples > 0:
                overall_model_rankings[model_id] = total_successes / total_samples

        # Sort rankings
        overall_model_rankings = dict(
            sorted(overall_model_rankings.items(), key=lambda x: x[1], reverse=True)
        )

        report = ModelEffectivenessReport(
            stats_by_model_category=stats_by_model_category,
            best_model_by_category=best_model_by_category,
            overall_model_rankings=overall_model_rankings,
            analysis_window_days=window_days,
            total_phases_analyzed=total_phases,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        logger.info(
            f"[IMP-LOOP-032] Model effectiveness analysis: "
            f"analyzed {total_phases} phases, "
            f"found {len(stats_by_model_category)} models, "
            f"top model={next(iter(overall_model_rankings.keys()), 'none')}"
        )

        return report

    def ingest_diagnostic_findings(
        self,
        findings: List[Dict[str, Any]],
        run_id: Optional[str] = None,
        phase_id: Optional[str] = None,
    ) -> List[RankedIssue]:
        """Ingest diagnostic findings and convert them to RankedIssue format (IMP-LOOP-016).

        Creates a bridge between DiagnosticsAgent and the telemetry system, enabling
        diagnostic findings to be tracked and actioned through the same pipeline as
        other telemetry-derived issues.

        Args:
            findings: List of diagnostic findings with structure:
                - failure_class: str - Classification of the failure
                - probe_name: str - Name of the probe that found the issue
                - resolved: bool - Whether the probe resolved the issue
                - severity: str - "high", "medium", or "low"
                - evidence: str - Summary of evidence found
                - commands_run: int - Number of commands executed
                - exit_codes: List[int] - Exit codes from commands
            run_id: Optional run ID for context
            phase_id: Optional phase ID for context

        Returns:
            List of RankedIssue objects with issue_type="diagnostic"
        """
        ranked_issues: List[RankedIssue] = []

        for i, finding in enumerate(findings):
            failure_class = finding.get("failure_class", "unknown")
            probe_name = finding.get("probe_name", "unknown_probe")
            resolved = finding.get("resolved", False)
            severity = finding.get("severity", "medium")
            evidence = finding.get("evidence", "")
            commands_run = finding.get("commands_run", 0)
            exit_codes = finding.get("exit_codes", [])

            # Calculate a metric value based on severity and resolution
            # Higher values indicate more critical issues
            severity_weights = {"high": 3.0, "medium": 2.0, "low": 1.0}
            base_weight = severity_weights.get(severity, 2.0)
            # Unresolved issues get higher weight
            metric_value = base_weight * (2.0 if not resolved else 1.0)

            issue = RankedIssue(
                rank=i + 1,
                issue_type="diagnostic",
                phase_id=phase_id or f"diag-{failure_class}",
                phase_type=f"diagnostic:{failure_class}",
                metric_value=metric_value,
                details={
                    "failure_class": failure_class,
                    "probe_name": probe_name,
                    "resolved": resolved,
                    "severity": severity,
                    "evidence": evidence,
                    "commands_run": commands_run,
                    "exit_codes": exit_codes,
                    "run_id": run_id,
                    "source": "diagnostics_agent",
                },
            )
            ranked_issues.append(issue)

        # Persist to memory if available (same pattern as aggregate_telemetry)
        if self.memory_service and self.memory_service.enabled and ranked_issues:
            from autopack.telemetry.telemetry_to_memory_bridge import \
                TelemetryToMemoryBridge

            bridge = TelemetryToMemoryBridge(self.memory_service)
            flat_issues = []
            for issue in ranked_issues:
                flat_issues.append(
                    {
                        "issue_type": "diagnostic",
                        "insight_id": f"diag-{issue.rank}",
                        "rank": issue.rank,
                        "phase_id": issue.phase_id,
                        "phase_type": issue.phase_type,
                        "severity": issue.details.get("severity", "medium"),
                        "description": f"Diagnostic finding: {issue.details.get('failure_class', '')} "
                        f"via {issue.details.get('probe_name', '')}",
                        "metric_value": issue.metric_value,
                        "occurrences": 1,
                        "details": issue.details,
                        "suggested_action": f"Investigate {issue.details.get('failure_class', '')} "
                        f"{'(resolved)' if issue.details.get('resolved') else '(unresolved)'}",
                    }
                )
            bridge.persist_insights(
                flat_issues,
                run_id=run_id or self.run_id,
                project_id=None,
            )

        logger.info(
            f"[IMP-LOOP-016] Ingested {len(ranked_issues)} diagnostic findings "
            f"(run_id={run_id}, phase_id={phase_id})"
        )

        return ranked_issues

    @staticmethod
    def convert_probe_results_to_findings(
        probe_results: List["ProbeRunResult"],
        failure_class: str,
    ) -> List[Dict[str, Any]]:
        """Convert ProbeRunResult objects to diagnostic findings format (IMP-LOOP-016).

        Helper method for DiagnosticsAgent to convert probe results into the
        format expected by ingest_diagnostic_findings().

        Args:
            probe_results: List of ProbeRunResult from DiagnosticsAgent
            failure_class: The failure classification from diagnostics

        Returns:
            List of finding dictionaries ready for ingest_diagnostic_findings()
        """
        findings: List[Dict[str, Any]] = []

        for pr in probe_results:
            # Extract exit codes from command results
            exit_codes = [
                cr.exit_code
                for cr in pr.command_results
                if not cr.skipped and cr.exit_code is not None
            ]

            # Build evidence summary from command results
            evidence_parts = []
            for cr in pr.command_results:
                if cr.skipped:
                    evidence_parts.append(f"{cr.label or cr.command}: skipped")
                elif cr.timed_out:
                    evidence_parts.append(f"{cr.label or cr.command}: timed out")
                else:
                    evidence_parts.append(f"{cr.label or cr.command}: exit={cr.exit_code}")
            evidence = "; ".join(evidence_parts) if evidence_parts else "No commands executed"

            # Determine severity based on probe results
            # Unresolved probes with failures are high severity
            if not pr.resolved and any(code != 0 for code in exit_codes):
                severity = "high"
            elif not pr.resolved:
                severity = "medium"
            else:
                severity = "low"

            findings.append(
                {
                    "failure_class": failure_class,
                    "probe_name": pr.probe.name,
                    "resolved": pr.resolved,
                    "severity": severity,
                    "evidence": evidence,
                    "commands_run": len(pr.command_results),
                    "exit_codes": exit_codes,
                }
            )

        return findings

    # IMP-LOOP-033: Long-term impact tracking methods

    def measure_regression_prevention(
        self,
        task_id: str,
        since_date: datetime,
        related_phase_types: Optional[List[str]] = None,
        window_days: int = 30,
    ) -> RegressionPreventionReport:
        """Measure whether a task prevented regressions since completion.

        IMP-LOOP-033: Analyzes telemetry to determine if an improvement task
        has prevented regressions by comparing failure rates before and after
        the task completion date.

        Args:
            task_id: The task identifier to measure.
            since_date: The task completion date (start of measurement).
            related_phase_types: Optional list of phase types related to this task.
                If not provided, will attempt to detect based on task_id pattern.
            window_days: Number of days to look back before since_date for comparison.

        Returns:
            RegressionPreventionReport with regression prevention metrics.
        """
        # Calculate time windows
        before_start = since_date - timedelta(days=window_days)
        before_end = since_date
        after_start = since_date
        after_end = datetime.now(timezone.utc)

        # Calculate actual window in days
        actual_window_days = (after_end - after_start).days

        # If no related phase types specified, try to detect from task_id
        if related_phase_types is None:
            related_phase_types = self._detect_related_phase_types(task_id)

        # Count failures before and after
        failures_before = self._count_failures_in_window(
            before_start, before_end, related_phase_types
        )
        failures_after = self._count_failures_in_window(after_start, after_end, related_phase_types)

        # Count total related test runs in each period
        runs_before = self._count_runs_in_window(before_start, before_end, related_phase_types)
        runs_after = self._count_runs_in_window(after_start, after_end, related_phase_types)

        # Calculate regressions prevented
        # Normalize by the number of runs to account for different activity levels
        failure_rate_before = 0.0
        failure_rate_after = 0.0
        if runs_before > 0 and runs_after > 0:
            failure_rate_before = failures_before / runs_before
            failure_rate_after = failures_after / runs_after

            # Expected failures if rate hadn't changed
            expected_failures_after = int(failure_rate_before * runs_after)
            regressions_prevented = max(0, expected_failures_after - failures_after)
        else:
            regressions_prevented = 0

        # Calculate confidence based on sample size
        confidence = self._calculate_confidence(runs_before, runs_after)

        # Build notes
        notes_parts = []
        if related_phase_types:
            notes_parts.append(f"Phase types: {', '.join(related_phase_types)}")
        notes_parts.append(f"Runs before: {runs_before}, after: {runs_after}")
        if runs_before > 0:
            notes_parts.append(f"Failure rate before: {failure_rate_before:.1%}")
        if runs_after > 0:
            notes_parts.append(f"Failure rate after: {failure_rate_after:.1%}")

        report = RegressionPreventionReport(
            task_id=task_id,
            since_date=since_date,
            related_test_count=runs_after,
            failures_before=failures_before,
            failures_after=failures_after,
            regressions_prevented=regressions_prevented,
            confidence=confidence,
            measurement_window_days=actual_window_days,
            notes="; ".join(notes_parts),
        )

        logger.info(
            "[IMP-LOOP-033] Measured regression prevention for %s: "
            "failures_before=%d, failures_after=%d, regressions_prevented=%d, "
            "confidence=%.2f",
            task_id,
            failures_before,
            failures_after,
            regressions_prevented,
            confidence,
        )

        return report

    def _detect_related_phase_types(self, task_id: str) -> List[str]:
        """Detect phase types related to a task ID based on naming patterns.

        IMP-LOOP-033: Helper method to identify which phase types are likely
        affected by a given improvement task.

        Args:
            task_id: The task identifier (e.g., "IMP-LOOP-033", "IMP-MEM-020").

        Returns:
            List of phase type patterns to match.
        """
        # Extract category from task_id pattern (e.g., "LOOP", "MEM", "TELE")
        task_id_upper = task_id.upper()

        phase_type_mappings = {
            "LOOP": ["task_generation", "feedback_pipeline", "autonomous_loop"],
            "MEM": ["memory", "context_injection", "learning"],
            "TELE": ["telemetry", "metrics", "analysis"],
            "COST": ["cost", "budget", "token"],
            "INT": ["integration", "task_generation"],
            "TASK": ["task", "effectiveness"],
        }

        related_types = []
        for category, types in phase_type_mappings.items():
            if category in task_id_upper:
                related_types.extend(types)

        # If no specific mapping found, return empty list (will match all)
        return related_types

    def _count_failures_in_window(
        self,
        start_date: datetime,
        end_date: datetime,
        phase_types: Optional[List[str]] = None,
    ) -> int:
        """Count failures in a time window, optionally filtered by phase types.

        IMP-LOOP-033: Helper method for regression prevention measurement.

        Args:
            start_date: Start of the window.
            end_date: End of the window.
            phase_types: Optional list of phase types to filter by.

        Returns:
            Number of failures in the window.
        """
        if phase_types:
            # Build a LIKE clause for each phase type
            phase_conditions = " OR ".join([f"phase_type LIKE '%{pt}%'" for pt in phase_types])
            query = text(f"""
                SELECT COUNT(*) as failure_count
                FROM phase_outcome_events
                WHERE timestamp >= :start_date
                    AND timestamp < :end_date
                    AND phase_outcome != 'SUCCESS'
                    AND ({phase_conditions})
            """)
        else:
            query = text("""
                SELECT COUNT(*) as failure_count
                FROM phase_outcome_events
                WHERE timestamp >= :start_date
                    AND timestamp < :end_date
                    AND phase_outcome != 'SUCCESS'
            """)

        result = self.db.execute(query, {"start_date": start_date, "end_date": end_date})
        row = result.fetchone()
        return row.failure_count if row else 0

    def _count_runs_in_window(
        self,
        start_date: datetime,
        end_date: datetime,
        phase_types: Optional[List[str]] = None,
    ) -> int:
        """Count total runs in a time window, optionally filtered by phase types.

        IMP-LOOP-033: Helper method for regression prevention measurement.

        Args:
            start_date: Start of the window.
            end_date: End of the window.
            phase_types: Optional list of phase types to filter by.

        Returns:
            Number of runs in the window.
        """
        if phase_types:
            # Build a LIKE clause for each phase type
            phase_conditions = " OR ".join([f"phase_type LIKE '%{pt}%'" for pt in phase_types])
            query = text(f"""
                SELECT COUNT(*) as run_count
                FROM phase_outcome_events
                WHERE timestamp >= :start_date
                    AND timestamp < :end_date
                    AND ({phase_conditions})
            """)
        else:
            query = text("""
                SELECT COUNT(*) as run_count
                FROM phase_outcome_events
                WHERE timestamp >= :start_date
                    AND timestamp < :end_date
            """)

        result = self.db.execute(query, {"start_date": start_date, "end_date": end_date})
        row = result.fetchone()
        return row.run_count if row else 0

    def _calculate_confidence(self, runs_before: int, runs_after: int) -> float:
        """Calculate confidence level based on sample sizes.

        IMP-LOOP-033: Higher sample sizes in both periods lead to higher confidence.

        Args:
            runs_before: Number of runs before the task.
            runs_after: Number of runs after the task.

        Returns:
            Confidence score between 0.0 and 1.0.
        """
        # Minimum samples for any confidence
        if runs_before < 5 or runs_after < 5:
            return 0.0

        # Calculate confidence based on sample sizes
        # Using a simple heuristic: confidence grows with log of sample size
        import math

        min_runs = min(runs_before, runs_after)

        # Confidence formula:
        # - 10 runs: ~0.5
        # - 50 runs: ~0.75
        # - 100 runs: ~0.85
        # - 500 runs: ~0.95
        confidence = min(1.0, 0.3 + 0.15 * math.log10(min_runs))

        return round(confidence, 2)

    def get_long_term_impact_report(
        self,
        task_ids: List[str],
        since_dates: Dict[str, datetime],
        window_days: int = 30,
    ) -> Dict[str, RegressionPreventionReport]:
        """Generate long-term impact reports for multiple tasks.

        IMP-LOOP-033: Batch method to measure regression prevention for
        multiple tasks at once.

        Args:
            task_ids: List of task identifiers to measure.
            since_dates: Dictionary mapping task_id to completion date.
            window_days: Number of days for the comparison window.

        Returns:
            Dictionary mapping task_id to RegressionPreventionReport.
        """
        reports = {}

        for task_id in task_ids:
            if task_id not in since_dates:
                logger.warning(
                    "[IMP-LOOP-033] No completion date for task %s, skipping",
                    task_id,
                )
                continue

            reports[task_id] = self.measure_regression_prevention(
                task_id=task_id,
                since_date=since_dates[task_id],
                window_days=window_days,
            )

        logger.info(
            "[IMP-LOOP-033] Generated long-term impact reports for %d tasks",
            len(reports),
        )

        return reports
