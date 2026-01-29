"""Integration tests for bootstrap pipeline (IMP-RES-007).

Tests the full bootstrap pipeline from idea to READY_FOR_BUILD marker.
"""

import json

import pytest

from autopack.cli.commands.bootstrap import (
    READY_FOR_BUILD_MARKER,
    BootstrapOptions,
    BootstrapRunner,
)
from autopack.intention_anchor.v2 import IntentionAnchorV2
from autopack.research.anchor_mapper import ResearchToAnchorMapper
from autopack.research.idea_parser import IdeaParser, ProjectType, RiskProfile
from autopack.research.models.bootstrap_session import BootstrapPhase
from autopack.research.orchestrator import ResearchOrchestrator
from autopack.research.qa_controller import AnswerSource, QAController


@pytest.fixture
def ecommerce_idea():
    """E-commerce project idea."""
    return """
    # Online Marketplace for Vintage Items

    Create a marketplace platform for buying and selling vintage items.

    ## Core Features
    - User registration with email verification
    - Product listing with image uploads
    - Search and filter functionality
    - Shopping cart and wishlist
    - Secure checkout with Stripe
    - Order tracking and history
    - Seller ratings and reviews
    - Admin dashboard for moderation
    """


@pytest.fixture
def trading_idea():
    """Trading project idea."""
    return """
    # Crypto Trading Bot

    Build an automated cryptocurrency trading system.

    ## Features
    - Connect to multiple exchanges (Binance, Coinbase)
    - Real-time price monitoring
    - Multiple trading strategies (mean reversion, momentum)
    - Risk management with stop-loss
    - Backtesting engine
    - Performance analytics
    - API key management
    """


@pytest.fixture
def automation_idea():
    """Automation project idea."""
    return """
    # CI/CD Pipeline Automation

    Create an automation tool for managing CI/CD workflows.

    ## Features
    - GitHub integration
    - Automated test execution
    - Deployment pipeline management
    - Notification system (Slack, Email)
    - Configuration as code
    - Secrets management
    """


class TestIdeaParserIntegration:
    """Integration tests for IdeaParser with full documents."""

    def test_parser_extracts_ecommerce_details(self, ecommerce_idea):
        """Test that parser extracts detailed requirements from e-commerce idea."""
        parser = IdeaParser()
        parsed = parser.parse_single(ecommerce_idea)

        assert parsed is not None
        assert parsed.detected_project_type == ProjectType.ECOMMERCE
        assert len(parsed.raw_requirements) >= 5
        assert parsed.confidence_score >= 0.6

    def test_parser_extracts_trading_details(self, trading_idea):
        """Test that parser extracts details from trading idea."""
        parser = IdeaParser()
        parsed = parser.parse_single(trading_idea)

        assert parsed is not None
        assert parsed.detected_project_type == ProjectType.TRADING
        assert parsed.risk_profile == RiskProfile.HIGH

    def test_parser_extracts_automation_details(self, automation_idea):
        """Test that parser extracts details from automation idea."""
        parser = IdeaParser()
        parsed = parser.parse_single(automation_idea)

        assert parsed is not None
        assert parsed.detected_project_type == ProjectType.AUTOMATION


class TestResearchOrchestratorIntegration:
    """Integration tests for ResearchOrchestrator."""

    @pytest.mark.asyncio
    async def test_orchestrator_runs_bootstrap_session(self, ecommerce_idea):
        """Test that orchestrator runs full bootstrap session."""
        parser = IdeaParser()
        parsed = parser.parse_single(ecommerce_idea)

        orchestrator = ResearchOrchestrator()
        session = await orchestrator.start_bootstrap_session(
            parsed_idea=parsed,
            use_cache=False,
            parallel=True,
        )

        assert session is not None
        assert session.session_id is not None
        # Session should have completed phases
        assert session.current_phase in [BootstrapPhase.COMPLETED, BootstrapPhase.FAILED]

    @pytest.mark.asyncio
    async def test_orchestrator_caches_results(self, ecommerce_idea):
        """Test that orchestrator caches and reuses results."""
        parser = IdeaParser()
        parsed = parser.parse_single(ecommerce_idea)

        orchestrator = ResearchOrchestrator()

        # First run
        session1 = await orchestrator.start_bootstrap_session(
            parsed_idea=parsed,
            use_cache=True,
            parallel=True,
        )

        # Second run should use cache
        session2 = await orchestrator.start_bootstrap_session(
            parsed_idea=parsed,
            use_cache=True,
            parallel=True,
        )

        # Should return same session from cache
        assert session1.idea_hash == session2.idea_hash


