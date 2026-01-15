"""Telemetry analysis, anomaly detection, model optimization, and self-healing for ROAD components.

Provides:
- Automated analysis of PhaseOutcomeEvent telemetry (ROAD-B)
- Real-time anomaly detection (ROAD-G)
- Alert routing
- Self-healing engine (ROAD-J)
- Telemetry-driven model selection optimization (ROAD-L)
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
]
