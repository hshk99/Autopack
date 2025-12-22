"""Research Hooks for Autonomous Mode.

This module provides integration hooks that trigger research sessions
before planning when research would be valuable for decision-making.

Design Principles:
- Non-invasive integration with existing autonomous executor
- Configurable research triggers based on task characteristics
- Graceful degradation if research system unavailable
- Clear audit trail of research-triggered decisions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ResearchTrigger(str, Enum):
    """Conditions that trigger research before planning."""

    HIGH_COMPLEXITY = "high_complexity"  # Complex tasks benefit from research
    AMBIGUOUS_REQUIREMENTS = "ambiguous_requirements"  # Unclear specs need investigation
    NEW_TECHNOLOGY = "new_technology"  # Unfamiliar tech requires research
    MULTIPLE_APPROACHES = "multiple_approaches"  # Need to evaluate options
    INTEGRATION_RISK = "integration_risk"  # Integration points need analysis
    HISTORICAL_FAILURES = "historical_failures"  # Past failures suggest research needed


@dataclass
class ResearchDecision:
    """Decision about whether to conduct research."""

    should_research: bool
    trigger: Optional[ResearchTrigger]
    confidence: float  # 0.0-1.0
    reasoning: str
    estimated_value: float  # Expected value of research (0.0-1.0)
    research_goals: List[str]


class ResearchHooks:
    """Hooks for triggering research in autonomous mode."""

    def __init__(
        self,
        project_root: Path,
        db_session: Optional[Session] = None,
        enable_research: bool = True,
    ):
        """
        Initialize research hooks.

        Args:
            project_root: Root directory of the project
            db_session: Optional database session
            enable_research: Whether to enable research triggers
        """
        self.project_root = project_root
        self._db_session = db_session
        self.enable_research = enable_research

    def should_research_before_planning(
        self,
        phase_description: str,
        task_category: str,
        complexity: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ResearchDecision:
        """
        Determine if research should be conducted before planning.

        Args:
            phase_description: Description of the phase
            task_category: Category of the task
            complexity: Complexity level (LOW, MEDIUM, HIGH)
            context: Optional additional context

        Returns:
            ResearchDecision with recommendation
        """
        if not self.enable_research:
            return ResearchDecision(
                should_research=False,
                trigger=None,
                confidence=1.0,
                reasoning="Research hooks disabled",
                estimated_value=0.0,
                research_goals=[],
            )

        context = context or {}
        triggers = []
        research_goals = []

        # Check for high complexity
        if complexity.upper() in ["HIGH", "VERY_HIGH"]:
            triggers.append(ResearchTrigger.HIGH_COMPLEXITY)
            research_goals.append(
                f"Identify best practices for {task_category} tasks"
            )
            research_goals.append("Evaluate implementation approaches")

        # Check for ambiguous requirements
        ambiguous_keywords = ["unclear", "ambiguous", "multiple options", "not sure"]
        if any(kw in phase_description.lower() for kw in ambiguous_keywords):
            triggers.append(ResearchTrigger.AMBIGUOUS_REQUIREMENTS)
            research_goals.append("Clarify requirements and constraints")

        # Check for new technology indicators
        new_tech_keywords = ["new", "unfamiliar", "first time", "experimental"]
        if any(kw in phase_description.lower() for kw in new_tech_keywords):
            triggers.append(ResearchTrigger.NEW_TECHNOLOGY)
            research_goals.append("Research technology capabilities and limitations")

        # Check for integration risks
        integration_keywords = ["integrate", "connect", "interface", "api"]
        if any(kw in phase_description.lower() for kw in integration_keywords):
            triggers.append(ResearchTrigger.INTEGRATION_RISK)
            research_goals.append("Analyze integration points and dependencies")

        # Calculate estimated value
        estimated_value = self._calculate_research_value(
            triggers, complexity, task_category
        )

        # Make decision
        should_research = estimated_value > 0.5 and len(triggers) > 0
        primary_trigger = triggers[0] if triggers else None

        return ResearchDecision(
            should_research=should_research,
            trigger=primary_trigger,
            confidence=min(0.9, 0.5 + (len(triggers) * 0.15)),
            reasoning=self._build_reasoning(triggers, estimated_value),
            estimated_value=estimated_value,
            research_goals=research_goals,
        )

    def _calculate_research_value(
        self, triggers: List[ResearchTrigger], complexity: str, category: str
    ) -> float:
        """
        Calculate estimated value of conducting research.

        Args:
            triggers: List of triggered conditions
            complexity: Task complexity
            category: Task category

        Returns:
            Estimated value (0.0-1.0)
        """
        base_value = 0.3

        # Add value per trigger
        trigger_value = len(triggers) * 0.15

        # Complexity multiplier
        complexity_multipliers = {
            "LOW": 0.5,
            "MEDIUM": 0.75,
            "HIGH": 1.0,
            "VERY_HIGH": 1.2,
        }
        complexity_mult = complexity_multipliers.get(complexity.upper(), 0.75)

        # Category-specific adjustments
        high_value_categories = [
            "IMPLEMENT_FEATURE",
            "REFACTOR",
            "ARCHITECTURE",
            "INTEGRATION",
        ]
        category_bonus = 0.1 if category in high_value_categories else 0.0

        total_value = (base_value + trigger_value) * complexity_mult + category_bonus
        return min(1.0, total_value)

    def _build_reasoning(self, triggers: List[ResearchTrigger], value: float) -> str:
        """
        Build human-readable reasoning for the decision.

        Args:
            triggers: List of triggered conditions
            value: Estimated research value

        Returns:
            Reasoning string
        """
        if not triggers:
            return "No research triggers detected"

        trigger_descriptions = {
            ResearchTrigger.HIGH_COMPLEXITY: "high task complexity",
            ResearchTrigger.AMBIGUOUS_REQUIREMENTS: "ambiguous requirements",
            ResearchTrigger.NEW_TECHNOLOGY: "unfamiliar technology",
            ResearchTrigger.MULTIPLE_APPROACHES: "multiple implementation options",
            ResearchTrigger.INTEGRATION_RISK: "integration complexity",
            ResearchTrigger.HISTORICAL_FAILURES: "historical failure patterns",
        }

        trigger_list = ", ".join(
            trigger_descriptions.get(t, str(t)) for t in triggers
        )
        return f"Research recommended due to: {trigger_list} (estimated value: {value:.2f})"
