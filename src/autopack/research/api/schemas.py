from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResearchSession(BaseModel):
    """Research session response model."""

    session_id: str
    status: str
    created_at: str
    topic: str
    description: str


class CreateResearchSession(BaseModel):
    """Request model for creating a research session."""

    topic: str = Field(..., min_length=1, max_length=200, description="Research topic")
    description: str = Field(..., min_length=1, max_length=2000, description="Research description")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"topic": "AI Research", "description": "Exploring new AI techniques"}
        }
    )


class UpdateResearchSession(BaseModel):
    """Request model for updating a research session."""

    status: str = Field(..., min_length=1, description="New session status")

    model_config = ConfigDict(json_schema_extra={"example": {"status": "completed"}})


# =============================================================================
# Confidence Report Schemas (IMP-SCHEMA-013)
# =============================================================================


class ConfidenceMetric(BaseModel):
    """Individual confidence metric for a pivot type."""

    score: float = Field(
        ...,
        ge=0,
        le=100,
        description="Confidence score on a 0-100 scale",
    )
    reasoning: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Explanation of the confidence score",
    )

    @field_validator("score")
    @classmethod
    def validate_score_range(cls, v: float) -> float:
        """Validate that score is between 0 and 100.

        Args:
            v: The score value to validate

        Returns:
            The validated score

        Raises:
            ValueError: If score is outside 0-100 range
        """
        if not (0 <= v <= 100):
            raise ValueError(f"Confidence score must be between 0 and 100, got {v}")
        return v

    @field_validator("reasoning")
    @classmethod
    def validate_reasoning(cls, v: str) -> str:
        """Validate that reasoning is not empty or whitespace only.

        Args:
            v: The reasoning string to validate

        Returns:
            The validated reasoning

        Raises:
            ValueError: If reasoning is empty or whitespace only
        """
        if not v or not v.strip():
            raise ValueError("Confidence reasoning cannot be empty or whitespace only")
        return v.strip()


class ConfidenceReport(BaseModel):
    """Confidence report for bootstrap response with per-pivot-type scores."""

    market_research: Optional[ConfidenceMetric] = Field(
        default=None, description="Confidence in market research findings"
    )
    competitive_analysis: Optional[ConfidenceMetric] = Field(
        default=None, description="Confidence in competitive analysis findings"
    )
    technical_feasibility: Optional[ConfidenceMetric] = Field(
        default=None, description="Confidence in technical feasibility assessment"
    )
    overall_confidence: Optional[float] = Field(
        default=None,
        ge=0,
        le=100,
        description="Overall confidence score across all research",
    )

    @field_validator("overall_confidence")
    @classmethod
    def validate_overall_confidence(cls, v: Optional[float]) -> Optional[float]:
        """Validate overall confidence score.

        Args:
            v: The overall confidence score

        Returns:
            The validated score or None

        Raises:
            ValueError: If overall_confidence is outside 0-100 range
        """
        if v is not None and not (0 <= v <= 100):
            raise ValueError(f"Overall confidence score must be between 0 and 100, got {v}")
        return v

    def validate_consistency(self) -> List[str]:
        """Validate that confidence metrics are internally consistent.

        Returns:
            List of consistency warnings (empty if all consistent)
        """
        warnings = []

        # Check if we have any metrics at all
        metrics = [
            self.market_research,
            self.competitive_analysis,
            self.technical_feasibility,
        ]
        populated_metrics = [m for m in metrics if m is not None]

        if not populated_metrics:
            warnings.append(
                "No individual confidence metrics provided. At least one should be specified."
            )
            return warnings

        # Check if overall_confidence is consistent with individual metrics
        if self.overall_confidence is not None and populated_metrics:
            # Overall confidence should be within reasonable range of individual scores
            scores = [m.score for m in populated_metrics]
            min_score = min(scores)
            max_score = max(scores)
            avg_score = sum(scores) / len(scores)

            # Overall confidence should be between min and max, or close to average
            if not (min_score - 5 <= self.overall_confidence <= max_score + 5):
                warnings.append(
                    f"Overall confidence ({self.overall_confidence}) is inconsistent with "
                    f"individual metrics (min={min_score}, max={max_score}, avg={avg_score:.1f}). "
                    f"Overall confidence should be between min and max with small tolerance."
                )

        # Check for extreme disparities between individual metrics
        if len(populated_metrics) > 1:
            scores = [m.score for m in populated_metrics]
            score_spread = max(scores) - min(scores)

            if score_spread > 50:
                warnings.append(
                    f"Large disparity between confidence metrics (spread={score_spread}). "
                    f"Consider reviewing research findings for inconsistencies."
                )

        return warnings


