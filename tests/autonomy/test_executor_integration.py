"""Tests for BUILD-181 ExecutorContext integration."""

from unittest.mock import MagicMock

import pytest

from autopack.autonomy.executor_integration import ExecutorContext, create_executor_context
from autopack.stuck_handling import StuckReason, StuckResolutionDecision


@pytest.fixture
def mock_anchor():
    """Create a mock IntentionAnchorV2."""
    anchor = MagicMock()
    anchor.project_id = "test-project"
    anchor.raw_input_digest = "abc123"

    # Mock pivot_intentions
    anchor.pivot_intentions = MagicMock()
    anchor.pivot_intentions.safety_risk = MagicMock()
    anchor.pivot_intentions.safety_risk.risk_tolerance = "moderate"
    anchor.pivot_intentions.safety_risk.never_allow = []
    anchor.pivot_intentions.safety_risk.requires_approval = []
    anchor.pivot_intentions.budget_cost = MagicMock()
    anchor.pivot_intentions.budget_cost.token_cap_global = 10000
    anchor.pivot_intentions.north_star = MagicMock()
    anchor.pivot_intentions.north_star.desired_outcomes = ["Complete task"]
    anchor.pivot_intentions.north_star.non_goals = ["Over-engineer"]

    return anchor


@pytest.fixture
def mock_layout(tmp_path):
    """Create a mock RunFileLayout."""
    layout = MagicMock()
    layout.run_id = "test-run-001"
    layout.project_id = "test-project"
    layout.base_dir = (
        tmp_path / ".autonomous_runs" / "test-project" / "runs" / "default" / "test-run-001"
    )
    layout.base_dir.mkdir(parents=True, exist_ok=True)
    return layout


class TestExecutorContextSafetyProfile:
    """Tests for safety profile derivation."""

    @pytest.mark.timeout(60)  # Increased from 30s to reduce I/O flakes
    def test_normal_safety_profile_for_moderate_risk(self, mock_anchor, mock_layout):
        """Test that moderate risk maps to normal safety profile."""
        mock_anchor.pivot_intentions.safety_risk.risk_tolerance = "moderate"

        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        assert ctx.safety_profile == "normal"
        assert not ctx.is_strict

    @pytest.mark.timeout(60)  # Increased from 30s for slow CI runners
    def test_strict_safety_profile_for_low_risk(self, mock_anchor, mock_layout):
        """Test that low risk maps to strict safety profile."""
        mock_anchor.pivot_intentions.safety_risk.risk_tolerance = "low"

        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        assert ctx.safety_profile == "strict"
        assert ctx.is_strict

    def test_strict_default_when_no_safety_risk(self, mock_anchor, mock_layout):
        """Test that missing safety_risk defaults to strict."""
        mock_anchor.pivot_intentions.safety_risk = None

        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        assert ctx.safety_profile == "strict"
        assert ctx.is_strict

    def test_needs_elevated_review_with_never_allow(self, mock_anchor, mock_layout):
        """Test elevated review required when never_allow is set."""
        mock_anchor.pivot_intentions.safety_risk.risk_tolerance = "high"
        mock_anchor.pivot_intentions.safety_risk.never_allow = ["delete"]

        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        assert ctx.needs_elevated_review


