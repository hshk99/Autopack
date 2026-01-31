"""
Analysis module for Autopack research.

Contains cost-effectiveness analysis, gap detection, build vs buy analysis,
deployment analysis, and follow-up research triggers.
"""

from autopack.research.analysis.build_vs_buy_analyzer import (
    BuildVsBuyAnalysis,
    BuildVsBuyAnalyzer,
    ComponentRequirements,
    CostEstimate,
    DecisionRecommendation,
    RiskAssessment,
    RiskCategory,
    StrategicImportance,
    VendorOption,
)
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
from autopack.research.analysis.budget_enforcement import (
    BudgetEnforcer,
    BudgetMetrics,
    BudgetStatus,
    PhaseBudget,
    PhaseType,
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
from autopack.research.analysis.deployment_analysis import (
    ContainerConfig,
    DeploymentAnalyzer,
    DeploymentArchitecture,
    DeploymentRecommendation,
    DeploymentTarget,
    InfrastructureProvider,
    KubernetesConfig,
    ScalingStrategy,
    ServerlessConfig,
)

__all__ = [
    # Build vs Buy analysis
    "BuildVsBuyAnalyzer",
    "BuildVsBuyAnalysis",
    "ComponentRequirements",
    "VendorOption",
    "CostEstimate",
    "RiskAssessment",
    "DecisionRecommendation",
    "RiskCategory",
    "StrategicImportance",
    # Cost effectiveness
    "CostEffectivenessAnalyzer",
    "ComponentCostData",
    "ProjectCostProjection",
    "CostCategory",
    "ScalingModel",
    # Budget enforcement
    "BudgetEnforcer",
    "BudgetMetrics",
    "BudgetStatus",
    "PhaseBudget",
    "PhaseType",
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
    # Deployment analysis
    "DeploymentAnalyzer",
    "DeploymentArchitecture",
    "DeploymentRecommendation",
    "DeploymentTarget",
    "InfrastructureProvider",
    "ScalingStrategy",
    "ContainerConfig",
    "KubernetesConfig",
    "ServerlessConfig",
]