# =============================================================================
# Analysis Results Schemas
# =============================================================================


class CostEffectivenessSummary(BaseModel):
    """Executive summary of cost effectiveness analysis."""

    total_year_1_cost: float = Field(..., description="Total cost projection for year 1")
    total_year_3_cost: float = Field(..., description="Total cost projection for year 3")
    total_year_5_cost: float = Field(..., description="Total cost projection for year 5")
    primary_cost_drivers: List[str] = Field(
        default_factory=list, description="Primary cost driver categories"
    )
    key_recommendations: List[str] = Field(
        default_factory=list, description="Key recommendations for cost optimization"
    )
    cost_confidence: str = Field(..., description="Confidence level of cost estimates")


class ComponentCostDecision(BaseModel):
    """Build vs buy decision for a single component."""

    component: str = Field(..., description="Component name")
    decision: str = Field(..., description="Decision: build, buy, integrate, or outsource")
    service: str = Field(..., description="Service or vendor name if applicable")
    year_1_cost: float = Field(..., description="Year 1 cost projection")
    year_5_cost: float = Field(..., description="Year 5 cost projection")
    vs_build_savings: float = Field(..., description="Savings vs building in-house")
    rationale: str = Field(..., description="Reasoning for the decision")


class AITokenProjection(BaseModel):
    """AI/LLM token cost projection."""

    year_1: Dict[str, Any] = Field(..., description="Year 1 projections")
    year_3: Dict[str, Any] = Field(..., description="Year 3 projections")
    year_5: Dict[str, Any] = Field(..., description="Year 5 projections")
    optimization_potential: Optional[Dict[str, Any]] = Field(
        default=None, description="Optimization opportunities"
    )


class CostEffectivenessResponse(BaseModel):
    """Complete cost effectiveness analysis response."""

    session_id: str = Field(..., description="Research session ID")
    executive_summary: CostEffectivenessSummary = Field(..., description="Executive summary")
    component_analysis: List[ComponentCostDecision] = Field(
        default_factory=list, description="Component-level cost decisions"
    )
    ai_token_projection: Optional[AITokenProjection] = Field(
        default=None, description="AI token cost projections"
    )
    infrastructure_projection: Optional[Dict[str, Any]] = Field(
        default=None, description="Infrastructure cost projections"
    )
    development_costs: Optional[Dict[str, Any]] = Field(
        default=None, description="Development cost breakdown"
    )
    total_cost_of_ownership: Optional[Dict[str, Any]] = Field(
        default=None, description="Total cost of ownership analysis"
    )
    cost_optimization_roadmap: List[Dict[str, Any]] = Field(
        default_factory=list, description="Cost optimization strategies"
    )
    risk_adjusted_costs: Optional[Dict[str, Any]] = Field(
        default=None, description="Risk-adjusted cost estimates"
    )
    break_even_analysis: Optional[Dict[str, Any]] = Field(
        default=None, description="Break-even point analysis"
    )
    vendor_lock_in_assessment: List[Dict[str, Any]] = Field(
        default_factory=list, description="Vendor lock-in risk assessment"
    )
    generated_at: str = Field(..., description="ISO timestamp of analysis generation")


class BuildVsBuyDecision(BaseModel):
    """Build vs buy analysis for a component."""

    component: str = Field(..., description="Component name")
    recommendation: str = Field(..., description="Recommendation: BUILD, BUY, or HYBRID")
    confidence: float = Field(..., description="Confidence score (0-1)")
    build_cost: Dict[str, Any] = Field(..., description="Build cost estimate")
    buy_cost: Dict[str, Any] = Field(..., description="Buy cost estimate")
    build_time_weeks: float = Field(..., description="Estimated build time in weeks")
    buy_integration_time_weeks: float = Field(..., description="Integration time in weeks")
    risks: List[Dict[str, Any]] = Field(default_factory=list, description="Risk assessment")
    rationale: str = Field(..., description="Reasoning for the recommendation")
    strategic_importance: str = Field(
        ..., description="Strategic importance: core_differentiator, supporting, or commodity"
    )
    key_factors: List[str] = Field(default_factory=list, description="Key decision factors")


