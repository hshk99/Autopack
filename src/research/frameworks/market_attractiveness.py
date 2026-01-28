"""Market Attractiveness Framework

This module evaluates the potential of a market based on various factors including
market size, growth rate, and competitive landscape.
"""

from typing import Any, Dict, List, Optional


class MarketAttractiveness:
    """Evaluates market potential using weighted scoring methodology.

    Attributes:
        weights: Dictionary of criterion weights (must sum to 1.0)
        scores: Dictionary of criterion scores (0-10 scale)
    """

    DEFAULT_WEIGHTS = {
        "market_size": 0.30,
        "growth_rate": 0.25,
        "profitability": 0.20,
        "accessibility": 0.15,
        "stability": 0.10,
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """Initialize the Market Attractiveness framework.

        Args:
            weights: Custom weights for criteria (must sum to 1.0)

        Raises:
            ValueError: If weights don't sum to 1.0
        """
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.scores: Dict[str, float] = {}
        self._validate_weights()

    def _validate_weights(self) -> None:
        """Validate that weights sum to 1.0."""
        total = sum(self.weights.values())
        if not (0.99 <= total <= 1.01):  # Allow small floating point errors
            raise ValueError(f"Weights must sum to 1.0, got {total}")

    def set_score(self, criterion: str, score: float) -> None:
        """Set score for a specific criterion.

        Args:
            criterion: Name of the criterion
            score: Score value (0-10 scale)

        Raises:
            ValueError: If criterion not in weights or score out of range
        """
        if criterion not in self.weights:
            raise ValueError(f"Unknown criterion: {criterion}")
        if not (0 <= score <= 10):
            raise ValueError(f"Score must be between 0 and 10, got {score}")
        self.scores[criterion] = score

    def set_scores(self, scores: Dict[str, float]) -> None:
        """Set multiple scores at once.

        Args:
            scores: Dictionary of criterion scores
        """
        for criterion, score in scores.items():
            self.set_score(criterion, score)

    def calculate_score(self) -> float:
        """Calculate weighted attractiveness score.

        Returns:
            Weighted score (0-10 scale)

        Raises:
            ValueError: If not all criteria have scores
        """
        missing = set(self.weights.keys()) - set(self.scores.keys())
        if missing:
            raise ValueError(f"Missing scores for criteria: {missing}")

        total_score = sum(
            self.weights[criterion] * self.scores[criterion] for criterion in self.weights.keys()
        )
        return round(total_score, 2)

    def get_interpretation(self) -> str:
        """Get interpretation of the attractiveness score.

        Returns:
            Interpretation string
        """
        score = self.calculate_score()
        if score >= 8.0:
            return "Highly Attractive"
        elif score >= 6.0:
            return "Moderately Attractive"
        elif score >= 4.0:
            return "Marginally Attractive"
        else:
            return "Unattractive"

    def get_detailed_analysis(self) -> Dict[str, Any]:
        """Get detailed analysis including weighted contributions.

        Returns:
            Dictionary with score breakdown and analysis
        """
        contributions = {
            criterion: round(self.weights[criterion] * self.scores[criterion], 2)
            for criterion in self.weights.keys()
        }

        total_score = self.calculate_score()

        return {
            "total_score": total_score,
            "interpretation": self.get_interpretation(),
            "scores": self.scores.copy(),
            "weights": self.weights.copy(),
            "contributions": contributions,
            "top_factors": self._get_top_factors(contributions),
            "weak_factors": self._get_weak_factors(),
        }

    def _get_top_factors(self, contributions: Dict[str, float]) -> List[str]:
        """Identify top contributing factors."""
        sorted_factors = sorted(contributions.items(), key=lambda x: x[1], reverse=True)
        return [factor for factor, _ in sorted_factors[:3]]

    def _get_weak_factors(self) -> List[str]:
        """Identify weak factors (score < 5)."""
        return [criterion for criterion, score in self.scores.items() if score < 5.0]

    def get_recommendations(self) -> List[str]:
        """Generate recommendations based on analysis.

        Returns:
            List of strategic recommendations
        """
        recommendations = []
        score = self.calculate_score()
        weak_factors = self._get_weak_factors()

        if score >= 7.0:
            recommendations.append("Strong market opportunity - prioritize market entry")
        elif score >= 5.0:
            recommendations.append("Moderate opportunity - conduct deeper analysis")
        else:
            recommendations.append("Weak market opportunity - consider alternatives")

        if weak_factors:
            recommendations.append(f"Address weak factors: {', '.join(weak_factors)}")

        if self.scores.get("growth_rate", 0) >= 8.0:
            recommendations.append("High growth market - move quickly to capture share")

        if self.scores.get("accessibility", 0) < 5.0:
            recommendations.append("Market access barriers - develop entry strategy")

        return recommendations
