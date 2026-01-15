"""Telemetry-driven model selection optimizer.

Tracks model performance by phase type and adjusts routing:
- Downgrade to cheaper model when success rate is stable (>95%)
- Escalate to expensive model when failure rate increases
- Maintain minimum sample count before auto-adjusting
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


@dataclass
class ModelPerformance:
    """Performance metrics for a model on a phase type."""

    model_id: str
    phase_type: str
    success_rate: float
    avg_tokens: float
    avg_duration: float
    sample_count: int
    last_updated: datetime


class TelemetryDrivenModelOptimizer:
    """Optimizes model selection based on historical performance."""

    # Model cost tiers (relative cost, lower = cheaper)
    MODEL_COST_TIERS = {
        "claude-3-haiku": 1,
        "claude-3-5-haiku": 1,
        "gemini-1.5-flash": 1,
        "claude-3-5-sonnet": 3,
        "gemini-1.5-pro": 3,
        "claude-3-opus": 10,
        "claude-opus-4": 10,
    }

    def __init__(
        self,
        db_session: Session,
        min_samples: int = 20,
        downgrade_success_threshold: float = 0.95,
        escalation_failure_threshold: float = 0.15,
        lookback_days: int = 7,
    ):
        self.db = db_session
        self.min_samples = min_samples
        self.downgrade_success_threshold = downgrade_success_threshold
        self.escalation_failure_threshold = escalation_failure_threshold
        self.lookback_days = lookback_days

        # Cache of performance stats
        self._performance_cache: Dict[str, ModelPerformance] = {}
        self._cache_timestamp: Optional[datetime] = None

    def get_performance_stats(self, phase_type: str) -> Dict[str, ModelPerformance]:
        """Query telemetry for model performance by phase type."""
        self._refresh_cache_if_needed()

        return {k: v for k, v in self._performance_cache.items() if v.phase_type == phase_type}

    def _refresh_cache_if_needed(self) -> None:
        """Refresh cache if stale (>5 min old)."""
        if (
            self._cache_timestamp
            and (datetime.now(timezone.utc) - self._cache_timestamp).seconds < 300
        ):
            return

        cutoff = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)

        result = self.db.execute(
            text(
                """
            SELECT phase_type, model_used,
                   COUNT(*) as total,
                   SUM(CASE WHEN phase_outcome = 'SUCCESS' THEN 1 ELSE 0 END) as successes,
                   AVG(tokens_used) as avg_tokens,
                   AVG(duration_seconds) as avg_duration,
                   MAX(timestamp) as last_updated
            FROM phase_outcome_events
            WHERE timestamp >= :cutoff
              AND phase_type IS NOT NULL
              AND model_used IS NOT NULL
            GROUP BY phase_type, model_used
        """
            ),
            {"cutoff": cutoff},
        )

        self._performance_cache = {}
        for row in result:
            key = f"{row.phase_type}:{row.model_used}"
            self._performance_cache[key] = ModelPerformance(
                model_id=row.model_used,
                phase_type=row.phase_type,
                success_rate=row.successes / row.total if row.total > 0 else 0,
                avg_tokens=row.avg_tokens or 0,
                avg_duration=row.avg_duration or 0,
                sample_count=row.total,
                last_updated=row.last_updated,
            )

        self._cache_timestamp = datetime.now(timezone.utc)

    def suggest_model(
        self, phase_type: str, current_model: str, complexity: str = "medium"
    ) -> Tuple[str, Optional[str]]:
        """
        Suggest optimal model based on telemetry.

        Returns:
            Tuple of (suggested_model, reason) where reason is None if no change.
        """
        stats = self.get_performance_stats(phase_type)
        current_key = f"{phase_type}:{current_model}"

        # Not enough data - use current model
        current_stats = stats.get(current_key)
        if not current_stats or current_stats.sample_count < self.min_samples:
            return current_model, None

        # Check if we should escalate (high failure rate)
        if current_stats.success_rate < (1 - self.escalation_failure_threshold):
            better_model = self._find_better_model(phase_type, current_model, stats)
            if better_model:
                return (
                    better_model,
                    f"Escalating: {current_model} success rate {current_stats.success_rate:.1%} below threshold",
                )

        # Check if we can downgrade (high success rate with cheaper model available)
        if current_stats.success_rate >= self.downgrade_success_threshold:
            cheaper_model = self._find_cheaper_model(phase_type, current_model, stats)
            if cheaper_model:
                return (
                    cheaper_model,
                    f"Downgrading: {current_model} success rate {current_stats.success_rate:.1%} allows cheaper model",
                )

        return current_model, None

    def _find_better_model(
        self, phase_type: str, current_model: str, stats: Dict[str, ModelPerformance]
    ) -> Optional[str]:
        """Find a more capable model for this phase type."""
        current_tier = self.MODEL_COST_TIERS.get(current_model, 5)

        for key, perf in stats.items():
            if perf.phase_type != phase_type:
                continue
            model_tier = self.MODEL_COST_TIERS.get(perf.model_id, 5)

            # Higher tier model with good success rate
            if (
                model_tier > current_tier
                and perf.success_rate > 0.9
                and perf.sample_count >= self.min_samples
            ):
                return perf.model_id

        return None

    def _find_cheaper_model(
        self, phase_type: str, current_model: str, stats: Dict[str, ModelPerformance]
    ) -> Optional[str]:
        """Find a cheaper model that still has high success rate."""
        current_tier = self.MODEL_COST_TIERS.get(current_model, 5)

        candidates = []
        for key, perf in stats.items():
            if perf.phase_type != phase_type:
                continue
            model_tier = self.MODEL_COST_TIERS.get(perf.model_id, 5)

            # Cheaper model with sufficient success rate
            if (
                model_tier < current_tier
                and perf.success_rate >= self.downgrade_success_threshold
                and perf.sample_count >= self.min_samples
            ):
                candidates.append((perf.model_id, model_tier, perf.success_rate))

        if candidates:
            # Pick cheapest among candidates
            candidates.sort(key=lambda x: (x[1], -x[2]))
            return candidates[0][0]

        return None