class BuildVsBuyAnalysisResponse(BaseModel):
    """Complete build vs buy analysis response."""

    session_id: str = Field(..., description="Research session ID")
    decisions: List[BuildVsBuyDecision] = Field(
        default_factory=list, description="Component-level decisions"
    )
    overall_recommendation: str = Field(
        default="HYBRID", description="Overall recommendation across components"
    )
    total_build_cost: Optional[float] = Field(default=None, description="Total build cost")
    total_buy_cost: Optional[float] = Field(default=None, description="Total buy cost")
    generated_at: str = Field(..., description="ISO timestamp of analysis generation")


class ResearchGap(BaseModel):
    """Identified research gap or uncertainty."""

    gap_id: str = Field(..., description="Unique gap identifier")
    gap_type: str = Field(
        ..., description="Gap type: coverage, entity, depth, recency, or validation"
    )
    category: str = Field(..., description="Category of the gap")
    description: str = Field(..., description="Description of the gap")
    priority: str = Field(..., description="Priority: critical, high, medium, or low")
    suggested_queries: List[str] = Field(
        default_factory=list, description="Suggested research queries"
    )
    identified_at: str = Field(..., description="ISO timestamp when gap was identified")
    addressed_at: Optional[str] = Field(
        default=None, description="ISO timestamp when gap was addressed"
    )
    status: str = Field(..., description="Current status of the gap")


class FollowupTrigger(BaseModel):
    """Individual followup research trigger."""

    trigger_id: str = Field(..., description="Unique trigger identifier")
    trigger_type: str = Field(
        ..., description="Trigger type: uncertainty, gap, depth, validation, or emerging"
    )
    priority: str = Field(..., description="Priority: critical, high, medium, or low")
    reason: str = Field(..., description="Reason for the trigger")
    source_finding: str = Field(..., description="Source finding that triggered this")
    research_plan: Optional[Dict[str, Any]] = Field(
        default=None, description="Plan for follow-up research"
    )
    created_at: str = Field(..., description="ISO timestamp when trigger was created")
    addressed: bool = Field(default=False, description="Whether this trigger has been addressed")
    callback_results: List[Dict[str, Any]] = Field(
        default_factory=list, description="Results from callback execution"
    )


class FollowupTriggerResponse(BaseModel):
    """Complete followup trigger analysis response."""

    session_id: str = Field(..., description="Research session ID")
    triggers: List[FollowupTrigger] = Field(
        default_factory=list, description="Identified research triggers"
    )
    should_research: bool = Field(..., description="Whether follow-up research is recommended")
    triggers_selected: int = Field(..., description="Number of triggers selected")
    total_estimated_time: int = Field(..., description="Total estimated research time in minutes")
    generated_at: str = Field(..., description="ISO timestamp of analysis generation")


class ResearchStateResponse(BaseModel):
    """Research state and gaps summary response."""

    session_id: str = Field(..., description="Research session ID")
    gaps: List[ResearchGap] = Field(default_factory=list, description="Identified research gaps")
    gap_count: int = Field(..., description="Total number of gaps identified")
    critical_gaps: int = Field(..., description="Number of critical priority gaps")
    coverage_metrics: Dict[str, Any] = Field(
        default_factory=dict, description="Research coverage metrics"
    )
    completed_queries: int = Field(default=0, description="Number of completed research queries")
    discovered_sources: int = Field(
        default=0, description="Number of sources discovered during research"
    )
    research_depth: str = Field(
        default="MEDIUM", description="Current research depth: shallow, medium, or deep"
    )
    generated_at: str = Field(..., description="ISO timestamp of state generation")


class AnalysisResultsAggregation(BaseModel):
    """Aggregated research analysis results."""

    session_id: str = Field(..., description="Research session ID")
    cost_effectiveness: Optional[CostEffectivenessResponse] = Field(
        default=None, description="Cost effectiveness analysis"
    )
    build_vs_buy: Optional[BuildVsBuyAnalysisResponse] = Field(
        default=None, description="Build vs buy analysis"
    )
    followup_triggers: Optional[FollowupTriggerResponse] = Field(
        default=None, description="Followup research triggers"
    )
    research_state: Optional[ResearchStateResponse] = Field(
        default=None, description="Research state and gaps"
    )
    generated_at: str = Field(..., description="ISO timestamp when analysis was generated")
