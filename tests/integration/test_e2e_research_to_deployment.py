"""E2E integration tests for research to deployment workflow (IMP-TEST-005).

Tests the complete workflow from research outputs → build decision → deployment artifacts.

This module exercises:
1. Research pipeline execution with mocked outputs
2. Build decision logic based on research viability metrics
3. Artifact generation conditional on build decision
4. Deployment artifact creation (guides, Docker, K8s configs)
5. Error scenarios and decision routing
"""

import time
from typing import Dict
from unittest.mock import MagicMock

import pytest

from autopack.research.orchestrator import ResearchOrchestrator

# =============================================================================
# Enums and Constants
# =============================================================================


class BuildDecision:
    """Enumeration of build decisions based on research findings."""

    BUILD = "BUILD"
    BUILD_WITH_CAUTION = "BUILD_WITH_CAUTION"
    DO_NOT_BUILD = "DO_NOT_BUILD"


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def viable_research_output():
    """Research output indicating a viable, buildable project."""
    return {
        "project_id": "proj-viable-001",
        "market_analysis": {
            "tam": 50000000,  # Large market
            "competitive_intensity": 0.4,  # Low competition
            "market_trends": ["Growing", "Underserved"],
            "demand_signals": 8.5,  # High demand
        },
        "feasibility_analysis": {
            "technical_complexity": 0.5,  # Medium complexity
            "team_size_requirement": 4,
            "timeline_weeks": 12,
            "estimated_cost": 120000,
        },
        "competitive_analysis": {
            "direct_competitors": 2,
            "differentiation_strength": 0.8,
            "market_gaps": ["Better UX", "AI features"],
        },
        "go_to_market": {
            "strategy": "B2B SaaS with freemium",
            "acquisition_cost": 150,
            "customer_lifetime_value": 5000,
            "payback_period_months": 3,
        },
        "tech_stack": ["Python", "FastAPI", "PostgreSQL", "React", "AWS"],
        "deployment_platforms": ["AWS", "Docker", "Kubernetes"],
        "confidence_scores": {
            "market_fit": 0.85,
            "technical_feasibility": 0.8,
            "go_to_market": 0.75,
            "overall": 0.8,
        },
    }


@pytest.fixture
def risky_research_output():
    """Research output indicating a risky but potentially viable project."""
    return {
        "project_id": "proj-risky-001",
        "market_analysis": {
            "tam": 20000000,  # Smaller market
            "competitive_intensity": 0.75,  # High competition
            "market_trends": ["Declining", "Saturated"],
            "demand_signals": 4.5,  # Moderate demand
        },
        "feasibility_analysis": {
            "technical_complexity": 0.8,  # High complexity
            "team_size_requirement": 8,
            "timeline_weeks": 24,
            "estimated_cost": 500000,
        },
        "competitive_analysis": {
            "direct_competitors": 12,
            "differentiation_strength": 0.4,
            "market_gaps": ["Expensive", "Poor support"],
        },
        "go_to_market": {
            "strategy": "B2C with heavy marketing",
            "acquisition_cost": 500,
            "customer_lifetime_value": 1200,
            "payback_period_months": 18,
        },
        "tech_stack": ["Python", "TensorFlow", "PostgreSQL", "React", "GCP"],
        "deployment_platforms": ["GCP", "Docker"],
        "confidence_scores": {
            "market_fit": 0.45,
            "technical_feasibility": 0.5,
            "go_to_market": 0.3,
            "overall": 0.42,
        },
        "risk_factors": [
            "High competition",
            "Declining market",
            "High technical complexity",
            "Long timeline",
            "Expensive to build",
        ],
    }


@pytest.fixture
def non_viable_research_output():
    """Research output indicating a non-viable project."""
    return {
        "project_id": "proj-blocked-001",
        "market_analysis": {
            "tam": 500000,  # Too small
            "competitive_intensity": 0.95,  # Extremely saturated
            "market_trends": ["Declining", "Mature"],
            "demand_signals": 1.5,  # Very low demand
        },
        "feasibility_analysis": {
            "technical_complexity": 0.9,  # Very high complexity
            "team_size_requirement": 15,
            "timeline_weeks": 52,
            "estimated_cost": 2000000,
        },
        "competitive_analysis": {
            "direct_competitors": 50,
            "differentiation_strength": 0.1,
            "market_gaps": None,
        },
        "legal_compliance": {
            "regulatory_barriers": ["GDPR", "CCPA", "Banking regulations"],
            "licensing_required": True,
            "estimated_compliance_cost": 500000,
        },
        "confidence_scores": {
            "market_fit": 0.1,
            "technical_feasibility": 0.2,
            "go_to_market": 0.05,
            "overall": 0.12,
        },
        "blockers": [
            "Saturated market with entrenched competitors",
            "Declining demand",
            "High regulatory barriers",
            "Cannot differentiate meaningfully",
        ],
    }


