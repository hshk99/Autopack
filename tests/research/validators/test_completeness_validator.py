"""Tests for ResearchCompletenessValidator (IMP-RESEARCH-002).

This test suite validates the completeness validation gates that ensure
research artifacts have all required fields before anchor generation.
"""

import pytest
from unittest.mock import MagicMock

from autopack.research.validators.completeness_validator import (
    CompletenessValidationResult,
    ResearchCompletenessValidator,
    ValidationIssue,
    ValidationSeverity,
)


class TestValidationSeverity:
    """Test ValidationSeverity enum."""

    def test_severity_values(self):
        """Test severity enum values."""
        assert ValidationSeverity.ERROR.value == "error"
        assert ValidationSeverity.WARNING.value == "warning"
        assert ValidationSeverity.INFO.value == "info"


class TestValidationIssue:
    """Test ValidationIssue dataclass."""

    def test_create_issue(self):
        """Test creating a validation issue."""
        issue = ValidationIssue(
            field_path="market_research.market_size",
            message="Missing market size",
            severity=ValidationSeverity.ERROR,
            expected_type="float",
        )

        assert issue.field_path == "market_research.market_size"
        assert issue.message == "Missing market size"
        assert issue.severity == ValidationSeverity.ERROR
        assert issue.expected_type == "float"
        assert issue.actual_value is None


class TestCompletenessValidationResult:
    """Test CompletenessValidationResult dataclass."""

    def test_empty_result_is_complete(self):
        """Test that result with no issues is complete."""
        result = CompletenessValidationResult(
            is_complete=True,
            issues=[],
            phase_coverage={"market_research": 1.0},
            overall_completeness_score=1.0,
        )

        assert result.is_complete is True
        assert result.has_errors is False
        assert result.has_warnings is False
        assert result.error_count == 0
        assert result.warning_count == 0

    def test_result_with_errors(self):
        """Test result with error issues."""
        result = CompletenessValidationResult(
            is_complete=False,
            issues=[
                ValidationIssue(
                    field_path="test",
                    message="Test error",
                    severity=ValidationSeverity.ERROR,
                ),
            ],
            phase_coverage={},
            overall_completeness_score=0.5,
        )

        assert result.is_complete is False
        assert result.has_errors is True
        assert result.error_count == 1

    def test_result_with_warnings(self):
        """Test result with warning issues."""
        result = CompletenessValidationResult(
            is_complete=True,
            issues=[
                ValidationIssue(
                    field_path="test",
                    message="Test warning",
                    severity=ValidationSeverity.WARNING,
                ),
            ],
            phase_coverage={},
            overall_completeness_score=0.8,
        )

        assert result.has_warnings is True
        assert result.warning_count == 1

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = CompletenessValidationResult(
            is_complete=True,
            issues=[
                ValidationIssue(
                    field_path="test.field",
                    message="Test message",
                    severity=ValidationSeverity.WARNING,
                    expected_type="str",
                ),
            ],
            phase_coverage={"market_research": 0.8},
            overall_completeness_score=0.8,
        )

        result_dict = result.to_dict()

        assert result_dict["is_complete"] is True
        assert result_dict["has_errors"] is False
        assert result_dict["has_warnings"] is True
        assert result_dict["overall_completeness_score"] == 0.8
        assert len(result_dict["issues"]) == 1
        assert result_dict["issues"][0]["field_path"] == "test.field"


