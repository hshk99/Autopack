"""Tests for Research API bootstrap endpoints (IMP-RES-006).

Tests the tri-state mode system and bootstrap endpoint behavior:
- ResearchAPIMode enum and mode detection
- Bootstrap guard vs research guard behavior
- Bootstrap endpoints accessibility per mode
"""

import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from autopack.research.api.router import (BootstrapRequest, BootstrapResponse,
                                          BootstrapStatusResponse,
                                          DraftAnchorResponse, ResearchAPIMode,
                                          _get_research_api_mode,
                                          bootstrap_guard, research_guard,
                                          research_router)


class TestResearchAPIMode:
    """Tests for ResearchAPIMode enum and mode detection."""

    def test_mode_enum_values(self):
        """Test that ResearchAPIMode has correct values."""
        assert ResearchAPIMode.DISABLED.value == "disabled"
        assert ResearchAPIMode.BOOTSTRAP_ONLY.value == "bootstrap_only"
        assert ResearchAPIMode.FULL.value == "full"

    def test_mode_enum_from_string(self):
        """Test creating mode from string value."""
        assert ResearchAPIMode("disabled") == ResearchAPIMode.DISABLED
        assert ResearchAPIMode("bootstrap_only") == ResearchAPIMode.BOOTSTRAP_ONLY
        assert ResearchAPIMode("full") == ResearchAPIMode.FULL

    def test_invalid_mode_raises_error(self):
        """Test that invalid mode string raises ValueError."""
        with pytest.raises(ValueError):
            ResearchAPIMode("invalid_mode")


class TestGetResearchAPIMode:
    """Tests for _get_research_api_mode() function."""

    def test_explicit_mode_disabled(self):
        """Test explicit RESEARCH_API_MODE=disabled."""
        with patch.dict(os.environ, {"RESEARCH_API_MODE": "disabled"}, clear=False):
            # Clear any conflicting env vars
            os.environ.pop("RESEARCH_API_ENABLED", None)
            assert _get_research_api_mode() == ResearchAPIMode.DISABLED

    def test_explicit_mode_bootstrap_only(self):
        """Test explicit RESEARCH_API_MODE=bootstrap_only."""
        with patch.dict(os.environ, {"RESEARCH_API_MODE": "bootstrap_only"}, clear=False):
            os.environ.pop("RESEARCH_API_ENABLED", None)
            assert _get_research_api_mode() == ResearchAPIMode.BOOTSTRAP_ONLY

    def test_explicit_mode_full(self):
        """Test explicit RESEARCH_API_MODE=full."""
        with patch.dict(os.environ, {"RESEARCH_API_MODE": "full"}, clear=False):
            os.environ.pop("RESEARCH_API_ENABLED", None)
            assert _get_research_api_mode() == ResearchAPIMode.FULL

    def test_legacy_enabled_true_maps_to_full(self):
        """Test legacy RESEARCH_API_ENABLED=true maps to FULL."""
        with patch.dict(os.environ, {"RESEARCH_API_ENABLED": "true"}, clear=False):
            os.environ.pop("RESEARCH_API_MODE", None)
            assert _get_research_api_mode() == ResearchAPIMode.FULL

    def test_legacy_enabled_false_maps_to_disabled(self):
        """Test legacy RESEARCH_API_ENABLED=false maps to DISABLED."""
        with patch.dict(os.environ, {"RESEARCH_API_ENABLED": "false"}, clear=False):
            os.environ.pop("RESEARCH_API_MODE", None)
            assert _get_research_api_mode() == ResearchAPIMode.DISABLED

    def test_production_default_is_disabled(self):
        """Test production environment defaults to DISABLED."""
        with patch.dict(os.environ, {"AUTOPACK_ENV": "production"}, clear=False):
            os.environ.pop("RESEARCH_API_MODE", None)
            os.environ.pop("RESEARCH_API_ENABLED", None)
            assert _get_research_api_mode() == ResearchAPIMode.DISABLED

    def test_development_default_is_full(self):
        """Test development environment defaults to FULL."""
        with patch.dict(os.environ, {"AUTOPACK_ENV": "development"}, clear=False):
            os.environ.pop("RESEARCH_API_MODE", None)
            os.environ.pop("RESEARCH_API_ENABLED", None)
            assert _get_research_api_mode() == ResearchAPIMode.FULL

    def test_explicit_mode_overrides_legacy(self):
        """Test RESEARCH_API_MODE takes priority over RESEARCH_API_ENABLED."""
        with patch.dict(
            os.environ,
            {"RESEARCH_API_MODE": "bootstrap_only", "RESEARCH_API_ENABLED": "true"},
            clear=False,
        ):
            assert _get_research_api_mode() == ResearchAPIMode.BOOTSTRAP_ONLY


