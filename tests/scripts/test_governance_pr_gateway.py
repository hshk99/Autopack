"""Tests for ROAD-D: Governance PR Gateway"""

import pytest
from scripts.governance_pr_gateway import PrGovernanceGateway


class TestPrGovernanceGateway:
    """Test governance gateway for auto-generated PRs."""

    def setup_method(self):
        """Create fresh gateway for each test."""
        self.gateway = PrGovernanceGateway()

    def test_create_approval_request(self):
        """Test creating approval request."""
        request = self.gateway.create_approval_request(
            pr_number=123,
            generated_from="COST-SINK-001",
            title="Optimize tokens",
            description="Reduce token usage in phase X",
            impact_assessment="Low risk - only affects token calculation",
            rollback_plan="Revert commit if issues arise",
        )

        assert request.pr_number == 123
        assert request.generated_from == "COST-SINK-001"
        assert request.status == "pending"
        assert self.gateway.get_pending_count() == 1

    def test_approve_pr(self):
        """Test PR approval."""
        self.gateway.create_approval_request(
            pr_number=123,
            generated_from="FAILURE-001",
            title="Fix timeout",
            description="Fix timeout in phase",
            impact_assessment="Medium",
            rollback_plan="Revert",
        )

        assert not self.gateway.can_merge(123)
        self.gateway.approve_pr(123, reviewer="alice")
        assert self.gateway.can_merge(123)
        assert self.gateway.get_pending_count() == 0

    def test_reject_pr(self):
        """Test PR rejection."""
        self.gateway.create_approval_request(
            pr_number=124,
            generated_from="FAILURE-002",
            title="Fix crash",
            description="Fix crash",
            impact_assessment="High",
            rollback_plan="Revert",
        )

        self.gateway.reject_pr(124, reason="Insufficient testing")
        assert not self.gateway.can_merge(124)
        assert 124 in self.gateway.rejected_prs

    def test_multiple_prs(self):
        """Test managing multiple PRs."""
        for i in range(3):
            self.gateway.create_approval_request(
                pr_number=100 + i,
                generated_from=f"ISSUE-{i}",
                title=f"Fix issue {i}",
                description="Fix",
                impact_assessment="Low",
                rollback_plan="Revert",
            )

        assert self.gateway.get_pending_count() == 3

        self.gateway.approve_pr(100)
        assert self.gateway.get_pending_count() == 2
        assert self.gateway.can_merge(100)

        self.gateway.reject_pr(101)
        assert self.gateway.get_pending_count() == 1
        assert not self.gateway.can_merge(101)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
