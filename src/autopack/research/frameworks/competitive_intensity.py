"""Competitive Intensity Framework

This module assesses the competitive intensity within a market.
"""

from typing import Any, Dict, List, Optional, Union


class CompetitiveIntensity:
    """Framework to assess the competitive intensity within a market."""

    DEFAULT_WEIGHTS = {
        "rivalry": 0.25,
        "threat_of_new_entrants": 0.20,
        "threat_of_substitutes": 0.20,
        "buyer_power": 0.20,
        "supplier_power": 0.15,
    }

    def __init__(self, weights=None):
        if isinstance(weights, list):
            self.factors = weights
            self.weights = self.DEFAULT_WEIGHTS.copy()
            self._legacy_mode = True
        else:
            self.factors = None
            self.weights = weights or self.DEFAULT_WEIGHTS.copy()
            self._legacy_mode = False

        self.scores = {}
        self.competitors = []
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

    def add_competitor(self, name, market_share, strengths, weaknesses):
        self.competitors.append({
            "name": name,
            "market_share": market_share,
            "strengths": strengths,
            "weaknesses": weaknesses
        })

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
            return "Extremely Intense"
        elif score >= 6.0:
            return "Highly Competitive"
        elif score >= 4.0:
            return "Moderately Competitive"
        return "Low Competition"

    def get_market_concentration(self):
        if not self.competitors:
            return {"hhi": 0, "top_3_share": 0, "concentration_level": "Fragmented"}

        shares = [c["market_share"] for c in self.competitors]
        hhi = sum(s ** 2 for s in shares)
        top_3_share = sum(sorted(shares, reverse=True)[:3])

        if hhi < 1500:
            concentration = "Fragmented"
        elif hhi < 2500:
            concentration = "Moderate Concentration"
        else:
            concentration = "High Concentration"

        return {"hhi": round(hhi, 2), "top_3_share": round(top_3_share, 2), "concentration_level": concentration}

    def get_detailed_analysis(self):
        base_score = self.calculate_score()
        contributions = {c: round(self.weights[c] * self.scores[c], 2) for c in self.weights.keys()}
        return {
            "base_score": base_score,
            "interpretation": self.get_interpretation(),
            "scores": self.scores.copy(),
            "weights": self.weights.copy(),
            "contributions": contributions,
            "key_forces": self._get_key_forces(contributions),
            "competitors": self.competitors.copy(),
            "market_concentration": self.get_market_concentration(),
        }

    def _get_key_forces(self, contributions):
        sorted_forces = sorted(contributions.items(), key=lambda x: x[1], reverse=True)
        return [force for force, _ in sorted_forces[:3]]

    def get_recommendations(self):
        recommendations = []
        score = self.calculate_score()

        if score >= 8.0:
            recommendations.append("Intense competition - differentiation critical")
        elif score >= 6.0:
            recommendations.append("Highly competitive market - strong positioning needed")
        elif score >= 4.0:
            recommendations.append("Moderate competition - sustainable advantage possible")
        else:
            recommendations.append("Low competition - first-mover advantage available")

        return recommendations

    def evaluate(self, data):
        if self._legacy_mode and self.factors:
            intensity = sum(data.get(f, 0) for f in self.factors)
            return {
                "framework": "Competitive Intensity",
                "intensity": intensity,
                "details": f"Evaluated against {len(self.factors)} factors",
            }
        intensity = sum(data.values()) if data else 0
        return {
            "framework": "Competitive Intensity",
            "intensity": intensity,
            "details": f"Evaluated against {len(data)} factors",
        }
