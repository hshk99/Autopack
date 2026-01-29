"""Task Generation Module.

Provides data-driven task prioritization and autonomous improvement suggestion
capabilities for the Autopack self-improvement loop.

Components:
- PriorityEngine: Prioritizes tasks based on historical success data
- InsightToTaskGenerator: **DEPRECATED** - Use AutonomousTaskGenerator from
  autopack.roadc.task_generator instead. Kept for backward compatibility.
- TaskEffectivenessTracker: Tracks task effectiveness for closed-loop validation
- TaskImpactReport: Report of actual task impact vs. target
- ROIAnalyzer: Calculates ROI and payback period for task prioritization
- PaybackAnalysis: Analysis of task ROI and payback period

Migration Guide (IMP-INT-006):
    Replace::

        from autopack.task_generation import InsightToTaskGenerator
        generator = InsightToTaskGenerator(analyzer)

    With::

        from autopack.roadc.task_generator import AutonomousTaskGenerator
        generator = AutonomousTaskGenerator(db_session=session)
"""

from __future__ import annotations

import warnings

from .insight_correlation import (
    InsightCorrelationEngine,
    InsightEffectivenessStats,
    InsightTaskCorrelation,
)
from .priority_engine import PriorityEngine
from .roi_analyzer import PaybackAnalysis, ROIAnalyzer
from .task_effectiveness_tracker import TaskEffectivenessTracker, TaskImpactReport


def __getattr__(name: str):
    """Lazy import with deprecation warning for InsightToTaskGenerator."""
    if name == "InsightToTaskGenerator":
        warnings.warn(
            "InsightToTaskGenerator is deprecated. "
            "Use AutonomousTaskGenerator from autopack.roadc.task_generator instead. "
            "See IMP-INT-006 for migration details.",
            DeprecationWarning,
            stacklevel=2,
        )
        from autopack.task_generation.insight_to_task import InsightToTaskGenerator

        return InsightToTaskGenerator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "InsightCorrelationEngine",
    "InsightEffectivenessStats",
    "InsightTaskCorrelation",
    "InsightToTaskGenerator",
    "PaybackAnalysis",
    "PriorityEngine",
    "ROIAnalyzer",
    "TaskEffectivenessTracker",
    "TaskImpactReport",
]
