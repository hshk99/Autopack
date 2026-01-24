"""Tests for IMP-SAFETY-011: Validate approved action IDs in approval workflow.

Validates that the autopilot controller properly validates approved action IDs
against the proposal's pending actions before execution. This prevents execution
of actions that were never proposed (e.g., injected or spoofed action IDs).
"""

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch


from autopack.autonomy.autopilot import AutopilotController
from autopack.autonomy.models import AutopilotSessionV1
from autopack.file_layout import RunFileLayout
from autopack.planning.models import Action, PlanProposalV1, PlanSummary


class TestActionIdValidation:
    """Tests for IMP-SAFETY-011: Action ID validation in approval workflow."""

    def _create_controller_with_temp_workspace(self, tmpdir: str) -> AutopilotController:
        """Create a controller with a temporary workspace."""
        workspace = Path(tmpdir)
        controller = AutopilotController(
            workspace_root=workspace,
            project_id="test-project",
            run_id="test-run",
            enabled=True,
        )
        controller.layout = RunFileLayout(
            run_id="test-run",
            project_id="test-project",
            base_dir=workspace,
        )
        return controller

    def _create_session(
        self, controller: AutopilotController, session_id: str, plan_proposal_id: str
    ) -> AutopilotSessionV1:
        """Create and save a test session."""
        autonomy_dir = controller.layout.base_dir / "autonomy"
        autonomy_dir.mkdir(parents=True, exist_ok=True)

        session = AutopilotSessionV1(
            format_version="v1",
            project_id="test-project",
            run_id="test-run",
            session_id=session_id,
            started_at=datetime.now(timezone.utc),
            status="blocked_approval_required",
            anchor_id="test-anchor",
            gap_report_id="test-gaps",
            plan_proposal_id=plan_proposal_id,
        )
        session.save_to_file(autonomy_dir / f"{session_id}.json")
        return session

    def _create_proposal(
        self, controller: AutopilotController, plan_proposal_id: str, action_ids: list[str]
    ) -> PlanProposalV1:
        """Create and save a test proposal with given action IDs."""
        plans_dir = controller.layout.base_dir / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)

        actions = [
            Action(
                action_id=action_id,
                action_type="custom",  # Custom type passes through
                target_gap_ids=[f"gap-{i}"],
                risk_score=0.3,
                approval_status="requires_approval",
            )
            for i, action_id in enumerate(action_ids)
        ]

        proposal = PlanProposalV1(
            format_version="v1",
            project_id="test-project",
            run_id="test-run",
            generated_at=datetime.now(timezone.utc),
            anchor_id="test-anchor",
            gap_report_id="test-gaps",
            actions=actions,
            summary=PlanSummary(
                total_actions=len(actions),
                auto_approved_actions=0,
                requires_approval_actions=len(actions),
                blocked_actions=0,
            ),
        )
        proposal.save_to_file(plans_dir / f"plan_proposal_{plan_proposal_id}.json")
        return proposal

    def test_valid_action_ids_are_executed(self):
        """IMP-SAFETY-011: Valid action IDs should be executed successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            controller = self._create_controller_with_temp_workspace(tmpdir)
            self._create_session(controller, "session-001", "plan-001")
            self._create_proposal(
                controller, "plan-001", ["action-001", "action-002", "action-003"]
            )

            mock_approval_svc = MagicMock()
            mock_approval_svc.get_approved_actions.return_value = ["action-001", "action-002"]

            with patch(
                "autopack.autonomy.approval_service.ApprovalService",
                return_value=mock_approval_svc,
            ):
                result = controller.execute_approved_proposals("session-001")

            # Both valid IDs should be executed (passthrough for custom type)
            assert result == 2, f"Expected 2 executed actions, got {result}"

    def test_invalid_action_ids_are_rejected(self):
        """IMP-SAFETY-011: Invalid action IDs not in proposal must be rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            controller = self._create_controller_with_temp_workspace(tmpdir)
            self._create_session(controller, "session-001", "plan-001")
            self._create_proposal(controller, "plan-001", ["action-001", "action-002"])

            mock_approval_svc = MagicMock()
            # Attempt to execute action IDs that don't exist in proposal
            mock_approval_svc.get_approved_actions.return_value = [
                "invalid-001",
                "invalid-002",
                "nonexistent-id",
            ]

            with patch(
                "autopack.autonomy.approval_service.ApprovalService",
                return_value=mock_approval_svc,
            ):
                result = controller.execute_approved_proposals("session-001")

            # All IDs are invalid, so no actions should be executed
            assert result == 0, f"Expected 0 executed actions for all invalid IDs, got {result}"

    def test_mixed_valid_invalid_ids_executes_only_valid(self):
        """IMP-SAFETY-011: Mixed valid/invalid IDs should only execute valid ones."""
        with tempfile.TemporaryDirectory() as tmpdir:
            controller = self._create_controller_with_temp_workspace(tmpdir)
            self._create_session(controller, "session-001", "plan-001")
            self._create_proposal(
                controller, "plan-001", ["action-001", "action-002", "action-003"]
            )

            mock_approval_svc = MagicMock()
            # Mix of valid and invalid action IDs
            mock_approval_svc.get_approved_actions.return_value = [
                "action-001",  # Valid
                "invalid-id",  # Invalid
                "action-003",  # Valid
                "spoofed-action",  # Invalid
            ]

            with patch(
                "autopack.autonomy.approval_service.ApprovalService",
                return_value=mock_approval_svc,
            ):
                result = controller.execute_approved_proposals("session-001")

            # Only the 2 valid IDs should be executed
            assert result == 2, f"Expected 2 executed actions (valid only), got {result}"

    def test_invalid_ids_are_logged(self, caplog):
        """IMP-SAFETY-011: Invalid action IDs should be logged with warning."""
        import logging

        with tempfile.TemporaryDirectory() as tmpdir:
            controller = self._create_controller_with_temp_workspace(tmpdir)
            self._create_session(controller, "session-001", "plan-001")
            self._create_proposal(controller, "plan-001", ["action-001"])

            mock_approval_svc = MagicMock()
            mock_approval_svc.get_approved_actions.return_value = [
                "action-001",
                "invalid-id-123",
                "spoofed-action-456",
            ]

            with caplog.at_level(logging.WARNING):
                with patch(
                    "autopack.autonomy.approval_service.ApprovalService",
                    return_value=mock_approval_svc,
                ):
                    controller.execute_approved_proposals("session-001")

            # Verify warning was logged about invalid IDs
            assert any("IMP-SAFETY-011" in record.message for record in caplog.records)
            assert any("invalid action ids" in record.message.lower() for record in caplog.records)

    def test_all_invalid_ids_returns_zero_with_error_log(self, caplog):
        """IMP-SAFETY-011: All invalid IDs should return 0 and log error."""
        import logging

        with tempfile.TemporaryDirectory() as tmpdir:
            controller = self._create_controller_with_temp_workspace(tmpdir)
            self._create_session(controller, "session-001", "plan-001")
            self._create_proposal(controller, "plan-001", ["action-001", "action-002"])

            mock_approval_svc = MagicMock()
            mock_approval_svc.get_approved_actions.return_value = [
                "completely-fake-id",
                "another-fake-id",
            ]

            with caplog.at_level(logging.ERROR):
                with patch(
                    "autopack.autonomy.approval_service.ApprovalService",
                    return_value=mock_approval_svc,
                ):
                    result = controller.execute_approved_proposals("session-001")

            assert result == 0
            # Verify error was logged when all IDs are invalid
            assert any("IMP-SAFETY-011" in record.message for record in caplog.records)

    def test_empty_proposal_actions_rejects_all(self):
        """IMP-SAFETY-011: Empty proposal actions should reject all approved IDs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            controller = self._create_controller_with_temp_workspace(tmpdir)
            self._create_session(controller, "session-001", "plan-001")
            # Create proposal with NO actions
            self._create_proposal(controller, "plan-001", [])

            mock_approval_svc = MagicMock()
            mock_approval_svc.get_approved_actions.return_value = ["action-001"]

            with patch(
                "autopack.autonomy.approval_service.ApprovalService",
                return_value=mock_approval_svc,
            ):
                result = controller.execute_approved_proposals("session-001")

            # No actions in proposal means all approved IDs are invalid
            assert result == 0

    def test_duplicate_approved_ids_handled_correctly(self):
        """IMP-SAFETY-011: Duplicate approved IDs should not cause issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            controller = self._create_controller_with_temp_workspace(tmpdir)
            self._create_session(controller, "session-001", "plan-001")
            self._create_proposal(controller, "plan-001", ["action-001", "action-002"])

            mock_approval_svc = MagicMock()
            # Duplicate valid IDs
            mock_approval_svc.get_approved_actions.return_value = [
                "action-001",
                "action-001",  # Duplicate
                "action-002",
            ]

            with patch(
                "autopack.autonomy.approval_service.ApprovalService",
                return_value=mock_approval_svc,
            ):
                result = controller.execute_approved_proposals("session-001")

            # Should execute unique actions (duplicates execute twice but are same action)
            # The implementation uses list filtering, so duplicate IDs execute the action twice
            # This is existing behavior - the test verifies no crash
            assert result >= 2

    def test_security_prevents_injection_attack(self):
        """IMP-SAFETY-011: Security test - prevent action ID injection attack.

        An attacker could try to inject arbitrary action IDs into the approval
        workflow to execute actions that were never proposed. This test verifies
        that only action IDs present in the original proposal are executed.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            controller = self._create_controller_with_temp_workspace(tmpdir)
            self._create_session(controller, "session-001", "plan-001")
            # Proposal only has safe, limited actions
            self._create_proposal(controller, "plan-001", ["safe-action-001", "safe-action-002"])

            mock_approval_svc = MagicMock()
            # Attacker tries to inject dangerous action IDs
            mock_approval_svc.get_approved_actions.return_value = [
                "delete-all-files",  # Injected malicious ID
                "safe-action-001",  # Valid ID
                "execute-backdoor",  # Injected malicious ID
                "rm-rf-root",  # Injected malicious ID
            ]

            with patch(
                "autopack.autonomy.approval_service.ApprovalService",
                return_value=mock_approval_svc,
            ):
                result = controller.execute_approved_proposals("session-001")

            # Only the 1 valid action should execute
            # Malicious injected IDs are rejected
            assert result == 1, (
                f"Security check failed: Expected only 1 valid action to execute, "
                f"got {result}. Injected action IDs may have been executed!"
            )
