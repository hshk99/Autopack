"""Aggregates costs by phase type and intent.

Enables cost analysis across multiple dimensions:
- by_phase_type(): aggregate by build/audit/test/tidy/doctor
- by_intent(): aggregate by feature/bugfix/refactor/docs
- generate_report(): comprehensive cost attribution report with insights
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..usage_recorder import LlmUsageEvent


@dataclass
class CostAggregation:
    """Cost aggregation for a category."""

    category: str
    category_value: str
    total_tokens: int
    total_cost_usd: float
    run_count: int
    avg_tokens_per_run: float
    avg_cost_per_run: float

    def __post_init__(self):
        """Validate aggregation data."""
        if self.run_count < 0:
            raise ValueError("run_count must be non-negative")
        if self.total_cost_usd < 0:
            raise ValueError("total_cost_usd must be non-negative")
        if self.total_tokens < 0:
            raise ValueError("total_tokens must be non-negative")


class CostAggregator:
    """Aggregates token costs by various dimensions (phase_type, intent).

    IMP-COST-005: Enable cost analysis by phase type (build/audit/test/tidy/doctor)
    and by intent (feature/bugfix/refactor/docs).
    """

    def __init__(self, session: Optional[Session] = None):
        """Initialize aggregator with optional session.

        Args:
            session: SQLAlchemy session; creates new one if not provided
        """
        self._session = session
        self._owns_session = session is None

    def by_phase_type(self, days: int = 30) -> List[CostAggregation]:
        """Aggregate costs by phase type (build, audit, test, tidy, doctor).

        Args:
            days: Number of days to look back (default: 30)

        Returns:
            List of CostAggregation objects grouped by phase_type
        """
        session = self._session or SessionLocal()
        try:
            # Calculate cutoff timestamp
            cutoff = datetime.utcnow() - timedelta(days=days)

            # Query aggregated by phase_type from LlmUsageEvent.phase_type
            results = (
                session.query(
                    LlmUsageEvent.phase_type,
                    func.sum(LlmUsageEvent.total_tokens).label("total_tokens"),
                    func.count(func.distinct(LlmUsageEvent.run_id)).label("run_count"),
                    func.count(LlmUsageEvent.id).label("event_count"),
                )
                .filter(LlmUsageEvent.created_at >= cutoff)
                .filter(LlmUsageEvent.phase_type.isnot(None))
                .group_by(LlmUsageEvent.phase_type)
                .all()
            )

            aggregations = []
            for phase_type, total_tokens, run_count, event_count in results:
                if total_tokens is None:
                    total_tokens = 0
                if run_count is None:
                    run_count = 0

                # Calculate cost: $0.003 per 1k tokens (approximate)
                total_cost_usd = (total_tokens / 1000.0) * 0.003
                avg_tokens_per_run = total_tokens / run_count if run_count > 0 else 0.0
                avg_cost_per_run = total_cost_usd / run_count if run_count > 0 else 0.0

                agg = CostAggregation(
                    category="phase_type",
                    category_value=phase_type or "unknown",
                    total_tokens=total_tokens,
                    total_cost_usd=round(total_cost_usd, 4),
                    run_count=run_count,
                    avg_tokens_per_run=round(avg_tokens_per_run, 2),
                    avg_cost_per_run=round(avg_cost_per_run, 6),
                )
                aggregations.append(agg)

            return aggregations
        finally:
            if self._owns_session:
                session.close()

    def by_intent(self, days: int = 30) -> List[CostAggregation]:
        """Aggregate costs by intent (feature, bugfix, refactor, docs).

        Args:
            days: Number of days to look back (default: 30)

        Returns:
            List of CostAggregation objects grouped by intent
        """
        session = self._session or SessionLocal()
        try:
            # Calculate cutoff timestamp
            cutoff = datetime.utcnow() - timedelta(days=days)

            # Query aggregated by intent from LlmUsageEvent.intent
            results = (
                session.query(
                    LlmUsageEvent.intent,
                    func.sum(LlmUsageEvent.total_tokens).label("total_tokens"),
                    func.count(func.distinct(LlmUsageEvent.run_id)).label("run_count"),
                    func.count(LlmUsageEvent.id).label("event_count"),
                )
                .filter(LlmUsageEvent.created_at >= cutoff)
                .filter(LlmUsageEvent.intent.isnot(None))
                .group_by(LlmUsageEvent.intent)
                .all()
            )

            aggregations = []
            for intent, total_tokens, run_count, event_count in results:
                if total_tokens is None:
                    total_tokens = 0
                if run_count is None:
                    run_count = 0

                # Calculate cost: $0.003 per 1k tokens (approximate)
                total_cost_usd = (total_tokens / 1000.0) * 0.003
                avg_tokens_per_run = total_tokens / run_count if run_count > 0 else 0.0
                avg_cost_per_run = total_cost_usd / run_count if run_count > 0 else 0.0

                agg = CostAggregation(
                    category="intent",
                    category_value=intent or "unknown",
                    total_tokens=total_tokens,
                    total_cost_usd=round(total_cost_usd, 4),
                    run_count=run_count,
                    avg_tokens_per_run=round(avg_tokens_per_run, 2),
                    avg_cost_per_run=round(avg_cost_per_run, 6),
                )
                aggregations.append(agg)

            return aggregations
        finally:
            if self._owns_session:
                session.close()

    def generate_report(self, days: int = 30) -> dict:
        """Generate comprehensive cost attribution report.

        Args:
            days: Number of days to include in report (default: 30)

        Returns:
            Dictionary with aggregations by phase_type and intent, plus insights
        """
        return {
            "period_days": days,
            "generated_at": datetime.utcnow().isoformat(),
            "by_phase_type": [a.__dict__ for a in self.by_phase_type(days)],
            "by_intent": [a.__dict__ for a in self.by_intent(days)],
            "insights": self._generate_insights(days),
        }

    def _generate_insights(self, days: int) -> List[str]:
        """Generate cost insights from aggregations.

        Args:
            days: Number of days for analysis period

        Returns:
            List of insight strings for cost optimization
        """
        insights = []

        # Analyze phase_type costs
        phase_costs = self.by_phase_type(days)
        if phase_costs:
            most_expensive = max(phase_costs, key=lambda x: x.avg_cost_per_run)
            insights.append(
                f"Most expensive phase type: {most_expensive.category_value} "
                f"(${most_expensive.avg_cost_per_run:.6f}/run, "
                f"{most_expensive.total_tokens:,} tokens total)"
            )

            total_phase_cost = sum(a.total_cost_usd for a in phase_costs)
            if total_phase_cost > 0:
                highest_volume = max(phase_costs, key=lambda x: x.total_tokens)
                volume_pct = (
                    highest_volume.total_tokens / sum(a.total_tokens for a in phase_costs)
                ) * 100
                insights.append(
                    f"Highest volume: {highest_volume.category_value} "
                    f"({volume_pct:.1f}% of tokens)"
                )

        # Analyze intent costs
        intent_costs = self.by_intent(days)
        if intent_costs:
            if len(intent_costs) > 1:
                sorted_by_cost = sorted(intent_costs, key=lambda x: x.total_cost_usd, reverse=True)
                insights.append(
                    f"Top intent by cost: {sorted_by_cost[0].category_value} "
                    f"(${sorted_by_cost[0].total_cost_usd:.4f})"
                )

        return insights