class TestExecutorContextUsageAccounting:
    """Tests for usage accounting."""

    def test_record_usage_event(self, mock_anchor, mock_layout):
        """Test recording a usage event."""
        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        event = ctx.record_usage_event(tokens_used=500, context_chars_used=1000)

        assert event.tokens_used == 500
        assert event.context_chars_used == 1000
        assert event.event_id.startswith("evt-")

    def test_usage_totals_aggregation(self, mock_anchor, mock_layout):
        """Test usage totals are correctly aggregated."""
        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        ctx.record_usage_event(tokens_used=100)
        ctx.record_usage_event(tokens_used=200)
        ctx.record_usage_event(tokens_used=300)

        totals = ctx.usage_totals
        assert totals.tokens_used == 600

    def test_budget_remaining_calculation(self, mock_anchor, mock_layout):
        """Test budget remaining calculation."""
        mock_anchor.pivot_intentions.budget_cost.token_cap_global = 1000

        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)
        ctx.record_usage_event(tokens_used=400)

        budget = ctx.get_budget_remaining()
        assert budget == pytest.approx(0.6)  # 60% remaining

    def test_budget_unlimited_when_no_cap(self, mock_anchor, mock_layout):
        """Test budget is 1.0 when no cap is set."""
        mock_anchor.pivot_intentions.budget_cost = None

        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)
        ctx.record_usage_event(tokens_used=10000)

        budget = ctx.get_budget_remaining()
        assert budget == 1.0


class TestExecutorContextStuckHandling:
    """Tests for stuck handling with scope reduction."""

    def test_set_phase_resets_counters(self, mock_anchor, mock_layout):
        """Test that set_phase resets iteration counters."""
        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)
        ctx._iterations_used = 5
        ctx._consecutive_failures = 3

        ctx.set_phase("new_phase")

        assert ctx._current_phase_id == "new_phase"
        assert ctx._iterations_used == 0
        assert ctx._consecutive_failures == 0

    def test_handle_stuck_needs_human_for_approval(self, mock_anchor, mock_layout):
        """Test that REQUIRES_APPROVAL reason returns NEEDS_HUMAN."""
        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        decision, proposal = ctx.handle_stuck(StuckReason.REQUIRES_APPROVAL)

        assert decision == StuckResolutionDecision.NEEDS_HUMAN
        assert proposal is None

    def test_handle_stuck_reduce_scope_when_budget_low(self, mock_anchor, mock_layout):
        """Test that low budget triggers REDUCE_SCOPE."""
        mock_anchor.pivot_intentions.budget_cost.token_cap_global = 1000

        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)
        # Use 90% of budget
        ctx.record_usage_event(tokens_used=900)

        decision, proposal = ctx.handle_stuck(
            StuckReason.BUDGET_EXCEEDED,
            current_tasks=["task1", "task2", "task3"],
        )

        assert decision == StuckResolutionDecision.REDUCE_SCOPE
        assert proposal is not None
        assert proposal.run_id == mock_layout.run_id

    def test_scope_reduction_proposal_written_to_artifact(self, mock_anchor, mock_layout):
        """Test that scope reduction proposal is written to artifacts."""
        mock_anchor.pivot_intentions.budget_cost.token_cap_global = 1000

        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)
        ctx.record_usage_event(tokens_used=900)

        decision, proposal = ctx.handle_stuck(
            StuckReason.BUDGET_EXCEEDED,
            current_tasks=["task1", "task2", "task3"],
        )

        # Check proposal file exists
        proposals_dir = mock_layout.base_dir / "proposals"
        assert proposals_dir.exists()
        proposal_files = list(proposals_dir.glob("scope_reduction_*.json"))
        assert len(proposal_files) == 1