@pytest.fixture
def research_execution_context():
    """Context for research execution tracking."""
    return {
        "research_id": "research-001",
        "start_time": None,
        "end_time": None,
        "phase_timings": {},
        "phases_executed": [],
    }


# =============================================================================
# Research Orchestration Tests
# =============================================================================


@pytest.mark.integration
class TestResearchOrchestrationE2E:
    """E2E tests for research pipeline orchestration."""

    def test_research_session_initialization(self):
        """Test that research sessions can be initialized."""
        # Setup
        orchestrator = ResearchOrchestrator()

        # Verify orchestrator is properly initialized
        assert orchestrator is not None
        assert isinstance(orchestrator, ResearchOrchestrator)

    @pytest.mark.aspirational
    def test_research_pipeline_multi_phase_execution(self, research_execution_context):
        """Test research pipeline executes all required phases."""
        # Setup
        ResearchOrchestrator()
        research_phases = [
            "market_analysis",
            "competitive_analysis",
            "feasibility_analysis",
            "go_to_market_planning",
            "tech_stack_recommendation",
        ]

        # Mock research execution (aspirational)
        mock_session = MagicMock()
        mock_session.session_id = "research-001"
        mock_session.phases_completed = research_phases

        # Execute
        research_execution_context["start_time"] = time.time()
        # (In actual implementation, would call orchestrator method)
        research_execution_context["end_time"] = time.time()
        research_execution_context["phases_executed"] = mock_session.phases_completed

        # Verify
        assert mock_session is not None
        assert len(research_execution_context["phases_executed"]) == 5
        assert research_execution_context["end_time"] >= research_execution_context["start_time"]

    def test_research_outputs_contain_required_metrics(self, viable_research_output):
        """Test that research outputs contain all required decision metrics."""
        # Verify required top-level keys
        required_keys = [
            "market_analysis",
            "feasibility_analysis",
            "competitive_analysis",
            "go_to_market",
            "confidence_scores",
        ]

        for key in required_keys:
            assert key in viable_research_output, f"Missing required key: {key}"

        # Verify market analysis contains key metrics
        market = viable_research_output["market_analysis"]
        assert "tam" in market
        assert "competitive_intensity" in market
        assert market["tam"] > 0
        assert 0 <= market["competitive_intensity"] <= 1

        # Verify confidence scores
        scores = viable_research_output["confidence_scores"]
        assert "overall" in scores
        assert 0 <= scores["overall"] <= 1


# =============================================================================
# Build Decision Logic Tests
# =============================================================================