class TestResearchGuard:
    """Tests for research_guard decorator."""

    @pytest.mark.asyncio
    async def test_research_guard_allows_in_full_mode(self):
        """Test research_guard allows access in FULL mode."""

        @research_guard
        async def protected_endpoint():
            return "success"

        with patch.dict(os.environ, {"RESEARCH_API_MODE": "full"}, clear=False):
            result = await protected_endpoint()
            assert result == "success"

    @pytest.mark.asyncio
    async def test_research_guard_blocks_in_disabled_mode(self):
        """Test research_guard blocks access in DISABLED mode."""

        @research_guard
        async def protected_endpoint():
            return "success"

        with patch.dict(os.environ, {"RESEARCH_API_MODE": "disabled"}, clear=False):
            with pytest.raises(HTTPException) as exc_info:
                await protected_endpoint()
            assert exc_info.value.status_code == 503
            assert "disabled" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_research_guard_blocks_in_bootstrap_only_mode(self):
        """Test research_guard blocks access in BOOTSTRAP_ONLY mode."""

        @research_guard
        async def protected_endpoint():
            return "success"

        with patch.dict(os.environ, {"RESEARCH_API_MODE": "bootstrap_only"}, clear=False):
            with pytest.raises(HTTPException) as exc_info:
                await protected_endpoint()
            assert exc_info.value.status_code == 503
            assert "bootstrap_only" in exc_info.value.detail


class TestBootstrapGuard:
    """Tests for bootstrap_guard decorator."""

    @pytest.mark.asyncio
    async def test_bootstrap_guard_allows_in_full_mode(self):
        """Test bootstrap_guard allows access in FULL mode."""

        @bootstrap_guard
        async def bootstrap_endpoint():
            return "success"

        with patch.dict(os.environ, {"RESEARCH_API_MODE": "full"}, clear=False):
            result = await bootstrap_endpoint()
            assert result == "success"

    @pytest.mark.asyncio
    async def test_bootstrap_guard_allows_in_bootstrap_only_mode(self):
        """Test bootstrap_guard allows access in BOOTSTRAP_ONLY mode."""

        @bootstrap_guard
        async def bootstrap_endpoint():
            return "success"

        with patch.dict(os.environ, {"RESEARCH_API_MODE": "bootstrap_only"}, clear=False):
            result = await bootstrap_endpoint()
            assert result == "success"

    @pytest.mark.asyncio
    async def test_bootstrap_guard_blocks_in_disabled_mode(self):
        """Test bootstrap_guard blocks access in DISABLED mode."""

        @bootstrap_guard
        async def bootstrap_endpoint():
            return "success"

        with patch.dict(os.environ, {"RESEARCH_API_MODE": "disabled"}, clear=False):
            with pytest.raises(HTTPException) as exc_info:
                await bootstrap_endpoint()
            assert exc_info.value.status_code == 503
            assert "disabled" in exc_info.value.detail


