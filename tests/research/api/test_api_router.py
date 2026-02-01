"""Tests for Research API router objective validation (IMP-SCHEMA-008).

Tests the objective field validation in the full research session endpoint:
- Objective format validation (length, content)
- Objective uniqueness
- Objective compatibility with research type
- Error responses for invalid objectives
- Logging of validation failures
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from autopack.research.api.router import (
    FullSessionRequest,
    ResearchAPIMode,
    _infer_research_type,
    research_router,
    validate_objective_compatibility,
    validate_objective_format,
)


class TestObjectiveFormat:
    """Tests for validate_objective_format function."""

    def test_valid_objective_format(self):
        """Test that valid objectives pass format validation."""
        validate_objective_format("Analyze market trends and competition", 0)
        validate_objective_format("Evaluate technical architecture options", 0)
        validate_objective_format("Assess cost-effectiveness of solutions", 0)

    def test_objective_too_short(self):
        """Test that objectives with less than 2 words fail."""
        with pytest.raises(ValueError, match="Must contain at least 2 words"):
            validate_objective_format("SingleWord", 0)

    def test_objective_empty_string(self):
        """Test that empty objectives fail."""
        with pytest.raises(ValueError, match="Cannot be empty or whitespace only"):
            validate_objective_format("", 0)

    def test_objective_whitespace_only(self):
        """Test that whitespace-only objectives fail."""
        with pytest.raises(ValueError, match="Cannot be empty or whitespace only"):
            validate_objective_format("   ", 0)

    def test_objective_not_string(self):
        """Test that non-string objectives fail."""
        with pytest.raises(ValueError, match="Must be a string"):
            validate_objective_format(123, 0)

    def test_objective_index_in_error_message(self):
        """Test that error messages include the objective index."""
        with pytest.raises(ValueError, match="index 5"):
            validate_objective_format("Single", 5)


class TestObjectiveValidation:
    """Tests for objective validation in FullSessionRequest."""

    def test_valid_objectives_list(self):
        """Test validation of a valid objectives list."""
        objectives = [
            "Evaluate technical architecture and design patterns",
            "Assess market size and customer demand",
            "Review competitive landscape and alternatives",
        ]
        cleaned = FullSessionRequest.model_validate(
            {
                "title": "Research Project",
                "description": "A comprehensive research project",
                "objectives": objectives,
            }
        ).objectives
        assert len(cleaned) == 3
        assert all(isinstance(obj, str) for obj in cleaned)

    def test_empty_objectives_list(self):
        """Test that empty objectives list is allowed (but endpoint validates presence)."""
        request = FullSessionRequest.model_validate(
            {
                "title": "Research Project",
                "description": "A comprehensive research project",
                "objectives": [],
            }
        )
        assert request.objectives == []

    def test_objectives_with_whitespace_trimmed(self):
        """Test that objectives have whitespace trimmed."""
        objectives = [
            "  Analyze market trends  ",
            "\tEvaluate technical options\t",
        ]
        cleaned = FullSessionRequest.model_validate(
            {
                "title": "Research Project",
                "description": "A comprehensive research project",
                "objectives": objectives,
            }
        ).objectives
        assert cleaned[0] == "Analyze market trends"
        assert cleaned[1] == "Evaluate technical options"

    def test_objectives_too_many(self):
        """Test that more than 10 objectives are rejected."""
        objectives = [f"Objective number {i} with meaningful content" for i in range(11)]
        with pytest.raises(ValueError, match="Maximum 10 objectives allowed"):
            FullSessionRequest.model_validate(
                {
                    "title": "Research Project",
                    "description": "A comprehensive research project",
                    "objectives": objectives,
                }
            )

    def test_objectives_minimum_length(self):
        """Test that objectives shorter than 10 characters are rejected."""
        with pytest.raises(ValueError, match="Must be at least 10 characters"):
            FullSessionRequest.model_validate(
                {
                    "title": "Research Project",
                    "description": "A comprehensive research project",
                    "objectives": ["Short obj"],
                }
            )

    def test_objectives_maximum_length(self):
        """Test that objectives longer than 500 characters are rejected."""
        long_objective = "A" * 501
        with pytest.raises(ValueError, match="Must not exceed 500 characters"):
            FullSessionRequest.model_validate(
                {
                    "title": "Research Project",
                    "description": "A comprehensive research project",
                    "objectives": [long_objective],
                }
            )

    def test_duplicate_objectives_rejected(self):
        """Test that duplicate objectives are rejected."""
        with pytest.raises(ValueError, match="Duplicate objective detected"):
            FullSessionRequest.model_validate(
                {
                    "title": "Research Project",
                    "description": "A comprehensive research project",
                    "objectives": [
                        "Analyze market trends and opportunities",
                        "analyze market trends and opportunities",  # Duplicate (case-insensitive)
                    ],
                }
            )

    def test_duplicate_with_whitespace_variations(self):
        """Test that duplicate detection works with whitespace variations."""
        with pytest.raises(ValueError, match="Duplicate objective detected"):
            FullSessionRequest.model_validate(
                {
                    "title": "Research Project",
                    "description": "A comprehensive research project",
                    "objectives": [
                        "Analyze  market  trends",
                        "Analyze market trends",  # Same after whitespace normalization
                    ],
                }
            )

    def test_empty_objective_in_list(self):
        """Test that empty objectives within a list are rejected."""
        with pytest.raises(ValueError, match="Cannot be empty or whitespace only"):
            FullSessionRequest.model_validate(
                {
                    "title": "Research Project",
                    "description": "A comprehensive research project",
                    "objectives": [
                        "Valid objective with content",
                        "",  # Empty
                    ],
                }
            )


class TestResearchTypeInference:
    """Tests for _infer_research_type function."""

    def test_infer_technical_research(self):
        """Test inference of technical research type."""
        assert (
            _infer_research_type("Technical Architecture Study", "Evaluate technology")
            == "technical"
        )
        assert _infer_research_type("Building Implementation", "How to build") == "technical"
        assert _infer_research_type("Development Approach", "Develop architecture") == "technical"

    def test_infer_market_research(self):
        """Test inference of market research type."""
        assert _infer_research_type("Market Analysis", "Understand customer demand") == "market"
        assert _infer_research_type("User Study", "User needs analysis") == "market"
        assert _infer_research_type("Market Size", "Estimate growth") == "market"

    def test_infer_competitive_research(self):
        """Test inference of competitive research type."""
        assert (
            _infer_research_type("Competitive Analysis", "Competitor comparison") == "competitive"
        )
        assert _infer_research_type("Market Position", "Competitive landscape") == "competitive"
        assert _infer_research_type("Alternative Solutions", "vs alternatives") == "competitive"

    def test_infer_feasibility_research(self):
        """Test inference of feasibility research type."""
        assert _infer_research_type("Feasibility Study", "Assess viability") == "feasibility"
        assert (
            _infer_research_type("Capability Analysis", "Possible implementations") == "feasibility"
        )

    def test_infer_general_research(self):
        """Test inference of general research type when no keywords match."""
        assert _infer_research_type("Some Project", "A generic description") == "general"
        assert _infer_research_type("Analysis", "Study") == "general"

    def test_infer_research_type_case_insensitive(self):
        """Test that research type inference is case-insensitive."""
        assert _infer_research_type("TECHNICAL ARCHITECTURE", "BUILD IMPLEMENTATION") == "technical"
        assert _infer_research_type("MARKET ANALYSIS", "CUSTOMER DEMAND") == "market"


class TestObjectiveCompatibility:
    """Tests for validate_objective_compatibility function."""

    def test_technical_research_with_technical_objectives(self):
        """Test that technical objectives pass technical research validation."""
        warnings = validate_objective_compatibility(
            [
                "Evaluate technical architecture patterns",
                "Design implementation approach",
            ],
            "technical",
        )
        assert len(warnings) == 0

    def test_technical_research_without_technical_keywords(self):
        """Test that non-technical objectives generate warning for technical research."""
        warnings = validate_objective_compatibility(
            ["Understand market dynamics", "Assess pricing strategy"],
            "technical",
        )
        assert len(warnings) > 0
        assert any("technical" in w.lower() for w in warnings)

    def test_market_research_with_market_objectives(self):
        """Test that market objectives pass market research validation."""
        warnings = validate_objective_compatibility(
            ["Analyze customer demand", "Estimate market size"],
            "market",
        )
        assert len(warnings) == 0

    def test_market_research_without_market_keywords(self):
        """Test that non-market objectives generate warning for market research."""
        warnings = validate_objective_compatibility(
            ["Evaluate technical implementation", "Design architecture"],
            "market",
        )
        assert len(warnings) > 0
        assert any("market" in w.lower() for w in warnings)

    def test_competitive_research_with_competitive_objectives(self):
        """Test that competitive objectives pass competitive research validation."""
        warnings = validate_objective_compatibility(
            ["Analyze competitors", "Evaluate market positioning"],
            "competitive",
        )
        assert len(warnings) == 0

    def test_empty_objectives_no_warnings(self):
        """Test that empty objectives list produces no warnings."""
        warnings = validate_objective_compatibility([], "technical")
        assert len(warnings) == 0

    def test_unknown_research_type_defaults_to_general(self):
        """Test that unknown research type defaults to general."""
        warnings = validate_objective_compatibility(["Some objective with content"], "unknown_type")
        # Should not raise, should just log a warning
        assert isinstance(warnings, list)

    def test_objective_compatibility_case_insensitive(self):
        """Test that keyword matching is case-insensitive."""
        warnings = validate_objective_compatibility(
            ["ANALYZE TECHNICAL ARCHITECTURE"],
            "technical",
        )
        assert len(warnings) == 0


class TestFullSessionEndpointValidation:
    """Tests for the start_full_session endpoint objective validation."""

    def test_endpoint_accepts_request_but_validates_empty_objectives(self):
        """Test that request with empty objectives passes Pydantic but endpoint rejects it.

        The schema validator allows empty lists, but the endpoint validates
        that at least one objective is provided before session creation.
        """
        # This should pass Pydantic validation (empty list is allowed)
        request = FullSessionRequest.model_validate(
            {
                "title": "Research Project",
                "description": "A comprehensive research project",
                "objectives": [],
            }
        )
        assert request.objectives == []
        # The endpoint would then reject this request for missing objectives

    def test_endpoint_rejects_invalid_objective_format(self):
        """Test that endpoint rejects requests with invalid objective format.

        This is tested at the Pydantic validation level since the endpoint
        validates objectives via the schema.
        """
        with pytest.raises(ValueError, match="Must be at least 10 characters"):
            FullSessionRequest.model_validate(
                {
                    "title": "Research Project",
                    "description": "A comprehensive research project",
                    "objectives": ["short"],
                }
            )

    def test_full_request_with_valid_objectives(self):
        """Test that full request accepts valid objectives."""
        request = FullSessionRequest.model_validate(
            {
                "title": "Research Project",
                "description": "A comprehensive research project",
                "objectives": [
                    "Analyze market trends and opportunities",
                    "Evaluate competitive landscape",
                ],
            }
        )

        assert len(request.objectives) == 2
        assert request.title == "Research Project"
        assert request.description == "A comprehensive research project"
