"""Integration tests for research-to-build-decision-to-artifacts pipeline.

Tests the complete flow from research outputs through build decisions to
artifact generation with different decision paths.
"""

from __future__ import annotations

from autopack.research.artifact_generators import (
    generate_build_decision_adjusted_artifacts,
    generate_do_not_build_report,
    get_registry,
)
from autopack.research.models.build_decision import (
    BuildDecision,
    BuildDecisionType,
    BuildViabilityMetrics,
    extract_build_decision_from_synthesis,
)
from autopack.research.models.bootstrap_session import BootstrapSession
from autopack.research.orchestrator import ResearchOrchestrator


class TestBuildDecisionExtraction:
    """Test extraction of build decisions from research synthesis."""

    def test_extract_build_decision_proceed(self):
        """Test extracting BUILD decision from positive synthesis."""
        synthesis = {
            "overall_recommendation": "proceed",
            "confidence_level": "high",
            "scores": {
                "market_attractiveness": 8.0,
                "competitive_intensity": 4.0,
                "technical_feasibility": 8.5,
                "total": 20.5,
            },
            "risk_assessment": "low",
            "key_dependencies": ["Python", "PostgreSQL"],
            "build_history_insights": {
                "success_rate": 0.85,
                "recommendations": [
                    "Use proven patterns from similar projects",
                ],
                "warnings": [],
            },
        }

        decision = extract_build_decision_from_synthesis(synthesis)

        assert decision.decision == BuildDecisionType.BUILD
        assert decision.metrics.market_attractiveness_score == 8.0
        assert decision.metrics.technical_feasibility_score == 8.5
        assert decision.confidence_percentage == 85.0
        assert "Market opportunity is strong" in decision.rationale
        assert len(decision.key_opportunities) > 0

    def test_extract_build_decision_with_caution(self):
        """Test extracting BUILD_WITH_CAUTION decision."""
        synthesis = {
            "overall_recommendation": "proceed_with_caution",
            "confidence_level": "medium",
            "scores": {
                "market_attractiveness": 5.5,
                "competitive_intensity": 7.0,
                "technical_feasibility": 6.0,
                "total": 18.5,
            },
            "risk_assessment": "medium",
            "key_dependencies": ["Node.js", "MongoDB"],
            "differentiation_factors": ["Real-time features"],
            "build_history_insights": {
                "success_rate": 0.75,
                "recommendations": ["Validate market with beta testers"],
                "warnings": ["High competition in space"],
            },
        }

        decision = extract_build_decision_from_synthesis(synthesis)

        assert decision.decision == BuildDecisionType.BUILD_WITH_CAUTION
        assert decision.confidence_percentage == 65.0
        assert len(decision.recommended_mitigations) > 0
        assert "Conduct detailed customer discovery" in str(decision.recommended_mitigations)

    def test_extract_build_decision_do_not_build(self):
        """Test extracting DO_NOT_BUILD decision."""
        synthesis = {
            "overall_recommendation": "reconsider",
            "confidence_level": "low",
            "scores": {
                "market_attractiveness": 2.0,
                "competitive_intensity": 9.0,
                "technical_feasibility": 3.0,
                "total": 14.0,
            },
            "risk_assessment": "high",
            "key_dependencies": ["Java"],
        }

        decision = extract_build_decision_from_synthesis(synthesis)

        assert decision.decision == BuildDecisionType.DO_NOT_BUILD
        assert decision.confidence_percentage == 45.0
        assert len(decision.key_blockers) > 0

    def test_decision_helper_methods(self):
        """Test decision helper methods."""
        decision = BuildDecision(
            decision=BuildDecisionType.BUILD,
            metrics=BuildViabilityMetrics(
                market_attractiveness_score=8.0,
                competitive_intensity_score=4.0,
                technical_feasibility_score=8.5,
                overall_confidence="high",
                risk_level="low",
            ),
            rationale="Good opportunity",
        )

        assert decision.is_proceed()
        assert not decision.is_proceed_with_caution()
        assert not decision.should_block()

    def test_decision_with_missing_synthesis_fields(self):
        """Test handling of incomplete synthesis data."""
        # Minimal synthesis with only required fields
        synthesis = {
            "overall_recommendation": "proceed",
            "confidence_level": "high",
            "scores": {},  # Empty scores
            "risk_assessment": "low",
        }

        decision = extract_build_decision_from_synthesis(synthesis)

        assert decision.decision == BuildDecisionType.BUILD
        assert decision.metrics.market_attractiveness_score == 0.0