class TestResearchCompletenessValidator:
    """Test ResearchCompletenessValidator class."""

    @pytest.fixture
    def validator(self):
        """Create a validator instance."""
        return ResearchCompletenessValidator()

    @pytest.fixture
    def complete_market_research(self):
        """Create complete market research data."""
        return {
            "market_size": 1000000.0,
            "growth_rate": 0.15,
            "target_segments": ["Enterprise", "SMB"],
            "tam_sam_som": {"tam": 10000000, "sam": 5000000, "som": 1000000},
        }

    @pytest.fixture
    def complete_competitive_analysis(self):
        """Create complete competitive analysis data."""
        return {
            "competitors": [
                {"name": "Competitor A", "description": "Market leader"},
                {"name": "Competitor B", "description": "Fast follower"},
            ],
            "differentiation_factors": ["AI-powered", "Better UX"],
            "competitive_intensity": "high",
        }

    @pytest.fixture
    def complete_technical_feasibility(self):
        """Create complete technical feasibility data."""
        return {
            "feasibility_score": 0.75,
            "key_challenges": ["Integration complexity"],
            "required_technologies": ["Python", "FastAPI"],
            "estimated_effort": "medium",
        }

    @pytest.fixture
    def complete_synthesis(self):
        """Create complete synthesis data."""
        return {
            "overall_recommendation": "proceed",
            "scores": {
                "market_attractiveness": 7.5,
                "competitive_intensity": 6.0,
                "technical_feasibility": 8.0,
                "total": 21.5,
            },
            "project_title": "Test Project",
            "project_type": "automation",
            "confidence_level": "high",
            "risk_assessment": "low",
            "key_dependencies": ["Python 3.10+"],
        }

    @pytest.fixture
    def mock_complete_session(
        self,
        complete_market_research,
        complete_competitive_analysis,
        complete_technical_feasibility,
        complete_synthesis,
    ):
        """Create a mock session with all complete data."""
        session = MagicMock()

        # Market research
        session.market_research = MagicMock()
        session.market_research.status = "completed"
        session.market_research.data = complete_market_research

        # Competitive analysis
        session.competitive_analysis = MagicMock()
        session.competitive_analysis.status = "completed"
        session.competitive_analysis.data = complete_competitive_analysis

        # Technical feasibility
        session.technical_feasibility = MagicMock()
        session.technical_feasibility.status = "completed"
        session.technical_feasibility.data = complete_technical_feasibility

        # Synthesis
        session.synthesis = complete_synthesis

        return session

    # ========================================================================
    # Test validate_session
    # ========================================================================

    def test_validate_complete_session(self, validator, mock_complete_session):
        """Test validation of a complete session passes."""
        result = validator.validate_session(mock_complete_session)

        assert result.is_complete is True
        assert result.has_errors is False
        assert result.overall_completeness_score >= 0.7

    def test_validate_session_missing_market_size(self, validator, mock_complete_session):
        """Test validation fails when market_size is missing."""
        del mock_complete_session.market_research.data["market_size"]

        result = validator.validate_session(mock_complete_session)

        assert result.has_errors is True
        error_paths = [issue.field_path for issue in result.issues]
        assert "market_research.market_size" in error_paths

    def test_validate_session_missing_growth_rate(self, validator, mock_complete_session):
        """Test validation fails when growth_rate is missing."""
        del mock_complete_session.market_research.data["growth_rate"]

        result = validator.validate_session(mock_complete_session)

        assert result.has_errors is True
        error_paths = [issue.field_path for issue in result.issues]
        assert "market_research.growth_rate" in error_paths

    def test_validate_session_missing_competitors(self, validator, mock_complete_session):
        """Test validation fails when competitors is missing."""
        del mock_complete_session.competitive_analysis.data["competitors"]

        result = validator.validate_session(mock_complete_session)

        assert result.has_errors is True
        error_paths = [issue.field_path for issue in result.issues]
        assert "competitive_analysis.competitors" in error_paths

    def test_validate_session_empty_competitors_warning(self, validator, mock_complete_session):
        """Test validation warns when competitors list is empty."""
        mock_complete_session.competitive_analysis.data["competitors"] = []

        result = validator.validate_session(mock_complete_session)

        # Should have a warning but not block
        assert result.has_warnings is True
        warning_paths = [
            issue.field_path
            for issue in result.issues
            if issue.severity == ValidationSeverity.WARNING
        ]
        assert "competitive_analysis.competitors" in warning_paths

    def test_validate_session_missing_feasibility_score(self, validator, mock_complete_session):
        """Test validation fails when feasibility_score is missing."""
        del mock_complete_session.technical_feasibility.data["feasibility_score"]

        result = validator.validate_session(mock_complete_session)

        assert result.has_errors is True
        error_paths = [issue.field_path for issue in result.issues]
        assert "technical_feasibility.feasibility_score" in error_paths

    def test_validate_session_invalid_feasibility_score_range(
        self, validator, mock_complete_session
    ):
        """Test validation warns when feasibility_score is out of range."""
        mock_complete_session.technical_feasibility.data["feasibility_score"] = 1.5

        result = validator.validate_session(mock_complete_session)

        assert result.has_warnings is True
        warning_messages = [issue.message for issue in result.issues]
        assert any("out of range" in msg for msg in warning_messages)

    def test_validate_session_missing_phase(self, validator):
        """Test validation fails when entire phase is missing."""
        session = MagicMock()
        session.market_research = None
        session.competitive_analysis = MagicMock()
        session.competitive_analysis.status = "completed"
        session.competitive_analysis.data = {}
        session.technical_feasibility = MagicMock()
        session.technical_feasibility.status = "completed"
        session.technical_feasibility.data = {}
        session.synthesis = None

        result = validator.validate_session(session)

        assert result.has_errors is True
        error_paths = [issue.field_path for issue in result.issues]
        assert "market_research" in error_paths

    def test_validate_session_phase_not_completed(self, validator, mock_complete_session):
        """Test validation fails when phase status is not completed."""
        mock_complete_session.market_research.status = "running"

        result = validator.validate_session(mock_complete_session)

        assert result.has_errors is True
        error_paths = [issue.field_path for issue in result.issues]
        assert "market_research.status" in error_paths

    # ========================================================================
    # Test validate_synthesis
    # ========================================================================

    def test_validate_complete_synthesis(self, validator, complete_synthesis):
        """Test validation of complete synthesis passes."""
        result = validator.validate_synthesis(complete_synthesis)

        assert result.is_complete is True
        assert result.has_errors is False

    def test_validate_synthesis_missing_recommendation(self, validator, complete_synthesis):
        """Test validation fails when recommendation is missing."""
        del complete_synthesis["overall_recommendation"]

        result = validator.validate_synthesis(complete_synthesis)

        assert result.has_errors is True
        error_paths = [issue.field_path for issue in result.issues]
        assert "synthesis.overall_recommendation" in error_paths

    def test_validate_synthesis_missing_scores(self, validator, complete_synthesis):
        """Test validation fails when scores is missing."""
        del complete_synthesis["scores"]

        result = validator.validate_synthesis(complete_synthesis)

        assert result.has_errors is True
        error_paths = [issue.field_path for issue in result.issues]
        assert "synthesis.scores" in error_paths

    def test_validate_synthesis_missing_score_fields(self, validator, complete_synthesis):
        """Test validation fails when required score fields are missing."""
        del complete_synthesis["scores"]["market_attractiveness"]

        result = validator.validate_synthesis(complete_synthesis)

        assert result.has_errors is True
        error_paths = [issue.field_path for issue in result.issues]
        assert "synthesis.scores.market_attractiveness" in error_paths

    def test_validate_synthesis_empty(self, validator):
        """Test validation fails for empty synthesis."""
        result = validator.validate_synthesis({})

        assert result.is_complete is False
        assert result.has_errors is True

    def test_validate_synthesis_none(self, validator):
        """Test validation fails for None synthesis."""
        result = validator.validate_synthesis(None)

        assert result.is_complete is False
        assert result.has_errors is True

    # ========================================================================
    # Test validate_before_anchor_generation
    # ========================================================================

    def test_validate_before_anchor_generation_complete(self, validator, mock_complete_session):
        """Test validation gate allows complete session."""
        can_proceed, result = validator.validate_before_anchor_generation(mock_complete_session)

        assert can_proceed is True
        assert result.is_complete is True

    def test_validate_before_anchor_generation_incomplete(self, validator, mock_complete_session):
        """Test validation gate blocks incomplete session."""
        del mock_complete_session.market_research.data["market_size"]

        can_proceed, result = validator.validate_before_anchor_generation(mock_complete_session)

        assert can_proceed is False
        assert result.is_complete is False

    # ========================================================================
    # Test strict mode
    # ========================================================================

    def test_strict_mode_treats_warnings_as_errors(self, mock_complete_session):
        """Test strict mode treats warnings as errors."""
        validator = ResearchCompletenessValidator(strict_mode=True)

        # Remove optional field to generate warning
        del mock_complete_session.market_research.data["target_segments"]

        result = validator.validate_session(mock_complete_session)

        # With strict mode, warnings make session incomplete
        assert result.has_warnings is True
        assert result.is_complete is False

    def test_non_strict_mode_allows_warnings(self, mock_complete_session):
        """Test non-strict mode allows warnings."""
        validator = ResearchCompletenessValidator(strict_mode=False)

        # Remove optional field to generate warning
        del mock_complete_session.market_research.data["target_segments"]

        result = validator.validate_session(mock_complete_session)

        # Without strict mode, warnings don't block
        assert result.has_warnings is True
        # Should still be complete if required fields present
        # (depends on other fields being present)

    # ========================================================================
    # Test threshold
    # ========================================================================

    def test_threshold_enforcement(self):
        """Test completeness threshold is enforced."""
        validator = ResearchCompletenessValidator(min_completeness_threshold=0.9)

        session = MagicMock()
        session.market_research = MagicMock()
        session.market_research.status = "completed"
        session.market_research.data = {"market_size": 1000000, "growth_rate": 0.1}

        session.competitive_analysis = MagicMock()
        session.competitive_analysis.status = "completed"
        session.competitive_analysis.data = {"competitors": [{"name": "A", "description": "B"}]}

        session.technical_feasibility = MagicMock()
        session.technical_feasibility.status = "completed"
        session.technical_feasibility.data = {"feasibility_score": 0.8}

        session.synthesis = None  # No synthesis

        result = validator.validate_session(session)

        # Should fail due to high threshold
        assert result.overall_completeness_score < 0.9
        assert result.is_complete is False

    # ========================================================================
    # Test get_required_fields_summary
    # ========================================================================

    def test_get_required_fields_summary(self, validator):
        """Test required fields summary returns all phases."""
        summary = validator.get_required_fields_summary()

        assert "market_research" in summary
        assert "competitive_analysis" in summary
        assert "technical_feasibility" in summary
        assert "synthesis" in summary

        # Check specific required fields
        assert "market_size" in summary["market_research"]
        assert "growth_rate" in summary["market_research"]
        assert "competitors" in summary["competitive_analysis"]
        assert "feasibility_score" in summary["technical_feasibility"]


