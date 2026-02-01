"""Build Decision Model for research-to-artifact pipeline.

This module provides the BuildDecision model which encapsulates the decision
of whether to proceed with building a project based on research findings.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BuildDecisionType(str, Enum):
    """Types of build decisions based on research viability."""

    BUILD = "BUILD"
    BUILD_WITH_CAUTION = "BUILD_WITH_CAUTION"
    DO_NOT_BUILD = "DO_NOT_BUILD"


class BuildViabilityMetrics(BaseModel):
    """Metrics extracted from research outputs to inform build decisions."""

    market_attractiveness_score: float = Field(
        ..., description="Market attractiveness score (0-10)", ge=0, le=10
    )
    competitive_intensity_score: float = Field(
        ..., description="Competitive intensity score (0-10)", ge=0, le=10
    )
    technical_feasibility_score: float = Field(
        ..., description="Technical feasibility score (0-10)", ge=0, le=10
    )
    overall_confidence: str = Field(..., description="Overall confidence level (high, medium, low)")
    risk_level: str = Field(..., description="Risk assessment level (high, medium, low)")

    @field_validator(
        "market_attractiveness_score", "competitive_intensity_score", "technical_feasibility_score"
    )
    @classmethod
    def validate_score_range(cls, v: float) -> float:
        """Ensure scores are between 0 and 10."""
        if not (0 <= v <= 10):
            raise ValueError("Score must be between 0 and 10")
        return v

    @field_validator("overall_confidence", "risk_level")
    @classmethod
    def validate_enum_fields(cls, v: str) -> str:
        """Ensure enum fields are valid."""
        if v not in ("high", "medium", "low"):
            raise ValueError("Value must be 'high', 'medium', or 'low'")
        return v


class BuildDecision(BaseModel):
    """Build decision based on research viability analysis.

    Encapsulates the decision of whether to BUILD, BUILD_WITH_CAUTION, or
    DO_NOT_BUILD based on research metrics and viability assessment.
    """

    decision: BuildDecisionType = Field(
        ..., description="The build decision: BUILD, BUILD_WITH_CAUTION, or DO_NOT_BUILD"
    )
    metrics: BuildViabilityMetrics = Field(
        ..., description="Viability metrics extracted from research"
    )
    rationale: str = Field(..., description="Detailed explanation for the decision")
    key_blockers: list[str] = Field(
        default_factory=list, description="Critical blockers preventing the build"
    )
    key_opportunities: list[str] = Field(
        default_factory=list, description="Key opportunities supporting the build"
    )
    recommended_mitigations: list[str] = Field(
        default_factory=list, description="Recommended actions to address risks"
    )
    confidence_percentage: float = Field(
        default=0.0, description="Confidence in this decision (0-100)", ge=0, le=100
    )

    def is_proceed(self) -> bool:
        """Check if the decision is to proceed with building."""
        return self.decision == BuildDecisionType.BUILD

    def is_proceed_with_caution(self) -> bool:
        """Check if the decision is to proceed with caution."""
        return self.decision == BuildDecisionType.BUILD_WITH_CAUTION

    def should_block(self) -> bool:
        """Check if the decision is to NOT build."""
        return self.decision == BuildDecisionType.DO_NOT_BUILD

    model_config = ConfigDict(arbitrary_types_allowed=True)


def extract_build_decision_from_synthesis(synthesis: dict[str, Any]) -> BuildDecision:
    """Extract build decision from research synthesis data.

    Analyzes research synthesis containing scores and recommendations
    to generate a formal BuildDecision.

    Args:
        synthesis: Dictionary from BootstrapSession.synthesis containing:
            - overall_recommendation: "proceed", "proceed_with_caution", "reconsider"
            - confidence_level: "high", "medium", "low"
            - scores: dict with market_attractiveness, competitive_intensity,
                     technical_feasibility, total
            - risk_assessment: "high", "medium", "low"
            - key_dependencies: list of tech dependencies
            - build_history_insights: optional dict with success metrics

    Returns:
        BuildDecision with decision, metrics, and rationale

    Raises:
        ValueError: If synthesis data is missing required fields
    """
    # Extract scores from synthesis
    scores = synthesis.get("scores", {})
    market_score = scores.get("market_attractiveness", 0.0)
    competitive_score = scores.get("competitive_intensity", 0.0)
    feasibility_score = scores.get("technical_feasibility", 0.0)

    # Extract recommendation and confidence
    recommendation = synthesis.get("overall_recommendation", "reconsider")
    confidence = synthesis.get("confidence_level", "low")
    risk_assessment = synthesis.get("risk_assessment", "high")

    # Map recommendation to decision type
    if recommendation == "proceed":
        decision_type = BuildDecisionType.BUILD
    elif recommendation == "proceed_with_caution":
        decision_type = BuildDecisionType.BUILD_WITH_CAUTION
    else:
        decision_type = BuildDecisionType.DO_NOT_BUILD

    # Build metrics object
    metrics = BuildViabilityMetrics(
        market_attractiveness_score=market_score,
        competitive_intensity_score=competitive_score,
        technical_feasibility_score=feasibility_score,
        overall_confidence=confidence,
        risk_level=risk_assessment,
    )

    # Generate rationale based on decision
    rationale = _generate_rationale(
        decision_type, market_score, competitive_score, feasibility_score, synthesis
    )

    # Extract blockers and opportunities from synthesis
    blockers = _extract_blockers(synthesis, decision_type)
    opportunities = _extract_opportunities(synthesis, decision_type)
    mitigations = _extract_mitigations(synthesis, decision_type)

    # Calculate confidence percentage
    confidence_pct = _calculate_confidence_percentage(confidence)

    return BuildDecision(
        decision=decision_type,
        metrics=metrics,
        rationale=rationale,
        key_blockers=blockers,
        key_opportunities=opportunities,
        recommended_mitigations=mitigations,
        confidence_percentage=confidence_pct,
    )


def _generate_rationale(
    decision_type: BuildDecisionType,
    market_score: float,
    competitive_score: float,
    feasibility_score: float,
    synthesis: dict[str, Any],
) -> str:
    """Generate detailed rationale for the build decision."""
    avg_score = (market_score + (10 - competitive_score) + feasibility_score) / 3

    if decision_type == BuildDecisionType.BUILD:
        return (
            f"Market opportunity is strong (score: {market_score}/10), competitive landscape "
            f"is manageable (intensity: {competitive_score}/10), and technical feasibility is "
            f"established (score: {feasibility_score}/10). Overall viability is high "
            f"(avg: {avg_score:.1f}/10). Proceed with full implementation."
        )
    elif decision_type == BuildDecisionType.BUILD_WITH_CAUTION:
        critical_area = _identify_critical_area(market_score, competitive_score, feasibility_score)
        return (
            f"While the overall opportunity has merit, there are concerns in {critical_area} "
            f"that require careful management. Market opportunity (score: {market_score}/10), "
            f"competitive intensity (score: {competitive_score}/10), feasibility (score: {feasibility_score}/10). "
            f"Implement mitigations before full launch."
        )
    else:
        critical_area = _identify_critical_area(market_score, competitive_score, feasibility_score)
        return (
            f"The project faces significant challenges in {critical_area} that make it unviable "
            f"at this time. Market opportunity (score: {market_score}/10), competitive intensity "
            f"(score: {competitive_score}/10), feasibility (score: {feasibility_score}/10). "
            f"Recommend re-evaluation after addressing core blockers."
        )


def _identify_critical_area(market: float, competitive: float, feasibility: float) -> str:
    """Identify which area (market, competitive, or feasibility) is the main concern."""
    scores = [
        ("market opportunity", market),
        ("competitive positioning", 10 - competitive),
        ("technical feasibility", feasibility),
    ]
    # Find the lowest area
    area, _ = min(scores, key=lambda x: x[1])
    return area


def _extract_blockers(synthesis: dict[str, Any], decision_type: BuildDecisionType) -> list[str]:
    """Extract key blockers from synthesis based on decision type."""
    blockers = []

    if decision_type == BuildDecisionType.DO_NOT_BUILD:
        # High competitive intensity can be a blocker
        competitive_score = synthesis.get("scores", {}).get("competitive_intensity", 0)
        if competitive_score > 7:
            blockers.append(
                "High competitive intensity: Market is crowded with entrenched competitors"
            )

        # Low feasibility is a blocker
        feasibility_score = synthesis.get("scores", {}).get("technical_feasibility", 0)
        if feasibility_score < 3:
            blockers.append(
                "Low technical feasibility: Required technologies or expertise not available"
            )

        # Small market is a blocker
        market_score = synthesis.get("scores", {}).get("market_attractiveness", 0)
        if market_score < 3:
            blockers.append(
                "Small market opportunity: TAM/SAM too limited for sustainable business"
            )

    # Add any identified risks
    risk_assessment = synthesis.get("risk_assessment", "")
    if risk_assessment == "high":
        blockers.append("High risk profile: Project faces significant execution risks")

    # Add any build history warnings
    history_insights = synthesis.get("build_history_insights", {})
    warnings = history_insights.get("warnings", [])
    blockers.extend(warnings[:2])

    return blockers


def _extract_opportunities(
    synthesis: dict[str, Any], decision_type: BuildDecisionType
) -> list[str]:
    """Extract key opportunities from synthesis that support the build."""
    opportunities = []

    if decision_type in (BuildDecisionType.BUILD, BuildDecisionType.BUILD_WITH_CAUTION):
        # Strong market opportunity
        market_score = synthesis.get("scores", {}).get("market_attractiveness", 0)
        if market_score > 6:
            opportunities.append(f"Strong market opportunity (score: {market_score}/10)")

        # Good feasibility
        feasibility_score = synthesis.get("scores", {}).get("technical_feasibility", 0)
        if feasibility_score > 6:
            opportunities.append(f"Good technical feasibility (score: {feasibility_score}/10)")

        # Differentiation factors
        diff_factors = synthesis.get("differentiation_factors", [])
        if diff_factors:
            opportunities.append(f"Clear differentiation: {', '.join(diff_factors[:2])}")

        # Pattern recommendations
        patterns = synthesis.get("pattern_recommendations", [])
        if patterns:
            opportunities.append(
                "Cross-project learning insights available to accelerate development"
            )

    return opportunities


def _extract_mitigations(synthesis: dict[str, Any], decision_type: BuildDecisionType) -> list[str]:
    """Extract recommended mitigations for risks."""
    mitigations = []

    if decision_type == BuildDecisionType.BUILD_WITH_CAUTION:
        # Mitigate market risks
        market_score = synthesis.get("scores", {}).get("market_attractiveness", 0)
        if market_score < 6:
            mitigations.append(
                "Conduct detailed customer discovery before full implementation to validate market demand"
            )

        # Mitigate competitive risks
        competitive_score = synthesis.get("scores", {}).get("competitive_intensity", 0)
        if competitive_score > 6:
            mitigations.append(
                "Develop and validate unique value proposition before launch to differentiate from competitors"
            )

        # Mitigate feasibility risks
        feasibility_score = synthesis.get("scores", {}).get("technical_feasibility", 0)
        if feasibility_score < 6:
            mitigations.append(
                "Start with MVP focusing on core features; validate technical approach with proof-of-concept"
            )

        # Use build history insights
        history_insights = synthesis.get("build_history_insights", {})
        recommendations = history_insights.get("recommendations", [])
        mitigations.extend(recommendations[:2])

    return mitigations


def _calculate_confidence_percentage(confidence_level: str) -> float:
    """Convert confidence level to percentage."""
    confidence_map = {
        "high": 85.0,
        "medium": 65.0,
        "low": 45.0,
    }
    return confidence_map.get(confidence_level, 50.0)
