"""Autopilot controller - autonomous execution with safe gates.

The autopilot controller orchestrates the full autonomy loop:
1. Load intention anchor (v2)
2. Scan for gaps
3. Propose plan with governance
4. Execute auto-approved actions (if any)
5. Stop and record if approval required

Default OFF - requires explicit enable flag.

BUILD-181 Integration:
- ExecutorContext for usage tracking, safety profile, scope reduction
- Approval service for pivot-impacting changes
- Coverage metrics processing

IMP-REL-001: Health-gated task generation with auto-resume support.
"""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

if TYPE_CHECKING:
    from ..telemetry.meta_metrics import FeedbackLoopHealth

from ..file_layout import RunFileLayout
from ..gaps.scanner import scan_workspace
from ..intention_anchor.v2 import IntentionAnchorV2
from ..planning.models import PlanProposalV1
from ..planning.plan_proposer import propose_plan
from ..research.analysis.followup_trigger import TriggerAnalysisResult
from .action_allowlist import ActionClassification
from .action_executor import ExecutionBatch, SafeActionExecutor
from .event_triggers import EventTriggerManager, EventType, WorkflowEvent
from .executor_integration import ExecutorContext, create_executor_context
from .models import (ApprovalRequest, AutopilotMetadata, AutopilotSessionV1,
                     ErrorLogEntry, ExecutionSummary)

logger = logging.getLogger(__name__)


