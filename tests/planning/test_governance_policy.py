"""Contract tests for governance policy (BUILD-192 / DEC-046).

Verifies:
1. NEVER_AUTO_APPROVE_PATTERNS are enforced for all protected paths
2. Auto-approval only for narrow low-risk paths outside protected zones
3. Safety profile affects approval thresholds
4. Default-deny policy is applied to all actions

These tests enforce the intentional policy documented in DEC-046:
- All code paths (src/, tests/) require human approval
- All infrastructure paths (docs/, config/, .github/) require human approval
- Auto-approval is narrow and explicit, not the default
"""

import pytest
from datetime import datetime, timezone

from autopack.planning.plan_proposer import (
    NEVER_AUTO_APPROVE_PATTERNS,
    propose_plan,
)
from autopack.gaps.models import GapReportV1, Gap, GapEvidence, GapExcerpt
from autopack.intention_anchor.v2 import (
    IntentionAnchorV2,
    PivotIntentions,
    NorthStarIntention,
    ScopeBoundariesIntention,
    GovernanceReviewIntention,
    SafetyRiskIntention,
)

# =============================================================================
# Helper functions to create valid model instances
# =============================================================================


def _make_gap_evidence(file_paths: list) -> GapEvidence:
    """Helper to create GapEvidence with correct structure."""
    return GapEvidence(
        file_paths=file_paths,
        excerpts=[GapExcerpt(source=p, preview="content") for p in file_paths],
    )


def _make_gap(
    gap_id: str,
    gap_type: str,
    file_paths: list,
    risk_classification: str = "medium",
    blocks_autopilot: bool = False,
) -> Gap:
    """Helper to create Gap with correct structure.

    Args:
        gap_id: Unique gap identifier
        gap_type: Must be one of the valid gap types
        file_paths: List of file paths for evidence
        risk_classification: One of critical/high/medium/low/info
        blocks_autopilot: Whether this gap blocks autopilot
    """
    return Gap(
        gap_id=gap_id,
        gap_type=gap_type,
        title=f"Test gap {gap_id}",
        description=f"Test gap for {gap_type}",
        detection_signals=["test_signal"],
        evidence=_make_gap_evidence(file_paths),
        risk_classification=risk_classification,
        blocks_autopilot=blocks_autopilot,
    )


def _make_gap_report(run_id: str, gaps: list) -> GapReportV1:
    """Helper to create GapReportV1 with correct structure."""
    return GapReportV1(
        project_id="test-project",
        run_id=run_id,
        generated_at=datetime.now(timezone.utc),
        gaps=gaps,
        workspace_state_digest=f"ws-{run_id}",
    )


def _make_minimal_anchor(raw_input_digest: str = "test123") -> IntentionAnchorV2:
    """Helper to create minimal valid IntentionAnchorV2."""
    return IntentionAnchorV2(
        project_id="test-project",
        created_at=datetime.now(timezone.utc),
        pivot_intentions=PivotIntentions(
            north_star=NorthStarIntention(
                desired_outcomes=["Test governance policy"],
                success_signals=["Policy enforced"],
            ),
        ),
        raw_input_digest=raw_input_digest,
    )


# =============================================================================
# Test: NEVER_AUTO_APPROVE_PATTERNS list contents
# =============================================================================


class TestNeverAutoApprovePatterns:
    """Test that NEVER_AUTO_APPROVE_PATTERNS list is as documented."""

    def test_never_auto_approve_patterns_contains_docs(self):
        """docs/ is in NEVER_AUTO_APPROVE_PATTERNS (DEC-046)."""
        assert "docs/" in NEVER_AUTO_APPROVE_PATTERNS

    def test_never_auto_approve_patterns_contains_config(self):
        """config/ is in NEVER_AUTO_APPROVE_PATTERNS (DEC-046)."""
        assert "config/" in NEVER_AUTO_APPROVE_PATTERNS

    def test_never_auto_approve_patterns_contains_github(self):
        """.github/ is in NEVER_AUTO_APPROVE_PATTERNS (DEC-046)."""
        assert ".github/" in NEVER_AUTO_APPROVE_PATTERNS

    def test_never_auto_approve_patterns_contains_src_autopack(self):
        """src/autopack/ is in NEVER_AUTO_APPROVE_PATTERNS (DEC-046)."""
        assert "src/autopack/" in NEVER_AUTO_APPROVE_PATTERNS

    def test_never_auto_approve_patterns_contains_tests(self):
        """tests/ is in NEVER_AUTO_APPROVE_PATTERNS (DEC-046)."""
        assert "tests/" in NEVER_AUTO_APPROVE_PATTERNS

    def test_never_auto_approve_patterns_count(self):
        """NEVER_AUTO_APPROVE_PATTERNS has exactly 5 patterns (DEC-046)."""
        assert len(NEVER_AUTO_APPROVE_PATTERNS) == 5


