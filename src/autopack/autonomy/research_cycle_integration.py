"""Research Cycle Integration for Autopilot.

IMP-AUT-001: Integrates research cycle triggering into the autopilot execution loop.
This module bridges the autopilot controller with the research orchestrator, providing:
- Follow-up research execution with budget enforcement (IMP-RES-002)
- Research outcome feedback to autopilot decisions
- Comprehensive logging and metrics for research triggers

Depends on:
- IMP-RES-002: Budget enforcement
- IMP-HIGH-005: Followup research trigger callbacks
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from .autopilot import AutopilotController
    from .executor_integration import ExecutorContext

from ..research.analysis.budget_enforcement import BudgetEnforcer
from ..research.analysis.followup_trigger import (
    FollowupResearchTrigger,
    FollowupTrigger,
    TriggerAnalysisResult,
    TriggerExecutionResult,
    TriggerPriority,
)

logger = logging.getLogger(__name__)


class ResearchCycleDecision(Enum):
    """Decision outcomes from research cycle analysis."""

    PROCEED = "proceed"  # Continue with current execution plan
    PAUSE_FOR_RESEARCH = "pause_for_research"  # Pause to conduct follow-up research
    ADJUST_PLAN = "adjust_plan"  # Modify execution plan based on findings
    BLOCK = "block"  # Block execution due to critical gaps
    SKIP = "skip"  # Skip research (budget or health constraints)


@dataclass
class ResearchCycleMetrics:
    """Metrics for research cycle execution tracking.

    IMP-AUT-001: Provides comprehensive tracking of research cycle activity
    for monitoring and debugging purposes.

    IMP-TRIGGER-001: Includes callback execution metrics for research
    complete callback observability.
    """

    total_cycles_triggered: int = 0
    successful_cycles: int = 0
    failed_cycles: int = 0
    skipped_budget: int = 0
    skipped_health: int = 0
    total_triggers_detected: int = 0
    total_triggers_executed: int = 0
    total_execution_time_ms: int = 0
    # IMP-TRIGGER-001: Callback execution tracking
    total_callbacks_invoked: int = 0
    total_callbacks_succeeded: int = 0
    total_callbacks_failed: int = 0
    total_callback_time_ms: int = 0
    decisions: Dict[str, int] = field(
        default_factory=lambda: {d.value: 0 for d in ResearchCycleDecision}
    )
    last_cycle_at: Optional[datetime] = None
    budget_at_last_cycle: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "research_cycle_metrics": {
                "total_cycles_triggered": self.total_cycles_triggered,
                "successful_cycles": self.successful_cycles,
                "failed_cycles": self.failed_cycles,
                "skipped_budget": self.skipped_budget,
                "skipped_health": self.skipped_health,
                "total_triggers_detected": self.total_triggers_detected,
                "total_triggers_executed": self.total_triggers_executed,
                "total_execution_time_ms": self.total_execution_time_ms,
                "total_callbacks_invoked": self.total_callbacks_invoked,
                "total_callbacks_succeeded": self.total_callbacks_succeeded,
                "total_callbacks_failed": self.total_callbacks_failed,
                "total_callback_time_ms": self.total_callback_time_ms,
                "decisions": self.decisions,
                "last_cycle_at": self.last_cycle_at.isoformat() if self.last_cycle_at else None,
                "budget_at_last_cycle": self.budget_at_last_cycle,
            }
        }


@dataclass
class ResearchCycleOutcome:
    """Outcome from a research cycle execution.

    IMP-AUT-001: Captures the full result of a research cycle for
    feeding back to autopilot decision-making.
    """

    decision: ResearchCycleDecision
    trigger_result: Optional[TriggerAnalysisResult] = None
    execution_result: Optional[TriggerExecutionResult] = None
    findings: List[Dict[str, Any]] = field(default_factory=list)
    gaps_addressed: int = 0
    gaps_remaining: int = 0
    budget_remaining: float = 1.0
    should_continue_execution: bool = True
    plan_adjustments: List[Dict[str, Any]] = field(default_factory=list)
    reason: str = ""
    cycle_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert outcome to dictionary."""
        return {
            "research_cycle_outcome": {
                "decision": self.decision.value,
                "trigger_result": self.trigger_result.to_dict() if self.trigger_result else None,
                "execution_result": (
                    self.execution_result.to_dict() if self.execution_result else None
                ),
                "findings_count": len(self.findings),
                "gaps_addressed": self.gaps_addressed,
                "gaps_remaining": self.gaps_remaining,
                "budget_remaining": self.budget_remaining,
                "should_continue_execution": self.should_continue_execution,
                "plan_adjustments": self.plan_adjustments,
                "reason": self.reason,
                "cycle_time_ms": self.cycle_time_ms,
            }
        }