class TestBootstrapSchemas:
    """Tests for bootstrap request/response schemas."""

    def test_bootstrap_request_validation(self):
        """Test BootstrapRequest validates required fields."""
        request = BootstrapRequest(idea_text="Build a task management app")
        assert request.idea_text == "Build a task management app"
        assert request.use_cache is True  # default
        assert request.parallel is True  # default

    def test_bootstrap_request_with_options(self):
        """Test BootstrapRequest with custom options."""
        request = BootstrapRequest(
            idea_text="Build a task management app",
            use_cache=False,
            parallel=False,
        )
        assert request.use_cache is False
        assert request.parallel is False

    def test_bootstrap_response_fields(self):
        """Test BootstrapResponse has all required fields."""
        response = BootstrapResponse(
            session_id="test-123",
            status="completed",
            message="Session completed successfully",
        )
        assert response.session_id == "test-123"
        assert response.status == "completed"
        assert response.message == "Session completed successfully"

    def test_bootstrap_status_response_fields(self):
        """Test BootstrapStatusResponse has all required fields."""
        response = BootstrapStatusResponse(
            session_id="test-123",
            status="in_progress",
            current_phase="market_research",
            is_complete=False,
            completed_phases=["initialized"],
            failed_phases=[],
            synthesis=None,
        )
        assert response.session_id == "test-123"
        assert response.is_complete is False
        assert "initialized" in response.completed_phases

    def test_draft_anchor_response_fields(self):
        """Test DraftAnchorResponse has all required fields."""
        response = DraftAnchorResponse(
            session_id="test-123",
            anchor={"project_id": "test"},
            clarifying_questions=["What is the main goal?"],
            confidence_report={"north_star": {"score": 0.8}},
        )
        assert response.session_id == "test-123"
        assert response.anchor["project_id"] == "test"
        assert len(response.clarifying_questions) == 1


class TestModeEndpoint:
    """Tests for the /mode diagnostic endpoint."""

    def test_mode_endpoint_in_disabled_mode(self):
        """Test /mode endpoint reports DISABLED mode correctly."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(research_router, prefix="/research")
        client = TestClient(app)

        with patch.dict(os.environ, {"RESEARCH_API_MODE": "disabled"}, clear=False):
            response = client.get("/research/mode")
            assert response.status_code == 200
            data = response.json()
            assert data["mode"] == "disabled"
            assert data["bootstrap_endpoints_enabled"] is False
            assert data["full_endpoints_enabled"] is False

    def test_mode_endpoint_in_bootstrap_only_mode(self):
        """Test /mode endpoint reports BOOTSTRAP_ONLY mode correctly."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(research_router, prefix="/research")
        client = TestClient(app)

        with patch.dict(os.environ, {"RESEARCH_API_MODE": "bootstrap_only"}, clear=False):
            response = client.get("/research/mode")
            assert response.status_code == 200
            data = response.json()
            assert data["mode"] == "bootstrap_only"
            assert data["bootstrap_endpoints_enabled"] is True
            assert data["full_endpoints_enabled"] is False

    def test_mode_endpoint_in_full_mode(self):
        """Test /mode endpoint reports FULL mode correctly."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(research_router, prefix="/research")
        client = TestClient(app)

        with patch.dict(os.environ, {"RESEARCH_API_MODE": "full"}, clear=False):
            response = client.get("/research/mode")
            assert response.status_code == 200
            data = response.json()
            assert data["mode"] == "full"
            assert data["bootstrap_endpoints_enabled"] is True
            assert data["full_endpoints_enabled"] is True


class TestQuarantinedEndpointsRespectMode:
    """Tests that quarantined (non-bootstrap) endpoints respect mode."""

    def test_sessions_endpoint_blocked_in_bootstrap_only(self):
        """Test /sessions endpoint is blocked in BOOTSTRAP_ONLY mode."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(research_router, prefix="/research")
        client = TestClient(app)

        with patch.dict(os.environ, {"RESEARCH_API_MODE": "bootstrap_only"}, clear=False):
            response = client.get("/research/sessions")
            assert response.status_code == 503
            assert "bootstrap_only" in response.json()["detail"]

    def test_sessions_endpoint_allowed_in_full(self):
        """Test /sessions endpoint is allowed in FULL mode."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(research_router, prefix="/research")
        client = TestClient(app)

        with patch.dict(os.environ, {"RESEARCH_API_MODE": "full"}, clear=False):
            response = client.get("/research/sessions")
            assert response.status_code == 200


class TestBootstrapEndpointsRespectMode:
    """Tests that bootstrap endpoints respect mode correctly."""

    def test_bootstrap_post_blocked_in_disabled(self):
        """Test POST /bootstrap is blocked in DISABLED mode."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(research_router, prefix="/research")
        client = TestClient(app)

        with patch.dict(os.environ, {"RESEARCH_API_MODE": "disabled"}, clear=False):
            response = client.post(
                "/research/bootstrap",
                json={"idea_text": "Build a task management app"},
            )
            assert response.status_code == 503
            assert "disabled" in response.json()["detail"]

    def test_bootstrap_status_blocked_in_disabled(self):
        """Test GET /bootstrap/{id}/status is blocked in DISABLED mode."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(research_router, prefix="/research")
        client = TestClient(app)

        with patch.dict(os.environ, {"RESEARCH_API_MODE": "disabled"}, clear=False):
            response = client.get("/research/bootstrap/test-123/status")
            assert response.status_code == 503

    def test_bootstrap_anchor_blocked_in_disabled(self):
        """Test GET /bootstrap/{id}/draft_anchor is blocked in DISABLED mode."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(research_router, prefix="/research")
        client = TestClient(app)

        with patch.dict(os.environ, {"RESEARCH_API_MODE": "disabled"}, clear=False):
            response = client.get("/research/bootstrap/test-123/draft_anchor")
            assert response.status_code == 503


