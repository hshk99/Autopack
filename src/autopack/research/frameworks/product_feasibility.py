"""Product Feasibility Framework

This module assesses the viability of a product by analyzing technical feasibility,
resource availability, cost implications, and risk factors.
"""

from typing import Any, Dict, List, Optional, Union


class ProductFeasibility:
    """Product Feasibility Framework Calculator."""

    DEFAULT_WEIGHTS = {
        "technical_feasibility": 0.25,
        "resource_availability": 0.20,
        "cost_viability": 0.20,
        "time_to_market": 0.20,
        "scalability": 0.15,
    }

    SEVERITY_LEVELS = {"low", "medium", "high", "critical"}

    def __init__(self, weights=None, parameters=None):
        if isinstance(weights, list):
            self.parameters = weights
            self.weights = self.DEFAULT_WEIGHTS.copy()
            self._legacy_mode = True
        elif parameters is not None and isinstance(parameters, list):
            self.parameters = parameters
            self.weights = self.DEFAULT_WEIGHTS.copy()
            self._legacy_mode = True
        else:
            self.parameters = None
            self.weights = weights or self.DEFAULT_WEIGHTS.copy()
            self._legacy_mode = False

        self.scores = {}
        self.risk_factors = []
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

    def add_risk_factor(self, name, severity, mitigation):
        if severity not in self.SEVERITY_LEVELS:
            raise ValueError(f"Severity must be one of {self.SEVERITY_LEVELS}, got {severity}")
        self.risk_factors.append({"name": name, "severity": severity, "mitigation": mitigation})

    def calculate_score(self):
        if not isinstance(self.weights, dict):
            raise ValueError("Cannot calculate score in legacy mode")
        missing = set(self.weights.keys()) - set(self.scores.keys())
        if missing:
            raise ValueError(f"Missing scores for criteria: {missing}")
        total_score = sum(self.weights[c] * self.scores[c] for c in self.weights.keys())
        return round(total_score, 2)

    def get_risk_adjusted_score(self):
        base_score = self.calculate_score()
        severity_penalty = {"low": 0.5, "medium": 1.0, "high": 2.0, "critical": 3.0}
        total_penalty = sum(severity_penalty.get(f.get("severity", "low"), 0.5) for f in self.risk_factors)
        return round(max(0.0, base_score - total_penalty), 2)

    def get_interpretation(self):
        score = self.calculate_score()
        if score >= 8.5:
            return "Very High Feasibility"
        elif score >= 7.0:
            return "High Feasibility"
        elif score >= 5.0:
            return "Moderate Feasibility"
        elif score >= 3.0:
            return "Low Feasibility"
        return "Very Low Feasibility"

    def _get_critical_risks(self):
        return [f for f in self.risk_factors if f.get("severity") in ["critical", "high"]]

    def _get_weak_areas(self):
        return [c for c, s in self.scores.items() if s < 5.0]

    def get_detailed_analysis(self):
        base_score = self.calculate_score()
        risk_adjusted_score = self.get_risk_adjusted_score()
        contributions = {c: round(self.weights[c] * self.scores[c], 2) for c in self.weights.keys()}
        return {
            "base_score": base_score,
            "risk_adjusted_score": risk_adjusted_score,
            "interpretation": self.get_interpretation(),
            "scores": self.scores.copy(),
            "weights": self.weights.copy(),
            "contributions": contributions,
            "risk_factors": self.risk_factors.copy(),
            "critical_risks": self._get_critical_risks(),
            "weak_areas": self._get_weak_areas(),
        }

    def get_recommendations(self):
        recommendations = []
        score = self.calculate_score()
        weak_areas = self._get_weak_areas()
        critical_risks = self._get_critical_risks()

        if score >= 7.5:
            recommendations.append("Strong feasibility - proceed with implementation")
        elif score >= 5.0:
            recommendations.append("Moderate feasibility - address weak areas before proceeding")
        else:
            recommendations.append("Low feasibility - reconsider approach or mitigate significant challenges")

        if weak_areas:
            recommendations.append(f"Strengthen weak areas: {', '.join(weak_areas)}")

        if critical_risks:
            risk_names = [r.get("name", "Unknown") for r in critical_risks]
            recommendations.append(f"Implement risk mitigation for: {', '.join(risk_names)}")

        if self.scores.get("technical_feasibility", 0) < 5:
            recommendations.append("Invest in technology research or consider alternative technical approaches")
        if self.scores.get("cost_viability", 0) < 5:
            recommendations.append("Develop cost reduction strategies or secure additional funding")
        if self.scores.get("time_to_market", 0) < 5:
            recommendations.append("Streamline development process or reduce scope for faster delivery")

        return recommendations

    def evaluate(self, data):
        if self._legacy_mode and self.parameters:
            feasibility = sum(data.get(p, 0) for p in self.parameters)
            return {
                "framework": "Product Feasibility",
                "feasibility": feasibility,
                "details": f"Evaluated against {len(self.parameters)} parameters",
            }
        feasibility = sum(data.values()) if data else 0
        return {
            "framework": "Product Feasibility",
            "feasibility": feasibility,
            "details": f"Evaluated against {len(data)} parameters",
        }
