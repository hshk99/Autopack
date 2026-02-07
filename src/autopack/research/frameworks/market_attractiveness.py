"""Market Attractiveness Framework

This module evaluates the potential of a market based on various factors including
market size, growth rate, and competitive landscape.
"""

from typing import Any, Dict, List, Optional, Union


class MarketAttractiveness:
    """Evaluates market potential using weighted scoring methodology."""

    DEFAULT_WEIGHTS = {
        "market_size": 0.30,
        "growth_rate": 0.25,
        "profitability": 0.20,
        "accessibility": 0.15,
        "stability": 0.10,
    }

    def __init__(self, weights=None):
        if isinstance(weights, list):
            self.indicators = weights
            self.weights = self.DEFAULT_WEIGHTS.copy()
            self._legacy_mode = True
        else:
            self.indicators = None
            self.weights = weights or self.DEFAULT_WEIGHTS.copy()
            self._legacy_mode = False

        self.scores = {}
        if not self._legacy_mode:
            self._validate_weights()

    def _validate_weights(self):
        if not isinstance(self.weights, dict):
            return
        total = sum(self.weights.values())
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"Weights must sum to 1.0, got {total}")

    def set_score(self, criterion, score):
        if not isinstance(self.weights, dict):
            raise ValueError("Cannot set scores in legacy mode")
        if criterion not in self.weights:
            raise ValueError(f"Unknown criterion: {criterion}")
        if not (0 <= score <= 10):
            raise ValueError(f"Score must be between 0 and 10, got {score}")
        self.scores[criterion] = score

    def set_scores(self, scores):
        for criterion, score in scores.items():
            self.set_score(criterion, score)

    def calculate_score(self):
        if not isinstance(self.weights, dict):
            raise ValueError("Cannot calculate score in legacy mode")
        missing = set(self.weights.keys()) - set(self.scores.keys())
        if missing:
            raise ValueError(f"Missing scores for criteria: {missing}")
        total_score = sum(self.weights[c] * self.scores[c] for c in self.weights.keys())
        return round(total_score, 2)

    def get_interpretation(self):
        score = self.calculate_score()
        if score >= 8.0:
            return "Highly Attractive"
        elif score >= 6.0:
            return "Moderately Attractive"
        elif score >= 4.0:
            return "Marginally Attractive"
        return "Unattractive"

    def get_detailed_analysis(self):
        contributions = {c: round(self.weights[c] * self.scores[c], 2) for c in self.weights.keys()}
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

    def _get_top_factors(self, contributions):
        sorted_factors = sorted(contributions.items(), key=lambda x: x[1], reverse=True)
        return [factor for factor, _ in sorted_factors[:3]]

    def _get_weak_factors(self):
        return [c for c, s in self.scores.items() if s < 5.0]

    def get_recommendations(self):
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

    def evaluate(self, data):
        if self._legacy_mode and self.indicators:
            attractiveness = sum(data.get(i, 0) for i in self.indicators)
            return {
                "framework": "Market Attractiveness",
                "attractiveness": attractiveness,
                "details": f"Evaluated against {len(self.indicators)} indicators",
            }
        attractiveness = sum(data.values()) if data else 0
        return {
            "framework": "Market Attractiveness",
            "attractiveness": attractiveness,
            "details": f"Evaluated against {len(data)} factors",
        }
