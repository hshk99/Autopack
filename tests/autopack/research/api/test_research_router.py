"""Tests for Research API router endpoints.

Note: These tests require RESEARCH_API_MODE=full or AUTOPACK_ENV=development
to access the research endpoints. The router is mounted at /research prefix.
"""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from autopack.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def enable_full_mode():
    """Enable full mode for all tests in this module."""
    with patch.dict(os.environ, {"AUTOPACK_ENV": "development"}):
        yield


@pytest.fixture
def mock_bootstrap_session():
    """Create a mock bootstrap session for testing."""
    session = MagicMock()
    session.session_id = "test-session-123"
    session.is_complete.return_value = True
    session.get_completed_phases.return_value = [
        "market_research",
        "competitive_analysis",
        "technical_feasibility",
    ]
    return session


@pytest.fixture
def mock_orchestrator(mock_bootstrap_session):
    """Create a mock orchestrator with analysis methods."""
    orchestrator = MagicMock()
    orchestrator.get_bootstrap_session.return_value = mock_bootstrap_session

    # Mock cost effectiveness analysis
    orchestrator.run_cost_effectiveness_analysis.return_value = {
        "executive_summary": {
            "total_year_1_cost": 150000,
            "total_year_3_cost": 300000,
            "total_year_5_cost": 450000,
            "primary_cost_drivers": ["development", "infrastructure"],
            "key_recommendations": ["use managed services", "optimize scaling"],
            "cost_confidence": "high",
        },
        "component_analysis": [
            {
                "component": "backend",
                "decision": "build",
                "service": "custom",
                "year_1_cost": 80000,
                "year_5_cost": 200000,
                "vs_build_savings": 0,
                "rationale": "Core differentiator",
            },
            {
                "component": "database",
                "decision": "buy",
                "service": "AWS RDS",
                "year_1_cost": 30000,
                "year_5_cost": 80000,
                "vs_build_savings": 50000,
                "rationale": "Managed service reduces operational burden",
            },
        ],
    }

    # Store build vs buy results to simulate cached state
    orchestrator._build_vs_buy_results = {
        "decisions": [],
        "overall_recommendation": "HYBRID",
        "total_build_cost": None,
        "total_buy_cost": None,
    }

    # Mock followup triggers analysis
    orchestrator.analyze_followup_triggers.return_value = {
        "should_research": True,
        "triggers": [
            {
                "trigger_id": "trig-001",
                "type": "uncertainty",
                "priority": "high",
                "reason": "Market size estimates vary",
                "source_finding": "Different analysts report 5-10B market",
                "research_plan": {
                    "queries": ["market size validation", "TAM estimation"],
                    "target_agent": "market-research",
                    "expected_outcome": "Consolidated market estimate",
                    "estimated_time_minutes": 30,
                },
                "created_at": datetime.utcnow().isoformat() + "Z",
                "addressed": False,
                "callback_results": [],
            }
        ],
        "triggers_selected": 1,
        "total_estimated_time": 30,
    }

    # Mock research state
    orchestrator.get_research_state_summary.return_value = {
        "coverage_metrics": {"market": 0.8, "competition": 0.6, "technology": 0.9},
        "completed_queries": 5,
        "discovered_sources": 12,
        "research_depth": "MEDIUM",
    }

    orchestrator.get_research_gaps.return_value = [
        {
            "gap_id": "gap-001",
            "gap_type": "coverage",
            "category": "market_analysis",
            "description": "Lack of regional market breakdown",
            "priority": "medium",
            "suggested_queries": ["regional market analysis"],
            "identified_at": datetime.utcnow().isoformat() + "Z",
            "addressed_at": None,
            "status": "open",
        }
    ]

    return orchestrator


