"""Telemetry analysis and anomaly detection for ROAD components.

Provides:
- Automated analysis of PhaseOutcomeEvent telemetry (ROAD-B)
- Real-time anomaly detection (ROAD-G)
- Alert routing
"""

from autopack.telemetry.analyzer import TelemetryAnalyzer, RankedIssue
from autopack.telemetry.anomaly_detector import (
    TelemetryAnomalyDetector,
    AnomalyAlert,
    AlertSeverity,
)
from autopack.telemetry.alerts import AlertRouter

__all__ = [
    "TelemetryAnalyzer",
    "RankedIssue",
    "TelemetryAnomalyDetector",
    "AnomalyAlert",
    "AlertSeverity",
    "AlertRouter",
]