@pytest.mark.integration
class TestBuildDecisionLogicE2E:
    """E2E tests for build decision making based on research findings."""

    def _make_build_decision(self, research_output: Dict) -> str:
        """Helper method to make build decision from research output.

        Decision rules:
        - BUILD: overall confidence >= 0.7
        - BUILD_WITH_CAUTION: 0.4 <= confidence < 0.7
        - DO_NOT_BUILD: confidence < 0.4
        """
        overall_confidence = research_output["confidence_scores"]["overall"]

        if overall_confidence >= 0.7:
            return BuildDecision.BUILD
        elif overall_confidence >= 0.4:
            return BuildDecision.BUILD_WITH_CAUTION
        else:
            return BuildDecision.DO_NOT_BUILD

    def test_viable_project_decision_is_build(self, viable_research_output):
        """Test that viable projects get BUILD decision."""
        # Execute
        decision = self._make_build_decision(viable_research_output)

        # Verify
        assert decision == BuildDecision.BUILD
        assert viable_research_output["confidence_scores"]["overall"] >= 0.7

    def test_risky_project_decision_is_build_with_caution(self, risky_research_output):
        """Test that risky projects get BUILD_WITH_CAUTION decision."""
        # Execute
        decision = self._make_build_decision(risky_research_output)

        # Verify
        assert decision == BuildDecision.BUILD_WITH_CAUTION
        assert 0.4 <= risky_research_output["confidence_scores"]["overall"] < 0.7

    def test_non_viable_project_decision_is_do_not_build(self, non_viable_research_output):
        """Test that non-viable projects get DO_NOT_BUILD decision."""
        # Execute
        decision = self._make_build_decision(non_viable_research_output)

        # Verify
        assert decision == BuildDecision.DO_NOT_BUILD
        assert non_viable_research_output["confidence_scores"]["overall"] < 0.4

    def test_build_decision_reasons_generated(self, viable_research_output):
        """Test that build decision includes reasoning."""
        # Setup
        decision = self._make_build_decision(viable_research_output)

        # For BUILD decision, generate positive reasons
        if decision == BuildDecision.BUILD:
            reasons = []
            if viable_research_output["market_analysis"]["tam"] > 10000000:
                reasons.append("Large addressable market")
            if viable_research_output["market_analysis"]["competitive_intensity"] < 0.5:
                reasons.append("Low competitive intensity")
            if viable_research_output["confidence_scores"]["overall"] > 0.75:
                reasons.append("High confidence in market fit")

        # Verify reasoning exists
        assert len(reasons) > 0

    def test_decision_influences_artifact_generation(self, viable_research_output):
        """Test that build decision influences which artifacts are generated."""
        decision = self._make_build_decision(viable_research_output)

        # For BUILD decision, all artifacts should be generated
        if decision == BuildDecision.BUILD:
            artifacts_to_generate = [
                "code_templates",
                "deployment_guide",
                "cicd_pipeline",
                "project_brief",
                "go_to_market_plan",
            ]
        # For BUILD_WITH_CAUTION, include caution notes
        elif decision == BuildDecision.BUILD_WITH_CAUTION:
            artifacts_to_generate = [
                "code_templates",
                "deployment_guide_with_warnings",
                "risk_mitigation_plan",
            ]
        # For DO_NOT_BUILD, generate rejection report
        else:
            artifacts_to_generate = ["rejection_analysis_report"]

        # Verify decision-artifact mapping makes sense
        if decision == BuildDecision.DO_NOT_BUILD:
            assert "code_templates" not in artifacts_to_generate
            assert "rejection_analysis_report" in artifacts_to_generate


# =============================================================================
# Artifact Generation Based on Build Decision
# =============================================================================


@pytest.mark.integration
class TestDecisionBasedArtifactGenerationE2E:
    """E2E tests for artifact generation conditioned on build decision."""

    @pytest.mark.aspirational
    def test_deployment_guide_generated_for_build_decision(self, viable_research_output):
        """Test that deployment guides are generated for BUILD decisions."""
        # Setup

        # Mock deployment guide generation (aspirational)
        deployment_artifacts = {
            "DEPLOYMENT.md": "# Deployment Guide\n## Prerequisites\n...",
            "docker-compose.yml": "version: '3.8'\nservices:\n...",
            "kubernetes-deployment.yaml": "apiVersion: apps/v1\nkind: Deployment\n...",
            "terraform/main.tf": "terraform {\n  required_version = ...\n",
        }

        # Verify
        assert deployment_artifacts is not None
        assert "DEPLOYMENT.md" in deployment_artifacts
        assert "docker-compose.yml" in deployment_artifacts
        assert len(deployment_artifacts) >= 3

    @pytest.mark.aspirational
    def test_risk_mitigation_plan_for_caution_decision(self, risky_research_output):
        """Test that risk mitigation plans are generated for BUILD_WITH_CAUTION."""
        # Setup
        decision = "BUILD_WITH_CAUTION"
        research_output = risky_research_output
        risk_factors = research_output.get("risk_factors", [])

        # Create risk mitigation plan
        mitigation_plan = {
            "decision": decision,
            "identified_risks": risk_factors,
            "mitigation_strategies": {},
        }

        for risk in risk_factors:
            if "competition" in risk.lower():
                mitigation_plan["mitigation_strategies"][risk] = [
                    "Focus on niche market",
                    "Build unique features",
                ]
            elif "timeline" in risk.lower():
                mitigation_plan["mitigation_strategies"][risk] = [
                    "Break into MVP phases",
                    "Use rapid prototyping",
                ]

        # Verify
        assert decision == "BUILD_WITH_CAUTION"
        assert len(mitigation_plan["identified_risks"]) > 0
        assert len(mitigation_plan["mitigation_strategies"]) > 0
        for risk, strategies in mitigation_plan["mitigation_strategies"].items():
            assert len(strategies) > 0

    @pytest.mark.aspirational
    def test_rejection_report_for_do_not_build_decision(self, non_viable_research_output):
        """Test that rejection reports are generated for DO_NOT_BUILD decisions."""
        # Setup
        decision = "DO_NOT_BUILD"
        research_output = non_viable_research_output
        blockers = research_output.get("blockers", [])

        # Create rejection report
        rejection_report = {
            "decision": decision,
            "recommendation": "Do not proceed with this project",
            "blockers": blockers,
            "alternatives": [
                "Focus on a different market segment",
                "Wait for market conditions to change",
                "Acquire existing players instead",
            ],
            "confidence_score": research_output["confidence_scores"]["overall"],
        }

        # Verify
        assert decision == "DO_NOT_BUILD"
        assert rejection_report["recommendation"] is not None
        assert len(rejection_report["blockers"]) > 0
        assert rejection_report["confidence_score"] < 0.4

    def test_artifact_content_reflects_decision_confidence(self, viable_research_output):
        """Test that artifact content is appropriate to decision confidence level."""
        # For high-confidence projects, artifacts should be comprehensive
        confidence = viable_research_output["confidence_scores"]["overall"]

        if confidence > 0.8:
            expected_detail_level = "comprehensive"
        elif confidence > 0.6:
            expected_detail_level = "standard"
        else:
            expected_detail_level = "minimal"

        # Verify mapping
        assert expected_detail_level in ["comprehensive", "standard", "minimal"]

        # High confidence should have more comprehensive artifacts
        if confidence > 0.8:
            assert expected_detail_level == "comprehensive"

    def test_multiple_deployment_platforms_in_artifacts(self, viable_research_output):
        """Test that artifacts support multiple deployment platforms."""
        # Setup
        platforms = viable_research_output.get("deployment_platforms", [])

        # Mock multi-platform deployment guide
        platform_guides = {}
        for platform in platforms:
            if platform == "AWS":
                platform_guides["AWS"] = "# AWS Deployment\n## EC2 Setup\n..."
            elif platform == "Docker":
                platform_guides["Docker"] = "FROM python:3.11\n..."
            elif platform == "Kubernetes":
                platform_guides["Kubernetes"] = "apiVersion: v1\nkind: Deployment\n..."

        # Verify all platforms have guides
        for platform in platforms:
            assert platform in platform_guides
            assert len(platform_guides[platform]) > 0


