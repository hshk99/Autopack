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
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from ..integrations.build_history_integrator import BuildHistoryIntegrator
    from ..phases.research_phase import (
        ResearchPhaseManager,
        ResearchPriority,
        ResearchQuery,
        create_research_phase_from_task,
    )
    RESEARCH_AVAILABLE = True
except ImportError:
    RESEARCH_AVAILABLE = False

logger = logging.getLogger(__name__)

#
# ---------------------------------------------------------------------------
# Compatibility shims (legacy API)
# ---------------------------------------------------------------------------
#
# Several older tests and historical autonomous runs expect a simpler "hook
# manager" surface:
#   - ResearchHookManager
#   - ResearchTrigger
#   - ResearchHookResult
#
# The newer API in this module is `ResearchHooks` / `ResearchTriggerConfig`.
# These shims are intentionally small and self-contained so we don't destabilize
# the current drain behavior.
#

@dataclass
class ResearchTriggerConfig:
    """Configuration for research trigger conditions."""
    
    # Enable/disable research hooks
    enabled: bool = True

    # Legacy: whether hooks should automatically trigger research when conditions match.
    # (Used by tests/autopack/integration/test_research_end_to_end.py)
    auto_trigger: bool = True

    # Legacy: store these paths on the config object so callers can pass only `config=...`
    # into `ResearchHooks(...)` without separately passing paths.
    build_history_path: Optional[Path] = None
    research_output_dir: Optional[Path] = None
    
    # Success rate threshold below which to trigger research
    success_rate_threshold: float = 0.7
    
    # Minimum number of historical phases to consider patterns
    min_history_size: int = 3
    
    # Keywords that indicate research might be valuable
    complexity_keywords: List[str] = field(default_factory=lambda: [
        "complex", "multiple", "integration", "architecture",
        "design", "evaluate", "compare", "research", "investigate",
        "analyze", "explore", "prototype",
    ])
    
    # Task categories that always trigger research
    always_research_categories: List[str] = field(default_factory=lambda: [
        "ARCHITECTURE_DESIGN",
        "TECHNOLOGY_EVALUATION",
    ])
    
    # Maximum concurrent research phases
    max_concurrent_research: int = 3
    
    # Auto-approve research results with confidence above this threshold
    auto_approve_threshold: float = 0.8


