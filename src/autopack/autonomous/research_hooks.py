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
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ResearchTrigger:
    """Defines when research should be triggered."""

    name: str
    condition: Callable[[Dict[str, Any]], bool]
    priority: int = 1  # 1=low, 5=high
    description: str = ""
    enabled: bool = True


@dataclass
class ResearchHookConfig:
    """Configuration for research hooks."""

    enabled: bool = True
    triggers: List[ResearchTrigger] = field(default_factory=list)
    max_research_time_minutes: int = 30
    require_approval: bool = False
    fallback_on_error: bool = True  # Continue without research if it fails
    log_decisions: bool = True


@dataclass
class ResearchDecision:
    """Records a decision about whether to trigger research."""

    triggered: bool
    trigger_name: Optional[str]
    reason: str
    timestamp: datetime = field(default_factory=datetime.now)
    task_context: Dict[str, Any] = field(default_factory=dict)


# Backward compatibility alias for tests
ResearchTriggerConfig = ResearchHookConfig


class ResearchHooks:
    """Manages research hooks for autonomous mode."""

    def __init__(
        self,
        config: Optional[ResearchHookConfig] = None,
        research_executor: Any = None,
        build_history_integrator: Any = None,
    ):
        """Initialize research hooks.

        Args:
            config: Hook configuration
            research_executor: Research phase executor instance
            build_history_integrator: BUILD_HISTORY integrator instance
        """
        self.config = config or ResearchHookConfig()
        self.research_executor = research_executor
        self.build_history_integrator = build_history_integrator
        self.decisions: List[ResearchDecision] = []

        # Register default triggers
        self._register_default_triggers()

    def _register_default_triggers(self) -> None:
        """Register default research triggers."""
        # Trigger 1: Low historical success rate
        self.config.triggers.append(
            ResearchTrigger(
                name="low_success_rate",
                condition=lambda ctx: self._check_low_success_rate(ctx),
                priority=4,
                description="Triggered when similar tasks have low success rate",
            )
        )

        # Trigger 2: Complex task
        self.config.triggers.append(
            ResearchTrigger(
                name="complex_task",
                condition=lambda ctx: self._check_task_complexity(ctx),
                priority=3,
                description="Triggered for complex or multi-step tasks",
            )
        )

        # Trigger 3: New domain
        self.config.triggers.append(
            ResearchTrigger(
                name="new_domain",
                condition=lambda ctx: self._check_new_domain(ctx),
                priority=5,
                description="Triggered when task involves unfamiliar domain",
            )
        )

        # Trigger 4: Explicit research request
        self.config.triggers.append(
            ResearchTrigger(
                name="explicit_request",
                condition=lambda ctx: ctx.get("request_research", False),
                priority=5,
                description="Triggered by explicit research request",
            )
        )

    def should_trigger_research(
        self,
        task_context: Dict[str, Any],
    ) -> ResearchDecision:
        """Determine if research should be triggered.

        Args:
            task_context: Context about the task being planned

        Returns:
            Decision about whether to trigger research
        """
        if not self.config.enabled:
            decision = ResearchDecision(
                triggered=False,
                trigger_name=None,
                reason="Research hooks disabled",
                task_context=task_context,
            )
            self.decisions.append(decision)
            return decision

        # Check each trigger
        for trigger in self.config.triggers:
            if not trigger.enabled:
                continue

            try:
                if trigger.condition(task_context):
                    decision = ResearchDecision(
                        triggered=True,
                        trigger_name=trigger.name,
                        reason=trigger.description,
                        task_context=task_context,
                    )
                    self.decisions.append(decision)
                    logger.info(f"Research triggered by '{trigger.name}': {trigger.description}")
                    return decision

            except Exception as e:
                logger.error(f"Trigger '{trigger.name}' failed: {e}")
                continue

        # No triggers fired
        decision = ResearchDecision(
            triggered=False,
            trigger_name=None,
            reason="No triggers matched",
            task_context=task_context,
        )
        self.decisions.append(decision)
        return decision

    def _check_low_success_rate(self, ctx: Dict[str, Any]) -> bool:
        """Check if historical success rate is low."""
        if not self.build_history_integrator:
            return False

        task_desc = ctx.get("description", "")
        category = ctx.get("category")

        return self.build_history_integrator.should_trigger_research(
            task_desc,
            category,
            threshold=0.6,
        )

    def _check_task_complexity(self, ctx: Dict[str, Any]) -> bool:
        """Check if task is complex."""
        # Heuristics for complexity
        description = ctx.get("description", "")

        # Check for complexity indicators
        complexity_keywords = [
            "integrate",
            "refactor",
            "migrate",
            "redesign",
            "architecture",
            "multiple",
            "complex",
        ]

        desc_lower = description.lower()
        matches = sum(1 for kw in complexity_keywords if kw in desc_lower)

        return matches >= 2

    def _check_new_domain(self, ctx: Dict[str, Any]) -> bool:
        """Check if task involves new/unfamiliar domain."""
        if not self.build_history_integrator:
            return False

        task_desc = ctx.get("description", "")
        category = ctx.get("category")

        insights = self.build_history_integrator.get_insights_for_task(
            task_desc,
            category,
        )

        # New domain if we have no historical data
        return insights.total_phases == 0

    def execute_research_phase(
        self,
        task_context: Dict[str, Any],
    ) -> Optional[Any]:
        """Execute a research phase.

        Args:
            task_context: Context about the task

        Returns:
            Research phase result, or None if research failed
        """
        if not self.research_executor:
            logger.warning("No research executor available")
            return None

        try:
            # Import here to avoid circular dependency
            from autopack.phases.research_phase import (
                ResearchPhase,
                ResearchPhaseConfig,
            )

            # Build research queries from task context
            queries = self._build_queries_from_context(task_context)

            # Create research phase
            phase = ResearchPhase(
                phase_id=f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                description=task_context.get("description", "Research phase"),
                config=ResearchPhaseConfig(
                    queries=queries,
                    max_duration_minutes=self.config.max_research_time_minutes,
                    require_human_review=self.config.require_approval,
                ),
            )

            # Execute
            result = self.research_executor.execute(phase)

            logger.info(f"Research phase completed: {result.status.value}")
            return result

        except Exception as e:
            logger.error(f"Research phase execution failed: {e}")
            if self.config.fallback_on_error:
                logger.info("Continuing without research (fallback enabled)")
                return None
            raise

    def _build_queries_from_context(
        self,
        ctx: Dict[str, Any],
    ) -> List[Any]:
        """Build research queries from task context.

        Args:
            ctx: Task context

        Returns:
            List of research queries
        """
        from autopack.phases.research_phase import ResearchQuery

        queries = []

        description = ctx.get("description", "")
        category = ctx.get("category", "")

        # Query 1: Best practices
        queries.append(
            ResearchQuery(
                query=f"What are the best practices for {description}?",
                context={"category": category},
                priority=3,
            )
        )

        # Query 2: Common pitfalls
        queries.append(
            ResearchQuery(
                query=f"What are common pitfalls when {description}?",
                context={"category": category},
                priority=4,
            )
        )

        # Query 3: Implementation approaches
        if category == "IMPLEMENT_FEATURE":
            queries.append(
                ResearchQuery(
                    query=f"What are different approaches to implement {description}?",
                    context={"category": category},
                    priority=5,
                    required=True,
                )
            )

        return queries

    def get_decision_history(self) -> List[ResearchDecision]:
        """Get history of research decisions.

        Returns:
            List of research decisions
        """
        return self.decisions.copy()

    def clear_decision_history(self) -> None:
        """Clear decision history."""
        self.decisions.clear()
