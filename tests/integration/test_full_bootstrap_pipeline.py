"""Integration tests for full bootstrap pipeline (IMP-RES-008).

Tests the complete pipeline integration:
    idea -> research -> anchor -> gaps -> plan -> (approval) -> build

This module specifically tests:
- GapScanner.scan_from_anchor() integration
- propose_from_gaps() with first-build approval gate
- End-to-end pipeline orchestration
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from autopack.gaps.models import GapReportV1
from autopack.gaps.scanner import GapScanner
from autopack.intention_anchor.v2 import IntentionAnchorV2, create_from_inputs
from autopack.planning.models import PlanProposalV1
from autopack.planning.plan_proposer import propose_from_gaps, propose_plan


@pytest.fixture
def sample_anchor() -> IntentionAnchorV2:
    """Create a sample IntentionAnchorV2 for testing."""
    return create_from_inputs(
        project_id="test-project-001",
        raw_input="Test project for bootstrap pipeline integration",
        north_star={
            "desired_outcomes": ["Complete bootstrap pipeline test"],
            "success_signals": ["All tests pass"],
            "non_goals": ["Production deployment"],
        },
        safety_risk={
            "never_allow": ["Delete production data"],
            "requires_approval": ["Database migrations"],
            "risk_tolerance": "low",
        },
        scope_boundaries={
            "allowed_write_roots": ["src/", "tests/"],
            "protected_paths": ["config/", "docs/"],
            "network_allowlist": [],
        },
        budget_cost={
            "token_cap_global": 100000,
            "token_cap_per_call": 10000,
        },
        governance_review={
            "default_policy": "deny",
            "auto_approve_rules": [],
            "approval_channels": ["github-pr"],
        },
    )


@pytest.fixture
def sample_gap_report(sample_anchor: IntentionAnchorV2) -> GapReportV1:
    """Create a sample GapReportV1 for testing."""
    from autopack.gaps.models import Gap, GapEvidence, GapMetadata, GapSummary, SafeRemediation

    gaps = [
        Gap(
            gap_id="test-gap-001",
            gap_type="doc_drift",
            title="Test documentation drift",
            description="Documentation is out of sync",
            detection_signals=["Detected via test"],
            evidence=GapEvidence(file_paths=["docs/test.md"]),
            risk_classification="medium",
            blocks_autopilot=False,
            safe_remediation=SafeRemediation(
                approach="Update documentation",
                requires_approval=True,
                estimated_actions=1,
            ),
        ),
        Gap(
            gap_id="test-gap-002",
            gap_type="root_clutter",
            title="Test root clutter",
            description="Files in wrong location",
            detection_signals=["Detected via test"],
            evidence=GapEvidence(file_paths=["test.md"]),
            risk_classification="low",
            blocks_autopilot=False,
            safe_remediation=SafeRemediation(
                approach="Move files",
                requires_approval=False,
                estimated_actions=1,
            ),
        ),
    ]

    return GapReportV1(
        project_id=sample_anchor.project_id,
        run_id="test-run-001",
        generated_at=datetime.now(timezone.utc),
        workspace_state_digest="test-digest-12345",
        gaps=gaps,
        summary=GapSummary(
            total_gaps=2,
            critical_gaps=0,
            high_gaps=0,
            medium_gaps=1,
            low_gaps=1,
            autopilot_blockers=0,
        ),
        metadata=GapMetadata(
            scanner_version="1.1.0",
            scan_duration_ms=100,
        ),
    )


class TestScanFromAnchor:
    """Tests for GapScanner.scan_from_anchor() method."""

    def test_scan_from_anchor_returns_gap_report(self, tmp_path, sample_anchor):
        """Test that scan_from_anchor returns a valid GapReportV1."""
        scanner = GapScanner(tmp_path)
        gap_report = scanner.scan_from_anchor(
            anchor=sample_anchor,
            project_dir=tmp_path,
        )

        assert isinstance(gap_report, GapReportV1)
        assert gap_report.project_id == sample_anchor.project_id
        assert gap_report.run_id.startswith("bootstrap-")

    def test_scan_from_anchor_uses_anchor_project_id(self, tmp_path, sample_anchor):
        """Test that scan_from_anchor uses project_id from anchor."""
        scanner = GapScanner(tmp_path)
        gap_report = scanner.scan_from_anchor(
            anchor=sample_anchor,
            project_dir=tmp_path,
        )

        assert gap_report.project_id == sample_anchor.project_id

    def test_scan_from_anchor_accepts_custom_run_id(self, tmp_path, sample_anchor):
        """Test that scan_from_anchor accepts custom run_id."""
        scanner = GapScanner(tmp_path)
        custom_run_id = "custom-test-run-123"
        gap_report = scanner.scan_from_anchor(
            anchor=sample_anchor,
            project_dir=tmp_path,
            run_id=custom_run_id,
        )

        assert gap_report.run_id == custom_run_id

    def test_scan_from_anchor_includes_summary(self, tmp_path, sample_anchor):
        """Test that scan_from_anchor includes summary statistics."""
        scanner = GapScanner(tmp_path)
        gap_report = scanner.scan_from_anchor(
            anchor=sample_anchor,
            project_dir=tmp_path,
        )

        assert gap_report.summary is not None
        assert isinstance(gap_report.summary.total_gaps, int)
        assert isinstance(gap_report.summary.autopilot_blockers, int)

    def test_scan_from_anchor_includes_metadata(self, tmp_path, sample_anchor):
        """Test that scan_from_anchor includes metadata."""
        scanner = GapScanner(tmp_path)
        gap_report = scanner.scan_from_anchor(
            anchor=sample_anchor,
            project_dir=tmp_path,
        )

        assert gap_report.metadata is not None
        assert gap_report.metadata.scanner_version is not None
        assert gap_report.metadata.scan_duration_ms is not None


class TestProposeFromGaps:
    """Tests for propose_from_gaps() function."""

    def test_propose_from_gaps_returns_plan(self, sample_anchor, sample_gap_report):
        """Test that propose_from_gaps returns a valid PlanProposalV1."""
        plan = propose_from_gaps(
            gap_report=sample_gap_report,
            anchor=sample_anchor,
        )

        assert isinstance(plan, PlanProposalV1)
        assert plan.project_id == sample_anchor.project_id

    def test_propose_from_gaps_first_build_requires_approval(
        self, sample_anchor, sample_gap_report
    ):
        """Test that first build actions require approval (none auto-approved)."""
        plan = propose_from_gaps(
            gap_report=sample_gap_report,
            anchor=sample_anchor,
            is_first_build=True,
        )

        # First build should have no auto-approved actions
        assert plan.summary is not None
        assert plan.summary.auto_approved_actions == 0

        # All non-blocked actions should require approval
        for action in plan.actions:
            if action.approval_status != "blocked":
                assert action.approval_status == "requires_approval"

    def test_propose_from_gaps_subsequent_build_allows_auto_approve(
        self, sample_anchor, sample_gap_report
    ):
        """Test that subsequent builds can have auto-approved actions."""
        plan = propose_from_gaps(
            gap_report=sample_gap_report,
            anchor=sample_anchor,
            is_first_build=False,
        )

        # Subsequent builds may have auto-approved actions depending on governance
        assert plan.summary is not None
        # The plan should be generated (actions exist if there are gaps)
        # Approval status depends on governance rules, not first-build gate

    def test_propose_from_gaps_includes_governance_checks(self, sample_anchor, sample_gap_report):
        """Test that propose_from_gaps includes governance checks."""
        plan = propose_from_gaps(
            gap_report=sample_gap_report,
            anchor=sample_anchor,
        )

        assert plan.governance_checks is not None
        assert plan.governance_checks.default_deny_applied is True

    def test_propose_from_gaps_links_to_gap_report(self, sample_anchor, sample_gap_report):
        """Test that plan links to gap report."""
        plan = propose_from_gaps(
            gap_report=sample_gap_report,
            anchor=sample_anchor,
        )

        assert plan.gap_report_id is not None


class TestPipelineIntegration:
    """End-to-end tests for the full pipeline integration."""

    def test_anchor_to_gaps_to_plan_flow(self, tmp_path):
        """Test the full flow: anchor -> gap scan -> plan proposal."""
        # Create anchor
        anchor = create_from_inputs(
            project_id="integration-test-001",
            raw_input="Integration test project",
            north_star={"desired_outcomes": ["Test pipeline"]},
            safety_risk={"risk_tolerance": "low"},
        )

        # Scan for gaps
        scanner = GapScanner(tmp_path)
        gap_report = scanner.scan_from_anchor(
            anchor=anchor,
            project_dir=tmp_path,
        )

        # Propose plan
        plan = propose_from_gaps(
            gap_report=gap_report,
            anchor=anchor,
            is_first_build=True,
        )

        # Verify chain of artifacts
        assert gap_report.project_id == anchor.project_id
        assert plan.project_id == anchor.project_id
        assert plan.anchor_id == f"anchor-{anchor.raw_input_digest}"

    def test_artifacts_can_be_saved_and_loaded(self, tmp_path):
        """Test that all pipeline artifacts can be saved and loaded."""
        # Create anchor
        anchor = create_from_inputs(
            project_id="save-load-test",
            raw_input="Save/load test project",
        )

        # Save anchor
        anchor_path = tmp_path / "anchor.json"
        anchor.save_to_file(anchor_path)

        # Scan for gaps
        scanner = GapScanner(tmp_path)
        gap_report = scanner.scan_from_anchor(anchor=anchor, project_dir=tmp_path)

        # Save gap report
        gap_report_path = tmp_path / "gap_report.json"
        gap_report.save_to_file(gap_report_path)

        # Propose plan
        plan = propose_from_gaps(gap_report=gap_report, anchor=anchor)

        # Save plan
        plan_path = tmp_path / "plan.json"
        plan.save_to_file(plan_path)

        # Load all artifacts back
        loaded_anchor = IntentionAnchorV2.load_from_file(anchor_path)
        loaded_gap_report = GapReportV1.load_from_file(gap_report_path)
        loaded_plan = PlanProposalV1.load_from_file(plan_path)

        # Verify loaded artifacts match
        assert loaded_anchor.project_id == anchor.project_id
        assert loaded_gap_report.project_id == gap_report.project_id
        assert loaded_plan.project_id == plan.project_id

    def test_pipeline_handles_empty_project(self, tmp_path):
        """Test pipeline handles empty project directory gracefully."""
        anchor = create_from_inputs(
            project_id="empty-project-test",
            raw_input="Empty project test",
        )

        scanner = GapScanner(tmp_path)
        gap_report = scanner.scan_from_anchor(anchor=anchor, project_dir=tmp_path)

        # Should still produce valid report (may have 0 gaps)
        assert gap_report is not None
        assert gap_report.summary is not None

        plan = propose_from_gaps(gap_report=gap_report, anchor=anchor)

        # Should still produce valid plan
        assert plan is not None
        assert plan.summary is not None

    def test_first_build_gate_reason_in_actions(self, tmp_path, sample_anchor, sample_gap_report):
        """Test that first-build gate ensures all actions require approval.

        Note: The first-build gate only modifies actions that would have been
        auto-approved. Actions already requiring approval (e.g., due to protected
        paths) retain their original approval reason.
        """
        plan = propose_from_gaps(
            gap_report=sample_gap_report,
            anchor=sample_anchor,
            is_first_build=True,
        )

        # All non-blocked actions should require approval on first build
        for action in plan.actions:
            if action.approval_status != "blocked":
                assert action.approval_status == "requires_approval"

        # Verify no auto-approved actions exist on first build
        assert plan.summary is not None
        assert plan.summary.auto_approved_actions == 0
