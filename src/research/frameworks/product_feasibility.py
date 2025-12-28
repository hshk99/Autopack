"""Product Feasibility Framework

This module assesses the viability of a product by analyzing technical feasibility,
cost implications, and resource requirements.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum


class RiskLevel(Enum):
    """Risk level enumeration."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FeasibilityLevel(Enum):
    """Overall feasibility assessment."""
    NOT_FEASIBLE = "not_feasible"
    MARGINALLY_FEASIBLE = "marginally_feasible"
    FEASIBLE = "feasible"
    HIGHLY_FEASIBLE = "highly_feasible"
    VERY_HIGH_FEASIBILITY = "very_high_feasibility"  # Test expects this


@dataclass
class TechnicalRequirement:
    """Individual technical requirement (singular for test compatibility)."""
    name: str
    complexity: str  # "low", "medium", "high"
    availability: str  # "readily_available", "limited", "unavailable"
    maturity: str  # "mature", "developing", "experimental"


@dataclass
class ResourceRequirement:
    """Resource requirement (singular for test compatibility)."""
    team_size: int
    required_skills: List[str]
    development_time_months: int
    estimated_cost: float


@dataclass
class ProductFeasibility:
    """Product Feasibility Framework Calculator.

    Assesses product viability across multiple dimensions:
    - Technical feasibility
    - Resource requirements
    - Risk assessment
    """

    technical_requirements: List[TechnicalRequirement] = field(default_factory=list)
    resource_requirements: Optional[ResourceRequirement] = None
    risks: List[Dict[str, Any]] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)

    def calculate_technical_score(self) -> float:
        """Calculate technical feasibility score (0-100).

        Returns higher scores for:
        - Low complexity
        - Readily available tech
        - Mature technologies
        """
        if not self.technical_requirements:
            return 50.0

        scores = []
        for req in self.technical_requirements:
            score = 0.0

            # Complexity scoring (lower is better)
            complexity_map = {"low": 100, "medium": 60, "high": 20}
            score += complexity_map.get(req.complexity, 50) * 0.4

            # Availability scoring
            availability_map = {
                "readily_available": 100,
                "limited": 50,
                "unavailable": 10,
            }
            score += availability_map.get(req.availability, 50) * 0.3

            # Maturity scoring
            maturity_map = {"mature": 100, "developing": 50, "experimental": 15}
            score += maturity_map.get(req.maturity, 50) * 0.3

            scores.append(score)

        return sum(scores) / len(scores)

    def calculate_resource_score(self) -> float:
        """Calculate resource feasibility score (0-100).

        Returns higher scores for:
        - Smaller teams
        - Shorter timelines
        - Lower costs
        """
        if not self.resource_requirements:
            return 50.0

        res = self.resource_requirements
        score = 0.0

        # Team size scoring (smaller is better)
        if res.team_size <= 5:
            score += 30
        elif res.team_size <= 10:
            score += 20
        elif res.team_size <= 20:
            score += 10
        else:
            score += 5

        # Timeline scoring (shorter is better)
        if res.development_time_months <= 6:
            score += 35
        elif res.development_time_months <= 12:
            score += 25
        elif res.development_time_months <= 24:
            score += 15
        else:
            score += 5

        # Cost scoring (lower is better)
        if res.estimated_cost <= 500_000:
            score += 35
        elif res.estimated_cost <= 1_000_000:
            score += 25
        elif res.estimated_cost <= 5_000_000:
            score += 15
        elif res.estimated_cost <= 10_000_000:
            score += 10
        else:
            score += 5

        return score

    def calculate_risk_score(self) -> float:
        """Calculate risk score (0-100).

        Returns higher scores for lower risks.
        """
        # Base score
        score = 100.0

        # Penalize for risks
        for risk in self.risks:
            level = risk.get("level", "low")
            impact = risk.get("impact", "low")

            # Risk penalty
            level_penalty = {
                "low": 5,
                "medium": 15,
                "high": 25,
                "critical": 35,
            }.get(level, 10)

            impact_penalty = {
                "low": 5,
                "medium": 15,
                "high": 25,
                "critical": 35,
            }.get(impact, 10)

            score -= (level_penalty + impact_penalty) / 2

        # Penalize for dependencies
        score -= len(self.dependencies) * 3

        # Penalize for constraints
        score -= len(self.constraints) * 2

        return max(0.0, min(100.0, score))

    def get_feasibility_level(self) -> FeasibilityLevel:
        """Determine overall feasibility level."""
        # Calculate aggregate score
        tech_score = self.calculate_technical_score()
        resource_score = self.calculate_resource_score()
        risk_score = self.calculate_risk_score()

        # Weighted average (tech and risk are more important)
        overall_score = (tech_score * 0.4 + resource_score * 0.3 + risk_score * 0.3)

        # Map to feasibility level
        if overall_score >= 85:
            return FeasibilityLevel.VERY_HIGH_FEASIBILITY
        elif overall_score >= 70:
            return FeasibilityLevel.HIGHLY_FEASIBLE
        elif overall_score >= 50:
            return FeasibilityLevel.FEASIBLE
        elif overall_score >= 30:
            return FeasibilityLevel.MARGINALLY_FEASIBLE
        else:
            return FeasibilityLevel.NOT_FEASIBLE

    def identify_critical_risks(self) -> List[Dict[str, Any]]:
        """Identify critical and high-severity risks."""
        critical_risks = []
        for risk in self.risks:
            level = risk.get("level", "low")
            if level in ["critical", "high"]:
                critical_risks.append(risk)
        return critical_risks

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive feasibility report."""
        return {
            "technical_score": self.calculate_technical_score(),
            "resource_score": self.calculate_resource_score(),
            "risk_score": self.calculate_risk_score(),
            "feasibility_level": self.get_feasibility_level().value,
            "critical_risks": self.identify_critical_risks(),
            "technical_requirements_count": len(self.technical_requirements),
            "risk_count": len(self.risks),
            "dependency_count": len(self.dependencies),
            "constraint_count": len(self.constraints),
        }