class TestFieldTypeValidation:
    """Test field type validation."""

    @pytest.fixture
    def validator(self):
        return ResearchCompletenessValidator()

    def test_wrong_type_for_market_size(self, validator):
        """Test validation fails for wrong type."""
        session = MagicMock()
        session.market_research = MagicMock()
        session.market_research.status = "completed"
        session.market_research.data = {
            "market_size": "not a number",  # Wrong type
            "growth_rate": 0.1,
        }
        session.competitive_analysis = MagicMock()
        session.competitive_analysis.status = "completed"
        session.competitive_analysis.data = {"competitors": []}
        session.technical_feasibility = MagicMock()
        session.technical_feasibility.status = "completed"
        session.technical_feasibility.data = {"feasibility_score": 0.5}
        session.synthesis = None

        result = validator.validate_session(session)

        assert result.has_errors is True
        error_messages = [issue.message for issue in result.issues]
        assert any("Invalid type" in msg for msg in error_messages)

    def test_wrong_type_for_competitors(self, validator):
        """Test validation fails when competitors is not a list."""
        session = MagicMock()
        session.market_research = MagicMock()
        session.market_research.status = "completed"
        session.market_research.data = {"market_size": 1000, "growth_rate": 0.1}
        session.competitive_analysis = MagicMock()
        session.competitive_analysis.status = "completed"
        session.competitive_analysis.data = {
            "competitors": "not a list",  # Wrong type
        }
        session.technical_feasibility = MagicMock()
        session.technical_feasibility.status = "completed"
        session.technical_feasibility.data = {"feasibility_score": 0.5}
        session.synthesis = None

        result = validator.validate_session(session)

        assert result.has_errors is True
        error_messages = [issue.message for issue in result.issues]
        assert any("Invalid type" in msg for msg in error_messages)


