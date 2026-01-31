"""
Autopack Research Module.

Provides comprehensive research capabilities including:
- Market research and competitive analysis
- Technical feasibility assessment
- Cost-effectiveness analysis
- Incremental research with state tracking
- Automated follow-up research triggers
"""

# Analysis submodule exports
from autopack.research.analysis import (  # Cost effectiveness; Research state tracking; Follow-up research triggers
    ComponentCostData, CostCategory, CostEffectivenessAnalyzer,
    CoverageMetrics, FollowupResearchTrigger, FollowupTrigger, GapPriority,
    GapType, ProjectCostProjection, ResearchDepth, ResearchGap, ResearchPlan,
    ResearchRequirements, ResearchState, ResearchStateTracker, ScalingModel,
    TriggerAnalysisResult, TriggerPriority, TriggerType)
from autopack.research.idea_parser import IdeaParser, ParsedIdea
from autopack.research.orchestrator import ResearchCache, ResearchOrchestrator
from autopack.research.sot_summarizer import (ArchitectureDecision, BuildEntry,
                                              SOTSummarizer, SOTSummary,
                                              get_sot_summarizer,
                                              summarize_sot_documents)

__all__ = [
    # Main orchestration
    "ResearchOrchestrator",
    "ResearchCache",
    "IdeaParser",
    "ParsedIdea",
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
    # SOT document summarization
    "SOTSummarizer",
    "SOTSummary",
    "BuildEntry",
    "ArchitectureDecision",
    "get_sot_summarizer",
    "summarize_sot_documents",
]
