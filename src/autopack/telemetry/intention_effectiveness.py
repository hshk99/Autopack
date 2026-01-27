"""Measures intention effectiveness through outcome correlation."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..database import SessionLocal
from ..usage_recorder import Phase6Metrics


@dataclass
class IntentionOutcome:
    """Records outcome of a run with/without intentions."""

    run_id: str
    phase_id: str
    had_intentions: bool
    intention_source: Optional[str]
    intention_chars: int
    goal_drift_score: float  # 0.0 = no drift, 1.0 = complete drift
    success: bool
    completion_time_sec: float
    error_count: int
    retry_count: int


class IntentionEffectivenessTracker:
    """Tracks and analyzes intention effectiveness."""

    def __init__(self, session=None):
        self._session = session

    def record_outcome(self, outcome: IntentionOutcome) -> None:
        """Record a phase outcome for intention effectiveness analysis.

        Args:
            outcome: IntentionOutcome with phase metrics
        """
        session = self._session or SessionLocal()
        try:
            # Record outcome in Phase6Metrics table
            from ..usage_recorder import record_phase6_metrics

            record_phase6_metrics(
                db=session,
                run_id=outcome.run_id,
                phase_id=outcome.phase_id,
                intention_context_injected=outcome.had_intentions,
                intention_context_chars=outcome.intention_chars,
                intention_context_source=outcome.intention_source,
                phase_success=outcome.success,
                goal_drift_score=outcome.goal_drift_score,
                completion_time_sec=outcome.completion_time_sec,
                error_count=outcome.error_count,
                retry_count=outcome.retry_count,
            )
        finally:
            if not self._session:
                session.close()

    def get_effectiveness_report(self, days: int = 30) -> dict:
        """Generate effectiveness report comparing with/without intentions.

        Args:
            days: Number of days to look back (default 30)

        Returns:
            Report with effectiveness metrics for runs with vs without intentions
        """
        session = self._session or SessionLocal()
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

            # Query metrics with intentions
            with_intentions = (
                session.query(Phase6Metrics)
                .filter(
                    Phase6Metrics.intention_context_injected.is_(True),
                    Phase6Metrics.created_at >= cutoff_date,
                    Phase6Metrics.phase_success.isnot(None),
                )
                .all()
            )

            # Query metrics without intentions
            without_intentions = (
                session.query(Phase6Metrics)
                .filter(
                    Phase6Metrics.intention_context_injected.is_(False),
                    Phase6Metrics.created_at >= cutoff_date,
                    Phase6Metrics.phase_success.isnot(None),
                )
                .all()
            )

            def compute_stats(metrics):
                """Compute statistics from metrics list."""
                if not metrics:
                    return {
                        "run_count": 0,
                        "success_rate": 0.0,
                        "avg_goal_drift": 0.0,
                        "avg_completion_time": 0.0,
                        "avg_error_count": 0.0,
                    }

                successful = sum(1 for m in metrics if m.phase_success)
                success_rate = successful / len(metrics) if metrics else 0.0

                # Filter out None values for averages
                valid_drift = [
                    m.goal_drift_score for m in metrics if m.goal_drift_score is not None
                ]
                avg_drift = sum(valid_drift) / len(valid_drift) if valid_drift else 0.0

                valid_time = [
                    m.completion_time_sec for m in metrics if m.completion_time_sec is not None
                ]
                avg_time = sum(valid_time) / len(valid_time) if valid_time else 0.0

                valid_errors = [m.error_count for m in metrics if m.error_count is not None]
                avg_errors = sum(valid_errors) / len(valid_errors) if valid_errors else 0.0

                return {
                    "run_count": len(metrics),
                    "success_rate": success_rate,
                    "avg_goal_drift": avg_drift,
                    "avg_completion_time": avg_time,
                    "avg_error_count": avg_errors,
                }

            with_stats = compute_stats(with_intentions)
            without_stats = compute_stats(without_intentions)

            # Calculate deltas
            success_improvement = (
                (with_stats["success_rate"] - without_stats["success_rate"])
                if without_stats["success_rate"] > 0
                else 0.0
            )
            drift_reduction = without_stats["avg_goal_drift"] - with_stats["avg_goal_drift"]
            time_reduction_pct = (
                (
                    (without_stats["avg_completion_time"] - with_stats["avg_completion_time"])
                    / without_stats["avg_completion_time"]
                    * 100
                )
                if without_stats["avg_completion_time"] > 0
                else 0.0
            )

            return {
                "period_days": days,
                "with_intentions": with_stats,
                "without_intentions": without_stats,
                "effectiveness_delta": {
                    "success_rate_improvement": success_improvement,
                    "goal_drift_reduction": drift_reduction,
                    "time_reduction_pct": time_reduction_pct,
                },
            }
        finally:
            if not self._session:
                session.close()

    def calculate_goal_drift(self, initial_goal: str, final_output: str) -> float:
        """Calculate goal drift score between initial goal and final output."""
        # Simple implementation - could use embeddings for better accuracy
        if not initial_goal or not final_output:
            return 1.0

        # Basic keyword overlap
        initial_words = set(initial_goal.lower().split())
        final_words = set(final_output.lower().split())

        if not initial_words:
            return 1.0

        overlap = len(initial_words & final_words)
        return 1.0 - (overlap / len(initial_words))
