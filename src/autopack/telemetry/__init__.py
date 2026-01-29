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

from autopack.telemetry.alerts import AlertRouter
from autopack.telemetry.analyzer import RankedIssue, TelemetryAnalyzer
from autopack.telemetry.anomaly_detector import (
    AlertSeverity,
    AnomalyAlert,
    TelemetryAnomalyDetector,
)
from autopack.telemetry.auto_healer import (
    AutoHealingEngine,
    HealingAction,
    HealingDecision,
)
from autopack.telemetry.causal_analysis import (
    CausalAnalysisReport,
    CausalAnalyzer,
    CausalRelationship,
    CausalStrength,
    ChangeEvent,
    OutcomeMetric,
)
from autopack.telemetry.cost_aggregator import CostAggregation, CostAggregator
from autopack.telemetry.cost_tracker import ContextPrepCost, ContextPrepTracker
from autopack.telemetry.loop_metrics import (
    InsightSource,
    LoopEffectivenessMetrics,
    LoopMetricsCollector,
    TaskOutcome,
)
from autopack.telemetry.meta_metrics import (
    ComponentHealthReport,
    ComponentStatus,
    FeedbackLoopHealth,
    FeedbackLoopHealthReport,
    MetaMetricsTracker,
    MetricTrend,
)
from autopack.telemetry.model_performance_tracker import (
    ModelPerformance,
    TelemetryDrivenModelOptimizer,
)
from autopack.telemetry.regression_protector import (
    FixStabilityReport,
    IssueFix,
    IssueType,
    RegressionDetection,
    RegressionProtector,
    RegressionSeverity,
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
    "ContextPrepCost",
    "ContextPrepTracker",
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
    "CostAggregator",
    "CostAggregation",
    # IMP-OBS-001: Closed-loop observability metrics
    "LoopMetricsCollector",
    "LoopEffectivenessMetrics",
    "InsightSource",
    "TaskOutcome",
]
