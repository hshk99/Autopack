"""ROAD-K: Meta-metrics dashboard for self-improvement loop visibility.

Provides user-facing dashboard to monitor:
- Task generation rate (ROAD-C)
- Validation success rate (ROAD-E)
- Promotion rate (ROAD-F)
- Rollback rate
- Overall loop health score
"""

from autopack.roadk.dashboard_data import (
    LoopHealthMetrics,
    TrendPoint,
    DashboardDataProvider,
)
from autopack.roadk.meta_metrics_dashboard import MetaMetricsDashboard

__all__ = [
    "LoopHealthMetrics",
    "TrendPoint",
    "DashboardDataProvider",
    "MetaMetricsDashboard",
]