class ResearchCycleIntegration:
    """Integrates research cycles into autopilot execution.

    IMP-AUT-001: This class provides the bridge between the autopilot controller
    and the research orchestrator, enabling:
    - Research triggering from autopilot health gates
    - Budget-enforced follow-up research execution
    - Research outcome feedback to autopilot decisions
    - Comprehensive metrics and logging

    Usage:
        ```python
        integration = ResearchCycleIntegration(
            budget_enforcer=budget_enforcer,
            min_budget_threshold=0.2,
        )

        # Execute a research cycle
        outcome = await integration.execute_research_cycle(
            analysis_results=analysis_results,
            executor_ctx=executor_ctx,
        )

        if outcome.decision == ResearchCycleDecision.PAUSE_FOR_RESEARCH:
            # Handle pause for research
            pass
        ```
    """

    # Configuration
    MIN_BUDGET_THRESHOLD = 0.2  # Minimum budget fraction required
    CRITICAL_GAP_THRESHOLD = 3  # Number of critical gaps to trigger BLOCK
    MAX_CYCLES_PER_SESSION = 5  # Prevent infinite research loops

    def __init__(
        self,
        budget_enforcer: Optional[BudgetEnforcer] = None,
        min_budget_threshold: float = 0.2,
        critical_gap_threshold: int = 3,
    ):
        """Initialize research cycle integration.

        Args:
            budget_enforcer: Optional budget enforcer for cost limits
            min_budget_threshold: Minimum budget fraction required for research
            critical_gap_threshold: Number of critical gaps to trigger BLOCK
        """
        self._budget_enforcer = budget_enforcer or BudgetEnforcer(total_budget=5000.0)
        self._min_budget_threshold = min_budget_threshold
        self._critical_gap_threshold = critical_gap_threshold

        # Follow-up trigger instance
        self._followup_trigger = FollowupResearchTrigger()

        # Metrics
        self._metrics = ResearchCycleMetrics()

        # Cycle tracking
        self._cycles_this_session = 0
        self._last_outcome: Optional[ResearchCycleOutcome] = None

        # Callbacks for research completion
        self._completion_callbacks: List[Callable[[ResearchCycleOutcome], None]] = []

        logger.info(
            f"[IMP-AUT-001] ResearchCycleIntegration initialized: "
            f"min_budget={min_budget_threshold:.0%}, "
            f"critical_gap_threshold={critical_gap_threshold}"
        )

    # === Budget Integration (IMP-RES-002) ===

    def can_proceed_with_research(self, phase_name: str = "followup_research") -> bool:
        """Check if research can proceed based on budget constraints.

        IMP-RES-002: Integrates with BudgetEnforcer to check if follow-up
        research should be allowed given current budget state.

        Args:
            phase_name: Name of the research phase

        Returns:
            True if budget allows research, False otherwise
        """
        if not self._budget_enforcer.can_proceed(phase_name):
            logger.warning(
                f"[IMP-RES-002] Research blocked: budget exhausted for phase '{phase_name}'"
            )
            self._metrics.skipped_budget += 1
            return False

        # Also check the minimum threshold
        metrics = self._budget_enforcer.get_metrics()
        utilization = metrics.utilization_percent / 100.0
        remaining = 1.0 - utilization

        if remaining < self._min_budget_threshold:
            logger.warning(
                f"[IMP-RES-002] Research blocked: budget remaining ({remaining:.0%}) "
                f"below threshold ({self._min_budget_threshold:.0%})"
            )
            self._metrics.skipped_budget += 1
            return False

        return True

    def get_budget_remaining(self) -> float:
        """Get remaining budget fraction.

        Returns:
            Fraction of budget remaining (0.0 to 1.0)
        """
        metrics = self._budget_enforcer.get_metrics()
        if metrics.total_budget == 0:
            return 0.0
        utilization = metrics.utilization_percent / 100.0
        return max(0.0, 1.0 - utilization)

    def record_research_cost(self, phase_name: str, cost: float) -> None:
        """Record cost for a research phase.

        Args:
            phase_name: Name of the research phase
            cost: Cost amount to record
        """
        self._budget_enforcer.record_cost(phase_name, cost)
        logger.debug(f"[IMP-RES-002] Recorded research cost: {phase_name}=${cost:.2f}")

    # === Research Cycle Execution ===

    async def execute_research_cycle(
        self,
        analysis_results: Dict[str, Any],
        validation_results: Optional[Dict[str, Any]] = None,
        executor_ctx: Optional["ExecutorContext"] = None,
        autopilot: Optional["AutopilotController"] = None,
    ) -> ResearchCycleOutcome:
        """Execute a full research cycle with budget enforcement.

        IMP-AUT-001: Main entry point for research cycle execution.
        Analyzes findings, checks budget, executes callbacks, and
        determines the decision for autopilot.

        Args:
            analysis_results: Results from analysis phase
            validation_results: Optional validation results
            executor_ctx: Optional executor context for budget/health checking
            autopilot: Optional autopilot controller for state access

        Returns:
            ResearchCycleOutcome with decision and findings
        """
        start_time = time.time()
        self._cycles_this_session += 1
        self._metrics.total_cycles_triggered += 1
        self._metrics.last_cycle_at = datetime.now(timezone.utc)

        logger.info(f"[IMP-AUT-001] Starting research cycle #{self._cycles_this_session}")

        # Check if we've exceeded max cycles
        if self._cycles_this_session > self.MAX_CYCLES_PER_SESSION:
            logger.warning(
                f"[IMP-AUT-001] Max research cycles ({self.MAX_CYCLES_PER_SESSION}) "
                "exceeded for session"
            )
            return self._create_skip_outcome(
                reason=f"Max cycles ({self.MAX_CYCLES_PER_SESSION}) exceeded",
                cycle_time_ms=int((time.time() - start_time) * 1000),
            )

        # Check health gate from autopilot if available
        if autopilot and autopilot.is_task_generation_paused():
            logger.info(
                f"[IMP-AUT-001] Research cycle skipped: task generation paused "
                f"({autopilot.get_pause_reason()})"
            )
            self._metrics.skipped_health += 1
            return self._create_skip_outcome(
                reason=f"Task generation paused: {autopilot.get_pause_reason()}",
                cycle_time_ms=int((time.time() - start_time) * 1000),
            )

        # Check circuit breaker from executor context
        if executor_ctx and not executor_ctx.circuit_breaker.is_available():
            logger.warning(
                f"[IMP-AUT-001] Research cycle skipped: circuit breaker "
                f"{executor_ctx.circuit_breaker.state.value}"
            )
            self._metrics.skipped_health += 1
            return self._create_skip_outcome(
                reason=f"Circuit breaker {executor_ctx.circuit_breaker.state.value}",
                cycle_time_ms=int((time.time() - start_time) * 1000),
            )

        # Check budget before proceeding
        if not self.can_proceed_with_research():
            return self._create_skip_outcome(
                reason="Budget constraints",
                cycle_time_ms=int((time.time() - start_time) * 1000),
            )

        # Record budget state
        self._metrics.budget_at_last_cycle = self.get_budget_remaining()

        # Start budget phase tracking
        self._budget_enforcer.start_phase("followup_research")

        try:
            # Analyze for triggers
            trigger_result = self._followup_trigger.analyze(
                analysis_results=analysis_results,
                validation_results=validation_results,
            )

            self._metrics.total_triggers_detected += trigger_result.triggers_detected

            if not trigger_result.should_research:
                logger.info("[IMP-AUT-001] No follow-up research needed")
                self._budget_enforcer.complete_phase("followup_research", actual_cost=10.0)
                return self._create_proceed_outcome(
                    trigger_result=trigger_result,
                    reason="No triggers requiring research",
                    cycle_time_ms=int((time.time() - start_time) * 1000),
                )

            logger.info(
                f"[IMP-AUT-001] {trigger_result.triggers_selected} triggers selected "
                f"for follow-up research"
            )

            # Execute callbacks for selected triggers
            execution_result = await self._followup_trigger.execute_triggers_async(
                triggers=trigger_result.selected_triggers,
                max_concurrent=3,
            )

            trigger_result.execution_result = execution_result
            self._metrics.total_triggers_executed += execution_result.triggers_executed

            # IMP-TRIGGER-001: Record callback execution metrics
            self._metrics.total_callbacks_invoked += execution_result.callbacks_invoked
            self._metrics.total_callbacks_succeeded += execution_result.successful_executions
            self._metrics.total_callbacks_failed += execution_result.failed_executions
            self._metrics.total_callback_time_ms += execution_result.total_execution_time_ms

            logger.debug(
                f"[IMP-TRIGGER-001] Callback execution complete: "
                f"{execution_result.successful_executions} succeeded, "
                f"{execution_result.failed_executions} failed, "
                f"{execution_result.total_execution_time_ms}ms total time"
            )

            # Determine decision based on results
            outcome = self._determine_decision(
                trigger_result=trigger_result,
                execution_result=execution_result,
                analysis_results=analysis_results,
            )

            outcome.cycle_time_ms = int((time.time() - start_time) * 1000)
            self._metrics.total_execution_time_ms += outcome.cycle_time_ms

            # Record success/failure
            if execution_result.successful_executions > 0:
                self._metrics.successful_cycles += 1
            else:
                self._metrics.failed_cycles += 1

            # Update decision metrics
            self._metrics.decisions[outcome.decision.value] += 1

            # Calculate research cost based on triggers executed
            estimated_cost = 50.0 + (execution_result.triggers_executed * 30.0)
            self._budget_enforcer.complete_phase("followup_research", actual_cost=estimated_cost)

            # Store outcome
            self._last_outcome = outcome

            # Invoke completion callbacks
            await self._invoke_completion_callbacks(outcome)

            logger.info(
                f"[IMP-AUT-001] Research cycle complete: decision={outcome.decision.value}, "
                f"triggers_executed={execution_result.triggers_executed}, "
                f"time={outcome.cycle_time_ms}ms"
            )

            return outcome

        except Exception as e:
            logger.error(f"[IMP-AUT-001] Research cycle failed: {e}")
            self._metrics.failed_cycles += 1
            self._budget_enforcer.complete_phase("followup_research", actual_cost=20.0)
            return self._create_error_outcome(
                error=str(e),
                cycle_time_ms=int((time.time() - start_time) * 1000),
            )

    def execute_research_cycle_sync(
        self,
        analysis_results: Dict[str, Any],
        validation_results: Optional[Dict[str, Any]] = None,
        executor_ctx: Optional["ExecutorContext"] = None,
        autopilot: Optional["AutopilotController"] = None,
    ) -> ResearchCycleOutcome:
        """Synchronous wrapper for execute_research_cycle.

        Args:
            analysis_results: Results from analysis phase
            validation_results: Optional validation results
            executor_ctx: Optional executor context
            autopilot: Optional autopilot controller

        Returns:
            ResearchCycleOutcome with decision and findings
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(
            self.execute_research_cycle(
                analysis_results=analysis_results,
                validation_results=validation_results,
                executor_ctx=executor_ctx,
                autopilot=autopilot,
            )
        )

    def _determine_decision(
        self,
        trigger_result: TriggerAnalysisResult,
        execution_result: TriggerExecutionResult,
        analysis_results: Dict[str, Any],
    ) -> ResearchCycleOutcome:
        """Determine autopilot decision based on research results.

        IMP-AUT-001: Analyzes trigger and execution results to determine
        the appropriate decision for autopilot.

        Args:
            trigger_result: Result from trigger analysis
            execution_result: Result from callback execution
            analysis_results: Original analysis results

        Returns:
            ResearchCycleOutcome with decision
        """
        findings = execution_result.integrated_findings
        gaps_addressed = execution_result.successful_executions
        gaps_remaining = trigger_result.triggers_detected - gaps_addressed

        # Count critical priority triggers
        critical_count = sum(
            1 for t in trigger_result.selected_triggers if t.priority == TriggerPriority.CRITICAL
        )

        # Determine decision
        decision: ResearchCycleDecision
        should_continue = True
        plan_adjustments: List[Dict[str, Any]] = []
        reason = ""

        # Check for critical gaps that warrant blocking
        if critical_count >= self._critical_gap_threshold:
            decision = ResearchCycleDecision.BLOCK
            should_continue = False
            reason = f"{critical_count} critical gaps require resolution"
            logger.warning(f"[IMP-AUT-001] BLOCK decision: {reason}")

        # Check if we have significant new findings that require plan adjustment
        elif len(findings) >= 3:
            decision = ResearchCycleDecision.ADJUST_PLAN
            should_continue = True
            reason = f"{len(findings)} findings warrant plan adjustment"

            # Generate plan adjustments based on findings
            plan_adjustments = self._generate_plan_adjustments(findings, analysis_results)
            logger.info(f"[IMP-AUT-001] ADJUST_PLAN decision: {reason}")

        # Check if research is ongoing and needs more time
        elif execution_result.failed_executions > execution_result.successful_executions:
            decision = ResearchCycleDecision.PAUSE_FOR_RESEARCH
            should_continue = False
            reason = "Research incomplete due to failures"
            logger.info(f"[IMP-AUT-001] PAUSE_FOR_RESEARCH decision: {reason}")

        # Otherwise proceed with execution
        else:
            decision = ResearchCycleDecision.PROCEED
            should_continue = True
            reason = "Research complete, no critical issues"
            logger.info(f"[IMP-AUT-001] PROCEED decision: {reason}")

        return ResearchCycleOutcome(
            decision=decision,
            trigger_result=trigger_result,
            execution_result=execution_result,
            findings=findings,
            gaps_addressed=gaps_addressed,
            gaps_remaining=gaps_remaining,
            budget_remaining=self.get_budget_remaining(),
            should_continue_execution=should_continue,
            plan_adjustments=plan_adjustments,
            reason=reason,
        )

    def _generate_plan_adjustments(
        self,
        findings: List[Dict[str, Any]],
        analysis_results: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Generate plan adjustments based on research findings.

        Args:
            findings: Research findings from callbacks
            analysis_results: Original analysis results

        Returns:
            List of plan adjustment recommendations
        """
        adjustments = []

        for finding in findings:
            if not finding:
                continue

            # Check for risk adjustments
            if finding.get("risk_level") == "high":
                adjustments.append(
                    {
                        "type": "risk_mitigation",
                        "description": finding.get("summary", "High risk finding"),
                        "action": "add_safety_check",
                        "priority": "high",
                    }
                )

            # Check for dependency updates
            if finding.get("dependency_change"):
                adjustments.append(
                    {
                        "type": "dependency_update",
                        "description": f"Update dependency: {finding.get('dependency_name', 'unknown')}",
                        "action": "update_requirements",
                        "priority": "medium",
                    }
                )

            # Check for scope changes
            if finding.get("scope_impact"):
                adjustments.append(
                    {
                        "type": "scope_adjustment",
                        "description": finding.get("scope_impact", "Scope change needed"),
                        "action": "review_scope",
                        "priority": "medium",
                    }
                )

        return adjustments

    def _create_skip_outcome(
        self,
        reason: str,
        cycle_time_ms: int,
    ) -> ResearchCycleOutcome:
        """Create a SKIP outcome."""
        self._metrics.decisions[ResearchCycleDecision.SKIP.value] += 1
        return ResearchCycleOutcome(
            decision=ResearchCycleDecision.SKIP,
            budget_remaining=self.get_budget_remaining(),
            should_continue_execution=True,
            reason=reason,
            cycle_time_ms=cycle_time_ms,
        )

    def _create_proceed_outcome(
        self,
        trigger_result: TriggerAnalysisResult,
        reason: str,
        cycle_time_ms: int,
    ) -> ResearchCycleOutcome:
        """Create a PROCEED outcome."""
        self._metrics.decisions[ResearchCycleDecision.PROCEED.value] += 1
        return ResearchCycleOutcome(
            decision=ResearchCycleDecision.PROCEED,
            trigger_result=trigger_result,
            budget_remaining=self.get_budget_remaining(),
            should_continue_execution=True,
            reason=reason,
            cycle_time_ms=cycle_time_ms,
        )

    def _create_error_outcome(
        self,
        error: str,
        cycle_time_ms: int,
    ) -> ResearchCycleOutcome:
        """Create an error outcome (maps to SKIP)."""
        self._metrics.decisions[ResearchCycleDecision.SKIP.value] += 1
        return ResearchCycleOutcome(
            decision=ResearchCycleDecision.SKIP,
            budget_remaining=self.get_budget_remaining(),
            should_continue_execution=True,
            reason=f"Error: {error}",
            cycle_time_ms=cycle_time_ms,
        )

    # === Callback Registration ===

    def register_trigger_callback(
        self,
        callback: Callable[[FollowupTrigger], Optional[Dict[str, Any]]],
    ) -> None:
        """Register a callback for trigger execution.

        Args:
            callback: Function that handles a trigger and returns findings
        """
        self._followup_trigger.register_callback(callback)
        logger.debug(
            f"[IMP-AUT-001] Registered trigger callback "
            f"(total: {self._followup_trigger.get_callback_count()})"
        )

    def register_async_trigger_callback(
        self,
        callback: Callable[[FollowupTrigger], "asyncio.Future[Optional[Dict[str, Any]]]"],
    ) -> None:
        """Register an async callback for trigger execution.

        Args:
            callback: Async function that handles a trigger and returns findings
        """
        self._followup_trigger.register_async_callback(callback)
        logger.debug(
            f"[IMP-AUT-001] Registered async trigger callback "
            f"(total: {self._followup_trigger.get_callback_count()})"
        )

    def register_completion_callback(
        self,
        callback: Callable[[ResearchCycleOutcome], None],
    ) -> None:
        """Register a callback to be invoked when a research cycle completes.

        Args:
            callback: Function that receives the cycle outcome
        """
        self._completion_callbacks.append(callback)
        logger.debug(
            f"[IMP-AUT-001] Registered completion callback "
            f"(total: {len(self._completion_callbacks)})"
        )

    async def _invoke_completion_callbacks(self, outcome: ResearchCycleOutcome) -> None:
        """Invoke all completion callbacks."""
        for callback in self._completion_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(outcome)
                else:
                    callback(outcome)
            except Exception as e:
                logger.warning(f"[IMP-AUT-001] Completion callback failed: {e}")

    # === Metrics and State ===

    def get_metrics(self) -> ResearchCycleMetrics:
        """Get current research cycle metrics.

        Returns:
            ResearchCycleMetrics with current state
        """
        return self._metrics

    def get_last_outcome(self) -> Optional[ResearchCycleOutcome]:
        """Get the last research cycle outcome.

        Returns:
            Last ResearchCycleOutcome or None
        """
        return self._last_outcome

    def get_budget_status(self) -> Dict[str, Any]:
        """Get budget status summary.

        Returns:
            Dictionary with budget information
        """
        return self._budget_enforcer.get_status_summary()

    def reset_session(self) -> None:
        """Reset session state for a new autopilot session."""
        self._cycles_this_session = 0
        self._last_outcome = None
        logger.debug("[IMP-AUT-001] Session state reset")


def create_research_cycle_integration(
    budget_enforcer: Optional[BudgetEnforcer] = None,
    min_budget_threshold: float = 0.2,
) -> ResearchCycleIntegration:
    """Create a ResearchCycleIntegration instance.

    Factory function for creating the integration with default configuration.

    Args:
        budget_enforcer: Optional budget enforcer
        min_budget_threshold: Minimum budget fraction for research

    Returns:
        Configured ResearchCycleIntegration
    """
    return ResearchCycleIntegration(
        budget_enforcer=budget_enforcer,
        min_budget_threshold=min_budget_threshold,
    )