# =============================================================================
# Test: Governance policy enforcement during plan proposal
# =============================================================================


class TestGovernancePolicyEnforcement:
    """Test that governance policy is enforced during plan proposal."""

    @pytest.fixture
    def minimal_anchor(self):
        """Create minimal anchor for testing."""
        return _make_minimal_anchor("test-governance")

    @pytest.fixture
    def gap_report_with_doc_gap(self):
        """Create gap report targeting docs/."""
        return _make_gap_report(
            "test-run-001",
            [_make_gap("gap-doc-001", "doc_drift", ["docs/README.md"])],
        )

    @pytest.fixture
    def gap_report_with_code_gap(self):
        """Create gap report targeting src/autopack/."""
        return _make_gap_report(
            "test-run-002",
            [
                _make_gap(
                    "gap-code-001",
                    "test_infra_drift",
                    ["src/autopack/main.py"],
                    risk_classification="high",
                )
            ],
        )

    @pytest.fixture
    def gap_report_with_test_gap(self):
        """Create gap report targeting tests/."""
        return _make_gap_report(
            "test-run-003",
            [_make_gap("gap-test-001", "test_infra_drift", ["tests/test_main.py"])],
        )

    @pytest.fixture
    def gap_report_with_github_gap(self):
        """Create gap report targeting .github/."""
        return _make_gap_report(
            "test-run-004",
            [
                _make_gap(
                    "gap-ci-001",
                    "baseline_policy_drift",
                    [".github/workflows/ci.yml"],
                    risk_classification="high",
                )
            ],
        )

    @pytest.fixture
    def gap_report_with_config_gap(self):
        """Create gap report targeting config/."""
        return _make_gap_report(
            "test-run-005",
            [_make_gap("gap-config-001", "baseline_policy_drift", ["config/settings.json"])],
        )

    def test_docs_path_requires_approval(self, minimal_anchor, gap_report_with_doc_gap):
        """Actions targeting docs/ require approval (DEC-046)."""
        proposal = propose_plan(minimal_anchor, gap_report_with_doc_gap)

        # All actions touching docs/ should require approval
        for action in proposal.actions:
            if any(p.startswith("docs/") for p in action.target_paths):
                assert (
                    action.approval_status != "auto_approved"
                ), f"Action {action.action_id} touching docs/ should NOT be auto-approved"

    def test_src_autopack_path_requires_approval(self, minimal_anchor, gap_report_with_code_gap):
        """Actions targeting src/autopack/ require approval (DEC-046)."""
        proposal = propose_plan(minimal_anchor, gap_report_with_code_gap)

        # All actions touching src/autopack/ should require approval
        for action in proposal.actions:
            if any(p.startswith("src/autopack/") for p in action.target_paths):
                assert (
                    action.approval_status != "auto_approved"
                ), f"Action {action.action_id} touching src/autopack/ should NOT be auto-approved"

    def test_tests_path_requires_approval(self, minimal_anchor, gap_report_with_test_gap):
        """Actions targeting tests/ require approval (DEC-046)."""
        proposal = propose_plan(minimal_anchor, gap_report_with_test_gap)

        # All actions touching tests/ should require approval
        for action in proposal.actions:
            if any(p.startswith("tests/") for p in action.target_paths):
                assert (
                    action.approval_status != "auto_approved"
                ), f"Action {action.action_id} touching tests/ should NOT be auto-approved"

    def test_github_path_requires_approval(self, minimal_anchor, gap_report_with_github_gap):
        """Actions targeting .github/ require approval (DEC-046)."""
        proposal = propose_plan(minimal_anchor, gap_report_with_github_gap)

        # All actions touching .github/ should require approval
        for action in proposal.actions:
            if any(p.startswith(".github/") for p in action.target_paths):
                assert (
                    action.approval_status != "auto_approved"
                ), f"Action {action.action_id} touching .github/ should NOT be auto-approved"

    def test_config_path_requires_approval(self, minimal_anchor, gap_report_with_config_gap):
        """Actions targeting config/ require approval (DEC-046)."""
        proposal = propose_plan(minimal_anchor, gap_report_with_config_gap)

        # All actions touching config/ should require approval
        for action in proposal.actions:
            if any(p.startswith("config/") for p in action.target_paths):
                assert (
                    action.approval_status != "auto_approved"
                ), f"Action {action.action_id} touching config/ should NOT be auto-approved"


# =============================================================================
# Test: Default-deny policy
# =============================================================================


