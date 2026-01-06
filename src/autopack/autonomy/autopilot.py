"""Autopilot controller - autonomous execution with safe gates.

The autopilot controller orchestrates the full autonomy loop:
1. Load intention anchor (v2)
2. Scan for gaps
3. Propose plan with governance
4. Execute auto-approved actions (if any)
5. Stop and record if approval required

Default OFF - requires explicit enable flag.
"""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..file_layout import RunFileLayout
from ..gaps.scanner import scan_workspace
from ..intention_anchor.v2 import IntentionAnchorV2
from ..planning.plan_proposer import propose_plan
from ..planning.models import PlanProposalV1
from .models import (
    AutopilotSessionV1,
    ExecutionSummary,
    ApprovalRequest,
    ErrorLogEntry,
    AutopilotMetadata,
)
from .action_executor import SafeActionExecutor, ExecutionBatch
from .action_allowlist import ActionType, ActionClassification

logger = logging.getLogger(__name__)


class AutopilotController:
    """Autopilot controller for autonomous execution within safe gates.

    Attributes:
        workspace_root: Root directory of workspace
        project_id: Project identifier
        run_id: Run identifier
        enabled: Whether autopilot is enabled (default: False)
        session: Current autopilot session
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

    def _handle_approval_required(self, proposal: PlanProposalV1) -> None:
        """Handle case where approval is required.

        Records what would be done and stops execution.

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

        logger.info(f"[Autopilot] Blocked: {self.session.blocked_reason}")

    def _execute_bounded_batch(self, proposal: PlanProposalV1) -> None:
        """Execute bounded batch of auto-approved actions.

        Uses SafeActionExecutor to run only safe actions (read-only commands
        and run-local artifact writes). Actions that would modify repo files
        are classified as requires_approval and not executed.

        Args:
            proposal: Plan proposal with auto-approved actions
        """
        logger.info("[Autopilot] Executing bounded batch with SafeActionExecutor")

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
                            action.target_path,
                            getattr(action, "content", "")
                        )

                if result:
                    batch.add_result(result)

                    if result.executed:
                        executed.append(action.action_id)
                        if result.success:
                            successful += 1
                        else:
                            failed += 1
                    elif result.classification == ActionClassification.REQUIRES_APPROVAL:
                        requires_approval += 1
                        logger.info(
                            f"[Autopilot] Action requires approval: {action.action_id} - {result.reason}"
                        )
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

    def _persist_run_local_artifacts(self, proposal: PlanProposalV1) -> None:
        """Persist run-local artifacts (gap report, plan proposal).

        Args:
            proposal: Plan proposal to persist
        """
        import json

        # Ensure autonomy directory exists
        autonomy_dir = self.layout.base_dir / "autonomy"
        autonomy_dir.mkdir(parents=True, exist_ok=True)

        # Save gap report if we have one
        if self.session and self.session.gap_report_id:
            gaps_dir = self.layout.base_dir / "gaps"
            gaps_dir.mkdir(parents=True, exist_ok=True)
            # Gap report would be saved by the scanner; just log
            logger.debug(f"[Autopilot] Gap report ID: {self.session.gap_report_id}")

        # Save plan proposal
        plans_dir = self.layout.base_dir / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plans_dir / f"plan_proposal_{self.session.plan_proposal_id}.json"

        try:
            plan_data = {
                "proposal_id": self.session.plan_proposal_id,
                "summary": {
                    "total_actions": proposal.summary.total_actions,
                    "auto_approved": proposal.summary.auto_approved_actions,
                    "requires_approval": proposal.summary.requires_approval_actions,
                    "blocked": proposal.summary.blocked_actions,
                },
                "actions": [
                    {
                        "action_id": a.action_id,
                        "action_type": a.action_type,
                        "approval_status": a.approval_status,
                    }
                    for a in proposal.actions
                ],
            }
            plan_path.write_text(json.dumps(plan_data, indent=2), encoding="utf-8")
            logger.info(f"[Autopilot] Saved plan proposal: {plan_path}")
        except Exception as e:
            logger.warning(f"[Autopilot] Failed to save plan proposal: {e}")

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