class AutopilotController:
    """Autopilot controller for autonomous execution within safe gates.

    Attributes:
        workspace_root: Root directory of workspace
        project_id: Project identifier
        run_id: Run identifier
        enabled: Whether autopilot is enabled (default: False)
        session: Current autopilot session
        executor_ctx: BUILD-181 ExecutorContext for integrated handling
        _event_trigger_manager: IMP-AUTO-002 EventTriggerManager for external events

    IMP-REL-001: Includes health-gated task generation with auto-resume support.
    Task generation can be paused when feedback loop health is degraded and
    automatically resumed when health recovers to HEALTHY.

    IMP-AUTO-002: Includes event-driven workflow triggers that respond to
    external events (API updates, dependency changes, market signals, etc).
    """

    def __init__(
        self,
        workspace_root: Path,
        project_id: str,
        run_id: str,
        enabled: bool = False,
    ):
        """Initialize autopilot controller.

        Args:
            workspace_root: Root directory of workspace
            project_id: Project identifier
            run_id: Run identifier
            enabled: Whether autopilot is explicitly enabled (default: False)
        """
        self.workspace_root = workspace_root
        self.project_id = project_id
        self.run_id = run_id
        self.enabled = enabled
        self.layout = RunFileLayout(run_id=run_id, project_id=project_id)
        self.session: Optional[AutopilotSessionV1] = None
        self.executor_ctx: Optional[ExecutorContext] = None

        # IMP-REL-001: Health-gated task generation state
        self._task_generation_paused: bool = False
        self._pause_reason: Optional[str] = None
        self._resume_callbacks: list[Callable[[], None]] = []

        # IMP-AUTO-001: Research cycle triggering callbacks
        self._research_cycle_callbacks: list[Callable[[TriggerAnalysisResult], None]] = []
        self._last_research_trigger_result: Optional[TriggerAnalysisResult] = None

        # IMP-AUTO-002: Event-driven workflow triggers
        self._event_trigger_manager = EventTriggerManager()
        self._pending_events: list[WorkflowEvent] = []

    def run_session(self, anchor: IntentionAnchorV2) -> AutopilotSessionV1:
        """Run autopilot session with safe execution gates.

        Steps:
        1. Load anchor (v2) - already provided
        2. Scan gaps
        3. Propose plan
        4. If all actions auto-approved: execute bounded batch
        5. Else: emit approval requests + stop (but record artifacts)

        Args:
            anchor: Intention anchor v2 to guide execution

        Returns:
            AutopilotSessionV1 with execution log

        Raises:
            RuntimeError: If autopilot is not enabled
        """
        if not self.enabled:
            raise RuntimeError(
                "Autopilot is disabled by default. "
                "Set enabled=True explicitly to run autonomous execution."
            )

        session_id = f"autopilot-{uuid.uuid4().hex[:8]}"
        started_at = datetime.now(timezone.utc)

        logger.info(f"[Autopilot] Starting session: {session_id}")

        # Initialize session
        self.session = AutopilotSessionV1(
            format_version="v1",
            project_id=self.project_id,
            run_id=self.run_id,
            session_id=session_id,
            started_at=started_at,
            status="running",
            anchor_id=anchor.raw_input_digest,
            gap_report_id="",  # Will be set after gap scan
            plan_proposal_id="",  # Will be set after plan proposal
            metadata=AutopilotMetadata(
                autopilot_version="0.1.0",
                enabled_explicitly=self.enabled,
            ),
        )

        try:
            # Initialize BUILD-181 ExecutorContext
            self.executor_ctx = create_executor_context(anchor=anchor, layout=self.layout)
            logger.info(
                f"[Autopilot] Initialized ExecutorContext with "
                f"safety_profile={self.executor_ctx.safety_profile}"
            )

            # Step 1: Anchor already loaded
            logger.info(f"[Autopilot] Using anchor: {anchor.raw_input_digest}")

            # Step 2: Scan gaps
            logger.info("[Autopilot] Scanning workspace for gaps...")
            gap_report = scan_workspace(
                workspace_root=self.workspace_root,
                project_id=self.project_id,
                run_id=self.run_id,
            )
            self.session.gap_report_id = gap_report.report_id
            logger.info(
                f"[Autopilot] Found {gap_report.summary.total_gaps} gaps "
                f"({gap_report.summary.autopilot_blockers} blockers)"
            )

            # IMP-AUTO-001: Check if follow-up research should be triggered
            budget_remaining = (
                self.executor_ctx.get_budget_remaining() if self.executor_ctx else 1.0
            )
            gap_summary = {
                "summary": {
                    "total_gaps": gap_report.summary.total_gaps,
                    "critical_gaps": gap_report.summary.autopilot_blockers,
                }
            }
            if self.should_trigger_followup_research(
                gap_report=gap_summary,
                budget_remaining=budget_remaining,
            ):
                logger.info("[IMP-AUTO-001] Follow-up research recommended based on gap analysis")
                # Note: Actual research execution would be handled by registered callbacks
                # or a separate async research phase

            # Step 3: Propose plan
            logger.info("[Autopilot] Proposing action plan...")
            proposal = propose_plan(
                anchor=anchor,
                gap_report=gap_report,
                workspace_root=self.workspace_root,
            )
            self.session.plan_proposal_id = f"plan-{uuid.uuid4().hex[:8]}"
            logger.info(
                f"[Autopilot] Generated {proposal.summary.total_actions} actions "
                f"({proposal.summary.auto_approved_actions} auto-approved, "
                f"{proposal.summary.requires_approval_actions} require approval, "
                f"{proposal.summary.blocked_actions} blocked)"
            )

            # Step 4: Check if we can proceed autonomously
            if proposal.summary.auto_approved_actions == 0:
                # No auto-approved actions - stop and request approval
                self._handle_approval_required(proposal)
                return self.session

            if (
                proposal.summary.requires_approval_actions > 0
                or proposal.summary.blocked_actions > 0
            ):
                # Some actions require approval - stop and request
                self._handle_approval_required(proposal)
                return self.session

            # All actions are auto-approved - execute bounded batch
            logger.info(
                f"[Autopilot] All {proposal.summary.auto_approved_actions} actions auto-approved. "
                "Executing bounded batch..."
            )
            self._execute_bounded_batch(proposal)

            # Mark session as completed
            self.session.status = "completed"
            self.session.completed_at = datetime.now(timezone.utc)

            # Calculate session duration
            if self.session.metadata:
                duration = (self.session.completed_at - self.session.started_at).total_seconds()
                self.session.metadata.session_duration_ms = int(duration * 1000)

            logger.info(f"[Autopilot] Session completed: {session_id}")

        except Exception as e:
            # Log error and mark session as failed
            logger.exception(f"[Autopilot] Session failed: {e}")
            self.session.status = "failed"
            self.session.completed_at = datetime.now(timezone.utc)
            self.session.error_log.append(
                ErrorLogEntry(
                    timestamp=datetime.now(timezone.utc),
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
            )

        return self.session

    def on_health_transition(
        self, old_status: "FeedbackLoopHealth", new_status: "FeedbackLoopHealth"
    ) -> None:
        """Handle health state transitions for auto-resume logic.

        IMP-REL-001: This callback is invoked when the feedback loop health
        transitions between states. When health recovers from ATTENTION_REQUIRED
        to HEALTHY, task generation is automatically resumed.

        Args:
            old_status: Previous health status
            new_status: New health status
        """
        from ..telemetry.meta_metrics import FeedbackLoopHealth

        logger.info(
            f"[IMP-REL-001] Autopilot received health transition: "
            f"{old_status.value} -> {new_status.value}"
        )

        # Check for recovery transition
        if (
            old_status == FeedbackLoopHealth.ATTENTION_REQUIRED
            and new_status == FeedbackLoopHealth.HEALTHY
        ):
            self._trigger_task_generation_resume()
        elif new_status == FeedbackLoopHealth.ATTENTION_REQUIRED:
            self._pause_task_generation("Health status is ATTENTION_REQUIRED")

    def _trigger_task_generation_resume(self) -> None:
        """Trigger resumption of task generation after health recovery.

        IMP-REL-001: Called when health transitions from ATTENTION_REQUIRED
        to HEALTHY. Invokes all registered resume callbacks and updates
        internal state to allow task generation.
        """
        if not self._task_generation_paused:
            logger.debug("[IMP-REL-001] Task generation not paused, no resume needed")
            return

        logger.info("[IMP-REL-001] Triggering task generation resume after health recovery")

        self._task_generation_paused = False
        self._pause_reason = None

        # Invoke all registered resume callbacks
        for callback in self._resume_callbacks:
            try:
                callback()
            except Exception as e:
                logger.warning(f"[IMP-REL-001] Task generation resume callback failed: {e}")

        logger.info("[IMP-REL-001] Task generation resumed successfully")

    def _pause_task_generation(self, reason: str) -> None:
        """Pause task generation due to health degradation.

        IMP-REL-001: Called when health transitions to ATTENTION_REQUIRED.
        Updates internal state to prevent new task generation until health
        recovers.

        Args:
            reason: Human-readable reason for the pause
        """
        if self._task_generation_paused:
            logger.debug(f"[IMP-REL-001] Task generation already paused: {self._pause_reason}")
            return

        logger.warning(f"[IMP-REL-001] Pausing task generation: {reason}")
        self._task_generation_paused = True
        self._pause_reason = reason

    def register_resume_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to be invoked when task generation resumes.

        IMP-REL-001: Callbacks are invoked when health recovers and task
        generation is resumed. Use this to restart any paused task generation
        processes.

        Args:
            callback: Function to call when task generation resumes
        """
        self._resume_callbacks.append(callback)
        logger.debug(
            f"[IMP-REL-001] Registered resume callback " f"(total: {len(self._resume_callbacks)})"
        )

    def unregister_resume_callback(self, callback: Callable[[], None]) -> bool:
        """Unregister a previously registered resume callback.

        Args:
            callback: The callback function to unregister

        Returns:
            True if callback was found and removed, False otherwise
        """
        try:
            self._resume_callbacks.remove(callback)
            return True
        except ValueError:
            return False

    def is_task_generation_paused(self) -> bool:
        """Check if task generation is currently paused due to health issues.

        IMP-REL-001: Returns True if task generation has been paused due
        to feedback loop health being in ATTENTION_REQUIRED state.

        Returns:
            True if task generation is paused, False otherwise
        """
        return self._task_generation_paused

    def get_pause_reason(self) -> Optional[str]:
        """Get the reason task generation is paused.

        Returns:
            Reason string if paused, None if not paused
        """
        return self._pause_reason if self._task_generation_paused else None

    # === IMP-AUTO-001: Research Cycle Triggering ===

    def register_research_cycle_callback(
        self, callback: Callable[[TriggerAnalysisResult], None]
    ) -> None:
        """Register a callback to be invoked when a research cycle is triggered.

        IMP-AUTO-001: Callbacks are invoked when follow-up research is detected
        as needed. Use this to trigger research phases in response to gaps.

        Args:
            callback: Function to call when research cycle is triggered.
                     Receives the TriggerAnalysisResult with trigger details.
        """
        self._research_cycle_callbacks.append(callback)
        logger.debug(
            f"[IMP-AUTO-001] Registered research cycle callback "
            f"(total: {len(self._research_cycle_callbacks)})"
        )

    def unregister_research_cycle_callback(
        self, callback: Callable[[TriggerAnalysisResult], None]
    ) -> bool:
        """Unregister a previously registered research cycle callback.

        Args:
            callback: The callback function to unregister

        Returns:
            True if callback was found and removed, False otherwise
        """
        try:
            self._research_cycle_callbacks.remove(callback)
            return True
        except ValueError:
            return False

    async def trigger_research_cycle(
        self,
        analysis_results: dict,
        validation_results: Optional[dict] = None,
    ) -> Optional[TriggerAnalysisResult]:
        """Trigger a research cycle if follow-up research is needed.

        IMP-AUTO-001: Analyzes research findings for gaps and triggers automated
        follow-up research when needed. This method integrates with the
        ResearchOrchestrator to detect gaps and invoke registered callbacks.

        Args:
            analysis_results: Results from analysis phase
            validation_results: Optional validation results

        Returns:
            TriggerAnalysisResult if research was triggered, None otherwise
        """
        if self._task_generation_paused:
            logger.info("[IMP-AUTO-001] Research cycle skipped: task generation paused")
            return None

        try:
            from ..research.analysis.followup_trigger import \
                FollowupResearchTrigger

            # Analyze findings for follow-up research triggers
            followup_trigger = FollowupResearchTrigger()
            trigger_result = followup_trigger.analyze(
                analysis_results=analysis_results,
                validation_results=validation_results,
            )

            self._last_research_trigger_result = trigger_result

            if trigger_result.should_research:
                logger.info(
                    f"[IMP-AUTO-001] Research cycle triggered: "
                    f"{trigger_result.triggers_selected} triggers detected"
                )

                # Invoke all registered callbacks
                for callback in self._research_cycle_callbacks:
                    try:
                        callback(trigger_result)
                    except Exception as e:
                        logger.warning(f"[IMP-AUTO-001] Research cycle callback failed: {e}")

                return trigger_result
            else:
                logger.debug("[IMP-AUTO-001] No follow-up research needed")
                return None

        except ImportError as e:
            logger.warning(f"[IMP-AUTO-001] Research orchestrator not available: {e}")
            return None
        except Exception as e:
            logger.error(f"[IMP-AUTO-001] Research cycle trigger failed: {e}")
            return None

    def should_trigger_followup_research(
        self,
        gap_report: Optional[dict] = None,
        budget_remaining: Optional[float] = None,
    ) -> bool:
        """Check if follow-up research should be triggered.

        IMP-AUTO-001: Determines if follow-up research is needed based on
        gap report and budget constraints.

        Args:
            gap_report: Gap report from workspace scan
            budget_remaining: Remaining budget fraction (0.0-1.0)

        Returns:
            True if follow-up research should be triggered
        """
        # Don't trigger if task generation is paused
        if self._task_generation_paused:
            return False

        # Don't trigger if budget is too low (< 20%)
        if budget_remaining is not None and budget_remaining < 0.2:
            logger.debug("[IMP-AUTO-001] Follow-up research skipped: insufficient budget")
            return False

        # Check if we have significant gaps
        if gap_report:
            total_gaps = gap_report.get("summary", {}).get("total_gaps", 0)
            critical_gaps = gap_report.get("summary", {}).get("critical_gaps", 0)

            # Trigger if we have critical gaps or many total gaps
            if critical_gaps > 0:
                logger.info(
                    f"[IMP-AUTO-001] Follow-up research recommended: "
                    f"{critical_gaps} critical gaps"
                )
                return True

            if total_gaps >= 5:
                logger.info(
                    f"[IMP-AUTO-001] Follow-up research recommended: " f"{total_gaps} total gaps"
                )
                return True

        # Check last trigger result
        if self._last_research_trigger_result:
            return self._last_research_trigger_result.should_research

        return False

    def get_last_research_trigger_result(self) -> Optional[TriggerAnalysisResult]:
        """Get the last research trigger analysis result.

        Returns:
            Last TriggerAnalysisResult or None if no research was triggered
        """
        return self._last_research_trigger_result

    # === IMP-AUTO-002: Event-Driven Workflow Triggers ===

    def register_event_handler(
        self,
        event_type: EventType,
        handler: Callable[[WorkflowEvent], None],
    ) -> None:
        """Register a handler for external events.

        IMP-AUTO-002: Handlers are invoked when events of the specified type
        are processed. Multiple handlers can be registered for the same event type.

        Args:
            event_type: Type of event to handle (from EventType enum)
            handler: Callable that receives WorkflowEvent

        Raises:
            ValueError: If handler is not callable
        """
        self._event_trigger_manager.register_handler(event_type, handler)
        logger.debug(
            f"[IMP-AUTO-002] Registered event handler for {event_type.value} "
            f"(total handlers: {self._event_trigger_manager.get_handler_count()})"
        )

    def unregister_event_handler(
        self,
        event_type: EventType,
        handler: Callable[[WorkflowEvent], None],
    ) -> bool:
        """Unregister a handler for an event type.

        Args:
            event_type: Type of event
            handler: Handler function to unregister

        Returns:
            True if handler was found and removed, False otherwise
        """
        return self._event_trigger_manager.unregister_handler(event_type, handler)

    async def trigger_event(
        self,
        event_type: EventType,
        source: str,
        payload: Optional[dict] = None,
    ) -> None:
        """Trigger a workflow event.

        IMP-AUTO-002: Creates a WorkflowEvent and dispatches it to all
        registered handlers for that event type.

        Args:
            event_type: Type of event to trigger
            source: Source system/service triggering the event
            payload: Optional event-specific data

        Raises:
            ValueError: If event creation fails
        """
        event = WorkflowEvent(
            event_type=event_type,
            source=source,
            payload=payload or {},
        )

        self._pending_events.append(event)
        logger.info(
            f"[IMP-AUTO-002] Event triggered: {event_type.value} from {source} "
            f"({len(self._pending_events)} pending)"
        )

        # Process immediately
        await self._event_trigger_manager.process_event(event)

    async def process_pending_events(self) -> int:
        """Process all pending workflow events.

        IMP-AUTO-002: Processes queued events and dispatches them to handlers.
        Returns the count of processed events.

        Returns:
            Number of events processed
        """
        if not self._pending_events:
            return 0

        logger.info(f"[IMP-AUTO-002] Processing {len(self._pending_events)} pending events")
        processed = 0

        while self._pending_events:
            event = self._pending_events.pop(0)
            try:
                await self._event_trigger_manager.process_event(event)
                processed += 1
            except Exception as e:
                logger.error(f"[IMP-AUTO-002] Failed to process event: {e}")

        logger.info(f"[IMP-AUTO-002] Processed {processed} events")
        return processed

    def get_event_handler_count(self, event_type: Optional[EventType] = None) -> int:
        """Get count of registered event handlers.

        Args:
            event_type: Specific event type, or None for total count

        Returns:
            Number of registered handlers
        """
        return self._event_trigger_manager.get_handler_count(event_type)

    def get_event_summary(self) -> Dict[str, Any]:
        """Get summary of event trigger state.

        Returns:
            Dictionary with handler and event information
        """
        return {
            **self._event_trigger_manager.get_summary(),
            "pending_events": len(self._pending_events),
        }

    def _handle_approval_required(self, proposal: PlanProposalV1) -> None:
        """Handle case where approval is required.

        Records what would be done and stops execution.
        IMP-AUTOPILOT-002: Queue approval requests for human review.

        Args:
            proposal: Plan proposal with actions requiring approval
        """
        logger.info("[Autopilot] Approval required - stopping execution")

        # Collect approval requests
        approval_requests = []
        blocked_count = 0

        for action in proposal.actions:
            if action.approval_status in ["requires_approval", "blocked"]:
                approval_requests.append(
                    ApprovalRequest(
                        action_id=action.action_id,
                        approval_status=action.approval_status,
                        reason=action.approval_reason or "No reason provided",
                    )
                )
                if action.approval_status == "blocked":
                    blocked_count += 1

        self.session.approval_requests = approval_requests
        self.session.status = "blocked_approval_required"
        self.session.completed_at = datetime.now(timezone.utc)

        if blocked_count > 0:
            self.session.blocked_reason = (
                f"{blocked_count} action(s) blocked by governance; "
                f"{len(approval_requests) - blocked_count} action(s) require manual approval"
            )
        else:
            self.session.blocked_reason = (
                f"{len(approval_requests)} action(s) require manual approval"
            )

        # Update execution summary
        self.session.execution_summary = ExecutionSummary(
            total_actions=proposal.summary.total_actions,
            auto_approved_actions=proposal.summary.auto_approved_actions,
            executed_actions=0,  # None executed
            successful_actions=0,
            failed_actions=0,
            blocked_actions=blocked_count,
        )

        # IMP-AUTOPILOT-002: Queue approval requests for human review
        try:
            from .approval_service import ApprovalService

            approval_svc = ApprovalService(
                run_id=self.run_id,
                project_id=self.project_id,
                workspace_root=self.workspace_root,
            )

            queued = approval_svc.queue_approvals(
                session_id=self.session.session_id,
                approval_requests=approval_requests,
                proposal_summary=getattr(proposal, "summary_text", None),
            )

            logger.info(
                f"[IMP-AUTOPILOT-002] Queued {queued} approval requests for human review. "
                f"Use approval_cli to review and approve."
            )
        except Exception as e:
            logger.warning(f"[IMP-AUTOPILOT-002] Failed to queue approval requests: {e}")

        logger.info(f"[Autopilot] Blocked: {self.session.blocked_reason}")

    def _execute_bounded_batch(self, proposal: PlanProposalV1) -> None:
        """Execute bounded batch of auto-approved actions.

        Uses SafeActionExecutor to run only safe actions (read-only commands
        and run-local artifact writes). Actions that would modify repo files
        are classified as requires_approval and not executed.

        BUILD-181: Records usage events for each action via ExecutorContext.

        Args:
            proposal: Plan proposal with auto-approved actions
        """
        logger.info("[Autopilot] Executing bounded batch with SafeActionExecutor")

        # Set phase for ExecutorContext tracking
        if self.executor_ctx:
            self.executor_ctx.set_phase("execute_batch")

        executor = SafeActionExecutor(
            workspace_root=self.workspace_root,
            command_timeout=30,
            dry_run=False,
        )

        batch = ExecutionBatch()
        executed = []
        successful = 0
        failed = 0
        requires_approval = 0

        for action in proposal.actions:
            if action.approval_status == "auto_approved":
                logger.info(
                    f"[Autopilot] Processing action: {action.action_id} ({action.action_type})"
                )

                # Determine action type and execute appropriately
                result = None

                if action.action_type in ["check_doc_drift", "run_lint", "run_test_collect"]:
                    # Read-only command actions
                    command = self._get_command_for_action(action)
                    if command:
                        result = executor.execute_command(command)
                elif action.action_type == "write_artifact":
                    # Run-local artifact write
                    artifact_path = getattr(action, "artifact_path", None)
                    artifact_content = getattr(action, "artifact_content", "{}")
                    if artifact_path:
                        result = executor.write_artifact(artifact_path, artifact_content)
                else:
                    # Unknown action type - classify based on whether it touches repo
                    if hasattr(action, "target_path"):
                        result = executor.write_artifact(
                            action.target_path, getattr(action, "content", "")
                        )

                if result:
                    batch.add_result(result)

                    if result.executed:
                        executed.append(action.action_id)
                        if result.success:
                            successful += 1
                        else:
                            failed += 1
                            # Record failure for stuck handling
                            if self.executor_ctx:
                                self.executor_ctx.record_failure()
                    elif result.classification == ActionClassification.REQUIRES_APPROVAL:
                        requires_approval += 1
                        logger.info(
                            f"[Autopilot] Action requires approval: {action.action_id} - {result.reason}"
                        )

                    # BUILD-181: Record usage event for this action
                    if self.executor_ctx and result.executed:
                        # Estimate tokens based on action type (simplified)
                        estimated_tokens = self._estimate_action_tokens(action)
                        self.executor_ctx.record_usage_event(
                            tokens_used=estimated_tokens,
                            event_id=f"action-{action.action_id}",
                        )
                        # Reset failure counter on success
                        if result.success:
                            self.executor_ctx.reset_failures()
                else:
                    # No result means we couldn't determine how to execute
                    # Mark as executed (passthrough) for backwards compatibility
                    executed.append(action.action_id)
                    successful += 1
                    logger.info(
                        f"[Autopilot] Action passed through: {action.action_id} ({action.action_type})"
                    )

        self.session.executed_action_ids = executed
        self.session.execution_summary = ExecutionSummary(
            total_actions=proposal.summary.total_actions,
            auto_approved_actions=proposal.summary.auto_approved_actions,
            executed_actions=len(executed),
            successful_actions=successful,
            failed_actions=failed,
            blocked_actions=requires_approval,
        )

        # Persist run-local artifacts
        self._persist_run_local_artifacts(proposal)

        # BUILD-181: Save usage events
        if self.executor_ctx:
            self.executor_ctx.save_usage_events()
            logger.info(
                f"[Autopilot] Budget remaining: {self.executor_ctx.get_budget_remaining():.1%}"
            )

        logger.info(
            f"[Autopilot] Executed {len(executed)} actions "
            f"({successful} successful, {failed} failed, {requires_approval} require approval)"
        )

    def _get_command_for_action(self, action) -> Optional[str]:
        """Get command string for an action.

        Args:
            action: Action with action_type

        Returns:
            Command string or None
        """
        action_commands = {
            "check_doc_drift": "python scripts/check_docs_drift.py",
            "check_sot_summary": "python scripts/tidy/sot_summary_refresh.py --check",
            "run_lint": "ruff check .",
            "run_test_collect": "pytest --collect-only -q",
        }
        return action_commands.get(action.action_type)

    def _estimate_action_tokens(self, action) -> int:
        """Estimate token usage for an action.

        Uses estimated_cost from action if available, otherwise defaults.

        Args:
            action: Action with optional estimated_cost

        Returns:
            Estimated token count
        """
        # Use action's estimated cost if available
        if hasattr(action, "estimated_cost") and action.estimated_cost:
            if action.estimated_cost.tokens:
                return action.estimated_cost.tokens

        # Default estimates by action type
        default_estimates = {
            "check_doc_drift": 100,
            "check_sot_summary": 50,
            "run_lint": 200,
            "run_test_collect": 150,
            "doc_update": 500,
            "file_move": 200,
            "file_delete": 100,
            "test_fix": 2000,
            "config_update": 300,
            "write_artifact": 100,
        }
        return default_estimates.get(action.action_type, 100)

    def _persist_run_local_artifacts(self, proposal: PlanProposalV1) -> None:
        """Persist run-local artifacts (gap report, plan proposal).

        IMP-FEAT-004: Save full PlanProposalV1 to enable loading for approved action execution.

        Args:
            proposal: Plan proposal to persist
        """
        # Ensure autonomy directory exists
        autonomy_dir = self.layout.base_dir / "autonomy"
        autonomy_dir.mkdir(parents=True, exist_ok=True)

        # Save gap report if we have one
        if self.session and self.session.gap_report_id:
            gaps_dir = self.layout.base_dir / "gaps"
            gaps_dir.mkdir(parents=True, exist_ok=True)
            # Gap report would be saved by the scanner; just log
            logger.debug(f"[Autopilot] Gap report ID: {self.session.gap_report_id}")

        # Save plan proposal - IMP-FEAT-004: Save full proposal for later loading
        plans_dir = self.layout.base_dir / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plans_dir / f"plan_proposal_{self.session.plan_proposal_id}.json"

        try:
            # Save full PlanProposalV1 using its built-in serialization
            proposal.save_to_file(plan_path)
            logger.info(f"[Autopilot] Saved full plan proposal: {plan_path}")
        except Exception as e:
            logger.warning(f"[Autopilot] Failed to save plan proposal: {e}")

    def execute_approved_proposals(self, session_id: str) -> int:
        """Execute proposals that have been approved via approval workflow.

        IMP-FEAT-004: Complete implementation for loading and executing approved proposals.

        This method:
        1. Loads the autopilot session to get the plan_proposal_id
        2. Loads the full PlanProposalV1 from the plans directory
        3. Filters actions to only those that have been approved
        4. Executes each approved action via SafeActionExecutor
        5. Records results and updates the session

        Args:
            session_id: Session ID to execute approved actions for

        Returns:
            Number of approved actions successfully executed

        Raises:
            RuntimeError: If autopilot is not enabled
        """
        if not self.enabled:
            raise RuntimeError(
                "Autopilot is disabled. Set enabled=True explicitly to execute approved proposals."
            )

        from .approval_service import ApprovalService

        logger.info(f"[IMP-FEAT-004] Executing approved proposals for session {session_id}")

        # Load approval service
        approval_svc = ApprovalService(
            run_id=self.run_id,
            project_id=self.project_id,
            workspace_root=self.workspace_root,
        )

        # Get approved actions for this session
        approved_ids = approval_svc.get_approved_actions(session_id=session_id)

        if not approved_ids:
            logger.info("[IMP-FEAT-004] No approved actions to execute")
            return 0

        logger.info(f"[IMP-FEAT-004] Found {len(approved_ids)} approved actions")

        # Step 1: Load the original session to get plan_proposal_id
        session_path = self.layout.base_dir / "autonomy" / f"{session_id}.json"
        if not session_path.exists():
            logger.error(f"[IMP-FEAT-004] Session file not found: {session_path}")
            return 0

        try:
            original_session = AutopilotSessionV1.load_from_file(session_path)
            plan_proposal_id = original_session.plan_proposal_id
            logger.info(f"[IMP-FEAT-004] Loaded session with plan_proposal_id: {plan_proposal_id}")
        except Exception as e:
            logger.error(f"[IMP-FEAT-004] Failed to load session: {e}")
            return 0

        # Step 2: Load the full PlanProposalV1
        plan_path = self.layout.base_dir / "plans" / f"plan_proposal_{plan_proposal_id}.json"
        if not plan_path.exists():
            logger.error(f"[IMP-FEAT-004] Plan proposal file not found: {plan_path}")
            return 0

        try:
            proposal = PlanProposalV1.load_from_file(plan_path)
            logger.info(f"[IMP-FEAT-004] Loaded plan proposal with {len(proposal.actions)} actions")
        except Exception as e:
            logger.error(f"[IMP-FEAT-004] Failed to load plan proposal: {e}")
            return 0

        # IMP-SAFETY-011: Validate approved action IDs against proposal actions
        # This prevents execution of actions that were never proposed
        pending_ids = {action.action_id for action in proposal.actions}
        approved_ids_set = set(approved_ids)
        invalid_ids = approved_ids_set - pending_ids

        if invalid_ids:
            logger.warning(
                f"[IMP-SAFETY-011] Rejected {len(invalid_ids)} invalid action IDs not found in proposal: "
                f"{sorted(invalid_ids)[:5]}{'...' if len(invalid_ids) > 5 else ''}"
            )
            # Filter out invalid IDs - only execute actions that exist in the proposal
            approved_ids = [aid for aid in approved_ids if aid in pending_ids]

            if not approved_ids:
                logger.error(
                    "[IMP-SAFETY-011] All approved action IDs were invalid. No actions to execute."
                )
                return 0

        # Step 3: Filter to approved actions only
        approved_actions = [a for a in proposal.actions if a.action_id in approved_ids]

        if not approved_actions:
            logger.warning(
                f"[IMP-FEAT-004] No matching actions found in proposal for approved IDs: "
                f"{approved_ids[:3]}{'...' if len(approved_ids) > 3 else ''}"
            )
            return 0

        logger.info(f"[IMP-FEAT-004] Executing {len(approved_actions)} approved actions")

        # Step 4: Execute approved actions via SafeActionExecutor
        executor = SafeActionExecutor(
            workspace_root=self.workspace_root,
            command_timeout=30,
            dry_run=False,
        )

        executed_count = 0
        successful_count = 0
        failed_count = 0

        for action in approved_actions:
            logger.info(
                f"[IMP-FEAT-004] Executing approved action: {action.action_id} ({action.action_type})"
            )

            result = None

            # Execute based on action type
            if action.action_type in ["check_doc_drift", "run_lint", "run_test_collect"]:
                # Read-only command actions
                command = self._get_command_for_action(action)
                if command:
                    result = executor.execute_command(command)
            elif action.action_type == "write_artifact":
                # Artifact write
                artifact_path = getattr(action, "artifact_path", None) or (
                    action.target_paths[0] if action.target_paths else None
                )
                artifact_content = getattr(action, "artifact_content", "{}")
                if artifact_path:
                    result = executor.write_artifact(artifact_path, artifact_content)
            elif action.command:
                # Action with explicit command
                result = executor.execute_command(action.command)
            elif action.target_paths:
                # File-based action
                for target_path in action.target_paths:
                    result = executor.write_artifact(target_path, getattr(action, "content", ""))

            if result:
                executed_count += 1
                if result.success:
                    successful_count += 1
                    logger.info(f"[IMP-FEAT-004] Action {action.action_id} executed successfully")
                else:
                    failed_count += 1
                    logger.warning(
                        f"[IMP-FEAT-004] Action {action.action_id} failed: {result.reason}"
                    )
            else:
                # No result means passthrough (action type not requiring execution)
                executed_count += 1
                successful_count += 1
                logger.info(f"[IMP-FEAT-004] Action {action.action_id} passed through")

        # Step 5: Log final results
        logger.info(
            f"[IMP-FEAT-004] Execution complete: "
            f"{executed_count} executed, {successful_count} successful, {failed_count} failed"
        )

        return successful_count

    def save_session(self) -> Path:
        """Save autopilot session to run-local artifact.

        Returns:
            Path to saved session file

        Raises:
            RuntimeError: If no session exists
        """
        if not self.session:
            raise RuntimeError("No session to save")

        # Ensure directories exist
        self.layout.ensure_directories()

        # Create autonomy directory
        autonomy_dir = self.layout.base_dir / "autonomy"
        autonomy_dir.mkdir(exist_ok=True)

        # Save session
        session_path = autonomy_dir / f"{self.session.session_id}.json"
        self.session.save_to_file(session_path)

        logger.info(f"[Autopilot] Saved session: {session_path}")
        return session_path


def run_autopilot_session(
    workspace_root: Path,
    project_id: str,
    run_id: str,
    anchor: IntentionAnchorV2,
    enabled: bool = False,
    save: bool = True,
) -> AutopilotSessionV1:
    """Run autopilot session (convenience function).

    Args:
        workspace_root: Root directory of workspace
        project_id: Project identifier
        run_id: Run identifier
        anchor: Intention anchor v2 to guide execution
        enabled: Whether autopilot is explicitly enabled (default: False)
        save: Whether to save session to file (default: True)

    Returns:
        AutopilotSessionV1 with execution log

    Raises:
        RuntimeError: If autopilot is not enabled
    """
    controller = AutopilotController(
        workspace_root=workspace_root,
        project_id=project_id,
        run_id=run_id,
        enabled=enabled,
    )

    session = controller.run_session(anchor)

    if save:
        controller.save_session()

    return session
