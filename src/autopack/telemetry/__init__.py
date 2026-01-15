"""Telemetry analysis, anomaly detection, model optimization, and causal analysis for ROAD components.

Provides:
- Automated analysis of PhaseOutcomeEvent telemetry (ROAD-B)
- Real-time anomaly detection (ROAD-G)
- Alert routing
- Telemetry-driven model selection optimization (ROAD-L)
- Causal analysis for change impact assessment (ROAD-H)
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
from autopack.telemetry.causal_analysis import (
    CausalAnalyzer,
    CausalStrength,
    ChangeEvent,
    OutcomeMetric,
    CausalRelationship,
    CausalAnalysisReport,
)

__all__ = [
    "TelemetryAnalyzer",
    "RankedIssue",
    "TelemetryAnomalyDetector",
    "AnomalyAlert",
    "AlertSeverity",
    "AlertRouter",
    "TelemetryDrivenModelOptimizer",
    "ModelPerformance",
    "CausalAnalyzer",
    "CausalStrength",
    "ChangeEvent",
    "OutcomeMetric",
    "CausalRelationship",
    "CausalAnalysisReport",
]