class TestBuildDecisionReporting:
    """Test generation of build decision reports."""

    def test_generate_do_not_build_report(self):
        """Test generation of 'Do Not Build' report."""
        decision = BuildDecision(
            decision=BuildDecisionType.DO_NOT_BUILD,
            metrics=BuildViabilityMetrics(
                market_attractiveness_score=2.0,
                competitive_intensity_score=9.0,
                technical_feasibility_score=3.0,
                overall_confidence="low",
                risk_level="high",
            ),
            rationale="Market too competitive with limited technical feasibility",
            key_blockers=[
                "High competitive intensity",
                "Low market attractiveness",
            ],
            recommended_mitigations=[
                "Develop unique value proposition",
                "Invest in R&D for technical breakthroughs",
            ],
        )

        report = generate_do_not_build_report(decision)

        assert "# Build Decision Report: NOT RECOMMENDED" in report
        assert "DO_NOT_BUILD" in report
        assert "High competitive intensity" in report
        assert "Develop unique value proposition" in report
        assert "## Next Steps" in report

    def test_do_not_build_report_includes_all_sections(self):
        """Test that report includes all expected sections."""
        decision = BuildDecision(
            decision=BuildDecisionType.DO_NOT_BUILD,
            metrics=BuildViabilityMetrics(
                market_attractiveness_score=2.0,
                competitive_intensity_score=9.0,
                technical_feasibility_score=3.0,
                overall_confidence="low",
                risk_level="high",
            ),
            rationale="Not viable",
            key_blockers=["Blocker 1"],
            recommended_mitigations=["Mitigation 1"],
            confidence_percentage=45.0,
        )

        report = generate_do_not_build_report(decision)

        assert "## Summary" in report
        assert "## Viability Metrics" in report
        assert "## Critical Blockers" in report
        assert "## Recommendations for Future Consideration" in report
        assert "## Next Steps" in report


class TestBuildDecisionArtifactRouting:
    """Test artifact generation routing based on build decisions."""

    def test_routing_config_for_build_decision(self):
        """Test artifact routing config for BUILD decision."""
        decision = BuildDecision(
            decision=BuildDecisionType.BUILD,
            metrics=BuildViabilityMetrics(
                market_attractiveness_score=8.0,
                competitive_intensity_score=4.0,
                technical_feasibility_score=8.5,
                overall_confidence="high",
                risk_level="low",
            ),
            rationale="Good opportunity",
        )

        config = generate_build_decision_adjusted_artifacts(decision)

        assert config["decision"] == "BUILD"
        assert "project_brief" in config["artifacts"]
        assert "code" in config["artifacts"]
        assert "deployment" in config["artifacts"]
        assert len(config["artifacts"]) == 7

    def test_routing_config_for_caution_decision(self):
        """Test artifact routing config for BUILD_WITH_CAUTION decision."""
        decision = BuildDecision(
            decision=BuildDecisionType.BUILD_WITH_CAUTION,
            metrics=BuildViabilityMetrics(
                market_attractiveness_score=5.5,
                competitive_intensity_score=7.0,
                technical_feasibility_score=6.0,
                overall_confidence="medium",
                risk_level="medium",
            ),
            rationale="Proceed with caution",
            recommended_mitigations=["Validate market", "Mitigate competition"],
        )

        config = generate_build_decision_adjusted_artifacts(decision)

        assert config["decision"] == "BUILD_WITH_CAUTION"
        assert "project_brief" in config["artifacts"]
        assert len(config["emphasis"]) > 0
        assert any("mitigation" in e.lower() for e in config["emphasis"])

    def test_routing_config_for_do_not_build(self):
        """Test artifact routing config for DO_NOT_BUILD decision."""
        decision = BuildDecision(
            decision=BuildDecisionType.DO_NOT_BUILD,
            metrics=BuildViabilityMetrics(
                market_attractiveness_score=2.0,
                competitive_intensity_score=9.0,
                technical_feasibility_score=3.0,
                overall_confidence="low",
                risk_level="high",
            ),
            rationale="Not viable",
            key_blockers=["High competition", "Low market"],
        )

        config = generate_build_decision_adjusted_artifacts(decision)

        assert config["decision"] == "DO_NOT_BUILD"
        assert "do_not_build_report" in config["artifacts"]
        assert len(config["artifacts"]) == 1  # Only the report


