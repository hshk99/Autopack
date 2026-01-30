"""
Analysis module for Autopack research.

Contains cost-effectiveness analysis, gap detection, and follow-up research triggers.
"""

from autopack.research.analysis.cost_effectiveness import (
    ComponentCostData,
    CostCategory,
    CostEffectivenessAnalyzer,
    ProjectCostProjection,
    ScalingModel,
)
from autopack.research.analysis.followup_trigger import (
    FollowupResearchTrigger,
    FollowupTrigger,
    ResearchPlan,
    TriggerAnalysisResult,
    TriggerPriority,
    TriggerType,
)
from autopack.research.analysis.research_state import (
    CoverageMetrics,
    GapPriority,
    GapType,
    ResearchDepth,
    ResearchGap,
    ResearchRequirements,
    ResearchState,
    ResearchStateTracker,
)

__all__ = [
    # Cost effectiveness
    "CostEffectivenessAnalyzer",
    "ComponentCostData",
    "ProjectCostProjection",
    "CostCategory",
    "ScalingModel",
    # Research state tracking
    "ResearchStateTracker",
    "ResearchState",
    "ResearchGap",
    "ResearchRequirements",
    "GapType",
    "GapPriority",
    "ResearchDepth",
    "CoverageMetrics",
    # Follow-up research triggers
    "FollowupResearchTrigger",
    "FollowupTrigger",
    "TriggerType",
    "TriggerPriority",
    "TriggerAnalysisResult",
    "ResearchPlan",
]