class TestDefaultDenyPolicy:
    """Test that default-deny policy is applied."""

    @pytest.fixture
    def minimal_anchor(self):
        """Create minimal anchor for testing."""
        return _make_minimal_anchor("test-default-deny")

    @pytest.fixture
    def gap_report_any_gap(self):
        """Create gap report with any gap type (outside protected paths)."""
        return _make_gap_report(
            "test-run-default-deny",
            [
                _make_gap(
                    "gap-any-001",
                    "unknown",  # Valid gap_type
                    ["external/some/path.txt"],  # Outside protected paths
                    risk_classification="low",
                )
            ],
        )

    def test_governance_checks_show_default_deny_applied(self, minimal_anchor, gap_report_any_gap):
        """GovernanceChecks.default_deny_applied should be True (DEC-046)."""
        proposal = propose_plan(minimal_anchor, gap_report_any_gap)

        assert proposal.governance_checks.default_deny_applied is True


# =============================================================================
# Test: Safety profile thresholds
# =============================================================================


class TestSafetyProfileThresholds:
    """Test that safety profile affects approval thresholds."""

    @pytest.fixture
    def strict_anchor(self):
        """Create anchor that triggers strict safety profile."""
        return IntentionAnchorV2(
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            pivot_intentions=PivotIntentions(
                north_star=NorthStarIntention(
                    desired_outcomes=["Test strict profile"],
                    success_signals=["Strict thresholds"],
                ),
                scope_boundaries=ScopeBoundariesIntention(
                    protected_paths=["critical/"],  # Having protected paths
                ),
                safety_risk=SafetyRiskIntention(
                    risk_tolerance="minimal",  # Strict mode indicator
                ),
                governance_review=GovernanceReviewIntention(
                    default_policy="deny",
                    auto_approve_rules=[],
                ),
            ),
            raw_input_digest="strict789",
        )

    @pytest.fixture
    def normal_anchor(self):
        """Create anchor that triggers normal safety profile."""
        return _make_minimal_anchor("normal012")

    @pytest.fixture
    def gap_report_high_risk(self):
        """Create gap report that generates high-risk action."""
        return _make_gap_report(
            "test-run-risk",
            [
                _make_gap(
                    "gap-risk-001",
                    "git_state_corruption",  # High risk (0.9)
                    ["external/data.bin"],  # Outside protected paths
                    risk_classification="critical",
                    blocks_autopilot=True,
                )
            ],
        )

    def test_strict_profile_blocks_at_lower_risk(self, strict_anchor, gap_report_high_risk):
        """Strict safety profile blocks at risk >= 0.5 (DEC-046)."""
        proposal = propose_plan(strict_anchor, gap_report_high_risk)

        # git_state_corruption has risk 0.9, should be blocked in strict mode
        high_risk_actions = [a for a in proposal.actions if a.risk_score >= 0.5]
        for action in high_risk_actions:
            assert (
                action.approval_status == "blocked"
            ), f"Action with risk {action.risk_score} should be blocked in strict mode"

    def test_normal_profile_blocks_at_higher_risk(self, normal_anchor, gap_report_high_risk):
        """Normal safety profile blocks at risk >= 0.8 (DEC-046)."""
        proposal = propose_plan(normal_anchor, gap_report_high_risk)

        # git_state_corruption has risk 0.9, should be blocked in normal mode too
        very_high_risk_actions = [a for a in proposal.actions if a.risk_score >= 0.8]
        for action in very_high_risk_actions:
            assert (
                action.approval_status == "blocked"
            ), f"Action with risk {action.risk_score} should be blocked in normal mode"


# =============================================================================
# Test: Violation tracking
# =============================================================================


class TestNeverAutoApproveViolations:
    """Test that violations are tracked when auto-approval bypasses protected paths."""

    @pytest.fixture
    def minimal_anchor(self):
        """Create minimal anchor for testing."""
        return _make_minimal_anchor("test-violations")

    @pytest.fixture
    def gap_report_with_protected_path(self):
        """Create gap report targeting protected path."""
        return _make_gap_report(
            "test-run-violation",
            [
                _make_gap(
                    "gap-violation-001",
                    "doc_drift",
                    ["docs/API.md"],
                    risk_classification="low",
                )
            ],
        )

    def test_no_violations_when_policy_enforced(
        self, minimal_anchor, gap_report_with_protected_path
    ):
        """No NEVER_AUTO_APPROVE violations when policy is properly enforced."""
        proposal = propose_plan(minimal_anchor, gap_report_with_protected_path)

        # Should have no violations (all protected paths should require approval)
        assert (
            proposal.governance_checks.never_auto_approve_violations == []
        ), "Should have no violations - protected paths should require approval"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
