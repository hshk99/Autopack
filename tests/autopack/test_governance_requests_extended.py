"""Extended tests for governance_requests.py.

Tests cover:
- Approval flow (request creation, approval, rejection)
- Tier escalation (tier 1 -> tier 2 -> tier 3)
- Auto-approval based on risk level and confidence
- Edge cases (invalid requests, missing data, concurrent approvals)
- Integration with phase execution
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path


class TestApprovalFlow:
    """Test approval flow for governance requests."""

    def test_create_governance_request_basic(self):
        """Test creating a basic governance request."""
        from autopack.governance_requests import GovernanceRequest, RequestType

        request = GovernanceRequest(
            request_id="req_001",
            request_type=RequestType.PHASE_APPROVAL,
            phase_id="phase_001",
            description="Approve database migration phase",
            risk_level="medium",
            requested_by="system",
            requested_at=datetime.utcnow()
        )

        assert request.request_id == "req_001"
        assert request.request_type == RequestType.PHASE_APPROVAL
        assert request.phase_id == "phase_001"
        assert request.risk_level == "medium"
        assert request.status == "pending"

    def test_approve_request(self):
        """Test approving a governance request."""
        from autopack.governance_requests import GovernanceRequest, RequestType

        request = GovernanceRequest(
            request_id="req_001",
            request_type=RequestType.PHASE_APPROVAL,
            phase_id="phase_001",
            description="Test approval",
            risk_level="low",
            requested_by="system",
            requested_at=datetime.utcnow()
        )

        # Approve request
        request.approve(approved_by="admin", comments="Looks good")

        assert request.status == "approved"
        assert request.approved_by == "admin"
        assert request.approval_comments == "Looks good"
        assert request.approved_at is not None

    def test_reject_request(self):
        """Test rejecting a governance request."""
        from autopack.governance_requests import GovernanceRequest, RequestType

        request = GovernanceRequest(
            request_id="req_001",
            request_type=RequestType.PHASE_APPROVAL,
            phase_id="phase_001",
            description="Test rejection",
            risk_level="high",
            requested_by="system",
            requested_at=datetime.utcnow()
        )

        # Reject request
        request.reject(rejected_by="admin", reason="Insufficient testing")

        assert request.status == "rejected"
        assert request.rejected_by == "admin"
        assert request.rejection_reason == "Insufficient testing"
        assert request.rejected_at is not None

    def test_cannot_approve_already_approved(self):
        """Test that already approved request cannot be approved again."""
        from autopack.governance_requests import GovernanceRequest, RequestType

        request = GovernanceRequest(
            request_id="req_001",
            request_type=RequestType.PHASE_APPROVAL,
            phase_id="phase_001",
            description="Test",
            risk_level="low",
            requested_by="system",
            requested_at=datetime.utcnow()
        )

        # First approval
        request.approve(approved_by="admin1")

        # Second approval should raise error
        with pytest.raises(ValueError, match="already approved|already processed"):
            request.approve(approved_by="admin2")

    def test_cannot_reject_already_rejected(self):
        """Test that already rejected request cannot be rejected again."""
        from autopack.governance_requests import GovernanceRequest, RequestType

        request = GovernanceRequest(
            request_id="req_001",
            request_type=RequestType.PHASE_APPROVAL,
            phase_id="phase_001",
            description="Test",
            risk_level="low",
            requested_by="system",
            requested_at=datetime.utcnow()
        )

        # First rejection
        request.reject(rejected_by="admin1", reason="Reason 1")

        # Second rejection should raise error
        with pytest.raises(ValueError, match="already rejected|already processed"):
            request.reject(rejected_by="admin2", reason="Reason 2")


class TestTierEscalation:
    """Test tier escalation for governance requests."""

    def test_tier_1_auto_approval(self):
        """Test that tier 1 (low risk) requests can be auto-approved."""
        from autopack.governance_requests import GovernanceRequest, RequestType, should_auto_approve

        request = GovernanceRequest(
            request_id="req_001",
            request_type=RequestType.PHASE_APPROVAL,
            phase_id="phase_001",
            description="Low risk change",
            risk_level="low",
            requested_by="system",
            requested_at=datetime.utcnow()
        )

        # Tier 1 (low risk) should be auto-approvable
        assert should_auto_approve(request) is True

    def test_tier_2_requires_approval(self):
        """Test that tier 2 (medium risk) requires human approval."""
        from autopack.governance_requests import GovernanceRequest, RequestType, should_auto_approve

        request = GovernanceRequest(
            request_id="req_001",
            request_type=RequestType.PHASE_APPROVAL,
            phase_id="phase_001",
            description="Medium risk change",
            risk_level="medium",
            requested_by="system",
            requested_at=datetime.utcnow()
        )

        # Tier 2 (medium risk) should NOT be auto-approved
        assert should_auto_approve(request) is False

    def test_tier_3_requires_senior_approval(self):
        """Test that tier 3 (high risk) requires senior approval."""
        from autopack.governance_requests import GovernanceRequest, RequestType, requires_senior_approval

        request = GovernanceRequest(
            request_id="req_001",
            request_type=RequestType.PHASE_APPROVAL,
            phase_id="phase_001",
            description="High risk change",
            risk_level="high",
            requested_by="system",
            requested_at=datetime.utcnow()
        )

        # Tier 3 (high risk) should require senior approval
        assert requires_senior_approval(request) is True

    def test_escalation_on_timeout(self):
        """Test that requests escalate to higher tier on timeout."""
        from autopack.governance_requests import GovernanceRequest, RequestType, should_escalate

        # Create request from 2 hours ago
        old_time = datetime.utcnow() - timedelta(hours=2)
        request = GovernanceRequest(
            request_id="req_001",
            request_type=RequestType.PHASE_APPROVAL,
            phase_id="phase_001",
            description="Pending request",
            risk_level="medium",
            requested_by="system",
            requested_at=old_time
        )

        # Should escalate after 1 hour timeout
        assert should_escalate(request, timeout_hours=1) is True

    def test_no_escalation_within_timeout(self):
        """Test that requests don't escalate within timeout period."""
        from autopack.governance_requests import GovernanceRequest, RequestType, should_escalate

        # Create recent request
        request = GovernanceRequest(
            request_id="req_001",
            request_type=RequestType.PHASE_APPROVAL,
            phase_id="phase_001",
            description="Recent request",
            risk_level="medium",
            requested_by="system",
            requested_at=datetime.utcnow()
        )

        # Should NOT escalate within timeout
        assert should_escalate(request, timeout_hours=1) is False


