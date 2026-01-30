"""
Analysis module for Autopack research.

Contains cost-effectiveness analysis, gap detection, and follow-up research triggers.
"""

from autopack.research.analysis.cost_effectiveness import (
    CostEffectivenessAnalyzer,
    ComponentCostData,
    ProjectCostProjection,
    CostCategory,
    ScalingModel,
)

from autopack.research.analysis.research_state import (
    ResearchStateTracker,
    ResearchState,
    ResearchGap,
    ResearchRequirements,
    GapType,
    GapPriority,
    ResearchDepth,
    CoverageMetrics,
)

from autopack.research.analysis.followup_trigger import (
    FollowupResearchTrigger,
    FollowupTrigger,
    TriggerType,
    TriggerPriority,
    TriggerAnalysisResult,
    ResearchPlan,
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
