"""Telemetry analysis, anomaly detection, model optimization, self-healing, and causal analysis for ROAD components.

Provides:
- Automated analysis of PhaseOutcomeEvent telemetry (ROAD-B)
- Real-time anomaly detection (ROAD-G)
- Alert routing
- Self-healing engine (ROAD-J)
- Telemetry-driven model selection optimization (ROAD-L)
- Meta-metrics for feedback loop quality (ROAD-K)
- Causal analysis for change impact assessment (ROAD-H)
- Regression protection to prevent fixed issues from reoccurring (ROAD-I)
"""

from autopack.telemetry.analyzer import TelemetryAnalyzer, RankedIssue
from autopack.telemetry.anomaly_detector import (
    TelemetryAnomalyDetector,
    AnomalyAlert,
    AlertSeverity,
)
from autopack.telemetry.alerts import AlertRouter
from autopack.telemetry.auto_healer import AutoHealingEngine, HealingAction, HealingDecision
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
from autopack.telemetry.causal_analysis import (
    CausalAnalyzer,
    CausalStrength,
    ChangeEvent,
    OutcomeMetric,
    CausalRelationship,
    CausalAnalysisReport,
)
from autopack.telemetry.regression_protector import (
    RegressionProtector,
    IssueFix,
    IssueType,
    RegressionSeverity,
    RegressionDetection,
    FixStabilityReport,
)

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
    "CausalAnalyzer",
    "CausalStrength",
    "ChangeEvent",
    "OutcomeMetric",
    "CausalRelationship",
    "CausalAnalysisReport",
    "RegressionProtector",
    "IssueFix",
    "IssueType",
    "RegressionSeverity",
    "RegressionDetection",
    "FixStabilityReport",
]