class TestAnchorMapperIntegration:
    """Integration tests for ResearchToAnchorMapper."""

    @pytest.mark.asyncio
    async def test_mapper_creates_valid_anchor(self, ecommerce_idea):
        """Test that mapper creates valid IntentionAnchorV2."""
        parser = IdeaParser()
        parsed = parser.parse_single(ecommerce_idea)

        orchestrator = ResearchOrchestrator()
        session = await orchestrator.start_bootstrap_session(
            parsed_idea=parsed,
            use_cache=False,
            parallel=True,
        )

        mapper = ResearchToAnchorMapper()
        anchor, questions = mapper.map_to_anchor(session, parsed)

        assert anchor is not None
        assert isinstance(anchor, IntentionAnchorV2)
        assert anchor.project_id is not None
        assert anchor.format_version == "v2"

    @pytest.mark.asyncio
    async def test_mapper_generates_clarifying_questions(self, trading_idea):
        """Test that mapper generates appropriate clarifying questions."""
        parser = IdeaParser()
        parsed = parser.parse_single(trading_idea)

        orchestrator = ResearchOrchestrator()
        session = await orchestrator.start_bootstrap_session(
            parsed_idea=parsed,
            use_cache=False,
            parallel=True,
        )

        mapper = ResearchToAnchorMapper()
        anchor, questions = mapper.map_to_anchor(session, parsed)

        # Should generate questions about never_allow (critical for safety)
        assert len(questions) > 0
        # Should include safety-related questions
        safety_questions = [q for q in questions if "NEVER" in q or "never" in q.lower()]
        assert len(safety_questions) > 0


class TestQAControllerIntegration:
    """Integration tests for QAController."""

    def test_qa_controller_classifies_questions(self):
        """Test that QA controller correctly classifies question priorities."""
        questions = [
            "CRITICAL: What operations must NEVER be allowed?",
            "What are the desired outcomes for this project?",
            "Is parallelism allowed?",
        ]

        controller = QAController(
            answer_source=AnswerSource.DEFAULT,
            project_type=ProjectType.ECOMMERCE,
        )

        classified = controller.classify_questions(questions)

        assert len(classified) == 3
        # First question should be CRITICAL
        assert classified[0].priority.value == "critical"

    def test_qa_controller_uses_project_defaults(self):
        """Test that QA controller uses appropriate defaults per project type."""
        controller = QAController(
            answer_source=AnswerSource.DEFAULT,
            project_type=ProjectType.TRADING,
        )

        defaults = controller.get_project_defaults()

        assert "parallelism_isolation" in defaults
        # Trading projects should have parallelism disabled
        assert defaults["parallelism_isolation"]["allowed"] is False