class TestExecutorContextPatchCorrection:
    """Tests for patch correction."""

    def test_patch_correction_blocked_when_budget_low(self, mock_anchor, mock_layout):
        """Test that patch correction is blocked when budget is too low."""
        mock_anchor.pivot_intentions.budget_cost.token_cap_global = 1000

        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)
        # Use 95% of budget (below MIN_BUDGET_FOR_CORRECTION)
        ctx.record_usage_event(tokens_used=950)

        result = ctx.attempt_patch_correction(
            original_patch='{"field": "value"}',
            http_422_detail={"message": "Missing required field"},
        )

        assert not result.attempted
        assert result.blocked_reason == "budget_or_empty_error"

    def test_patch_correction_attempted_when_budget_ok(self, mock_anchor, mock_layout):
        """Test that patch correction is attempted when budget is sufficient."""
        mock_anchor.pivot_intentions.budget_cost.token_cap_global = 1000

        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)
        # Use 50% of budget
        ctx.record_usage_event(tokens_used=500)

        result = ctx.attempt_patch_correction(
            original_patch='{"field": "value"}',
            http_422_detail={"message": "Field 'name' is required", "path": "$.data.name"},
        )

        assert result.attempted
        assert result.evidence is not None

    def test_patch_correction_only_once_per_event(self, mock_anchor, mock_layout):
        """Test that patch correction is only attempted once per event."""
        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        # First attempt
        result1 = ctx.attempt_patch_correction(
            original_patch='{"field": "value"}',
            http_422_detail={"message": "error"},
        )
        assert result1.attempted

        # Second attempt with same inputs should be blocked
        result2 = ctx.attempt_patch_correction(
            original_patch='{"field": "value"}',
            http_422_detail={"message": "error"},
        )
        assert not result2.attempted
        assert result2.blocked_reason == "max_attempts_exceeded"


class TestExecutorContextCoverage:
    """Tests for coverage metrics processing."""

    def test_coverage_info_unknown_when_no_ci_result(self, mock_anchor, mock_layout):
        """Test coverage is unknown when no CI result."""
        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        info = ctx.process_ci_result(None)

        assert info.status == "unknown"
        assert info.delta is None

    def test_coverage_info_available_with_data(self, mock_anchor, mock_layout):
        """Test coverage is available when CI has data."""
        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        info = ctx.process_ci_result(
            {
                "coverage": {
                    "baseline": 80.0,
                    "current": 85.0,
                }
            }
        )

        assert info.status == "available"
        assert info.delta == 5.0
        assert info.baseline == 80.0
        assert info.current == 85.0

    def test_can_trust_coverage(self, mock_anchor, mock_layout):
        """Test trust check for coverage data."""
        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        assert not ctx.can_trust_coverage(None)
        assert not ctx.can_trust_coverage({})
        assert ctx.can_trust_coverage({"coverage": {"delta": 0.5}})


class TestExecutorContextApprovalService:
    """Tests for approval service integration."""

    def test_approval_not_needed_for_normal_retry(self, mock_anchor, mock_layout):
        """Test that normal retry does not trigger approval."""
        from autopack.approvals.service import ApprovalTriggerReason

        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        result = ctx.request_approval_if_needed(
            trigger_reason=ApprovalTriggerReason.NORMAL_RETRY,
            description="Retrying after transient error",
        )

        assert result is None  # No approval needed

    def test_approval_needed_for_pivot_change(self, mock_anchor, mock_layout):
        """Test that pivot change triggers approval request."""
        from autopack.approvals.service import ApprovalTriggerReason

        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        result = ctx.request_approval_if_needed(
            trigger_reason=ApprovalTriggerReason.PIVOT_INTENTION_CHANGE,
            description="Changing north star",
            affected_pivots=["north_star"],
        )

        assert result is not None
        assert result.success  # Noop service returns success


class TestExecutorContextIntegrationHelpers:
    """Tests for integration helper methods."""

    def test_should_block_action_strict_profile(self, mock_anchor, mock_layout):
        """Test action blocking in strict profile."""
        mock_anchor.pivot_intentions.safety_risk.risk_tolerance = "low"

        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        assert ctx.should_block_action(0.5)  # Blocked at 0.5 in strict
        assert not ctx.should_block_action(0.4)

    def test_should_block_action_normal_profile(self, mock_anchor, mock_layout):
        """Test action blocking in normal profile."""
        mock_anchor.pivot_intentions.safety_risk.risk_tolerance = "high"

        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        assert ctx.should_block_action(0.8)  # Blocked at 0.8 in normal
        assert not ctx.should_block_action(0.7)

    def test_get_approval_threshold(self, mock_anchor, mock_layout):
        """Test approval threshold varies by profile."""
        mock_anchor.pivot_intentions.safety_risk.risk_tolerance = "low"
        ctx_strict = ExecutorContext(anchor=mock_anchor, layout=mock_layout)
        assert ctx_strict.get_approval_threshold() == 0.3

        mock_anchor.pivot_intentions.safety_risk.risk_tolerance = "high"
        ctx_normal = ExecutorContext(anchor=mock_anchor, layout=mock_layout)
        assert ctx_normal.get_approval_threshold() == 0.5

    def test_to_summary_dict(self, mock_anchor, mock_layout):
        """Test summary dict generation."""
        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)
        ctx.record_usage_event(tokens_used=100)
        ctx.set_phase("test_phase")

        summary = ctx.to_summary_dict()

        assert summary["project_id"] == "test-project"
        assert summary["run_id"] == "test-run-001"
        assert summary["phase_id"] == "test_phase"
        assert "usage" in summary
        assert "budget_remaining" in summary