def test_get_research_sessions():
    """Test GET /research/sessions returns list of sessions."""
    response = client.get("/research/sessions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_research_session():
    """Test POST /research/sessions creates a new session."""
    response = client.post(
        "/research/sessions",
        json={"topic": "AI Research", "description": "Exploring new AI techniques"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["topic"] == "AI Research"
    assert data["description"] == "Exploring new AI techniques"
    assert data["status"] == "active"


def test_get_specific_research_session():
    """Test GET /research/sessions/{id} retrieves a specific session."""
    # First, create a session
    create_response = client.post(
        "/research/sessions",
        json={"topic": "AI Research", "description": "Exploring new AI techniques"},
    )
    session_id = create_response.json()["session_id"]

    # Now, retrieve the specific session
    response = client.get(f"/research/sessions/{session_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id


def test_get_nonexistent_research_session():
    """Test GET /research/sessions/{id} returns 404 for unknown session."""
    response = client.get("/research/sessions/nonexistent")
    assert response.status_code == 404
    assert response.json() == {"detail": "Session not found"}


def test_create_research_session_invalid():
    """Test POST /research/sessions rejects invalid input."""
    response = client.post("/research/sessions", json={"topic": "", "description": ""})
    assert response.status_code == 422
    # Pydantic v2 uses 'string_too_short' instead of 'value_error'
    detail = response.json()["detail"]
    assert any(
        "string_too_short" in d.get("type", "") or "value_error" in d.get("type", "")
        for d in detail
    )


def test_get_api_mode():
    """Test GET /research/mode returns current mode configuration."""
    response = client.get("/research/mode")
    assert response.status_code == 200
    data = response.json()
    assert "mode" in data
    assert "bootstrap_endpoints_enabled" in data
    assert "full_endpoints_enabled" in data
    assert "safety_gates" in data


# =============================================================================
# Tests for new analysis endpoints
# =============================================================================


def test_get_cost_effectiveness_analysis(mock_orchestrator):
    """Test GET /research/full/session/{id}/analysis/cost-effectiveness returns analysis."""
    with (
        patch("autopack.research.api.router._orchestrator", mock_orchestrator),
        patch("autopack.research.api.router._bootstrap_available", True),
    ):
        response = client.get("/research/full/session/test-session-123/analysis/cost-effectiveness")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-session-123"
        assert "executive_summary" in data
        assert data["executive_summary"]["total_year_1_cost"] == 150000
        assert len(data["component_analysis"]) == 2
        assert "generated_at" in data


def test_get_cost_effectiveness_analysis_incomplete_session(mock_orchestrator):
    """Test cost effectiveness analysis returns 400 for incomplete session."""
    mock_orchestrator.get_bootstrap_session.return_value.is_complete.return_value = False

    with (
        patch("autopack.research.api.router._orchestrator", mock_orchestrator),
        patch("autopack.research.api.router._bootstrap_available", True),
    ):
        response = client.get("/research/full/session/test-session-123/analysis/cost-effectiveness")
        assert response.status_code == 400
        assert "not complete" in response.json()["detail"]


def test_get_cost_effectiveness_analysis_session_not_found(mock_orchestrator):
    """Test cost effectiveness analysis returns 404 for nonexistent session."""
    mock_orchestrator.get_bootstrap_session.return_value = None

    with (
        patch("autopack.research.api.router._orchestrator", mock_orchestrator),
        patch("autopack.research.api.router._bootstrap_available", True),
    ):
        response = client.get("/research/full/session/nonexistent/analysis/cost-effectiveness")
        assert response.status_code == 404


def test_get_cost_effectiveness_analysis_with_query_params(mock_orchestrator):
    """Test cost effectiveness analysis with include_optimization_roadmap parameter."""
    with (
        patch("autopack.research.api.router._orchestrator", mock_orchestrator),
        patch("autopack.research.api.router._bootstrap_available", True),
    ):
        response = client.get(
            "/research/full/session/test-session-123/analysis/cost-effectiveness?include_optimization_roadmap=false"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["cost_optimization_roadmap"] == []


def test_get_build_vs_buy_analysis(mock_orchestrator):
    """Test GET /research/full/session/{id}/analysis/build-vs-buy returns analysis."""
    with (
        patch("autopack.research.api.router._orchestrator", mock_orchestrator),
        patch("autopack.research.api.router._bootstrap_available", True),
    ):
        response = client.get("/research/full/session/test-session-123/analysis/build-vs-buy")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-session-123"
        assert "decisions" in data
        assert len(data["decisions"]) >= 0
        assert "generated_at" in data


def test_get_followup_triggers(mock_orchestrator):
    """Test GET /research/full/session/{id}/analysis/followup-triggers returns triggers."""
    with (
        patch("autopack.research.api.router._orchestrator", mock_orchestrator),
        patch("autopack.research.api.router._bootstrap_available", True),
    ):
        response = client.get("/research/full/session/test-session-123/analysis/followup-triggers")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-session-123"
        assert "triggers" in data
        assert data["should_research"] is True
        assert data["triggers_selected"] == 1
        assert "generated_at" in data


def test_get_followup_triggers_with_priority_filter(mock_orchestrator):
    """Test followup triggers with priority_filter parameter."""
    with (
        patch("autopack.research.api.router._orchestrator", mock_orchestrator),
        patch("autopack.research.api.router._bootstrap_available", True),
    ):
        response = client.get(
            "/research/full/session/test-session-123/analysis/followup-triggers?priority_filter=high"
        )
        assert response.status_code == 200
        data = response.json()
        # All returned triggers should match the filter
        for trigger in data["triggers"]:
            assert trigger["priority"] == "high"


def test_get_followup_triggers_with_invalid_priority(mock_orchestrator):
    """Test followup triggers rejects invalid priority filter."""
    with (
        patch("autopack.research.api.router._orchestrator", mock_orchestrator),
        patch("autopack.research.api.router._bootstrap_available", True),
    ):
        response = client.get(
            "/research/full/session/test-session-123/analysis/followup-triggers?priority_filter=invalid"
        )
        assert response.status_code == 400
        assert "Invalid priority filter" in response.json()["detail"]


def test_get_followup_triggers_with_limit(mock_orchestrator):
    """Test followup triggers respects limit parameter."""
    with (
        patch("autopack.research.api.router._orchestrator", mock_orchestrator),
        patch("autopack.research.api.router._bootstrap_available", True),
    ):
        response = client.get(
            "/research/full/session/test-session-123/analysis/followup-triggers?limit=5"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["triggers_selected"] <= 5


def test_get_research_state(mock_orchestrator):
    """Test GET /research/full/session/{id}/analysis/research-state returns state."""
    with (
        patch("autopack.research.api.router._orchestrator", mock_orchestrator),
        patch("autopack.research.api.router._bootstrap_available", True),
    ):
        response = client.get("/research/full/session/test-session-123/analysis/research-state")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-session-123"
        assert "gaps" in data
        assert "gap_count" in data
        assert "coverage_metrics" in data
        assert "generated_at" in data


def test_get_research_state_without_details(mock_orchestrator):
    """Test research state with include_details=false."""
    with (
        patch("autopack.research.api.router._orchestrator", mock_orchestrator),
        patch("autopack.research.api.router._bootstrap_available", True),
    ):
        response = client.get(
            "/research/full/session/test-session-123/analysis/research-state?include_details=false"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["gaps"] == []


def test_get_all_analysis_results(mock_orchestrator):
    """Test GET /research/full/session/{id}/analysis returns aggregated results."""
    with (
        patch("autopack.research.api.router._orchestrator", mock_orchestrator),
        patch("autopack.research.api.router._bootstrap_available", True),
    ):
        response = client.get("/research/full/session/test-session-123/analysis")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-session-123"
        assert "cost_effectiveness" in data
        assert "build_vs_buy" in data
        assert "followup_triggers" in data
        assert "research_state" in data
        assert "generated_at" in data


def test_get_all_analysis_results_selective(mock_orchestrator):
    """Test aggregated analysis with selective inclusion."""
    with (
        patch("autopack.research.api.router._orchestrator", mock_orchestrator),
        patch("autopack.research.api.router._bootstrap_available", True),
    ):
        response = client.get(
            "/research/full/session/test-session-123/analysis?"
            "include_cost_effectiveness=true&include_build_vs_buy=false&"
            "include_followup_triggers=true&include_research_state=false"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["cost_effectiveness"] is not None
        assert data["build_vs_buy"] is None
        assert data["followup_triggers"] is not None
        assert data["research_state"] is None


if __name__ == "__main__":
    pytest.main()
