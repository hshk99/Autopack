"""Telemetry analysis and aggregation for ROAD-B.

Provides automated analysis of PhaseOutcomeEvent telemetry to identify:
- Top cost sinks (phases consuming the most tokens)
- Top failure modes (most common failure patterns)
- Top retry causes (phases that retry most frequently)
- Phase type statistics (for ROAD-L model optimization)
"""

from autopack.telemetry.analyzer import TelemetryAnalyzer, RankedIssue

__all__ = ["TelemetryAnalyzer", "RankedIssue"]