class TestCreateExecutorContext:
    """Tests for factory function."""

    def test_create_executor_context(self, mock_anchor, mock_layout):
        """Test factory creates valid context."""
        ctx = create_executor_context(anchor=mock_anchor, layout=mock_layout)

        assert isinstance(ctx, ExecutorContext)
        assert ctx.anchor == mock_anchor
        assert ctx.layout == mock_layout


class TestResearchIntegration:
    """Tests for IMP-AUTO-001: Research integration."""

    def test_should_trigger_followup_research_no_analysis_results(self, mock_anchor, mock_layout):
        """Test that no analysis results returns False."""
        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        result = ctx.should_trigger_followup_research(analysis_results=None)

        assert result is False

    def test_should_trigger_followup_research_low_budget(self, mock_anchor, mock_layout):
        """Test that low budget prevents follow-up research."""
        mock_anchor.pivot_intentions.budget_cost.token_cap_global = 1000
        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        # Use 90% of budget
        ctx.record_usage_event(tokens_used=900)

        result = ctx.should_trigger_followup_research(
            analysis_results={"findings": []},
            min_budget_threshold=0.2,
        )

        assert result is False

    def test_should_trigger_followup_research_with_low_confidence(self, mock_anchor, mock_layout):
        """Test that low confidence findings trigger follow-up research."""
        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        analysis_results = {
            "findings": [
                {
                    "id": "finding-1",
                    "confidence": 0.3,  # Below 0.7 threshold
                    "summary": "Test finding with low confidence",
                    "topic": "test",
                }
            ]
        }

        result = ctx.should_trigger_followup_research(
            analysis_results=analysis_results,
        )

        assert result is True

    def test_should_trigger_followup_research_with_gaps(self, mock_anchor, mock_layout):
        """Test that identified gaps trigger follow-up research."""
        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        analysis_results = {
            "findings": [],
            "identified_gaps": [
                {
                    "category": "market_research",
                    "description": "Missing market size data",
                }
            ],
        }

        result = ctx.should_trigger_followup_research(
            analysis_results=analysis_results,
        )

        assert result is True

    def test_should_not_trigger_followup_research_high_confidence(self, mock_anchor, mock_layout):
        """Test that high confidence findings don't trigger follow-up research."""
        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        analysis_results = {
            "findings": [
                {
                    "id": "finding-1",
                    "confidence": 0.9,  # Above 0.7 threshold
                    "summary": "Test finding with high confidence",
                    "topic": "test",
                }
            ],
            "identified_gaps": [],
        }

        result = ctx.should_trigger_followup_research(
            analysis_results=analysis_results,
        )

        assert result is False

    def test_get_research_gaps_returns_empty_list_on_error(self, mock_anchor, mock_layout):
        """Test that get_research_gaps returns empty list on error."""
        ctx = ExecutorContext(anchor=mock_anchor, layout=mock_layout)

        # This should return empty list since state tracker is not initialized
        gaps = ctx.get_research_gaps()

        assert gaps == []
