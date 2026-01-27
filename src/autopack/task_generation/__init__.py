"""Task Generation Module.

Provides data-driven task prioritization and autonomous improvement suggestion
capabilities for the Autopack self-improvement loop.

Components:
- PriorityEngine: Prioritizes tasks based on historical success data
- InsightToTaskGenerator: Generates improvement suggestions from telemetry insights
- TaskEffectivenessTracker: Tracks task effectiveness for closed-loop validation
- TaskImpactReport: Report of actual task impact vs. target
- ROIAnalyzer: Calculates ROI and payback period for task prioritization
- PaybackAnalysis: Analysis of task ROI and payback period
"""

from __future__ import annotations

from autopack.task_generation.insight_to_task import InsightToTaskGenerator

from .priority_engine import PriorityEngine
from .roi_analyzer import PaybackAnalysis, ROIAnalyzer
from .task_effectiveness_tracker import TaskEffectivenessTracker, TaskImpactReport

__all__ = [
    "InsightToTaskGenerator",
    "PaybackAnalysis",
    "PriorityEngine",
    "ROIAnalyzer",
    "TaskEffectivenessTracker",
    "TaskImpactReport",
]
