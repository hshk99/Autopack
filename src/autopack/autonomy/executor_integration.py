"""BUILD-181 Executor Integration - Wiring into Autopilot Hot Path.

This module integrates BUILD-181 executor modules into the autonomy loop:
- Usage accounting for budget tracking
- Safety profile derivation for governance gates
- Scope reduction flow for stuck handling
- Patch correction for 422 errors
- Coverage metrics for CI result processing
- Approval service for pivot-impacting changes

Usage:
    from autopack.autonomy.executor_integration import ExecutorContext

    ctx = ExecutorContext(anchor=anchor, layout=layout)
    ctx.record_usage_event(tokens_used=500)
    ctx.check_budget_and_handle_stuck(...)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ..approvals.service import (
    ApprovalRequest,
    ApprovalResult,
    ApprovalService,
    ApprovalTriggerReason,
    get_approval_service,
    should_trigger_approval,
)
from ..executor.circuit_breaker import CircuitBreaker
from ..executor.coverage_metrics import (
    CoverageInfo,
    compute_coverage_info,
    format_coverage_for_display,
    should_trust_coverage,
)
from ..executor.patch_correction import (
    CorrectedPatchResult,
    PatchCorrectionTracker,
    should_attempt_patch_correction,
)
from ..executor.safety_profile import SafetyProfile, derive_safety_profile, requires_elevated_review
from ..executor.scope_reduction_flow import (
    ScopeReductionProposal,
    generate_scope_reduction_proposal,
    write_scope_reduction_proposal,
)
from ..executor.usage_accounting import (
    UsageEvent,
    UsageTotals,
    aggregate_usage,
    compute_budget_remaining,
    save_usage_events,
)
from ..stuck_handling import StuckHandlingPolicy, StuckReason, StuckResolutionDecision

if TYPE_CHECKING:
    from ..file_layout import RunFileLayout
    from ..intention_anchor.v2 import IntentionAnchorV2

logger = logging.getLogger(__name__)


class ExecutorContext:
    """Context for BUILD-181 executor integration.

    Aggregates all executor concerns into a single context object
    that can be passed through the autopilot loop.
    """

    def __init__(
        self,
        anchor: "IntentionAnchorV2",
        layout: "RunFileLayout",
        stuck_policy: Optional[StuckHandlingPolicy] = None,
    ):
        """Initialize executor context.

        Args:
            anchor: IntentionAnchorV2 guiding execution
            layout: RunFileLayout for artifact paths
            stuck_policy: Optional stuck handling policy (uses default if None)
        """
        self.anchor = anchor
        self.layout = layout
        self.stuck_policy = stuck_policy or StuckHandlingPolicy()

        # Usage tracking
        self._usage_events: List[UsageEvent] = []
        self._usage_totals: Optional[UsageTotals] = None

        # IMP-RESEARCH-001: Budget enforcement tracking
        self._budget_warnings_issued: set = set()  # Track which thresholds we've warned about

        # Patch correction tracking
        self._patch_tracker = PatchCorrectionTracker()

        # IMP-HIGH-001: Circuit breaker for runaway protection
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            reset_timeout_seconds=300,
            half_open_max_calls=1,
            health_threshold=0.5,
        )

        # Approval service (lazy initialized)
        self._approval_service: Optional[ApprovalService] = None

        # Derived values (cached)
        self._safety_profile: Optional[SafetyProfile] = None

        # Phase state tracking
        self._current_phase_id: str = "init"
        self._iterations_used: int = 0
        self._escalations_used: int = 0
        self._consecutive_failures: int = 0
        self._replan_attempted: bool = False

        # IMP-TRIGGER-001: Health transition tracking for task regeneration
        self._health_states: Dict[str, bool] = (
            {}
        )  # Track provider health states for transition detection
        self._last_health_transition: Optional[datetime] = None
        self._health_transition_count: int = 0

        # IMP-RESEARCH-002: Research gap detection and pause tracking
        self._gap_detection_count: int = 0
        self._gap_pause_count: int = 0
        self._total_gaps_detected: int = 0
        self._total_gaps_addressed: int = 0
        self._last_gap_pause_details: Optional[Dict[str, Any]] = None
        self._gap_pause_history: List[Dict[str, Any]] = []

        logger.debug(
            f"[ExecutorContext] Initialized for project={anchor.project_id}, run={layout.run_id}. "
            f"[IMP-HIGH-001] Circuit breaker initialized with failure_threshold={self.circuit_breaker.failure_threshold}"
        )

    # === Safety Profile ===

    @property
    def safety_profile(self) -> SafetyProfile:
        """Get safety profile derived from anchor.

        Returns:
            SafetyProfile: "strict" or "normal"
        """
        if self._safety_profile is None:
            self._safety_profile = derive_safety_profile(self.anchor)
            logger.debug(f"[ExecutorContext] Safety profile: {self._safety_profile}")
        return self._safety_profile

    @property
    def is_strict(self) -> bool:
        """Check if strict safety profile applies."""
        return self.safety_profile == "strict"

    @property
    def needs_elevated_review(self) -> bool:
        """Check if elevated review is required."""
        return requires_elevated_review(self.anchor)

    # === Usage Accounting ===

    def record_usage_event(
        self,
        tokens_used: int = 0,
        context_chars_used: int = 0,
        sot_chars_used: int = 0,
        event_id: Optional[str] = None,
    ) -> UsageEvent:
        """Record a usage event.

        Args:
            tokens_used: Tokens consumed
            context_chars_used: Context characters loaded
            sot_chars_used: SOT characters retrieved
            event_id: Optional unique ID (auto-generated if None)

        Returns:
            The recorded UsageEvent
        """
        if event_id is None:
            event_id = f"evt-{uuid.uuid4().hex[:8]}"

        event = UsageEvent(
            event_id=event_id,
            timestamp=datetime.now(timezone.utc),
            tokens_used=tokens_used,
            context_chars_used=context_chars_used,
            sot_chars_used=sot_chars_used,
        )
        self._usage_events.append(event)

        # Invalidate cached totals
        self._usage_totals = None

        logger.debug(
            f"[ExecutorContext] Recorded usage event {event_id}: "
            f"tokens={tokens_used}, context={context_chars_used}, sot={sot_chars_used}"
        )
        return event

    @property
    def usage_totals(self) -> UsageTotals:
        """Get aggregated usage totals."""
        if self._usage_totals is None:
            self._usage_totals = aggregate_usage(self._usage_events)
        return self._usage_totals

    def get_budget_remaining(self) -> float:
        """Compute remaining budget fraction.

        Uses caps from anchor's budget_cost pivot.

        Returns:
            Fraction remaining (0.0 to 1.0)
        """
        totals = self.usage_totals

        # Get caps from anchor
        token_cap: Optional[int] = None
        context_cap: Optional[int] = None

        if self.anchor.pivot_intentions.budget_cost:
            budget = self.anchor.pivot_intentions.budget_cost
            token_cap = budget.token_cap_global
            # Context cap not directly in budget_cost, use None

        return compute_budget_remaining(totals, token_cap, context_cap)

    def can_proceed(self, phase_name: Optional[str] = None) -> bool:
        """Check if research can proceed based on budget constraints.

        IMP-COST-001: Implements BudgetTracker protocol for research budget enforcement.

        IMP-HIGH-001: Also checks circuit breaker state to block runaway execution.

        Args:
            phase_name: Optional name of phase to check budget for

        Returns:
            True if budget allows proceeding, False if exhausted or circuit open
        """
        # IMP-HIGH-001: Check circuit breaker first
        if not self.circuit_breaker.is_available():
            logger.warning(
                f"[IMP-HIGH-001] Execution blocked: circuit breaker is {self.circuit_breaker.state.value}. "
                f"Consecutive failures: {self.circuit_breaker.consecutive_failures}/{self.circuit_breaker.failure_threshold}"
            )
            return False

        budget_remaining = self.get_budget_remaining()
        # Allow proceeding if at least 5% of budget remains
        can_proceed = budget_remaining >= 0.05
        if not can_proceed and phase_name:
            logger.warning(
                f"[IMP-COST-001] Budget threshold reached for phase '{phase_name}': "
                f"{budget_remaining:.1%} remaining"
            )
        return can_proceed

    def get_budget_status(self) -> Dict[str, Any]:
        """Get detailed budget status including warnings.

        IMP-RESEARCH-001: Provides comprehensive budget status with thresholds.
        Tracks warnings at 75% and 90% utilization to prevent spam.

        Returns:
            Dictionary with budget status information
        """
        budget_remaining = self.get_budget_remaining()
        budget_used = 1.0 - budget_remaining
        budget_used_percent = budget_used * 100.0

        status_dict = {
            "budget_remaining_fraction": budget_remaining,
            "budget_used_fraction": budget_used,
            "budget_used_percent": round(budget_used_percent, 2),
            "usage_totals": (
                self.usage_totals.to_dict() if hasattr(self.usage_totals, "to_dict") else None
            ),
            "can_proceed": self.can_proceed(),
        }

        # IMP-RESEARCH-001: Issue warnings at thresholds
        self._check_budget_thresholds(budget_used_percent)

        return status_dict

    def _check_budget_thresholds(self, budget_used_percent: float) -> None:
        """Check budget thresholds and issue warnings.

        IMP-RESEARCH-001: Issues warnings at 75% and 90% budget utilization.
        Tracks warnings to avoid duplicate messages.

        Args:
            budget_used_percent: Percentage of budget used (0-100)
        """
        if budget_used_percent >= 90 and "90%" not in self._budget_warnings_issued:
            logger.warning(
                f"[IMP-RESEARCH-001] CRITICAL: Research budget 90% exhausted ({budget_used_percent:.1f}% used). "
                f"Prepare to halt research or escalate as configured."
            )
            self._budget_warnings_issued.add("90%")

        elif budget_used_percent >= 75 and "75%" not in self._budget_warnings_issued:
            logger.warning(
                f"[IMP-RESEARCH-001] WARNING: Research budget 75% spent ({budget_used_percent:.1f}% used). "
                f"Consider pausing non-critical research operations."
            )
            self._budget_warnings_issued.add("75%")

    def enforce_budget_policy(
        self,
        proposed_cost: float = 0,
    ) -> bool:
        """Enforce budget cost escalation policy.

        IMP-RESEARCH-001: Checks cost_escalation_policy from anchor and applies it.

        Args:
            proposed_cost: Estimated cost of proposed operation (in budget units)

        Returns:
            True if operation should proceed, False if blocked
        """
        budget_remaining = self.get_budget_remaining()

        # If no budget cap set, allow proceeding
        if budget_remaining is None:
            return True

        # Get cost escalation policy from anchor
        policy = "request_approval"  # Default
        if self.anchor.pivot_intentions and self.anchor.pivot_intentions.budget_cost:
            policy = self.anchor.pivot_intentions.budget_cost.cost_escalation_policy

        # Check if we have sufficient budget
        if budget_remaining > 0.05:  # More than 5% remaining
            return True

        # Budget is low - enforce policy
        if policy == "block":
            logger.error(
                f"[IMP-RESEARCH-001] Budget enforcement: BLOCK policy active. "
                f"Research operation blocked due to insufficient budget ({budget_remaining:.1%} remaining)."
            )
            return False

        elif policy == "warn":
            logger.warning(
                f"[IMP-RESEARCH-001] Budget enforcement: WARN policy active. "
                f"Proceeding with caution ({budget_remaining:.1%} remaining)."
            )
            return True

        elif policy == "request_approval":
            logger.warning(
                f"[IMP-RESEARCH-001] Budget enforcement: REQUEST_APPROVAL policy active. "
                f"Approval may be required for research operations ({budget_remaining:.1%} remaining)."
            )
            return True

        return True

    def save_usage_events(self) -> Path:
        """Save usage events to run-local artifact.

        Returns:
            Path to saved file
        """
        artifact_path = self.layout.base_dir / "usage" / "usage_events.json"
        save_usage_events(self._usage_events, artifact_path)
        logger.info(f"[ExecutorContext] Saved {len(self._usage_events)} usage events")
        return artifact_path

    # === Stuck Handling with Scope Reduction ===

    def set_phase(
        self,
        phase_id: str,
        reset_counters: bool = True,
    ) -> None:
        """Set current phase and optionally reset counters.

        Args:
            phase_id: Phase identifier
            reset_counters: Whether to reset iteration/failure counters
        """
        self._current_phase_id = phase_id
        if reset_counters:
            self._iterations_used = 0
            self._consecutive_failures = 0
            self._replan_attempted = False
            # Note: escalations_used is NOT reset per-phase by default
        logger.debug(f"[ExecutorContext] Set phase: {phase_id}")

    def record_iteration(self) -> None:
        """Record an iteration in current phase."""
        self._iterations_used += 1

    def record_failure(self) -> None:
        """Record a consecutive failure.

        IMP-HIGH-001: Also records with circuit breaker for runaway protection.
        """
        self._consecutive_failures += 1
        self.circuit_breaker.record_failure()
        logger.debug(
            f"[IMP-HIGH-001] Failure recorded: {self._consecutive_failures} consecutive failures, "
            f"circuit breaker state: {self.circuit_breaker.state.value}"
        )

    def reset_failures(self) -> None:
        """Reset consecutive failure count (after success).

        IMP-HIGH-001: Also records success with circuit breaker for recovery tracking.
        """
        self._consecutive_failures = 0
        self.circuit_breaker.record_success()
        logger.debug(
            f"[IMP-HIGH-001] Success recorded: circuit breaker state: {self.circuit_breaker.state.value}"
        )

    def record_replan(self) -> None:
        """Record that replan was attempted."""
        self._replan_attempted = True

    def record_escalation(self) -> None:
        """Record a model escalation."""
        self._escalations_used += 1

    def handle_stuck(
        self,
        reason: StuckReason,
        current_tasks: Optional[List[str]] = None,
    ) -> tuple[StuckResolutionDecision, Optional[ScopeReductionProposal]]:
        """Handle stuck situation with potential scope reduction.

        Args:
            reason: Why we're stuck
            current_tasks: Current task scope (for scope reduction)

        Returns:
            Tuple of (decision, scope_reduction_proposal if REDUCE_SCOPE)
        """
        budget_remaining = self.get_budget_remaining()

        decision = self.stuck_policy.decide(
            reason=reason,
            iterations_used=self._iterations_used,
            budget_remaining=budget_remaining,
            escalations_used=self._escalations_used,
            consecutive_failures=self._consecutive_failures,
            replan_attempted=self._replan_attempted,
        )

        logger.info(
            f"[ExecutorContext] Stuck handling: reason={reason.value}, "
            f"decision={decision.value}, budget={budget_remaining:.1%}"
        )

        # Generate scope reduction proposal if that's the decision
        proposal: Optional[ScopeReductionProposal] = None
        if decision == StuckResolutionDecision.REDUCE_SCOPE and current_tasks:
            proposal = generate_scope_reduction_proposal(
                run_id=self.layout.run_id,
                phase_id=self._current_phase_id,
                anchor=self.anchor,
                current_scope=current_tasks,
                budget_remaining=budget_remaining,
            )
            # Write proposal to artifact
            write_scope_reduction_proposal(self.layout, proposal)
            logger.info(
                f"[ExecutorContext] Generated scope reduction proposal: "
                f"{proposal.proposal_id}, dropping {len(proposal.dropped_items)} items"
            )

        return decision, proposal

    # === Patch Correction ===

    def attempt_patch_correction(
        self,
        original_patch: str,
        http_422_detail: Dict[str, Any],
    ) -> CorrectedPatchResult:
        """Attempt one-shot patch correction for 422 error.

        Uses PatchCorrectionTracker to enforce max 1 attempt per event.

        Args:
            original_patch: Original patch that failed
            http_422_detail: Error detail from HTTP 422

        Returns:
            CorrectedPatchResult with outcome
        """
        budget_remaining = self.get_budget_remaining()

        # Check if we should attempt
        if not should_attempt_patch_correction(http_422_detail, budget_remaining):
            return CorrectedPatchResult(
                attempted=False,
                original_patch=original_patch,
                error_detail=http_422_detail,
                blocked_reason="budget_or_empty_error",
            )

        # Attempt with tracking
        context = {
            "run_id": self.layout.run_id,
            "phase_id": self._current_phase_id,
        }
        result = self._patch_tracker.attempt_correction(
            original_patch=original_patch,
            validator_error_detail=http_422_detail,
            context=context,
        )

        logger.info(
            f"[ExecutorContext] Patch correction: attempted={result.attempted}, "
            f"successful={result.correction_successful}"
        )
        return result

    # === Coverage Metrics ===

    def process_ci_result(
        self,
        ci_result: Optional[Dict[str, Any]],
    ) -> CoverageInfo:
        """Process CI result and extract coverage info.

        Returns None for delta when unknown, never 0.0.

        Args:
            ci_result: CI result dictionary

        Returns:
            CoverageInfo with explicit status
        """
        info = compute_coverage_info(ci_result)

        if info.status == "unknown":
            logger.debug("[ExecutorContext] Coverage data unknown")
        else:
            logger.debug(
                f"[ExecutorContext] Coverage: delta={info.delta}, "
                f"baseline={info.baseline}, current={info.current}"
            )

        return info

    def format_coverage(self, ci_result: Optional[Dict[str, Any]]) -> str:
        """Format coverage for human display."""
        return format_coverage_for_display(ci_result)

    def can_trust_coverage(self, ci_result: Optional[Dict[str, Any]]) -> bool:
        """Check if coverage data can be trusted for decisions."""
        return should_trust_coverage(ci_result)

    # === IMP-AUTO-001: Research Integration ===

    def should_trigger_followup_research(
        self,
        analysis_results: Optional[Dict[str, Any]] = None,
        validation_results: Optional[Dict[str, Any]] = None,
        min_budget_threshold: float = 0.2,
    ) -> bool:
        """Check if follow-up research should be triggered.

        IMP-AUTO-001: Integrates with ResearchOrchestrator to detect gaps
        and determine if follow-up research is needed based on analysis
        results and budget constraints.

        IMP-RESEARCH-001: Enhanced with budget status checking.

        Args:
            analysis_results: Results from analysis phase
            validation_results: Optional validation results
            min_budget_threshold: Minimum budget fraction required (default: 0.2)

        Returns:
            True if follow-up research should be triggered
        """
        # IMP-RESEARCH-001: Check budget constraints with status
        budget_remaining = self.get_budget_remaining()
        budget_status = self.get_budget_status()

        if budget_remaining < min_budget_threshold:
            logger.debug(
                f"[IMP-RESEARCH-001] Follow-up research skipped: "
                f"budget {budget_remaining:.1%} < {min_budget_threshold:.1%} threshold. "
                f"Used: {budget_status['budget_used_percent']:.1f}%"
            )
            return False

        # No analysis results means nothing to check
        if not analysis_results:
            return False

        try:
            from ..research.analysis.followup_trigger import FollowupResearchTrigger

            followup_trigger = FollowupResearchTrigger()
            trigger_result = followup_trigger.analyze(
                analysis_results=analysis_results,
                validation_results=validation_results,
            )

            if trigger_result.should_research:
                logger.info(
                    f"[IMP-AUTO-001] Follow-up research recommended: "
                    f"{trigger_result.triggers_selected} triggers detected "
                    f"(types: {trigger_result.trigger_summary}). "
                    f"[IMP-RESEARCH-001] Budget available: {budget_remaining:.1%}"
                )
                return True

            return False

        except ImportError as e:
            logger.warning(f"[IMP-AUTO-001] FollowupResearchTrigger not available: {e}")
            return False
        except Exception as e:
            logger.error(f"[IMP-AUTO-001] Error checking follow-up triggers: {e}")
            return False

    def get_research_gaps(
        self,
        project_root: Optional["Path"] = None,
    ) -> List[Dict[str, Any]]:
        """Get current research gaps from the ResearchOrchestrator.

        IMP-AUTO-001: Queries the ResearchOrchestrator's state tracker
        for identified research gaps.

        IMP-COST-001: Passes budget tracker to enforce cost limits during research.

        Args:
            project_root: Project root for state tracking (optional)

        Returns:
            List of identified research gaps with priorities
        """
        try:
            from pathlib import Path

            from ..research.orchestrator import ResearchOrchestrator

            root = project_root or Path(self.layout.base_dir).parent.parent.parent
            orchestrator = ResearchOrchestrator(
                project_root=root,
                budget_tracker=self,  # IMP-COST-001: Pass self as budget tracker
            )

            return orchestrator.get_research_gaps()

        except ImportError as e:
            logger.warning(f"[IMP-AUTO-001] ResearchOrchestrator not available: {e}")
            return []
        except Exception as e:
            logger.error(f"[IMP-AUTO-001] Error getting research gaps: {e}")
            return []

    # === Approval Service ===

    @property
    def approval_service(self) -> ApprovalService:
        """Get approval service (lazy initialized)."""
        if self._approval_service is None:
            self._approval_service = get_approval_service()
        return self._approval_service

    def request_approval_if_needed(
        self,
        trigger_reason: ApprovalTriggerReason,
        description: str,
        affected_pivots: Optional[List[str]] = None,
        diff_summary: Optional[Dict[str, Any]] = None,
    ) -> Optional[ApprovalResult]:
        """Request approval if trigger reason requires it.

        Only pivot-impacting triggers actually send requests.

        Args:
            trigger_reason: Why approval is being requested
            description: Human-readable description
            affected_pivots: List of affected pivot types
            diff_summary: Change summary

        Returns:
            ApprovalResult if request was sent, None if not needed
        """
        request = ApprovalRequest(
            request_id=f"apr-{uuid.uuid4().hex[:8]}",
            run_id=self.layout.run_id,
            phase_id=self._current_phase_id,
            trigger_reason=trigger_reason,
            affected_pivots=affected_pivots or [],
            description=description,
            diff_summary=diff_summary or {},
        )

        # Check if this trigger requires approval
        if not should_trigger_approval(request):
            logger.debug(
                f"[ExecutorContext] Trigger {trigger_reason.value} does not require approval"
            )
            return None

        # Send approval request
        result = self.approval_service.request_approval(request)
        logger.info(
            f"[ExecutorContext] Approval requested: {request.request_id}, "
            f"success={result.success}, approved={result.approved}"
        )
        return result

    # === IMP-TRIGGER-001: Health Transition & Task Regeneration ===

    def on_health_transition(
        self,
        provider_name: str,
        new_health_state: bool,
        trigger_task_regen: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Handle health transition event and optionally trigger task regeneration.

        IMP-TRIGGER-001: Detects health state changes for a provider and
        automatically triggers task regeneration to capitalize on new opportunities
        or mitigate degradation.

        Args:
            provider_name: Name of the provider experiencing health transition
            new_health_state: New health state (True=healthy, False=unhealthy)
            trigger_task_regen: Whether to trigger task regeneration (default: True)

        Returns:
            Dictionary with transition details and task regeneration result,
            or None if no transition detected
        """
        # Check if this is a transition (state changed)
        previous_state = self._health_states.get(provider_name)
        is_transition = previous_state is not None and previous_state != new_health_state

        # Update tracked state
        self._health_states[provider_name] = new_health_state

        if not is_transition:
            logger.debug(
                f"[IMP-TRIGGER-001] Health state for {provider_name} unchanged: {new_health_state}"
            )
            return None

        # Log transition
        transition_type = "recovered" if new_health_state else "degraded"
        self._last_health_transition = datetime.now(timezone.utc)
        self._health_transition_count += 1

        logger.info(
            f"[IMP-TRIGGER-001] Health transition detected for {provider_name}: "
            f"{transition_type} (was {previous_state}, now {new_health_state}). "
            f"Total transitions: {self._health_transition_count}"
        )

        # Trigger task regeneration if enabled
        task_regen_result = None
        if trigger_task_regen:
            task_regen_result = self.trigger_task_regeneration(
                trigger_reason=f"health_{transition_type}",
                provider_name=provider_name,
            )

        return {
            "provider_name": provider_name,
            "previous_state": previous_state,
            "new_state": new_health_state,
            "transition_type": transition_type,
            "timestamp": self._last_health_transition.isoformat(),
            "task_regeneration": task_regen_result,
        }

    def trigger_task_regeneration(
        self,
        trigger_reason: str,
        provider_name: Optional[str] = None,
        db_session: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """Trigger immediate task regeneration via TelemetryTaskDaemon.

        IMP-TRIGGER-001: Uses the telemetry-to-task daemon to automatically
        generate new tasks in response to health state changes.

        Args:
            trigger_reason: Reason for regeneration (e.g., "health_recovered")
            provider_name: Optional provider name that triggered regeneration
            db_session: Optional database session (lazy-initialized if None)

        Returns:
            Dictionary with regeneration result (cycle metrics) or None on error
        """
        try:
            from ..roadc.task_daemon import TelemetryTaskDaemon

            # Create daemon with appropriate configuration
            daemon = TelemetryTaskDaemon(
                db_session=db_session,
                interval_seconds=300,  # Not used for run_once()
                min_confidence=0.65,  # Slightly lower confidence for triggered regeneration
                max_tasks_per_cycle=3,  # Limit tasks to avoid overwhelming executor
                project_id=self.anchor.project_id,
                auto_persist=True,
                auto_queue=True,
            )

            # Run a single cycle immediately
            logger.debug(
                f"[IMP-TRIGGER-001] Triggering task regeneration: reason={trigger_reason}, "
                f"provider={provider_name}"
            )

            cycle_result = daemon.run_once()

            # Convert result to dictionary
            regen_result = {
                "cycle_number": cycle_result.cycle_number,
                "timestamp": cycle_result.timestamp.isoformat(),
                "trigger_reason": trigger_reason,
                "provider_name": provider_name,
                "insights_found": cycle_result.insights_found,
                "tasks_generated": cycle_result.tasks_generated,
                "tasks_persisted": cycle_result.tasks_persisted,
                "tasks_queued": cycle_result.tasks_queued,
                "cycle_duration_ms": cycle_result.cycle_duration_ms,
                "error": cycle_result.error,
                "skipped_reason": cycle_result.skipped_reason,
            }

            if cycle_result.error:
                logger.warning(
                    f"[IMP-TRIGGER-001] Task regeneration cycle {cycle_result.cycle_number} "
                    f"failed: {cycle_result.error}"
                )
            elif cycle_result.skipped_reason:
                logger.debug(
                    f"[IMP-TRIGGER-001] Task regeneration cycle {cycle_result.cycle_number} "
                    f"skipped: {cycle_result.skipped_reason}"
                )
            else:
                logger.info(
                    f"[IMP-TRIGGER-001] Task regeneration completed: "
                    f"{cycle_result.insights_found} insights -> {cycle_result.tasks_generated} tasks "
                    f"({cycle_result.tasks_persisted} persisted, {cycle_result.tasks_queued} queued)"
                )

            return regen_result

        except ImportError as e:
            logger.warning(
                f"[IMP-TRIGGER-001] TelemetryTaskDaemon not available: {e}. "
                f"Task regeneration cannot be triggered."
            )
            return None
        except Exception as e:
            logger.error(
                f"[IMP-TRIGGER-001] Error triggering task regeneration: {e}. "
                f"Reason: {trigger_reason}, Provider: {provider_name}"
            )
            return None

    def get_health_transition_metrics(self) -> Dict[str, Any]:
        """Get metrics about health transitions and task regeneration.

        IMP-TRIGGER-001: Provides observability into health-driven task regeneration.

        Returns:
            Dictionary with health transition metrics
        """
        return {
            "health_states_tracked": len(self._health_states),
            "healthy_providers": sum(1 for state in self._health_states.values() if state),
            "degraded_providers": sum(1 for state in self._health_states.values() if not state),
            "total_transitions": self._health_transition_count,
            "last_transition": (
                self._last_health_transition.isoformat() if self._last_health_transition else None
            ),
        }

    # === IMP-RESEARCH-002: Research Gap Detection Metrics ===

    def record_gap_detection(
        self,
        gaps_detected: int,
        gaps_addressed: int = 0,
        gap_types: Optional[List[str]] = None,
    ) -> None:
        """Record research gap detection event.

        IMP-RESEARCH-002: Tracks gap detection events for monitoring and
        decision-making about whether execution should be paused.

        Args:
            gaps_detected: Number of gaps detected
            gaps_addressed: Number of gaps already addressed
            gap_types: Optional list of gap type strings
        """
        self._gap_detection_count += 1
        self._total_gaps_detected += gaps_detected
        self._total_gaps_addressed += gaps_addressed

        gap_info = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'gaps_detected': gaps_detected,
            'gaps_addressed': gaps_addressed,
            'remaining_gaps': gaps_detected - gaps_addressed,
            'gap_types': gap_types or [],
        }

        logger.info(
            f"[IMP-RESEARCH-002] Gap detection recorded: "
            f"{gaps_detected} detected, {gaps_addressed} addressed, "
            f"{gaps_detected - gaps_addressed} remaining"
        )

    def record_gap_pause(
        self,
        gaps_remaining: int,
        reason: str,
        gaps_addressed: int = 0,
    ) -> None:
        """Record execution pause due to research gaps.

        IMP-RESEARCH-002: Tracks pause events caused by gap detection
        to understand execution flow and decision impact.

        Args:
            gaps_remaining: Number of gaps remaining
            reason: Reason for pause
            gaps_addressed: Number of gaps addressed
        """
        self._gap_pause_count += 1

        pause_info = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'gaps_remaining': gaps_remaining,
            'gaps_addressed': gaps_addressed,
            'reason': reason,
            'pause_number': self._gap_pause_count,
        }

        self._last_gap_pause_details = pause_info
        self._gap_pause_history.append(pause_info)

        logger.warning(
            f"[IMP-RESEARCH-002] Execution paused for gaps: "
            f"pause_count={self._gap_pause_count}, gaps_remaining={gaps_remaining}, "
            f"reason={reason}"
        )

    def get_gap_detection_metrics(self) -> Dict[str, Any]:
        """Get research gap detection and pause metrics.

        IMP-RESEARCH-002: Provides comprehensive gap detection metrics for
        monitoring, debugging, and decision-making.

        Returns:
            Dictionary with gap detection and pause metrics
        """
        return {
            'gap_detection_count': self._gap_detection_count,
            'gap_pause_count': self._gap_pause_count,
            'total_gaps_detected': self._total_gaps_detected,
            'total_gaps_addressed': self._total_gaps_addressed,
            'gaps_remaining': self._total_gaps_detected - self._total_gaps_addressed,
            'last_gap_pause': self._last_gap_pause_details,
            'gap_pause_history': self._gap_pause_history[-5:] if self._gap_pause_history else [],
        }

    def has_detected_gaps(self) -> bool:
        """Check if gaps have been detected during execution.

        Returns:
            True if gaps detected, False otherwise
        """
        return self._gap_detection_count > 0

    def get_remaining_gaps(self) -> int:
        """Get count of remaining gaps.

        Returns:
            Number of gaps still remaining
        """
        return max(0, self._total_gaps_detected - self._total_gaps_addressed)

    # === Integration Helpers ===

    def should_block_action(self, action_risk_score: float) -> bool:
        """Check if action should be blocked based on safety profile.

        In strict profile, blocks higher risk actions.

        Args:
            action_risk_score: Risk score (0.0-1.0)

        Returns:
            True if action should be blocked
        """
        if self.is_strict:
            # Strict profile: block anything above 0.5 risk
            return action_risk_score >= 0.5

        # Normal profile: only block very high risk
        return action_risk_score >= 0.8

    def get_approval_threshold(self) -> float:
        """Get risk threshold above which approval is required.

        Returns:
            Risk score threshold
        """
        if self.is_strict:
            return 0.3  # Lower threshold in strict mode

        return 0.5  # Normal threshold

    def estimate_operation_cost(
        self,
        operation_type: str,
        estimated_tokens: int = 0,
        estimated_context_chars: int = 0,
        estimated_sot_chars: int = 0,
    ) -> Dict[str, Any]:
        """Estimate cost of a proposed operation.

        IMP-RESEARCH-001: Provides cost estimation before expensive operations
        to allow pre-emptive budget checks.

        Args:
            operation_type: Type of operation (e.g., "api_call", "embedding", "web_search")
            estimated_tokens: Estimated token usage
            estimated_context_chars: Estimated context characters
            estimated_sot_chars: Estimated SOT characters

        Returns:
            Dictionary with cost estimation and feasibility check
        """
        budget_remaining = self.get_budget_remaining()

        # Estimate if operation will fit in remaining budget
        # Assume: 1 token ≈ 4 chars for token budgets
        total_estimated_chars = estimated_tokens * 4 + estimated_context_chars + estimated_sot_chars

        return {
            "operation_type": operation_type,
            "estimated_tokens": estimated_tokens,
            "estimated_context_chars": estimated_context_chars,
            "estimated_sot_chars": estimated_sot_chars,
            "total_estimated_chars": total_estimated_chars,
            "budget_remaining_fraction": budget_remaining,
            "fits_in_budget": budget_remaining > 0.05,
            "warning": (
                f"Operation uses {total_estimated_chars} chars, "
                f"budget remaining: {budget_remaining:.1%}"
            ),
        }

    def to_summary_dict(self) -> Dict[str, Any]:
        """Generate summary for logging/artifacts.

        IMP-RESEARCH-001: Includes budget status in summary.
        IMP-TRIGGER-001: Includes health transition metrics in summary.
        IMP-RESEARCH-002: Includes gap detection and pause metrics in summary.

        Returns:
            Summary dictionary
        """
        budget_status = self.get_budget_status()
        health_metrics = self.get_health_transition_metrics()
        gap_metrics = self.get_gap_detection_metrics()
        return {
            "project_id": self.anchor.project_id,
            "run_id": self.layout.run_id,
            "safety_profile": self.safety_profile,
            "needs_elevated_review": self.needs_elevated_review,
            "usage": self.usage_totals.to_dict(),
            "budget_remaining": self.get_budget_remaining(),
            "budget_status": budget_status,
            "phase_id": self._current_phase_id,
            "iterations_used": self._iterations_used,
            "escalations_used": self._escalations_used,
            "consecutive_failures": self._consecutive_failures,
            "replan_attempted": self._replan_attempted,
            "health_transitions": health_metrics,
            "gap_detection": gap_metrics,
        }


def create_executor_context(
    anchor: "IntentionAnchorV2",
    layout: "RunFileLayout",
) -> ExecutorContext:
    """Create an ExecutorContext for a run.

    Convenience factory function.

    Args:
        anchor: IntentionAnchorV2 guiding execution
        layout: RunFileLayout for artifacts

    Returns:
        Configured ExecutorContext
    """
    return ExecutorContext(anchor=anchor, layout=layout)