class TestArtifactGeneratorWithDecision:
    """Test artifact generator registry with build decision routing."""

    def test_registry_has_decision_method(self):
        """Test that registry has build decision generation method."""
        registry = get_registry()
        assert hasattr(registry, "generate_with_build_decision")

    def test_registry_generate_with_do_not_build_decision(self):
        """Test registry generates only report for DO_NOT_BUILD."""
        registry = get_registry()
        decision = BuildDecision(
            decision=BuildDecisionType.DO_NOT_BUILD,
            metrics=BuildViabilityMetrics(
                market_attractiveness_score=2.0,
                competitive_intensity_score=9.0,
                technical_feasibility_score=3.0,
                overall_confidence="low",
                risk_level="high",
            ),
            rationale="Not viable",
        )

        artifacts = registry.generate_with_build_decision(decision)

        assert "do_not_build_report" in artifacts
        assert "# Build Decision Report: NOT RECOMMENDED" in artifacts["do_not_build_report"]

    def test_registry_generate_with_build_decision_no_findings(self):
        """Test registry handles BUILD decision without research findings."""
        registry = get_registry()
        decision = BuildDecision(
            decision=BuildDecisionType.BUILD,
            metrics=BuildViabilityMetrics(
                market_attractiveness_score=8.0,
                competitive_intensity_score=4.0,
                technical_feasibility_score=8.5,
                overall_confidence="high",
                risk_level="low",
            ),
            rationale="Good opportunity",
        )

        # Without research_findings, should return minimal artifacts
        artifacts = registry.generate_with_build_decision(decision)

        # Should at least have decision notes if applicable
        assert isinstance(artifacts, dict)


