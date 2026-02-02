"""Tests for IMP-REL-005: Autopilot rollback/recovery on API failures."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autopack.autonomy.autopilot import AutopilotController, StateCheckpoint
from autopack.autonomy.models import AutopilotSessionV1
from autopack.intention_anchor.v2 import IntentionAnchorV2


class TestStateCheckpoint:
    """Tests for StateCheckpoint class."""

    def test_checkpoint_captures_session_state(self):
        """Test that checkpoint captures current session state."""
        session = AutopilotSessionV1(
            format_version="v1",
            project_id="test-project",
            run_id="test-run",
            session_id="test-session",
            started_at=datetime.now(timezone.utc),
            status="running",
            anchor_id="test-anchor",
            gap_report_id="gap-123",
            plan_proposal_id="plan-456",
        )

        checkpoint = StateCheckpoint(session=session)

        assert checkpoint.session_state is not None
        assert checkpoint.session_state.gap_report_id == "gap-123"
        assert checkpoint.session_state.status == "running"

    def test_checkpoint_deep_copies_session(self):
        """Test that checkpoint creates a deep copy of session state."""
        session = AutopilotSessionV1(
            format_version="v1",
            project_id="test-project",
            run_id="test-run",
            session_id="test-session",
            started_at=datetime.now(timezone.utc),
            status="running",
            anchor_id="test-anchor",
            gap_report_id="gap-123",
            plan_proposal_id="plan-456",
        )

        checkpoint = StateCheckpoint(session=session)

        # Modify original session
        session.status = "completed"
        session.gap_report_id = "new-gap-id"

        # Checkpoint should be unchanged
        assert checkpoint.session_state.status == "running"
        assert checkpoint.session_state.gap_report_id == "gap-123"

    def test_restore_session_from_checkpoint(self):
        """Test that session can be restored from checkpoint."""
        session = AutopilotSessionV1(
            format_version="v1",
            project_id="test-project",
            run_id="test-run",
            session_id="test-session",
            started_at=datetime.now(timezone.utc),
            status="running",
            anchor_id="test-anchor",
            gap_report_id="gap-123",
            plan_proposal_id="plan-456",
        )

        # Create checkpoint
        checkpoint = StateCheckpoint(session=session)

        # Modify session
        session.status = "completed"
        session.gap_report_id = "new-gap"

        # Restore from checkpoint
        checkpoint.restore_session(session)

        # Should be back to original state
        assert session.status == "running"
        assert session.gap_report_id == "gap-123"

    def test_restore_with_none_state(self):
        """Test that restoring with None state is handled gracefully."""
        checkpoint = StateCheckpoint(session=None)
        session = AutopilotSessionV1(
            format_version="v1",
            project_id="test-project",
            run_id="test-run",
            session_id="test-session",
            started_at=datetime.now(timezone.utc),
            status="running",
            anchor_id="test-anchor",
            gap_report_id="gap-123",
            plan_proposal_id="plan-456",
        )

        # Should not raise exception
        checkpoint.restore_session(session)


class TestAutopilotCheckpointManagement:
    """Tests for checkpoint management in AutopilotController."""

    @pytest.fixture
    def controller(self, tmp_path: Path) -> AutopilotController:
        """Create an AutopilotController for testing."""
        return AutopilotController(
            workspace_root=tmp_path,
            project_id="test-project",
            run_id="test-run",
            enabled=True,
        )

    def test_create_state_checkpoint(self, controller: AutopilotController):
        """Test creating a state checkpoint."""
        session = AutopilotSessionV1(
            format_version="v1",
            project_id="test-project",
            run_id="test-run",
            session_id="test-session",
            started_at=datetime.now(timezone.utc),
            status="running",
            anchor_id="test-anchor",
            gap_report_id="gap-123",
            plan_proposal_id="plan-456",
        )
        controller.session = session

        checkpoint_id = controller._create_state_checkpoint("test_checkpoint")

        assert checkpoint_id is not None
        assert checkpoint_id in controller._state_checkpoints
        assert checkpoint_id == controller._last_checkpoint_id

    def test_restore_from_checkpoint(self, controller: AutopilotController):
        """Test restoring from a checkpoint."""
        session = AutopilotSessionV1(
            format_version="v1",
            project_id="test-project",
            run_id="test-run",
            session_id="test-session",
            started_at=datetime.now(timezone.utc),
            status="running",
            anchor_id="test-anchor",
            gap_report_id="gap-123",
            plan_proposal_id="plan-456",
        )
        controller.session = session

        # Create checkpoint
        checkpoint_id = controller._create_state_checkpoint("test")

        # Modify session
        session.status = "completed"
        session.gap_report_id = "new-id"

        # Restore
        success = controller._restore_from_checkpoint(checkpoint_id)

        assert success is True
        assert session.status == "running"
        assert session.gap_report_id == "gap-123"

    def test_restore_nonexistent_checkpoint_fails(self, controller: AutopilotController):
        """Test that restoring a nonexistent checkpoint returns False."""
        session = AutopilotSessionV1(
            format_version="v1",
            project_id="test-project",
            run_id="test-run",
            session_id="test-session",
            started_at=datetime.now(timezone.utc),
            status="running",
            anchor_id="test-anchor",
            gap_report_id="gap-123",
            plan_proposal_id="plan-456",
        )
        controller.session = session

        success = controller._restore_from_checkpoint("nonexistent-checkpoint")

        assert success is False

    def test_cleanup_checkpoints(self, controller: AutopilotController):
        """Test cleaning up checkpoints."""
        session = AutopilotSessionV1(
            format_version="v1",
            project_id="test-project",
            run_id="test-run",
            session_id="test-session",
            started_at=datetime.now(timezone.utc),
            status="running",
            anchor_id="test-anchor",
            gap_report_id="gap-123",
            plan_proposal_id="plan-456",
        )
        controller.session = session

        # Create multiple checkpoints
        controller._create_state_checkpoint("checkpoint1")
        controller._create_state_checkpoint("checkpoint2")
        controller._create_state_checkpoint("checkpoint3")

        assert len(controller._state_checkpoints) == 3

        # Cleanup
        controller._cleanup_checkpoints()

        assert len(controller._state_checkpoints) == 0
        assert controller._last_checkpoint_id is None


class TestAutopilotAPIFailureRollback:
    """Tests for rollback behavior on API failures."""

    @pytest.fixture
    def controller(self, tmp_path: Path) -> AutopilotController:
        """Create an AutopilotController for testing."""
        return AutopilotController(
            workspace_root=tmp_path,
            project_id="test-project",
            run_id="test-run",
            enabled=True,
        )

    def test_gap_scan_failure_rolls_back_state(self, controller: AutopilotController):
        """Test that gap scan failure triggers rollback."""
        anchor = MagicMock(spec=IntentionAnchorV2)
        anchor.raw_input_digest = "test-digest"

        with patch("autopack.autonomy.autopilot.create_executor_context") as mock_create_ctx:
            mock_ctx = MagicMock()
            mock_ctx.circuit_breaker.is_available.return_value = True
            mock_ctx.circuit_breaker.state.value = "closed"
            mock_ctx.circuit_breaker.health_score = 1.0
            mock_ctx.circuit_breaker.total_checks = 0
            mock_ctx.circuit_breaker.checks_passed = 0
            mock_ctx.get_budget_remaining.return_value = 100.0
            mock_create_ctx.return_value = mock_ctx

            with patch("autopack.autonomy.autopilot.scan_workspace") as mock_scan:
                mock_scan.side_effect = RuntimeError("Gap scan failed")

                session = controller.run_session(anchor)

                # Session should be marked as failed
                assert session.status == "failed"
                # Error should be logged
                assert len(session.error_log) > 0
                assert session.error_log[0].error_type == "GapScanError"

    def test_plan_proposal_failure_rolls_back_state(self, controller: AutopilotController):
        """Test that plan proposal failure triggers rollback."""
        anchor = MagicMock(spec=IntentionAnchorV2)
        anchor.raw_input_digest = "test-digest"

        with patch("autopack.autonomy.autopilot.create_executor_context") as mock_create_ctx:
            mock_ctx = MagicMock()
            mock_ctx.circuit_breaker.is_available.return_value = True
            mock_ctx.circuit_breaker.state.value = "closed"
            mock_ctx.circuit_breaker.health_score = 1.0
            mock_ctx.circuit_breaker.total_checks = 0
            mock_ctx.circuit_breaker.checks_passed = 0
            mock_ctx.get_budget_remaining.return_value = 100.0
            mock_create_ctx.return_value = mock_ctx

            with patch("autopack.autonomy.autopilot.scan_workspace") as mock_scan:
                mock_report = MagicMock()
                mock_report.report_id = "gap-123"
                mock_report.summary.total_gaps = 0
                mock_report.summary.autopilot_blockers = 0
                mock_scan.return_value = mock_report

                with patch("autopack.autonomy.autopilot.propose_plan") as mock_propose:
                    mock_propose.side_effect = RuntimeError("Plan proposal failed")

                    session = controller.run_session(anchor)

                    # Session should be marked as failed
                    assert session.status == "failed"
                    # Error should be logged
                    assert len(session.error_log) > 0
                    assert session.error_log[0].error_type == "PlanProposalError"

    def test_checkpoints_cleaned_up_after_session(self, controller: AutopilotController):
        """Test that checkpoints are cleaned up after session completes."""
        anchor = MagicMock(spec=IntentionAnchorV2)
        anchor.raw_input_digest = "test-digest"

        with patch("autopack.autonomy.autopilot.create_executor_context") as mock_create_ctx:
            mock_ctx = MagicMock()
            mock_ctx.circuit_breaker.is_available.return_value = True
            mock_ctx.circuit_breaker.state.value = "closed"
            mock_ctx.circuit_breaker.health_score = 1.0
            mock_ctx.circuit_breaker.total_checks = 0
            mock_ctx.circuit_breaker.checks_passed = 0
            mock_ctx.get_budget_remaining.return_value = 100.0
            mock_create_ctx.return_value = mock_ctx

            with patch("autopack.autonomy.autopilot.scan_workspace") as mock_scan:
                mock_report = MagicMock()
                mock_report.report_id = "gap-123"
                mock_report.summary.total_gaps = 0
                mock_report.summary.autopilot_blockers = 0
                mock_scan.return_value = mock_report

                with patch("autopack.autonomy.autopilot.propose_plan") as mock_propose:
                    mock_proposal = MagicMock()
                    mock_proposal.summary.auto_approved_actions = 0
                    mock_proposal.summary.requires_approval_actions = 0
                    mock_proposal.summary.blocked_actions = 0
                    mock_proposal.summary.total_actions = 0
                    mock_propose.return_value = mock_proposal

                    controller.run_session(anchor)

                    # Checkpoints should be cleaned up
                    assert len(controller._state_checkpoints) == 0
                    assert controller._last_checkpoint_id is None

    def test_error_logged_on_api_failure(self, controller: AutopilotController):
        """Test that API errors are logged in session error_log."""
        anchor = MagicMock(spec=IntentionAnchorV2)
        anchor.raw_input_digest = "test-digest"
        error_message = "API connection timeout"

        with patch("autopack.autonomy.autopilot.create_executor_context") as mock_create_ctx:
            mock_ctx = MagicMock()
            mock_ctx.circuit_breaker.is_available.return_value = True
            mock_ctx.circuit_breaker.state.value = "closed"
            mock_ctx.circuit_breaker.health_score = 1.0
            mock_ctx.circuit_breaker.total_checks = 0
            mock_ctx.circuit_breaker.checks_passed = 0
            mock_ctx.get_budget_remaining.return_value = 100.0
            mock_create_ctx.return_value = mock_ctx

            with patch("autopack.autonomy.autopilot.scan_workspace") as mock_scan:
                mock_scan.side_effect = RuntimeError(error_message)

                session = controller.run_session(anchor)

                # Error should be in log with original message
                assert len(session.error_log) > 0
                assert error_message in session.error_log[0].error_message

    def test_research_cycle_failure_does_not_fail_session(self, controller: AutopilotController):
        """Test that research cycle failure allows session to continue."""
        anchor = MagicMock(spec=IntentionAnchorV2)
        anchor.raw_input_digest = "test-digest"

        with patch("autopack.autonomy.autopilot.create_executor_context") as mock_create_ctx:
            mock_ctx = MagicMock()
            mock_ctx.circuit_breaker.is_available.return_value = True
            mock_ctx.circuit_breaker.state.value = "closed"
            mock_ctx.circuit_breaker.health_score = 1.0
            mock_ctx.circuit_breaker.total_checks = 0
            mock_ctx.circuit_breaker.checks_passed = 0
            mock_ctx.get_budget_remaining.return_value = 100.0
            mock_create_ctx.return_value = mock_ctx

            with patch("autopack.autonomy.autopilot.scan_workspace") as mock_scan:
                mock_report = MagicMock()
                mock_report.report_id = "gap-123"
                mock_report.summary.total_gaps = 10  # Trigger research cycle
                mock_report.summary.autopilot_blockers = 2
                mock_scan.return_value = mock_report

                with patch("autopack.autonomy.autopilot.propose_plan") as mock_propose:
                    mock_proposal = MagicMock()
                    mock_proposal.summary.auto_approved_actions = 0
                    mock_proposal.summary.requires_approval_actions = 0
                    mock_proposal.summary.blocked_actions = 0
                    mock_proposal.summary.total_actions = 0
                    mock_propose.return_value = mock_proposal

                    with patch.object(
                        controller, "should_execute_research_cycle", return_value=True
                    ):
                        with patch.object(
                            controller, "execute_integrated_research_cycle"
                        ) as mock_research:
                            mock_research.side_effect = RuntimeError("Research failed")

                            session = controller.run_session(anchor)

                            # Session should NOT be failed due to research error
                            # It should be in approval_required state instead
                            assert session.status != "failed"
                            # Error should still be logged
                            assert any(
                                err.error_type == "ResearchCycleError" for err in session.error_log
                            )