class TestFullBootstrapPipeline:
    """End-to-end integration tests for the full bootstrap pipeline."""

    def test_full_pipeline_ecommerce(self, tmp_path, ecommerce_idea):
        """Test full pipeline for e-commerce project."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=ecommerce_idea,
            autonomous=True,
            skip_research=True,  # Skip for faster tests
            output_dir=tmp_path / "ecommerce_project",
        )

        result = runner.run(options)

        assert result.success
        assert result.project_dir.exists()
        assert result.anchor_path.exists()
        assert (result.project_dir / READY_FOR_BUILD_MARKER).exists()

        # Verify anchor content
        anchor_data = json.loads(result.anchor_path.read_text())
        assert anchor_data["format_version"] == "v2"

        # Verify ready marker content
        marker_data = json.loads((result.project_dir / READY_FOR_BUILD_MARKER).read_text())
        assert marker_data["status"] == "ready"
        assert marker_data["bootstrap_complete"] is True

    def test_full_pipeline_trading(self, tmp_path, trading_idea):
        """Test full pipeline for trading project."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=trading_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "trading_project",
        )

        result = runner.run(options)

        assert result.success
        assert result.parsed_idea.detected_project_type == ProjectType.TRADING
        assert result.parsed_idea.risk_profile == RiskProfile.HIGH

        # Verify marker includes high-risk project type
        marker_data = json.loads((result.project_dir / READY_FOR_BUILD_MARKER).read_text())
        assert marker_data["project_type"] == "trading"

    def test_full_pipeline_with_answers_file(self, tmp_path, ecommerce_idea):
        """Test full pipeline with pre-defined answers."""
        # Create answers file
        answers = {
            "safety_risk": {
                "never_allow": ["delete all data", "bypass payment"],
                "requires_approval": ["bulk operations"],
                "risk_tolerance": "minimal",
            },
            "north_star": {
                "desired_outcomes": ["Launch within 3 months"],
            },
        }
        answers_file = tmp_path / "answers.json"
        answers_file.write_text(json.dumps(answers))

        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=ecommerce_idea,
            answers_file=answers_file,
            skip_research=True,
            output_dir=tmp_path / "project_with_answers",
        )

        result = runner.run(options)

        assert result.success
        # Verify anchor incorporated answers
        anchor_data = json.loads(result.anchor_path.read_text())
        pivot = anchor_data.get("pivot_intentions", {})
        safety = pivot.get("safety_risk", {})
        assert "risk_tolerance" in safety

    def test_pipeline_creates_research_file_when_not_skipped(self, tmp_path, automation_idea):
        """Test that pipeline creates research file when research is run."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=automation_idea,
            autonomous=True,
            skip_research=False,  # Run research
            output_dir=tmp_path / "automation_project",
        )

        result = runner.run(options)

        assert result.success
        # Should have created research file
        research_file = result.project_dir / "bootstrap_research.json"
        assert research_file.exists()

        # Verify research content
        research_data = json.loads(research_file.read_text())
        assert "session_id" in research_data

    def test_pipeline_handles_minimal_idea(self, tmp_path):
        """Test that pipeline handles minimal idea gracefully."""
        minimal_idea = "Build a TODO app"

        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=minimal_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "minimal_project",
        )

        result = runner.run(options)

        assert result.success
        # Should still create valid output
        assert result.project_dir.exists()
        assert result.anchor_path.exists()


class TestBootstrapErrorHandling:
    """Tests for error handling in bootstrap pipeline."""

    def test_handles_empty_idea(self, tmp_path):
        """Test that empty idea is handled gracefully."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea="",
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "empty_project",
        )

        result = runner.run(options)

        assert not result.success
        assert len(result.errors) > 0

    def test_handles_nonexistent_idea_file(self, tmp_path):
        """Test that nonexistent idea file is handled gracefully."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea_file=tmp_path / "nonexistent.md",
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        assert not result.success

    def test_handles_invalid_research_file(self, tmp_path, ecommerce_idea):
        """Test that invalid research file is handled with warning."""
        # Create invalid research file
        invalid_research = tmp_path / "invalid_research.json"
        invalid_research.write_text("not valid json {")

        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=ecommerce_idea,
            research_file=invalid_research,
            autonomous=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        # Should succeed but with warning
        assert result.success
        assert len(result.warnings) > 0


class TestBootstrapMarkerFile:
    """Tests for READY_FOR_BUILD marker file."""

    def test_marker_contains_required_fields(self, tmp_path, ecommerce_idea):
        """Test that marker file contains all required fields."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=ecommerce_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        marker_path = result.project_dir / READY_FOR_BUILD_MARKER
        marker_data = json.loads(marker_path.read_text())

        required_fields = [
            "status",
            "created_at",
            "project_id",
            "project_title",
            "project_type",
            "anchor_digest",
            "bootstrap_complete",
        ]

        for field in required_fields:
            assert field in marker_data, f"Missing required field: {field}"

    def test_marker_timestamp_is_iso_format(self, tmp_path, ecommerce_idea):
        """Test that marker timestamp is in ISO format."""
        from datetime import datetime

        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=ecommerce_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        marker_path = result.project_dir / READY_FOR_BUILD_MARKER
        marker_data = json.loads(marker_path.read_text())

        # Should be able to parse as ISO datetime
        created_at = datetime.fromisoformat(marker_data["created_at"].replace("Z", "+00:00"))
        assert created_at is not None