class TestResearchOrchestratorDecision:
    """Test integration with ResearchOrchestrator."""

    def test_orchestrator_get_build_decision_from_session(self):
        """Test orchestrator can extract build decision from bootstrap session."""
        orchestrator = ResearchOrchestrator()

        # Create a mock bootstrap session with synthesis
        session = BootstrapSession(
            session_id="test_session",
            idea_hash="hash123",
            parsed_idea_title="Test Project",
            parsed_idea_type="backend",
        )

        # Simulate completed research phases by setting synthesis
        session.synthesis = {
            "overall_recommendation": "proceed",
            "confidence_level": "high",
            "scores": {
                "market_attractiveness": 8.0,
                "competitive_intensity": 4.0,
                "technical_feasibility": 8.5,
                "total": 20.5,
            },
            "risk_assessment": "low",
        }

        # Mark phases as complete
        session.market_research.status = "completed"
        session.competitive_analysis.status = "completed"
        session.technical_feasibility.status = "completed"

        decision = orchestrator.get_build_decision(session)

        assert decision is not None
        assert decision.decision == BuildDecisionType.BUILD
        assert decision.metrics.market_attractiveness_score == 8.0

    def test_orchestrator_handles_incomplete_session(self):
        """Test orchestrator handles incomplete sessions gracefully."""
        orchestrator = ResearchOrchestrator()

        session = BootstrapSession(
            session_id="incomplete_session",
            idea_hash="hash456",
            parsed_idea_title="Incomplete Project",
            parsed_idea_type="backend",
        )

        # Session is not complete - no synthesis yet
        decision = orchestrator.get_build_decision(session)

        assert decision is None

    def test_orchestrator_handles_minimal_synthesis(self):
        """Test orchestrator handles minimal synthesis data gracefully."""
        orchestrator = ResearchOrchestrator()

        session = BootstrapSession(
            session_id="minimal_session",
            idea_hash="hash789",
            parsed_idea_title="Minimal Project",
            parsed_idea_type="backend",
        )

        # Create minimal synthesis with only essential fields
        session.synthesis = {
            "overall_recommendation": "proceed",
            "confidence_level": "medium",
            "scores": {},
            "risk_assessment": "medium",
        }
        session.market_research.status = "completed"
        session.competitive_analysis.status = "completed"
        session.technical_feasibility.status = "completed"

        # Should handle gracefully and return a decision
        decision = orchestrator.get_build_decision(session)
        assert decision is not None
        assert decision.decision == BuildDecisionType.BUILD
        assert decision.metrics.market_attractiveness_score == 0.0


class TestEndToEndFlow:
    """End-to-end tests for complete research→decision→artifact flow."""

    def test_complete_flow_with_build_decision(self):
        """Test complete flow from research synthesis to artifact generation."""
        orchestrator = ResearchOrchestrator()
        registry = get_registry()

        # Create and prepare a bootstrap session
        session = BootstrapSession(
            session_id="e2e_test",
            idea_hash="hash_e2e",
            parsed_idea_title="E2E Test Project",
            parsed_idea_type="saas",
        )

        session.synthesis = {
            "overall_recommendation": "proceed",
            "confidence_level": "high",
            "scores": {
                "market_attractiveness": 8.0,
                "competitive_intensity": 4.0,
                "technical_feasibility": 8.5,
                "total": 20.5,
            },
            "risk_assessment": "low",
            "differentiation_factors": ["Unique algorithm"],
        }

        session.market_research.status = "completed"
        session.competitive_analysis.status = "completed"
        session.technical_feasibility.status = "completed"

        # Extract decision
        decision = orchestrator.get_build_decision(session)
        assert decision is not None

        # Generate artifacts (without research findings for this test)
        artifacts = registry.generate_with_build_decision(decision)
        assert isinstance(artifacts, dict)
        assert decision.decision == BuildDecisionType.BUILD

    def test_research_to_do_not_build_flow(self):
        """Test flow that results in DO_NOT_BUILD decision."""
        orchestrator = ResearchOrchestrator()
        registry = get_registry()

        session = BootstrapSession(
            session_id="not_build_test",
            idea_hash="hash_not_build",
            parsed_idea_title="Not Viable Project",
            parsed_idea_type="saas",
        )

        session.synthesis = {
            "overall_recommendation": "reconsider",
            "confidence_level": "low",
            "scores": {
                "market_attractiveness": 2.0,
                "competitive_intensity": 9.0,
                "technical_feasibility": 2.0,
                "total": 13.0,
            },
            "risk_assessment": "high",
        }

        session.market_research.status = "completed"
        session.competitive_analysis.status = "completed"
        session.technical_feasibility.status = "completed"

        # Extract decision
        decision = orchestrator.get_build_decision(session)
        assert decision.decision == BuildDecisionType.DO_NOT_BUILD

        # Generate artifacts - should only have DO_NOT_BUILD report
        artifacts = registry.generate_with_build_decision(decision)
        assert "do_not_build_report" in artifacts
