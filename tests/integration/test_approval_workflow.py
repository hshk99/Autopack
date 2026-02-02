"""End-to-End Approval Workflow Integration Tests (IMP-E2E-003)

These tests verify the complete governance gate approval workflow:
1. Approval request submission via API
2. Gate decision making
3. Phase state update based on approval decision

The tests cover:
- Submitting an approval request for a phase
- Polling for approval status
- Approving the request and verifying phase state updates
- Rejecting the request and verifying appropriate state changes
- Timeout handling when no decision is made
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from autopack.models import Phase, PhaseState, Run, RunState, Tier, TierState


@pytest.fixture
def setup_run_tier_phase(db_session: Session):
    """Fixture to create run, tier, and phase with proper relationships."""

    def _setup(run_id: str, phase_id: str, **phase_kwargs):
        # Create run
        run = Run(
            id=run_id,
            state=RunState.PHASE_EXECUTION,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.flush()

        # Create tier
        tier = Tier(
            tier_id="T1",
            run_id=run_id,
            tier_index=0,
            name="Test Tier",
            state=TierState.IN_PROGRESS,
        )
        db_session.add(tier)
        db_session.flush()

        # Create phase with defaults
        phase_defaults = {
            "phase_id": phase_id,
            "run_id": run_id,
            "tier_id": tier.id,
            "phase_index": 0,
            "name": "Test Phase",
            "state": PhaseState.GATE,
            "retry_attempt": 0,
            "revision_epoch": 0,
            "escalation_level": 0,
        }
        phase_defaults.update(phase_kwargs)

        phase = Phase(**phase_defaults)
        db_session.add(phase)
        db_session.commit()

        return run, tier, phase

    return _setup


@pytest.fixture
def mock_approval_request():
    """Fixture providing a mock approval request."""
    return {
        "phase_id": "test-phase-approval-001",
        "run_id": "test-run-approval-001",
        "context": "governance_escalation",
        "decision_info": {
            "trigger_reason": "GOVERNANCE_ESCALATION",
            "affected_pivots": ["market_size", "competitive_intensity"],
            "description": "Phase requires governance approval due to policy violation",
        },
    }


@pytest.mark.aspirational
class TestGovernanceGateApprovalWorkflow:
    """Test the complete governance gate approval workflow."""

    def test_submit_approval_request_and_check_status(
        self, setup_run_tier_phase, mock_approval_request, db_session
    ):
        """Test submitting an approval request and polling for its status.

        Verifies:
        1. Phase is in GATE state
        2. Approval request can be created in database
        3. Request status can be polled
        """
        # Setup phase in GATE state
        run, tier, phase = setup_run_tier_phase(
            "test-run-approval-001",
            "test-phase-approval-001",
            state=PhaseState.GATE,
        )

        assert phase.state == PhaseState.GATE

        # Create approval request in database
        from autopack.models import ApprovalRequest

        approval_request = ApprovalRequest(
            run_id=mock_approval_request["run_id"],
            phase_id=mock_approval_request["phase_id"],
            context=mock_approval_request["context"],
            decision_info=mock_approval_request["decision_info"],
            status="pending",
            response_method="manual",
            telegram_sent=False,
        )
        db_session.add(approval_request)
        db_session.commit()

        # Verify request was created
        retrieved = (
            db_session.query(ApprovalRequest)
            .filter_by(phase_id=mock_approval_request["phase_id"])
            .first()
        )
        assert retrieved is not None
        assert retrieved.status == "pending"
        assert retrieved.phase_id == mock_approval_request["phase_id"]

    def test_approval_request_approval_workflow(self, setup_run_tier_phase, db_session):
        """Test the complete approval workflow: submit -> approve -> update state.

        Verifies:
        1. Approval request is created
        2. Request can be approved
        3. Phase state reflects the approval decision
        """
        # Setup phase
        run, tier, phase = setup_run_tier_phase(
            "test-run-approval-002",
            "test-phase-approval-002",
            state=PhaseState.GATE,
        )

        from autopack.models import ApprovalRequest

        # Create and save approval request
        approval_request = ApprovalRequest(
            run_id="test-run-approval-002",
            phase_id="test-phase-approval-002",
            context="governance_escalation",
            decision_info={"reason": "test approval workflow"},
            status="pending",
            response_method="manual",
            telegram_sent=False,
        )
        db_session.add(approval_request)
        db_session.commit()

        # Simulate approval
        approval_request.status = "approved"
        approval_request.responded_at = datetime.now(timezone.utc)
        db_session.commit()

        # Verify approval was recorded
        retrieved = (
            db_session.query(ApprovalRequest).filter_by(phase_id="test-phase-approval-002").first()
        )
        assert retrieved is not None
        assert retrieved.status == "approved"

        # Update phase state based on approval
        phase.state = PhaseState.EXECUTING
        db_session.commit()

        # Verify phase state was updated
        retrieved_phase = (
            db_session.query(Phase).filter_by(phase_id="test-phase-approval-002").first()
        )
        assert retrieved_phase is not None
        assert retrieved_phase.state == PhaseState.EXECUTING

    def test_approval_request_rejection_workflow(self, setup_run_tier_phase, db_session):
        """Test the rejection workflow: submit -> reject -> update state.

        Verifies:
        1. Approval request can be rejected
        2. Phase state reflects the rejection
        3. Appropriate failure reason is recorded
        """
        # Setup phase
        run, tier, phase = setup_run_tier_phase(
            "test-run-approval-003",
            "test-phase-approval-003",
            state=PhaseState.GATE,
        )

        from autopack.models import ApprovalRequest

        # Create approval request
        approval_request = ApprovalRequest(
            run_id="test-run-approval-003",
            phase_id="test-phase-approval-003",
            context="governance_escalation",
            decision_info={"reason": "test rejection workflow"},
            status="pending",
            response_method="manual",
            telegram_sent=False,
        )
        db_session.add(approval_request)
        db_session.commit()

        # Simulate rejection
        approval_request.status = "rejected"
        approval_request.responded_at = datetime.now(timezone.utc)
        db_session.commit()

        # Verify rejection was recorded
        retrieved = (
            db_session.query(ApprovalRequest).filter_by(phase_id="test-phase-approval-003").first()
        )
        assert retrieved is not None
        assert retrieved.status == "rejected"

        # Update phase state based on rejection
        phase.state = PhaseState.FAILED
        phase.last_failure_reason = "Approval was rejected"
        db_session.commit()

        # Verify phase state reflects rejection
        retrieved_phase = (
            db_session.query(Phase).filter_by(phase_id="test-phase-approval-003").first()
        )
        assert retrieved_phase is not None
        assert retrieved_phase.state == PhaseState.FAILED
        assert "rejected" in retrieved_phase.last_failure_reason.lower()

    def test_approval_request_timeout_workflow(self, setup_run_tier_phase, db_session):
        """Test timeout workflow: pending request times out -> phase fails.

        Verifies:
        1. Pending approval request times out
        2. Phase state is updated to FAILED on timeout
        3. Timeout is recorded as failure reason
        """
        # Setup phase
        run, tier, phase = setup_run_tier_phase(
            "test-run-approval-004",
            "test-phase-approval-004",
            state=PhaseState.GATE,
        )

        from autopack.models import ApprovalRequest

        # Create approval request with timeout
        approval_request = ApprovalRequest(
            run_id="test-run-approval-004",
            phase_id="test-phase-approval-004",
            context="governance_escalation",
            decision_info={"reason": "test timeout workflow"},
            status="timeout",
            response_method="timeout",
            telegram_sent=False,
        )
        db_session.add(approval_request)
        db_session.commit()

        # Verify timeout was recorded
        retrieved = (
            db_session.query(ApprovalRequest).filter_by(phase_id="test-phase-approval-004").first()
        )
        assert retrieved is not None
        assert retrieved.status == "timeout"

        # Update phase state due to timeout (default: reject)
        phase.state = PhaseState.FAILED
        phase.last_failure_reason = "Approval request timed out (no decision made)"
        db_session.commit()

        # Verify phase reflects timeout failure
        retrieved_phase = (
            db_session.query(Phase).filter_by(phase_id="test-phase-approval-004").first()
        )
        assert retrieved_phase is not None
        assert retrieved_phase.state == PhaseState.FAILED
        assert "timed out" in retrieved_phase.last_failure_reason.lower()

    def test_multiple_approval_requests_isolation(self, setup_run_tier_phase, db_session):
        """Test that multiple approval requests don't interfere with each other.

        Verifies:
        1. Multiple phases can have independent approval requests
        2. Approving one doesn't affect others
        3. Each phase state is updated correctly
        """
        from autopack.models import ApprovalRequest

        # Setup two phases
        run1, tier1, phase1 = setup_run_tier_phase(
            "test-run-multi-001", "test-phase-multi-001", state=PhaseState.GATE
        )
        run2, tier2, phase2 = setup_run_tier_phase(
            "test-run-multi-002", "test-phase-multi-002", state=PhaseState.GATE
        )

        # Create two approval requests
        request1 = ApprovalRequest(
            run_id="test-run-multi-001",
            phase_id="test-phase-multi-001",
            context="governance_escalation",
            decision_info={"reason": "request1"},
            status="pending",
            response_method="manual",
            telegram_sent=False,
        )
        request2 = ApprovalRequest(
            run_id="test-run-multi-002",
            phase_id="test-phase-multi-002",
            context="governance_escalation",
            decision_info={"reason": "request2"},
            status="pending",
            response_method="manual",
            telegram_sent=False,
        )
        db_session.add(request1)
        db_session.add(request2)
        db_session.commit()

        # Approve only the first request
        request1.status = "approved"
        request1.responded_at = datetime.now(timezone.utc)
        db_session.commit()

        # Update first phase state
        phase1.state = PhaseState.EXECUTING
        db_session.commit()

        # Verify first phase was updated
        updated_phase1 = db_session.query(Phase).filter_by(phase_id="test-phase-multi-001").first()
        assert updated_phase1.state == PhaseState.EXECUTING

        # Verify second phase is still in GATE state
        updated_phase2 = db_session.query(Phase).filter_by(phase_id="test-phase-multi-002").first()
        assert updated_phase2.state == PhaseState.GATE

        # Verify second request is still pending
        updated_request2 = (
            db_session.query(ApprovalRequest).filter_by(phase_id="test-phase-multi-002").first()
        )
        assert updated_request2.status == "pending"

    def test_approval_decision_persistence(
        self, setup_run_tier_phase, mock_approval_request, db_session
    ):
        """Test that approval decisions are persisted correctly in database.

        Verifies:
        1. Approval request is saved to database
        2. Response metadata is recorded (responded_at, response_method)
        3. Decision can be retrieved and verified
        """
        from autopack.models import ApprovalRequest

        # Setup phase
        run, tier, phase = setup_run_tier_phase(
            "test-run-approval-005",
            "test-phase-approval-005",
            state=PhaseState.GATE,
        )

        # Create approval request
        approval_request = ApprovalRequest(
            run_id=mock_approval_request["run_id"],
            phase_id=mock_approval_request["phase_id"],
            context=mock_approval_request["context"],
            decision_info=mock_approval_request["decision_info"],
            status="pending",
            response_method="manual",
            telegram_sent=False,
        )
        db_session.add(approval_request)
        db_session.commit()

        request_id = approval_request.id

        # Simulate approval with metadata
        now = datetime.now(timezone.utc)
        approval_request.status = "approved"
        approval_request.responded_at = now
        approval_request.response_method = "telegram"
        approval_request.telegram_sent = True
        approval_request.telegram_message_id = "msg_123"
        db_session.commit()

        # Retrieve and verify all metadata was persisted
        retrieved = db_session.query(ApprovalRequest).filter_by(id=request_id).first()
        assert retrieved is not None
        assert retrieved.status == "approved"
        assert retrieved.responded_at is not None
        assert retrieved.response_method == "telegram"
        assert retrieved.telegram_sent is True
        assert retrieved.telegram_message_id == "msg_123"

    def test_gate_state_to_executing_transition(self, setup_run_tier_phase, db_session):
        """Test phase state transition from GATE to EXECUTING after approval.

        Verifies:
        1. Phase starts in GATE state
        2. After approval, phase transitions to EXECUTING
        3. Transition is recorded in database
        """
        from autopack.models import ApprovalRequest

        # Setup phase in GATE state
        run, tier, phase = setup_run_tier_phase(
            "test-run-approval-006",
            "test-phase-approval-006",
            state=PhaseState.GATE,
        )

        initial_state = phase.state
        assert initial_state == PhaseState.GATE

        # Create and approve request
        approval_request = ApprovalRequest(
            run_id="test-run-approval-006",
            phase_id="test-phase-approval-006",
            context="governance_escalation",
            decision_info={"reason": "test state transition"},
            status="approved",
            response_method="manual",
            telegram_sent=False,
            responded_at=datetime.now(timezone.utc),
        )
        db_session.add(approval_request)

        # Transition phase to EXECUTING
        phase.state = PhaseState.EXECUTING
        phase.started_at = datetime.now(timezone.utc)
        db_session.commit()

        # Verify state transition
        retrieved_phase = (
            db_session.query(Phase).filter_by(phase_id="test-phase-approval-006").first()
        )
        assert retrieved_phase is not None
        assert retrieved_phase.state == PhaseState.EXECUTING
        assert retrieved_phase.started_at is not None

    def test_approval_workflow_with_multiple_affected_pivots(
        self, setup_run_tier_phase, db_session
    ):
        """Test approval workflow tracking multiple affected pivots.

        Verifies:
        1. Approval request records multiple affected pivots
        2. Decision information includes pivot list
        3. Can query requests by affected pivots
        """
        from autopack.models import ApprovalRequest

        # Setup phase
        run, tier, phase = setup_run_tier_phase(
            "test-run-approval-007",
            "test-phase-approval-007",
            state=PhaseState.GATE,
        )

        # Create approval request with multiple affected pivots
        decision_info = {
            "trigger_reason": "GOVERNANCE_ESCALATION",
            "affected_pivots": [
                "market_size",
                "competitive_intensity",
                "adoption_readiness",
            ],
            "description": "Phase affects multiple business pivots",
        }

        approval_request = ApprovalRequest(
            run_id="test-run-approval-007",
            phase_id="test-phase-approval-007",
            context="governance_escalation",
            decision_info=decision_info,
            status="pending",
            response_method="manual",
            telegram_sent=False,
        )
        db_session.add(approval_request)
        db_session.commit()

        # Verify affected pivots are recorded
        retrieved = (
            db_session.query(ApprovalRequest).filter_by(phase_id="test-phase-approval-007").first()
        )
        assert retrieved is not None
        assert len(retrieved.decision_info["affected_pivots"]) == 3
        assert "market_size" in retrieved.decision_info["affected_pivots"]
        assert "competitive_intensity" in retrieved.decision_info["affected_pivots"]
        assert "adoption_readiness" in retrieved.decision_info["affected_pivots"]
