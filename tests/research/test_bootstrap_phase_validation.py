"""Tests for bootstrap session phase result schema validation."""

import pytest

from autopack.research.models.bootstrap_session import (
    BootstrapPhase, BootstrapSession, CompetitiveAnalysisResult,
    MarketResearchResult, TechnicalFeasibilityResult)


class TestMarketResearchSchema:
    """Test MarketResearchResult schema validation."""

    def test_valid_market_research_data(self):
        """Test that valid market research data passes validation."""
        data = {
            "market_size": 1000000.0,
            "growth_rate": 0.15,
            "target_segments": ["B2B", "Enterprise"],
            "tam_sam_som": {
                "tam": 10000000.0,
                "sam": 2000000.0,
                "som": 500000.0,
            },
        }
        result = MarketResearchResult(**data)
        assert result.market_size == 1000000.0
        assert result.growth_rate == 0.15

    def test_growth_rate_bounds(self):
        """Test that growth rate must be between 0 and 1."""
        with pytest.raises(ValueError, match="growth_rate must be between 0 and 1"):
            MarketResearchResult(
                market_size=1000000.0,
                growth_rate=1.5,  # Invalid: > 1
            )

        with pytest.raises(ValueError, match="growth_rate must be between 0 and 1"):
            MarketResearchResult(
                market_size=1000000.0,
                growth_rate=-0.1,  # Invalid: < 0
            )

    def test_market_size_non_negative(self):
        """Test that market size must be non-negative."""
        with pytest.raises(ValueError, match="market_size must be non-negative"):
            MarketResearchResult(
                market_size=-1000.0,
                growth_rate=0.1,
            )

    def test_required_fields(self):
        """Test that required fields are enforced."""
        with pytest.raises(ValueError):
            MarketResearchResult(growth_rate=0.1)  # Missing market_size

        with pytest.raises(ValueError):
            MarketResearchResult(market_size=1000000.0)  # Missing growth_rate


class TestCompetitiveAnalysisSchema:
    """Test CompetitiveAnalysisResult schema validation."""

    def test_valid_competitive_analysis_data(self):
        """Test that valid competitive analysis data passes validation."""
        data = {
            "competitors": [
                {"name": "Competitor A", "description": "Market leader"},
                {"name": "Competitor B", "description": "Emerging player"},
            ],
            "differentiation_factors": [
                "Superior AI capabilities",
                "Lower pricing",
            ],
            "competitive_intensity": "high",
        }
        result = CompetitiveAnalysisResult(**data)
        assert len(result.competitors) == 2
        assert result.competitive_intensity == "high"

    def test_competitor_required_fields(self):
        """Test that competitors must have name and description."""
        with pytest.raises(ValueError, match="missing required fields"):
            CompetitiveAnalysisResult(
                competitors=[
                    {"name": "Competitor A"},  # Missing description
                ]
            )

        with pytest.raises(ValueError, match="missing required fields"):
            CompetitiveAnalysisResult(
                competitors=[
                    {"description": "Some description"},  # Missing name
                ]
            )

    def test_empty_competitors_allowed(self):
        """Test that empty competitor list is allowed."""
        result = CompetitiveAnalysisResult()
        assert result.competitors == []


class TestTechnicalFeasibilitySchema:
    """Test TechnicalFeasibilityResult schema validation."""

    def test_valid_technical_feasibility_data(self):
        """Test that valid technical feasibility data passes validation."""
        data = {
            "feasibility_score": 0.8,
            "key_challenges": [
                "ML model training infrastructure",
                "Data pipeline scalability",
            ],
            "required_technologies": [
                "PyTorch",
                "PostgreSQL",
                "Kubernetes",
            ],
            "estimated_effort": "high",
        }
        result = TechnicalFeasibilityResult(**data)
        assert result.feasibility_score == 0.8
        assert len(result.key_challenges) == 2

    def test_feasibility_score_bounds(self):
        """Test that feasibility score must be between 0 and 1."""
        with pytest.raises(ValueError, match="feasibility_score must be between 0 and 1"):
            TechnicalFeasibilityResult(
                feasibility_score=1.5,  # Invalid: > 1
                key_challenges=[],
            )

        with pytest.raises(ValueError, match="feasibility_score must be between 0 and 1"):
            TechnicalFeasibilityResult(
                feasibility_score=-0.1,  # Invalid: < 0
                key_challenges=[],
            )

    def test_required_fields(self):
        """Test that required fields are enforced."""
        with pytest.raises(ValueError):
            TechnicalFeasibilityResult()  # Missing feasibility_score


