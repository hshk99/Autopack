"""Task Generation Module.

Provides data-driven task prioritization and autonomous improvement suggestion
capabilities for the Autopack self-improvement loop.

Components:
- PriorityEngine: Prioritizes tasks based on historical success data
- TaskEffectivenessTracker: Tracks task effectiveness for closed-loop validation
- TaskImpactReport: Report of actual task impact vs. target
- ROIAnalyzer: Calculates ROI and payback period for task prioritization
- PaybackAnalysis: Analysis of task ROI and payback period

Note: InsightToTaskGenerator has been removed (IMP-INT-010).
Use AutonomousTaskGenerator from autopack.roadc.task_generator instead.
"""

from __future__ import annotations

from .insight_correlation import (InsightCorrelationEngine,
                                  InsightEffectivenessStats,
                                  InsightTaskCorrelation)
from .priority_engine import PriorityEngine
from .roi_analyzer import PaybackAnalysis, ROIAnalyzer
from .task_effectiveness_tracker import (TaskEffectivenessTracker,
                                         TaskImpactReport)

__all__ = [
    "InsightCorrelationEngine",
    "InsightEffectivenessStats",
    "InsightTaskCorrelation",
    "PaybackAnalysis",
    "PriorityEngine",
    "ROIAnalyzer",
    "TaskEffectivenessTracker",
    "TaskImpactReport",
]
