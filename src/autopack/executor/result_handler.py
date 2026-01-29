"""
Result Handler Module

Extracted from autonomous_executor.py to manage result processing and posting.
This module addresses complexity by separating result handling into
testable, modular components.

Key responsibilities:
- Process builder results
- Process auditor results
- Post results to API
- Handle success/failure outcomes
- Record learning hints from failures
- Update phase state and telemetry
- IMP-TEL-001: Emit SLA breach alerts for pipeline latency enforcement

Related modules:
- builder_result_poster.py: Builder result posting
- auditor_result_poster.py: Auditor result posting
- phase_state_manager.py: Phase state persistence
- learning_pipeline.py: Learning hint recording
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ResultOutcome(Enum):
    """Outcome of phase execution"""

    SUCCESS = "COMPLETE"
    FAILURE = "FAILED"
    BLOCKED = "BLOCKED"
    CI_FAILED = "CI_FAILED"
    DELIVERABLES_FAILED = "DELIVERABLES_VALIDATION_FAILED"


@dataclass
class ResultAction:
    """Action to take based on result"""

    action: str
    reason: str
    retryable: bool
    record_hint: bool
    hint_type: Optional[str] = None
    hint_details: Optional[str] = None


@dataclass
class SLABreachInfo:
    """IMP-TEL-001: Information about an SLA breach for alerting.

    Attributes:
        breached: Whether an SLA breach was detected
        level: Severity level ("warning" or "critical")
        threshold_ms: SLA threshold in milliseconds
        actual_ms: Actual latency in milliseconds
        breach_amount_ms: Amount by which SLA was exceeded
        message: Human-readable breach message
        stage_from: Starting pipeline stage (if applicable)
        stage_to: Ending pipeline stage (if applicable)
    """

    breached: bool = False
    level: str = ""
    threshold_ms: float = 0.0
    actual_ms: float = 0.0
    breach_amount_ms: float = 0.0
    message: str = ""
    stage_from: Optional[str] = None
    stage_to: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "breached": self.breached,
            "level": self.level,
            "threshold_ms": self.threshold_ms,
            "actual_ms": self.actual_ms,
            "breach_amount_ms": self.breach_amount_ms,
            "message": self.message,
            "stage_from": self.stage_from,
            "stage_to": self.stage_to,
        }


@dataclass
class ProcessingResult:
    """Result of result processing"""

    outcome: ResultOutcome
    action: ResultAction
    posted_to_api: bool = False
    sla_breaches: List[SLABreachInfo] = field(default_factory=list)


class ResultHandler:
    """
    Handles processing of builder and auditor results.

    Coordinates:
    - Result validation
    - API posting
    - Learning hint recording
    - Phase state updates
    """

    def __init__(
        self,
        builder_result_poster: Any,
        auditor_result_poster: Any,
        phase_state_mgr: Any,
        learning_pipeline: Optional[Any] = None,
        api_client: Optional[Any] = None,
        run_id: str = "",
    ):
        """Initialize ResultHandler with dependencies.

        Args:
            builder_result_poster: Builder result poster
            auditor_result_poster: Auditor result poster
            phase_state_mgr: Phase state manager
            learning_pipeline: Optional learning pipeline
            api_client: Optional API client for approval requests
            run_id: Run identifier
        """
        self.builder_result_poster = builder_result_poster
        self.auditor_result_poster = auditor_result_poster
        self.phase_state_mgr = phase_state_mgr
        self.learning_pipeline = learning_pipeline
        self.api_client = api_client
        self.run_id = run_id

    def process_builder_result(
        self,
        phase_id: str,
        result: Any,
        allowed_paths: Optional[List[str]] = None,
    ) -> bool:
        """Process builder result and post to API.

        Args:
            phase_id: Phase identifier
            result: Builder result
            allowed_paths: Optional governance allowed paths

        Returns:
            True if posting succeeded
        """
        logger.info(f"[{phase_id}] Processing builder result...")
        return asyncio.run(self.builder_result_poster.post_result(phase_id, result, allowed_paths))

    def process_auditor_result(
        self,
        phase_id: str,
        result: Any,
    ) -> bool:
        """Process auditor result and post to API.

        Args:
            phase_id: Phase identifier
            result: Auditor result

        Returns:
            True if posting succeeded
        """
        logger.info(f"[{phase_id}] Processing auditor result...")
        return self.auditor_result_poster.post_result(phase_id, result)

    def process_results(
        self,
        phase_id: str,
        phase: Dict,
        builder_result: Any,
        auditor_result: Any,
        ci_result: Optional[Dict],
        quality_report: Any,
        allowed_paths: Optional[List[str]] = None,
    ) -> ProcessingResult:
        """Process all results and determine next action.

        Args:
            phase_id: Phase identifier
            phase: Phase specification dict
            builder_result: Builder execution result
            auditor_result: Auditor review result
            ci_result: CI execution result
            quality_report: Quality gate report
            allowed_paths: Optional governance allowed paths

        Returns:
            ProcessingResult with outcome and action
        """
        logger.info(f"[{phase_id}] Determining execution outcome...")

        # Post results to API
        builder_posted = self.process_builder_result(phase_id, builder_result, allowed_paths)
        auditor_posted = self.process_auditor_result(phase_id, auditor_result)

        # Determine outcome
        outcome = self._determine_outcome(builder_result, auditor_result, ci_result, quality_report)

        # Determine action
        action = self._determine_action(
            outcome, phase, phase_id, auditor_result, ci_result, quality_report
        )

        # Record learning hints if applicable
        if action.record_hint and self.learning_pipeline:
            self._record_learning_hint(phase, action.hint_type, action.hint_details)

        # Update phase status
        self._update_phase_status(phase_id, outcome.value)

        return ProcessingResult(
            outcome=outcome,
            action=action,
            posted_to_api=builder_posted and auditor_posted,
        )

    def _determine_outcome(
        self,
        builder_result: Any,
        auditor_result: Any,
        ci_result: Optional[Dict],
        quality_report: Any,
    ) -> ResultOutcome:
        """Determine overall outcome from all results.

        Args:
            builder_result: Builder execution result
            auditor_result: Auditor review result
            ci_result: CI execution result
            quality_report: Quality gate report

        Returns:
            ResultOutcome enum value
        """
        # Check for failures in order of precedence

        # 1. Builder failure
        if not builder_result or getattr(builder_result, "success", True) is False:
            return ResultOutcome.FAILURE

        # 2. CI failure
        if ci_result and not ci_result.get("success", True):
            return ResultOutcome.CI_FAILED

        # 3. Deliverables validation failure
        if (
            quality_report
            and hasattr(quality_report, "checks")
            and quality_report.checks.get("deliverables_valid", True) is False
        ):
            return ResultOutcome.DELIVERABLES_FAILED

        # 4. Auditor rejection (BLOCKED)
        if auditor_result and getattr(auditor_result, "approved", True) is False:
            return ResultOutcome.BLOCKED

        # 5. Quality gate BLOCKED
        if quality_report and getattr(quality_report, "quality_level", "") == "BLOCK":
            return ResultOutcome.BLOCKED

        # All checks passed
        return ResultOutcome.SUCCESS

    def _determine_action(
        self,
        outcome: ResultOutcome,
        phase: Dict,
        phase_id: str,
        auditor_result: Any,
        ci_result: Optional[Dict],
        quality_report: Any,
    ) -> ResultAction:
        """Determine next action based on outcome.

        Args:
            outcome: ResultOutcome from determine_outcome
            phase: Phase specification dict
            phase_id: Phase identifier
            auditor_result: Auditor review result
            ci_result: CI execution result
            quality_report: Quality gate report

        Returns:
            ResultAction with action details
        """
        phase_name = phase.get("name", phase_id)

        if outcome == ResultOutcome.SUCCESS:
            return ResultAction(
                action="continue",
                reason="Phase completed successfully",
                retryable=False,
                record_hint=False,
            )

        elif outcome == ResultOutcome.FAILURE:
            return ResultAction(
                action="retry_or_fail",
                reason=f"Builder failed for phase {phase_name}",
                retryable=True,
                record_hint=True,
                hint_type="builder_failure",
                hint_details=f"Phase {phase_name} failed during execution",
            )

        elif outcome == ResultOutcome.CI_FAILED:
            return ResultAction(
                action="retry_or_fail",
                reason=f"CI failed for phase {phase_name}",
                retryable=True,
                record_hint=True,
                hint_type="ci_fail",
                hint_details=f"Phase {phase_name} failed CI tests",
            )

        elif outcome == ResultOutcome.DELIVERABLES_FAILED:
            return ResultAction(
                action="retry_or_fail",
                reason=f"Deliverables validation failed for phase {phase_name}",
                retryable=True,
                record_hint=True,
                hint_type="deliverables_validation_failed",
                hint_details=f"Phase {phase_name} failed deliverables validation",
            )

        elif outcome == ResultOutcome.BLOCKED:
            # Determine block reason
            if auditor_result and hasattr(auditor_result, "issues_found"):
                issues = auditor_result.issues_found
                reason = f"Auditor found {len(issues)} issue(s)"
            elif quality_report:
                reason = f"Quality gate blocked: {quality_report.quality_level}"
            else:
                reason = "Phase blocked by quality gate"

            return ResultAction(
                action="block",
                reason=reason,
                retryable=False,
                record_hint=True,
                hint_type="auditor_reject",
                hint_details=f"Phase {phase_name} blocked by auditor/quality gate",
            )

        # Fallback
        return ResultAction(
            action="unknown",
            reason="Unknown outcome",
            retryable=False,
            record_hint=False,
        )

    def _record_learning_hint(
        self,
        phase: Dict,
        hint_type: str,
        details: str,
    ) -> None:
        """Record learning hint for this phase.

        Args:
            phase: Phase specification dict
            hint_type: Type of hint
            details: Human-readable details about what was learned
        """
        if not self.learning_pipeline:
            return

        try:
            self.learning_pipeline.record_hint(phase, hint_type, details)
            logger.info(f"[{phase.get('phase_id', 'unknown')}] Recorded learning hint: {hint_type}")
        except Exception as e:
            logger.warning(f"Failed to record learning hint: {e}")

    def _update_phase_status(
        self,
        phase_id: str,
        status: str,
    ) -> bool:
        """Update phase status in database.

        Args:
            phase_id: Phase identifier
            status: New phase status

        Returns:
            True if update succeeded
        """
        try:
            return self.phase_state_mgr.update_status(phase_id, status)
        except Exception as e:
            logger.warning(f"Failed to update phase status: {e}")
            return False

    def request_human_approval(
        self,
        phase_id: str,
        quality_report: Any,
        timeout_seconds: int = 3600,
    ) -> bool:
        """Request human approval via Telegram for blocked phases.

        Args:
            phase_id: Phase identifier
            quality_report: Quality gate report with risk assessment
            timeout_seconds: How long to wait for approval (default: 1 hour)

        Returns:
            True if approved, False if rejected or timed out
        """
        if not self.api_client:
            logger.error(f"[{phase_id}] Cannot request approval - no API client")
            return False

        # Import approval flow module
        from autopack.executor.approval_flow import request_human_approval

        return request_human_approval(
            api_client=self.api_client,
            phase_id=phase_id,
            quality_report=quality_report,
            run_id=self.run_id,
            last_files_changed=[],  # Would need proper tracking
            timeout_seconds=timeout_seconds,
        )

    def emit_sla_breach_alert(
        self,
        phase_id: str,
        breach_info: SLABreachInfo,
    ) -> None:
        """Emit an alert for SLA breach.

        IMP-TEL-001: Logs SLA breach alerts for visibility and records them
        for operational monitoring. Critical breaches (>50% over threshold)
        are logged at critical level.

        Args:
            phase_id: Phase identifier where breach was detected
            breach_info: SLA breach information
        """
        if not breach_info.breached:
            return

        alert_msg = (
            f"[IMP-TEL-001] SLA breach for phase {phase_id}: "
            f"{breach_info.message} "
            f"(actual={breach_info.actual_ms:.0f}ms, "
            f"threshold={breach_info.threshold_ms:.0f}ms, "
            f"breach_amount={breach_info.breach_amount_ms:.0f}ms)"
        )

        if breach_info.level == "critical":
            logger.critical(alert_msg)
        else:
            logger.warning(alert_msg)

    def check_and_emit_sla_breaches(
        self,
        phase_id: str,
        latency_tracker: Any,
    ) -> List[SLABreachInfo]:
        """Check latency tracker for SLA breaches and emit alerts.

        IMP-TEL-001: Inspects the pipeline latency tracker for any SLA
        breaches and emits alerts for each detected breach.

        Args:
            phase_id: Phase identifier
            latency_tracker: PipelineLatencyTracker instance

        Returns:
            List of SLABreachInfo for detected breaches
        """
        breaches: List[SLABreachInfo] = []

        if latency_tracker is None:
            return breaches

        try:
            # Import here to avoid circular imports
            from autopack.telemetry.meta_metrics import SLABreachAlert

            raw_breaches: List[SLABreachAlert] = latency_tracker.check_sla_breaches()

            for raw_breach in raw_breaches:
                breach_info = SLABreachInfo(
                    breached=True,
                    level=raw_breach.level,
                    threshold_ms=raw_breach.threshold_ms,
                    actual_ms=raw_breach.actual_ms,
                    breach_amount_ms=raw_breach.breach_amount_ms,
                    message=raw_breach.message,
                    stage_from=raw_breach.stage_from,
                    stage_to=raw_breach.stage_to,
                )
                breaches.append(breach_info)

                # Emit alert for each breach
                self.emit_sla_breach_alert(phase_id, breach_info)

            if breaches:
                logger.info(
                    f"[IMP-TEL-001] Detected {len(breaches)} SLA breach(es) for phase {phase_id}"
                )

        except Exception as e:
            logger.warning(
                f"[IMP-TEL-001] Failed to check SLA breaches for phase {phase_id}: {e}"
            )

        return breaches