class TestBootstrapEndpointValidation:
    """Tests for bootstrap endpoint input validation."""

    def test_bootstrap_rejects_short_idea_text(self):
        """Test POST /bootstrap rejects idea_text < 10 characters."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(research_router, prefix="/research")
        client = TestClient(app)

        with patch.dict(os.environ, {"RESEARCH_API_MODE": "bootstrap_only"}, clear=False):
            response = client.post(
                "/research/bootstrap",
                json={"idea_text": "short"},
            )
            # Should be 400 for validation error
            assert response.status_code == 400
            assert "10 characters" in response.json()["detail"]

    def test_bootstrap_rejects_empty_idea_text(self):
        """Test POST /bootstrap rejects empty idea_text."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(research_router, prefix="/research")
        client = TestClient(app)

        with patch.dict(os.environ, {"RESEARCH_API_MODE": "bootstrap_only"}, clear=False):
            response = client.post(
                "/research/bootstrap",
                json={"idea_text": ""},
            )
            assert response.status_code == 400


class TestProductionDefaults:
    """Tests that production has safe defaults."""

    def test_production_defaults_to_disabled(self):
        """Test production environment defaults to DISABLED mode."""
        with patch.dict(os.environ, {"AUTOPACK_ENV": "production"}, clear=False):
            os.environ.pop("RESEARCH_API_MODE", None)
            os.environ.pop("RESEARCH_API_ENABLED", None)
            mode = _get_research_api_mode()
            assert mode == ResearchAPIMode.DISABLED

    def test_bootstrap_only_preserves_quarantine_for_non_bootstrap(self):
        """Test BOOTSTRAP_ONLY mode still blocks non-bootstrap endpoints."""
        with patch.dict(os.environ, {"RESEARCH_API_MODE": "bootstrap_only"}, clear=False):
            mode = _get_research_api_mode()
            assert mode == ResearchAPIMode.BOOTSTRAP_ONLY
            # Non-bootstrap endpoints should still be blocked
            # (verified by research_guard behavior in other tests)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
