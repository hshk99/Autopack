"""Telemetry analysis, anomaly detection, model optimization, and self-healing for ROAD components.

Provides:
- Automated analysis of PhaseOutcomeEvent telemetry (ROAD-B)
- Real-time anomaly detection (ROAD-G)
- Alert routing
- Self-healing engine (ROAD-J)
- Telemetry-driven model selection optimization (ROAD-L)
- Meta-metrics for feedback loop quality (ROAD-K)
"""

from autopack.telemetry.analyzer import TelemetryAnalyzer, RankedIssue
from autopack.telemetry.anomaly_detector import (
    TelemetryAnomalyDetector,
    AnomalyAlert,
    AlertSeverity,
)
from autopack.telemetry.alerts import AlertRouter
from autopack.telemetry.model_performance_tracker import (
    TelemetryDrivenModelOptimizer,
    ModelPerformance,
)
from autopack.telemetry.meta_metrics import (
    MetaMetricsTracker,
    FeedbackLoopHealth,
    ComponentStatus,
    MetricTrend,
    ComponentHealthReport,
    FeedbackLoopHealthReport,
)

# Try to import auto_healer if available (may not be on all branches)
try:
    from autopack.telemetry.auto_healer import AutoHealingEngine, HealingAction, HealingDecision

    __all__ = [
        "TelemetryAnalyzer",
        "RankedIssue",
        "TelemetryAnomalyDetector",
        "AnomalyAlert",
        "AlertSeverity",
        "AlertRouter",
        "AutoHealingEngine",
        "HealingAction",
        "HealingDecision",
        "TelemetryDrivenModelOptimizer",
        "ModelPerformance",
        "MetaMetricsTracker",
        "FeedbackLoopHealth",
        "ComponentStatus",
        "MetricTrend",
        "ComponentHealthReport",
        "FeedbackLoopHealthReport",
    ]
except ImportError:
    # auto_healer not available on this branch
    __all__ = [
        "TelemetryAnalyzer",
        "RankedIssue",
        "TelemetryAnomalyDetector",
        "AnomalyAlert",
        "AlertSeverity",
        "AlertRouter",
        "TelemetryDrivenModelOptimizer",
        "ModelPerformance",
        "MetaMetricsTracker",
        "FeedbackLoopHealth",
        "ComponentStatus",
        "MetricTrend",
        "ComponentHealthReport",
        "FeedbackLoopHealthReport",
    ]