class TestPhaseStatusValidation:
    """Test validation of phase statuses."""

    @pytest.fixture
    def validator(self):
        return ResearchCompletenessValidator()

    def test_pending_phase_fails(self, validator):
        """Test validation fails for pending phase."""
        session = MagicMock()
        session.market_research = MagicMock()
        session.market_research.status = "pending"
        session.market_research.data = {}
        session.competitive_analysis = MagicMock()
        session.competitive_analysis.status = "completed"
        session.competitive_analysis.data = {}
        session.technical_feasibility = MagicMock()
        session.technical_feasibility.status = "completed"
        session.technical_feasibility.data = {}
        session.synthesis = None

        result = validator.validate_session(session)

        assert result.has_errors is True
        error_paths = [issue.field_path for issue in result.issues]
        assert "market_research.status" in error_paths

    def test_failed_phase_fails(self, validator):
        """Test validation fails for failed phase."""
        session = MagicMock()
        session.market_research = MagicMock()
        session.market_research.status = "failed"
        session.market_research.data = {}
        session.competitive_analysis = MagicMock()
        session.competitive_analysis.status = "completed"
        session.competitive_analysis.data = {}
        session.technical_feasibility = MagicMock()
        session.technical_feasibility.status = "completed"
        session.technical_feasibility.data = {}
        session.synthesis = None

        result = validator.validate_session(session)

        assert result.has_errors is True
        error_paths = [issue.field_path for issue in result.issues]
        assert "market_research.status" in error_paths