@dataclass
class ResearchTriggerResult:
    """Result of evaluating research trigger conditions."""
    
    should_trigger: bool
    reason: str
    priority: ResearchPriority = ResearchPriority.MEDIUM
    suggested_queries: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ResearchHooks:
    """Provides hooks for triggering research in autonomous mode."""
    
    def __init__(
        self,
        config: Optional[ResearchTriggerConfig] = None,
        build_history_path: Optional[Path] = None,
        research_storage_dir: Optional[Path] = None,
    ):
        """Initialize research hooks.
        
        Args:
            config: Research trigger configuration
            build_history_path: Path to BUILD_HISTORY.md
            research_storage_dir: Directory for research phase storage
        """
        self.config = config or ResearchTriggerConfig()

        # Back-compat: allow callers to supply paths via config only.
        build_history_path = build_history_path or self.config.build_history_path
        research_storage_dir = research_storage_dir or self.config.research_output_dir
        
        if not RESEARCH_AVAILABLE:
            logger.warning("Research system not available, hooks will be disabled")
            self.config.enabled = False
        
        self.history_integrator = None
        self.phase_manager = None
        
        if self.config.enabled:
            try:
                self.history_integrator = BuildHistoryIntegrator(
                    build_history_path=build_history_path,
                )
                self.phase_manager = ResearchPhaseManager(
                    storage_dir=research_storage_dir,
                )
            except Exception as e:
                logger.error(f"Error initializing research hooks: {e}")
                self.config.enabled = False

    # -----------------------------------------------------------------------
    # Compatibility helpers (legacy API expected by integration tests)
    # -----------------------------------------------------------------------

    def should_research(
        self,
        task_description: str,
        task_category: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Legacy boolean helper used by older callers/tests."""
        if not self.config.enabled or not getattr(self.config, "auto_trigger", True):
            return False
        result = self.should_trigger_research(
            task_description=task_description,
            task_category=task_category,
            context=context,
        )
        return bool(result.should_trigger)

    def pre_planning_hook(
        self,
        task_description: str,
        task_category: str,
        planning_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Legacy pre-planning hook: may execute research and attach results to context."""
        if not self.config.enabled or not getattr(self.config, "auto_trigger", True):
            return planning_context

        if not self.should_research(task_description, task_category, planning_context):
            return planning_context

        # Execute an offline-friendly research phase (patched in tests).
        try:
            from ..phases.research_phase import ResearchPhase, ResearchPhaseConfig
        except Exception as e:
            logger.debug("ResearchPhase unavailable for pre_planning_hook: %s", e)
            return planning_context

        try:
            cfg = ResearchPhaseConfig(
                query=task_description,
                max_iterations=3,
                output_dir=self.config.research_output_dir,
                store_results=True,
            )
            phase = ResearchPhase(config=cfg)
            research_result = phase.execute()
        except Exception as e:
            logger.debug("Research execution failed in pre_planning_hook: %s", e)
            return planning_context

        updated = dict(planning_context)
        updated["research_result"] = research_result
        updated["research_findings"] = list(getattr(research_result, "findings", []) or [])
        return updated

    def post_planning_hook(self, plan: Dict[str, Any], planning_context: Dict[str, Any]) -> Dict[str, Any]:
        """Legacy post-planning hook: annotate plan with research metadata."""
        updated_plan = dict(plan)
        research_result = planning_context.get("research_result")
        if not research_result:
            return updated_plan

        session_id = getattr(research_result, "session_id", None)
        confidence = float(getattr(research_result, "confidence_score", 0.0) or 0.0)
        findings = list(getattr(research_result, "findings", []) or [])

        metadata = dict(updated_plan.get("metadata", {}) or {})
        if session_id:
            metadata["research_session_id"] = session_id
        metadata["research_confidence"] = confidence
        metadata["research_findings_count"] = len(findings)
        updated_plan["metadata"] = metadata

        # Provide a human-readable notes field (tests assert it exists).
        updated_plan.setdefault("notes", "")
        if updated_plan["notes"]:
            updated_plan["notes"] += "\n"
        updated_plan["notes"] += "Research attached to planning context."

        return updated_plan
    
    def should_trigger_research(
        self,
        task_description: str,
        task_category: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ResearchTriggerResult:
        """Evaluate if research should be triggered for a task.
        
        Args:
            task_description: Description of the task
            task_category: Category of the task
            context: Additional context about the task
            
        Returns:
            ResearchTriggerResult with decision and reasoning
        """
        if not self.config.enabled:
            return ResearchTriggerResult(
                should_trigger=False,
                reason="Research hooks disabled",
            )
        
        # Check if category always triggers research
        if task_category in self.config.always_research_categories:
            return ResearchTriggerResult(
                should_trigger=True,
                reason=f"Category {task_category} always triggers research",
                priority=ResearchPriority.HIGH,
                suggested_queries=self._generate_queries(task_description, task_category),
            )
        
        # Check for complexity keywords
        description_lower = task_description.lower()
        matched_keywords = [
            kw for kw in self.config.complexity_keywords
            if kw in description_lower
        ]
        
        if matched_keywords:
            return ResearchTriggerResult(
                should_trigger=True,
                reason=f"Complexity indicators found: {', '.join(matched_keywords)}",
                priority=ResearchPriority.MEDIUM,
                suggested_queries=self._generate_queries(task_description, task_category),
                metadata={"matched_keywords": matched_keywords},
            )
        
        # Check build history
        if self.history_integrator:
            try:
                should_trigger, reason = self.history_integrator.should_trigger_research(
                    task_category=task_category,
                    task_description=task_description,
                    threshold=self.config.success_rate_threshold,
                )
                
                if should_trigger:
                    return ResearchTriggerResult(
                        should_trigger=True,
                        reason=f"Build history analysis: {reason}",
                        priority=ResearchPriority.HIGH,
                        suggested_queries=self._generate_queries(task_description, task_category),
                    )
            except Exception as e:
                logger.error(f"Error checking build history: {e}")
        
        return ResearchTriggerResult(
            should_trigger=False,
            reason="No research trigger conditions met",
        )
    
    def trigger_research(
        self,
        task_description: str,
        task_category: str,
        priority: ResearchPriority = ResearchPriority.MEDIUM,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Trigger a research phase for a task.
        
        Args:
            task_description: Description of the task
            task_category: Category of the task
            priority: Priority of the research phase
            context: Additional context for research
            
        Returns:
            Phase ID if research was triggered, None otherwise
        """
        if not self.config.enabled or not self.phase_manager:
            logger.warning("Cannot trigger research: system not available")
            return None
        
        # Check concurrent research limit
        active_phases = self.phase_manager.list_phases()
        in_progress = [p for p in active_phases if p.status.value == "in_progress"]
        
        if len(in_progress) >= self.config.max_concurrent_research:
            logger.warning(
                f"Cannot trigger research: {len(in_progress)} phases already in progress "
                f"(limit: {self.config.max_concurrent_research})"
            )
            return None
        
        try:
            phase = create_research_phase_from_task(
                task_description=task_description,
                task_category=task_category,
                context=context,
            )
            
            logger.info(
                f"Triggered research phase {phase.phase_id} for task: {task_description[:50]}"
            )
            
            return phase.phase_id
        except Exception as e:
            logger.error(f"Error triggering research: {e}")
            return None
    
    def check_research_status(self, phase_id: str) -> Optional[Dict[str, Any]]:
        """Check the status of a research phase.
        
        Args:
            phase_id: ID of the research phase
            
        Returns:
            Status information if phase exists, None otherwise
        """
        if not self.phase_manager:
            return None
        
        phase = self.phase_manager.get_phase(phase_id)
        if not phase:
            return None
        
        return {
            "phase_id": phase.phase_id,
            "status": phase.status.value,
            "title": phase.title,
            "results_count": len(phase.results),
            "created_at": phase.created_at.isoformat(),
            "completed_at": phase.completed_at.isoformat() if phase.completed_at else None,
        }
    
    def get_research_results(self, phase_id: str) -> Optional[Dict[str, Any]]:
        """Get results from a completed research phase.
        
        Args:
            phase_id: ID of the research phase
            
        Returns:
            Research results if available, None otherwise
        """
        if not self.phase_manager:
            return None
        
        phase = self.phase_manager.get_phase(phase_id)
        if not phase or phase.status.value != "completed":
            return None
        
        return {
            "phase_id": phase.phase_id,
            "title": phase.title,
            "description": phase.description,
            "results": [
                {
                    "query": result.query.query_text,
                    "summary": result.summary,
                    "confidence": result.confidence,
                    "findings_count": len(result.findings),
                    "sources": result.sources,
                }
                for result in phase.results
            ],
            "completed_at": phase.completed_at.isoformat() if phase.completed_at else None,
        }
    
    def _generate_queries(self, task_description: str, task_category: str) -> List[str]:
        """Generate suggested research queries for a task."""
        queries = [
            f"Best practices for {task_category}: {task_description}",
            f"Common issues when implementing {task_description}",
            f"Implementation approaches for {task_description}",
        ]
        
        # Add category-specific queries
        if "API" in task_category or "api" in task_description.lower():
            queries.append("API design patterns and best practices")
        
        if "DATABASE" in task_category or "database" in task_description.lower():
            queries.append("Database schema design and optimization")
        
        if "SECURITY" in task_category or "security" in task_description.lower():
            queries.append("Security best practices and common vulnerabilities")
        
        return queries


# Convenience function for autonomous executor integration
def create_research_hook(
    config: Optional[ResearchTriggerConfig] = None,
) -> Callable[[str, str, Optional[Dict[str, Any]]], Optional[str]]:
    """Create a research hook function for autonomous executor.
    
    Args:
        config: Research trigger configuration
        
    Returns:
        Hook function that can be called before task planning
    """
    hooks = ResearchHooks(config=config)
    
    def hook(
        task_description: str,
        task_category: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Hook function that evaluates and triggers research if needed.
        
        Returns:
            Phase ID if research was triggered, None otherwise
        """
        result = hooks.should_trigger_research(
            task_description=task_description,
            task_category=task_category,
            context=context,
        )
        
        if result.should_trigger:
            logger.info(f"Research triggered: {result.reason}")
            return hooks.trigger_research(
                task_description=task_description,
                task_category=task_category,
                priority=result.priority,
                context=context,
            )
        
        return None
    
    return hook


# ---------------------------------------------------------------------------
# Legacy API expected by tests/autopack/autonomous/test_research_hooks.py
# ---------------------------------------------------------------------------


@dataclass
class ResearchHookResult:
    """Legacy result object for research hook evaluation."""

    triggered: bool
    trigger_name: Optional[str] = None
    reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchTrigger:
    """Legacy trigger definition."""

    name: str
    description: str
    condition: Callable[[Dict[str, Any]], bool]
    enabled: bool = True


class ResearchHookManager:
    """Legacy hook manager used by older tests/runs.

    This is intentionally independent from the newer `ResearchHooks` logic.
    The legacy surface is mostly about maintaining a trigger list, recording
    evaluation history, and providing small pre/post hooks for planning.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config: Dict[str, Any] = config or {}
        storage_dir = self.config.get("research_storage_dir")
        self.research_storage_dir = Path(storage_dir) if storage_dir else None
        if self.research_storage_dir:
            self.research_storage_dir.mkdir(parents=True, exist_ok=True)

        self.triggers: List[ResearchTrigger] = []
        self._history: List[Dict[str, Any]] = []
        self._init_default_triggers()

    def _init_default_triggers(self) -> None:
        # Matches expectations in tests.
        self.triggers = [
            ResearchTrigger(
                name="unknown_category",
                description="Trigger when task category is not recognized",
                # Only evaluate if both category and known_categories are present; otherwise
                # this trigger would fire for unrelated contexts and preempt other triggers.
                condition=lambda ctx: (
                    bool(ctx.get("category"))
                    and bool(ctx.get("known_categories"))
                    and str(ctx.get("category", "")).upper()
                    not in [str(c).upper() for c in ctx.get("known_categories", [])]
                ),
            ),
            ResearchTrigger(
                name="high_risk",
                description="Trigger when risk is high/critical",
                condition=lambda ctx: str(ctx.get("risk_level", "")).lower()
                in {"high", "critical"},
            ),
            ResearchTrigger(
                name="low_success_rate",
                description="Trigger when success rate is below threshold",
                condition=lambda ctx: (
                    isinstance(ctx.get("success_rate"), (int, float))
                    and float(ctx["success_rate"]) < 0.5
                ),
            ),
        ]

    def add_trigger(self, trigger: ResearchTrigger) -> None:
        self.triggers.append(trigger)

    def remove_trigger(self, trigger_name: str) -> bool:
        before = len(self.triggers)
        self.triggers = [t for t in self.triggers if t.name != trigger_name]
        return len(self.triggers) != before

    def should_trigger_research(self, context: Dict[str, Any]) -> ResearchHookResult:
        fired: Optional[str] = None
        reason: Optional[str] = None

        for trigger in self.triggers:
            if not trigger.enabled:
                continue
            try:
                if trigger.condition(context):
                    fired = trigger.name
                    reason = trigger.description
                    break
            except Exception as e:
                # Legacy behavior: never crash on trigger evaluation errors.
                logger.debug(
                    "Legacy ResearchHookManager trigger %s error: %s",
                    trigger.name,
                    e,
                )
                continue

        result = ResearchHookResult(
            triggered=fired is not None,
            trigger_name=fired,
            reason=reason,
        )

        self._history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "context": dict(context),
                "triggered": result.triggered,
                "trigger_name": result.trigger_name,
            }
        )
        return result

    def pre_planning_hook(self, task_description: str, task_metadata: Dict[str, Any]) -> Optional[str]:
        result = self.should_trigger_research(task_metadata)
        if not result.triggered:
            return None
        # Create a synthetic research phase id.
        phase_id = f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if self.research_storage_dir:
            try:
                (self.research_storage_dir / f"{phase_id}.json").write_text(
                    json.dumps(
                        {
                            "phase_id": phase_id,
                            "task": task_description,
                            "metadata": task_metadata,
                            "created_at": datetime.now().isoformat(),
                            "trigger": result.trigger_name,
                        },
                        indent=2,
                    )
                )
            except Exception as e:
                logger.debug("Failed to persist legacy research stub: %s", e)
        return phase_id

    def post_research_hook(self, phase_id: str, planning_context: Dict[str, Any]) -> Dict[str, Any]:
        updated = dict(planning_context)
        updated["research_phase_id"] = phase_id
        updated["research_insights"] = {
            "phase_id": phase_id,
            "summary": "Research insights unavailable in legacy stub",
        }
        return updated

    def get_hook_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        if limit is None:
            return list(self._history)
        return list(self._history[-int(limit) :])

    def get_trigger_statistics(self) -> Dict[str, Dict[str, int]]:
        counts: Dict[str, int] = {}
        for entry in self._history:
            name = entry.get("trigger_name")
            if not name:
                continue
            counts[name] = counts.get(name, 0) + 1
        return {name: {"count": count} for name, count in counts.items()}