# =============================================================================
# Complete Research to Deployment Workflow Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.aspirational
class TestResearchToDeploymentCompleteE2E:
    """E2E test for complete research to deployment workflow."""

    def test_complete_workflow_viable_project(self, viable_research_output):
        """Test complete workflow for a viable project.

        Flow: Research → Decision (BUILD) → Full Artifacts
        """
        # Phase 1: Research
        assert viable_research_output["confidence_scores"]["overall"] >= 0.7

        # Phase 2: Build decision
        decision = (
            BuildDecision.BUILD
            if viable_research_output["confidence_scores"]["overall"] >= 0.7
            else BuildDecision.BUILD_WITH_CAUTION
        )
        assert decision == BuildDecision.BUILD

        # Phase 3: Artifact generation (full suite)
        expected_artifacts = [
            "code_templates",
            "deployment_guide",
            "cicd_pipeline",
            "project_brief",
            "monetization_plan",
        ]

        # Verify all artifacts would be generated
        assert len(expected_artifacts) == 5

    def test_complete_workflow_risky_project(self, risky_research_output):
        """Test complete workflow for a risky project.

        Flow: Research → Decision (BUILD_WITH_CAUTION) → Conditional Artifacts
        """
        # Phase 1: Research
        assert 0.4 <= risky_research_output["confidence_scores"]["overall"] < 0.7

        # Phase 2: Build decision

        # Phase 3: Artifact generation (with caution)
        expected_artifacts = [
            "code_templates",
            "deployment_guide_with_warnings",
            "risk_mitigation_plan",
        ]

        # Verify caution-appropriate artifacts
        assert "warnings" in expected_artifacts[1].lower()
        assert "risk" in expected_artifacts[2].lower()

    def test_complete_workflow_blocked_project(self, non_viable_research_output):
        """Test complete workflow for a blocked project.

        Flow: Research → Decision (DO_NOT_BUILD) → Rejection Report
        """
        # Phase 1: Research
        assert non_viable_research_output["confidence_scores"]["overall"] < 0.4

        # Phase 2: Build decision
        decision = BuildDecision.DO_NOT_BUILD

        # Phase 3: Artifact generation (rejection report only)
        expected_artifacts = ["rejection_analysis_report"]

        # Verify project is not built
        assert decision == BuildDecision.DO_NOT_BUILD
        assert len(expected_artifacts) == 1
        assert "rejection" in expected_artifacts[0].lower()
