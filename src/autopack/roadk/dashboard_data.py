"""Data models and queries for meta-metrics dashboard.

Provides data layer for the ROAD-K meta-metrics dashboard, integrating with
the existing telemetry infrastructure and MetaMetricsTracker.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..telemetry.meta_metrics import FeedbackLoopHealthReport, MetaMetricsTracker


@dataclass
class LoopHealthMetrics:
    """Health metrics for the self-improvement loop."""

    period_start: datetime
    period_end: datetime
    tasks_generated: int
    tasks_validated: int
    tasks_promoted: int
    tasks_rolled_back: int
    validation_success_rate: float
    promotion_rate: float
    rollback_rate: float
    avg_time_to_promotion_hours: float


@dataclass
class TrendPoint:
    """Single point in a trend line."""

    timestamp: datetime
    value: float


class DashboardDataProvider:
    """Provides data for the meta-metrics dashboard.

    Integrates with existing telemetry infrastructure to query metrics
    and leverage the MetaMetricsTracker for health analysis.
    """

    def __init__(
        self,
        meta_tracker: Optional[MetaMetricsTracker] = None,
        telemetry_data: Optional[Dict[str, Any]] = None,
        baseline_data: Optional[Dict[str, Any]] = None,
    ):
        """Initialize the data provider.

        Args:
            meta_tracker: Optional MetaMetricsTracker instance for health analysis
            telemetry_data: Optional telemetry data dict (for testing/injection)
            baseline_data: Optional baseline data dict (for testing/injection)
        """
        self._tracker = meta_tracker or MetaMetricsTracker()
        self._telemetry_data = telemetry_data
        self._baseline_data = baseline_data

    def get_loop_health(self, days: int = 30) -> LoopHealthMetrics:
        """Get loop health metrics for the specified period.

        Args:
            days: Number of days to include in the period

        Returns:
            LoopHealthMetrics with aggregated health data
        """
        end = datetime.utcnow()
        start = end - timedelta(days=days)

        # Get telemetry data (injected or from storage)
        telemetry = self._get_telemetry_data()

        # Extract task generation metrics (ROAD-C)
        road_c = telemetry.get("road_c", {})
        tasks_generated = road_c.get("total_tasks", 0)

        # Extract validation metrics (ROAD-E)
        road_e = telemetry.get("road_e", {})
        tasks_validated = road_e.get("valid_ab_tests", 0)
        total_ab_tests = road_e.get("total_ab_tests", 0)

        # Extract promotion/rollback metrics (ROAD-F)
        road_f = telemetry.get("road_f", {})
        total_promotions = road_f.get("total_promotions", 0)
        effective_promotions = road_f.get("effective_promotions", 0)
        rollbacks = road_f.get("rollbacks", 0)

        # Calculate rates
        validation_success_rate = tasks_validated / total_ab_tests if total_ab_tests > 0 else 0.0
        promotion_rate = effective_promotions / total_promotions if total_promotions > 0 else 0.0
        rollback_rate = rollbacks / total_promotions if total_promotions > 0 else 0.0

        # Estimate avg time to promotion (placeholder - would need timestamp data)
        avg_time_to_promotion = road_f.get("avg_promotion_time_hours", 0.0)

        return LoopHealthMetrics(
            period_start=start,
            period_end=end,
            tasks_generated=tasks_generated,
            tasks_validated=tasks_validated,
            tasks_promoted=effective_promotions,
            tasks_rolled_back=rollbacks,
            validation_success_rate=validation_success_rate,
            promotion_rate=promotion_rate,
            rollback_rate=rollback_rate,
            avg_time_to_promotion_hours=avg_time_to_promotion,
        )

    def get_generation_trend(self, days: int = 30) -> List[TrendPoint]:
        """Get task generation trend over time.

        Args:
            days: Number of days to include in the trend

        Returns:
            List of TrendPoint objects for daily task generation counts
        """
        telemetry = self._get_telemetry_data()
        trend_data = telemetry.get("generation_trend", [])

        # Convert raw trend data to TrendPoint objects
        trend_points = []
        for point in trend_data:
            if isinstance(point, dict):
                trend_points.append(
                    TrendPoint(
                        timestamp=(
                            datetime.fromisoformat(point["timestamp"])
                            if isinstance(point["timestamp"], str)
                            else point["timestamp"]
                        ),
                        value=float(point["value"]),
                    )
                )

        return trend_points

    def get_success_trend(self, days: int = 30) -> List[TrendPoint]:
        """Get validation success rate trend over time.

        Args:
            days: Number of days to include in the trend

        Returns:
            List of TrendPoint objects for daily validation success rates
        """
        telemetry = self._get_telemetry_data()
        trend_data = telemetry.get("success_trend", [])

        # Convert raw trend data to TrendPoint objects
        trend_points = []
        for point in trend_data:
            if isinstance(point, dict):
                trend_points.append(
                    TrendPoint(
                        timestamp=(
                            datetime.fromisoformat(point["timestamp"])
                            if isinstance(point["timestamp"], str)
                            else point["timestamp"]
                        ),
                        value=float(point["value"]),
                    )
                )

        return trend_points

    def get_full_health_report(
        self, telemetry_data: Optional[Dict[str, Any]] = None
    ) -> FeedbackLoopHealthReport:
        """Get comprehensive health report from MetaMetricsTracker.

        Args:
            telemetry_data: Optional telemetry data override

        Returns:
            FeedbackLoopHealthReport with detailed component analysis
        """
        data = telemetry_data or self._get_telemetry_data()
        baseline = self._baseline_data or {}
        return self._tracker.analyze_feedback_loop_health(data, baseline)

    def _get_telemetry_data(self) -> Dict[str, Any]:
        """Get telemetry data from injected source or storage.

        Returns:
            Dict containing telemetry data for all ROAD components
        """
        if self._telemetry_data is not None:
            return self._telemetry_data

        # Return empty structure when no data is available
        # In production, this would query the telemetry database
        return {
            "road_b": {},
            "road_c": {},
            "road_e": {},
            "road_f": {},
            "road_g": {},
            "road_j": {},
            "road_l": {},
            "generation_trend": [],
            "success_trend": [],
        }