class TestBootstrapSessionValidation:
    """Test BootstrapSession integration with phase validation."""

    def test_mark_phase_completed_with_valid_data(self):
        """Test marking phase complete with valid data."""
        session = BootstrapSession(
            session_id="test-session-001",
            idea_hash="abc123def456",
        )

        market_data = {
            "market_size": 5000000.0,
            "growth_rate": 0.20,
            "target_segments": ["Enterprise", "Mid-market"],
        }

        session.mark_phase_completed(BootstrapPhase.MARKET_RESEARCH, market_data)

        assert session.market_research.status == "completed"
        assert session.market_research.data["market_size"] == 5000000.0
        assert session.market_research.completed_at is not None

    def test_mark_phase_completed_with_invalid_data(self):
        """Test that invalid data raises ValueError during phase completion."""
        session = BootstrapSession(
            session_id="test-session-002",
            idea_hash="abc123def456",
        )

        invalid_market_data = {
            "market_size": -1000.0,  # Invalid: negative
            "growth_rate": 0.20,
        }

        with pytest.raises(ValueError, match="Invalid market_research data"):
            session.mark_phase_completed(BootstrapPhase.MARKET_RESEARCH, invalid_market_data)

    def test_mark_competitive_analysis_with_valid_data(self):
        """Test marking competitive analysis phase complete."""
        session = BootstrapSession(
            session_id="test-session-003",
            idea_hash="abc123def456",
        )

        competitive_data = {
            "competitors": [
                {"name": "Company X", "description": "Direct competitor"},
                {"name": "Company Y", "description": "Adjacent market"},
            ],
            "differentiation_factors": ["Patent portfolio", "Team experience"],
        }

        session.mark_phase_completed(BootstrapPhase.COMPETITIVE_ANALYSIS, competitive_data)

        assert session.competitive_analysis.status == "completed"
        assert len(session.competitive_analysis.data["competitors"]) == 2

    def test_mark_technical_feasibility_with_valid_data(self):
        """Test marking technical feasibility phase complete."""
        session = BootstrapSession(
            session_id="test-session-004",
            idea_hash="abc123def456",
        )

        feasibility_data = {
            "feasibility_score": 0.75,
            "key_challenges": ["Data availability", "Model optimization"],
            "required_technologies": ["TensorFlow", "PostgreSQL"],
            "estimated_effort": "medium",
        }

        session.mark_phase_completed(BootstrapPhase.TECHNICAL_FEASIBILITY, feasibility_data)

        assert session.technical_feasibility.status == "completed"
        assert session.technical_feasibility.data["feasibility_score"] == 0.75

    def test_all_phases_valid_for_synthesis(self):
        """Test that all phases can be completed with valid data."""
        session = BootstrapSession(
            session_id="test-session-005",
            idea_hash="abc123def456",
        )

        market_data = {
            "market_size": 2000000.0,
            "growth_rate": 0.25,
        }
        competitive_data = {
            "competitors": [{"name": "Rival", "description": "Test"}],
            "differentiation_factors": ["Innovation"],
        }
        feasibility_data = {
            "feasibility_score": 0.85,
            "key_challenges": [],
        }

        session.mark_phase_completed(BootstrapPhase.MARKET_RESEARCH, market_data)
        session.mark_phase_completed(BootstrapPhase.COMPETITIVE_ANALYSIS, competitive_data)
        session.mark_phase_completed(BootstrapPhase.TECHNICAL_FEASIBILITY, feasibility_data)

        assert session.is_complete()
        assert session.current_phase == BootstrapPhase.SYNTHESIS

    def test_validation_failure_doesnt_mark_complete(self):
        """Test that validation failure doesn't mark phase as complete."""
        session = BootstrapSession(
            session_id="test-session-006",
            idea_hash="abc123def456",
        )

        invalid_feasibility_data = {
            "feasibility_score": 2.0,  # Invalid: > 1
            "key_challenges": [],
        }

        with pytest.raises(ValueError):
            session.mark_phase_completed(
                BootstrapPhase.TECHNICAL_FEASIBILITY, invalid_feasibility_data
            )

        # Phase should still be in pending state
        assert session.technical_feasibility.status == "pending"
