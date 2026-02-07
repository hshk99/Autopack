"""Adoption Readiness Framework

This module evaluates the readiness of a product or service for market adoption.
"""

from typing import Any, Dict, List, Optional, Union


class AdoptionReadiness:
    """Framework to evaluate the readiness of a product or service for market adoption."""

    DEFAULT_WEIGHTS = {
        "customer_readiness": 0.30,
        "infrastructure": 0.25,
        "regulatory_environment": 0.20,
        "economic_conditions": 0.15,
        "cultural_fit": 0.10,
    }

    IMPACT_LEVELS = {"low", "medium", "high", "critical"}

    def __init__(self, weights=None):
        if isinstance(weights, list):
            self.criteria = weights
            self.weights = self.DEFAULT_WEIGHTS.copy()
            self._legacy_mode = True
        else:
            self.criteria = None
            self.weights = weights or self.DEFAULT_WEIGHTS.copy()
            self._legacy_mode = False

        self.scores = {}
        self.barriers = []
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

    def add_barrier(self, name, impact, timeframe, mitigation):
        if impact not in self.IMPACT_LEVELS:
            raise ValueError(f"Impact must be one of {self.IMPACT_LEVELS}, got {impact}")
        self.barriers.append({
            "name": name,
            "impact": impact,
            "timeframe": timeframe,
            "mitigation": mitigation
        })

    def calculate_score(self):
        if not isinstance(self.weights, dict):
            raise ValueError("Cannot calculate score in legacy mode")
        missing = set(self.weights.keys()) - set(self.scores.keys())
        if missing:
            raise ValueError(f"Missing scores for criteria: {missing}")
        total_score = sum(self.weights[c] * self.scores[c] for c in self.weights.keys())
        return round(total_score, 2)

    def get_barrier_adjusted_score(self):
        base_score = self.calculate_score()
        impact_penalty = {"low": 0.5, "medium": 1.0, "high": 2.0, "critical": 3.0}
        total_penalty = sum(impact_penalty.get(b.get("impact", "low"), 0.5) for b in self.barriers)
        return round(max(0.0, base_score - total_penalty), 2)

    def get_interpretation(self):
        score = self.calculate_score()
        if score >= 8.0:
            return "Highly Ready"
        elif score >= 6.0:
            return "Ready"
        elif score >= 4.0:
            return "Moderately Ready"
        return "Not Ready"

    def get_adoption_timeline(self):
        score = self.calculate_score()
        if score >= 8.5:
            return "Immediate"
        elif score >= 7.0:
            return "Short-term (3-6 months)"
        elif score >= 5.0:
            return "Near-term (6-12 months)"
        elif score >= 3.0:
            return "Medium-term (12-18 months)"
        return "Long-term (18+ months)"

    def get_detailed_analysis(self):
        base_score = self.calculate_score()
        adjusted_score = self.get_barrier_adjusted_score()
        contributions = {c: round(self.weights[c] * self.scores[c], 2) for c in self.weights.keys()}
        return {
            "base_score": base_score,
            "barrier_adjusted_score": adjusted_score,
            "interpretation": self.get_interpretation(),
            "adoption_timeline": self.get_adoption_timeline(),
            "scores": self.scores.copy(),
            "weights": self.weights.copy(),
            "contributions": contributions,
            "barriers": self.barriers.copy(),
            "critical_barriers": self._get_critical_barriers(),
            "readiness_gaps": self._get_readiness_gaps(),
        }

    def _get_critical_barriers(self):
        return [b for b in self.barriers if b.get("impact") in ["critical", "high"]]

    def _get_readiness_gaps(self):
        return [c for c, s in self.scores.items() if s < 5.0]

    def get_recommendations(self):
        recommendations = []
        score = self.calculate_score()
        barriers = self._get_critical_barriers()
        gaps = self._get_readiness_gaps()

        if score >= 7.5:
            recommendations.append("High readiness - accelerate adoption efforts")
        elif score >= 5.0:
            recommendations.append("Moderate readiness - address gaps before full rollout")
        else:
            recommendations.append("Low readiness - significant preparation needed")

        if gaps:
            recommendations.append(f"Close readiness gaps: {', '.join(gaps)}")

        if barriers:
            barrier_names = [b.get("name", "Unknown") for b in barriers]
            recommendations.append(f"Mitigate critical barriers: {', '.join(barrier_names)}")

        return recommendations

    def evaluate(self, data):
        if self._legacy_mode and self.criteria:
            score = sum(data.get(c, 0) for c in self.criteria)
            return {
                "framework": "Adoption Readiness",
                "score": score,
                "details": f"Evaluated against {len(self.criteria)} criteria",
            }
        score = sum(data.values()) if data else 0
        return {
            "framework": "Adoption Readiness",
            "score": score,
            "details": f"Evaluated against {len(data)} criteria",
        }
