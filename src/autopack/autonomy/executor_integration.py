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

        # Patch correction tracking
        self._patch_tracker = PatchCorrectionTracker()

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

        logger.debug(
            f"[ExecutorContext] Initialized for project={anchor.project_id}, run={layout.run_id}"
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
        """Record a consecutive failure."""
        self._consecutive_failures += 1

    def reset_failures(self) -> None:
        """Reset consecutive failure count (after success)."""
        self._consecutive_failures = 0

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

    def to_summary_dict(self) -> Dict[str, Any]:
        """Generate summary for logging/artifacts.

        Returns:
            Summary dictionary
        """
        return {
            "project_id": self.anchor.project_id,
            "run_id": self.layout.run_id,
            "safety_profile": self.safety_profile,
            "needs_elevated_review": self.needs_elevated_review,
            "usage": self.usage_totals.to_dict(),
            "budget_remaining": self.get_budget_remaining(),
            "phase_id": self._current_phase_id,
            "iterations_used": self._iterations_used,
            "escalations_used": self._escalations_used,
            "consecutive_failures": self._consecutive_failures,
            "replan_attempted": self._replan_attempted,
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