class TestFullBootstrapPipelineWithGaps:
    """IMP-RES-008: Integration tests for full bootstrap pipeline with gap scanning and plan proposal.

    Tests the complete pipeline: idea -> research -> anchor -> gaps -> plan -> (approval) -> build
    """

    def test_full_pipeline_creates_gap_report(self, tmp_path, ecommerce_idea):
        """Test that full pipeline creates gap report file."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=ecommerce_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        assert result.success
        assert result.gap_report is not None

        # Verify gap report file was created
        gap_report_path = result.project_dir / "gap_report_v1.json"
        assert gap_report_path.exists()

        # Verify gap report content
        gap_data = json.loads(gap_report_path.read_text())
        assert gap_data["format_version"] == "v1"
        assert "project_id" in gap_data
        assert "gaps" in gap_data
        assert "summary" in gap_data

    def test_full_pipeline_creates_plan_proposal(self, tmp_path, ecommerce_idea):
        """Test that full pipeline creates plan proposal file."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=ecommerce_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        assert result.success
        assert result.plan is not None

        # Verify plan proposal file was created
        plan_path = result.project_dir / "plan_proposal_v1.json"
        assert plan_path.exists()

        # Verify plan proposal content
        plan_data = json.loads(plan_path.read_text())
        assert plan_data["format_version"] == "v1"
        assert "project_id" in plan_data
        assert "actions" in plan_data
        assert "summary" in plan_data

    def test_first_build_requires_approval(self, tmp_path, ecommerce_idea):
        """Test that first build always requires human approval."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=ecommerce_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        assert result.success
        assert result.plan is not None

        # All actions should require approval on first build (none auto-approved)
        if result.plan.summary:
            assert result.plan.summary.auto_approved_actions == 0
            # If there are any actions, they should all require approval
            if result.plan.summary.total_actions > 0:
                approved_count = result.plan.summary.requires_approval_actions
                blocked_count = result.plan.summary.blocked_actions
                assert approved_count + blocked_count == result.plan.summary.total_actions

    def test_marker_includes_pipeline_status(self, tmp_path, ecommerce_idea):
        """Test that READY_FOR_BUILD marker includes full pipeline status."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=ecommerce_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        marker_path = result.project_dir / READY_FOR_BUILD_MARKER
        marker_data = json.loads(marker_path.read_text())

        # IMP-RES-008: Marker should include pipeline status
        assert "pipeline" in marker_data
        pipeline = marker_data["pipeline"]
        assert pipeline["idea_parsed"] is True
        assert pipeline["research_complete"] is True
        assert pipeline["anchor_created"] is True
        assert pipeline["gaps_scanned"] is True
        assert pipeline["plan_proposed"] is True
        assert pipeline["approval_required"] is True

    def test_marker_includes_gap_summary(self, tmp_path, ecommerce_idea):
        """Test that READY_FOR_BUILD marker includes gap summary."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=ecommerce_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        marker_path = result.project_dir / READY_FOR_BUILD_MARKER
        marker_data = json.loads(marker_path.read_text())

        # IMP-RES-008: Marker should include gaps summary
        assert "gaps" in marker_data
        gaps = marker_data["gaps"]
        assert "total" in gaps
        assert "blockers" in gaps
        assert isinstance(gaps["total"], int)

    def test_marker_includes_plan_summary(self, tmp_path, ecommerce_idea):
        """Test that READY_FOR_BUILD marker includes plan summary."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=ecommerce_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        marker_path = result.project_dir / READY_FOR_BUILD_MARKER
        marker_data = json.loads(marker_path.read_text())

        # IMP-RES-008: Marker should include plan summary
        assert "plan" in marker_data
        plan = marker_data["plan"]
        assert "total_actions" in plan
        assert "requires_approval" in plan
        assert "auto_approved" in plan
        assert "blocked" in plan

    def test_result_includes_gap_report_and_plan(self, tmp_path, ecommerce_idea):
        """Test that BootstrapResult includes gap_report and plan."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=ecommerce_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        assert result.success
        # IMP-RES-008: Result should include gap_report and plan
        assert result.gap_report is not None
        assert result.plan is not None
        assert result.gap_report.project_id == result.anchor.project_id
        assert result.plan.project_id == result.anchor.project_id

    def test_pipeline_with_trading_idea(self, tmp_path, trading_idea):
        """Test full pipeline with high-risk trading idea."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=trading_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "trading_project",
        )

        result = runner.run(options)

        assert result.success
        assert result.gap_report is not None
        assert result.plan is not None

        # High-risk project should have stricter governance
        # First build should still require approval
        if result.plan.summary:
            assert result.plan.summary.auto_approved_actions == 0