class TestAutoApproval:
    """Test auto-approval logic based on risk and confidence."""

    def test_auto_approve_low_risk_high_confidence(self):
        """Test auto-approval for low risk + high confidence."""
        from autopack.governance_requests import GovernanceRequest, RequestType, auto_approve_if_eligible

        request = GovernanceRequest(
            request_id="req_001",
            request_type=RequestType.PHASE_APPROVAL,
            phase_id="phase_001",
            description="Safe change",
            risk_level="low",
            requested_by="system",
            requested_at=datetime.utcnow(),
            confidence_score=0.95
        )

        # Should auto-approve
        result = auto_approve_if_eligible(request)
        assert result is True
        assert request.status == "approved"
        assert request.approved_by == "auto"

    def test_no_auto_approve_low_confidence(self):
        """Test that low confidence prevents auto-approval."""
        from autopack.governance_requests import GovernanceRequest, RequestType, auto_approve_if_eligible

        request = GovernanceRequest(
            request_id="req_001",
            request_type=RequestType.PHASE_APPROVAL,
            phase_id="phase_001",
            description="Uncertain change",
            risk_level="low",
            requested_by="system",
            requested_at=datetime.utcnow(),
            confidence_score=0.5
        )

        # Should NOT auto-approve due to low confidence
        result = auto_approve_if_eligible(request)
        assert result is False
        assert request.status == "pending"

    def test_no_auto_approve_high_risk(self):
        """Test that high risk prevents auto-approval."""
        from autopack.governance_requests import GovernanceRequest, RequestType, auto_approve_if_eligible

        request = GovernanceRequest(
            request_id="req_001",
            request_type=RequestType.PHASE_APPROVAL,
            phase_id="phase_001",
            description="Risky change",
            risk_level="high",
            requested_by="system",
            requested_at=datetime.utcnow(),
            confidence_score=0.95
        )

        # Should NOT auto-approve due to high risk
        result = auto_approve_if_eligible(request)
        assert result is False
        assert request.status == "pending"

    def test_auto_approve_threshold_configurable(self):
        """Test that auto-approval threshold is configurable."""
        from autopack.governance_requests import GovernanceRequest, RequestType, auto_approve_if_eligible

        request = GovernanceRequest(
            request_id="req_001",
            request_type=RequestType.PHASE_APPROVAL,
            phase_id="phase_001",
            description="Change",
            risk_level="low",
            requested_by="system",
            requested_at=datetime.utcnow(),
            confidence_score=0.85
        )

        # Should auto-approve with threshold 0.8
        result = auto_approve_if_eligible(request, confidence_threshold=0.8)
        assert result is True

        # Create new request
        request2 = GovernanceRequest(
            request_id="req_002",
            request_type=RequestType.PHASE_APPROVAL,
            phase_id="phase_002",
            description="Change",
            risk_level="low",
            requested_by="system",
            requested_at=datetime.utcnow(),
            confidence_score=0.85
        )

        # Should NOT auto-approve with threshold 0.9
        result2 = auto_approve_if_eligible(request2, confidence_threshold=0.9)
        assert result2 is False


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_invalid_risk_level(self):
        """Test handling of invalid risk level."""
        from autopack.governance_requests import GovernanceRequest, RequestType

        with pytest.raises(ValueError, match="invalid risk level|unknown risk"):
            GovernanceRequest(
                request_id="req_001",
                request_type=RequestType.PHASE_APPROVAL,
                phase_id="phase_001",
                description="Test",
                risk_level="invalid",
                requested_by="system",
                requested_at=datetime.utcnow()
            )

    def test_missing_required_fields(self):
        """Test that missing required fields raise errors."""
        from autopack.governance_requests import GovernanceRequest, RequestType

        with pytest.raises((TypeError, ValueError)):
            GovernanceRequest(
                request_id="req_001",
                request_type=RequestType.PHASE_APPROVAL,
                # Missing phase_id
                description="Test",
                risk_level="low",
                requested_by="system",
                requested_at=datetime.utcnow()
            )

    def test_concurrent_approval_attempts(self):
        """Test handling of concurrent approval attempts."""
        from autopack.governance_requests import GovernanceRequest, RequestType
        import threading

        request = GovernanceRequest(
            request_id="req_001",
            request_type=RequestType.PHASE_APPROVAL,
            phase_id="phase_001",
            description="Test",
            risk_level="low",
            requested_by="system",
            requested_at=datetime.utcnow()
        )

        results = []
        errors = []

        def approve_request():
            try:
                request.approve(approved_by="admin")
                results.append("approved")
            except Exception as e:
                errors.append(str(e))

        # Try concurrent approvals
        threads = [threading.Thread(target=approve_request) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only one should succeed
        assert len(results) == 1
        assert len(errors) == 2

    def test_request_serialization(self):
        """Test that requests can be serialized and deserialized."""
        from autopack.governance_requests import GovernanceRequest, RequestType

        original = GovernanceRequest(
            request_id="req_001",
            request_type=RequestType.PHASE_APPROVAL,
            phase_id="phase_001",
            description="Test request",
            risk_level="medium",
            requested_by="system",
            requested_at=datetime.utcnow(),
            confidence_score=0.85
        )

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = GovernanceRequest.from_dict(data)

        assert restored.request_id == original.request_id
        assert restored.request_type == original.request_type
        assert restored.phase_id == original.phase_id
        assert restored.risk_level == original.risk_level
        assert restored.confidence_score == original.confidence_score


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
