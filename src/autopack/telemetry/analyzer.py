"""Automated telemetry analysis for issue prioritization."""

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


class TelemetryAnalyzer:
    """Analyze telemetry data and generate ranked issues."""

    def __init__(self, db_session: Session):
        self.db = db_session

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

        return {
            "top_cost_sinks": self._find_cost_sinks(cutoff),
            "top_failure_modes": self._find_failure_modes(cutoff),
            "top_retry_causes": self._find_retry_causes(cutoff),
            "phase_type_stats": self._compute_phase_type_stats(cutoff),  # For ROAD-L
        }

    def _find_cost_sinks(self, cutoff: datetime) -> List[RankedIssue]:
        """Find phases consuming the most tokens.

        Args:
            cutoff: Only analyze events after this timestamp

        Returns:
            List of RankedIssue objects for top 10 cost sinks
        """
        result = self.db.execute(
            text(
                """
            SELECT phase_id, phase_type, SUM(tokens_used) as total_tokens,
                   AVG(tokens_used) as avg_tokens, COUNT(*) as count
            FROM phase_outcome_events
            WHERE timestamp >= :cutoff AND tokens_used IS NOT NULL
            GROUP BY phase_id, phase_type
            ORDER BY total_tokens DESC
            LIMIT 10
        """
            ),
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
            text(
                """
            SELECT phase_id, phase_type, phase_outcome, stop_reason,
                   COUNT(*) as count
            FROM phase_outcome_events
            WHERE timestamp >= :cutoff AND phase_outcome != 'SUCCESS'
            GROUP BY phase_id, phase_type, phase_outcome, stop_reason
            ORDER BY count DESC
            LIMIT 10
        """
            ),
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
            text(
                """
            SELECT phase_id, phase_type, stop_reason,
                   COUNT(*) as retry_count,
                   SUM(CASE WHEN phase_outcome = 'SUCCESS' THEN 1 ELSE 0 END) as success_count
            FROM phase_outcome_events
            WHERE timestamp >= :cutoff
            GROUP BY phase_id, phase_type, stop_reason
            HAVING COUNT(*) > 1
            ORDER BY retry_count DESC
            LIMIT 10
        """
            ),
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
            text(
                """
            SELECT phase_type, model_used,
                   COUNT(*) as total,
                   SUM(CASE WHEN phase_outcome = 'SUCCESS' THEN 1 ELSE 0 END) as successes,
                   AVG(tokens_used) as avg_tokens
            FROM phase_outcome_events
            WHERE timestamp >= :cutoff AND phase_type IS NOT NULL
            GROUP BY phase_type, model_used
        """
            ),
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
