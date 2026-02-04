"""Research API quarantine contract tests (PR8).

Ensures the research API subsystem is properly quarantined:
1. Research endpoints are disabled in production by default
2. Explicit enable flag works (RESEARCH_API_ENABLED)
3. Quarantine status is documented

Contract: Research API is not accidentally exposed in production.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent


class TestResearchAPIQuarantine:
    """Verify research API is quarantined in production."""

    def test_research_router_has_quarantine_guard(self):
        """Research router must have production guard."""
        router_file = REPO_ROOT / "src" / "autopack" / "research" / "api" / "router.py"
        assert router_file.exists(), "Research router not found"

        content = router_file.read_text(encoding="utf-8")

        # Must have guard function
        assert "_is_research_api_enabled" in content, (
            "Research router must have _is_research_api_enabled guard function"
        )
        assert "research_guard" in content, "Research router must have research_guard decorator"

    def test_research_api_disabled_in_production_by_default(self):
        """Research API must be disabled in production by default."""
        from autopack.research.api.router import _is_research_api_enabled

        with patch.dict(os.environ, {"AUTOPACK_ENV": "production"}, clear=False):
            os.environ.pop("RESEARCH_API_ENABLED", None)
            assert _is_research_api_enabled() is False, (
                "Research API must be disabled in production by default"
            )

    def test_research_api_enabled_in_development(self):
        """Research API should be enabled in development by default."""
        from autopack.research.api.router import _is_research_api_enabled

        with patch.dict(os.environ, {"AUTOPACK_ENV": "development"}, clear=False):
            os.environ.pop("RESEARCH_API_ENABLED", None)
            assert _is_research_api_enabled() is True, (
                "Research API should be enabled in development"
            )

    def test_research_api_explicit_enable(self):
        """RESEARCH_API_ENABLED=true should enable even in production."""
        from autopack.research.api.router import _is_research_api_enabled

        with patch.dict(
            os.environ,
            {"AUTOPACK_ENV": "production", "RESEARCH_API_ENABLED": "true"},
        ):
            assert _is_research_api_enabled() is True, (
                "Explicit RESEARCH_API_ENABLED=true should enable API"
            )

    def test_research_api_explicit_disable(self):
        """RESEARCH_API_ENABLED=false should disable even in development."""
        from autopack.research.api.router import _is_research_api_enabled

        with patch.dict(
            os.environ,
            {"AUTOPACK_ENV": "development", "RESEARCH_API_ENABLED": "false"},
        ):
            assert _is_research_api_enabled() is False, (
                "Explicit RESEARCH_API_ENABLED=false should disable API"
            )


class TestResearchEndpointsHaveGuard:
    """Verify all research endpoints have the guard decorator."""

    def test_get_sessions_has_guard(self):
        """GET /research/sessions must have guard."""
        router_file = REPO_ROOT / "src" / "autopack" / "research" / "api" / "router.py"
        content = router_file.read_text(encoding="utf-8")

        # Find get_research_sessions function and check for guard
        assert (
            "@research_guard"
            in content.split("def get_research_sessions")[0].split("@research_router.get")[-1]
        ), "get_research_sessions must have @research_guard decorator"

    def test_create_session_has_guard(self):
        """POST /research/sessions must have guard."""
        router_file = REPO_ROOT / "src" / "autopack" / "research" / "api" / "router.py"
        content = router_file.read_text(encoding="utf-8")

        # Check that create_research_session has guard
        assert (
            "@research_guard"
            in content.split("def create_research_session")[0].split("@research_router.post")[-1]
        ), "create_research_session must have @research_guard decorator"

    def test_get_session_by_id_has_guard(self):
        """GET /research/sessions/{id} must have guard."""
        router_file = REPO_ROOT / "src" / "autopack" / "research" / "api" / "router.py"
        content = router_file.read_text(encoding="utf-8")

        # Check that get_research_session has guard
        # This is the second @research_router.get
        get_sections = content.split("@research_router.get")
        assert len(get_sections) >= 3, "Expected at least 2 GET endpoints"
        # Check the sessions/{session_id} endpoint
        assert "@research_guard" in get_sections[2].split("def ")[0], (
            "get_research_session must have @research_guard decorator"
        )


class TestResearchQuarantineDocumentation:
    """Verify research quarantine is documented."""

    def test_quarantine_doc_exists_or_router_documented(self):
        """Research quarantine must be documented."""
        # Check for either dedicated doc or inline documentation
        quarantine_doc = REPO_ROOT / "docs" / "guides" / "RESEARCH_QUARANTINE.md"
        router_file = REPO_ROOT / "src" / "autopack" / "research" / "api" / "router.py"

        router_content = router_file.read_text(encoding="utf-8")

        # Either have dedicated doc OR have inline documentation
        has_doc = quarantine_doc.exists()
        has_inline_doc = "QUARANTINE" in router_content and "Production" in router_content

        assert has_doc or has_inline_doc, (
            "Research quarantine must be documented either in "
            "docs/guides/RESEARCH_QUARANTINE.md or in router.py docstring"
        )

    def test_router_has_docstring(self):
        """Research router must have module docstring explaining quarantine."""
        router_file = REPO_ROOT / "src" / "autopack" / "research" / "api" / "router.py"
        content = router_file.read_text(encoding="utf-8")

        # Must start with docstring containing QUARANTINE
        assert content.strip().startswith('"""'), "Research router must have module docstring"
        assert "QUARANTINE" in content.split('"""')[1], (
            "Research router docstring must mention QUARANTINE status"
        )


class TestProductionSafety:
    """Verify research API is safe in production."""

    def test_research_endpoints_return_503_in_production(self):
        """Research endpoints must return 503 in production."""
        from fastapi import HTTPException

        from autopack.research.api.router import research_guard

        @research_guard
        async def mock_endpoint():
            return {"ok": True}

        with patch.dict(os.environ, {"AUTOPACK_ENV": "production"}, clear=False):
            os.environ.pop("RESEARCH_API_ENABLED", None)

            import asyncio

            with pytest.raises(HTTPException) as excinfo:
                asyncio.get_event_loop().run_until_complete(mock_endpoint())

            assert excinfo.value.status_code == 503
            assert "quarantined" in excinfo.value.detail.lower()

    def test_project_index_documents_research_api_enabled(self):
        """PROJECT_INDEX.json should document RESEARCH_API_ENABLED."""
        import json

        project_index = REPO_ROOT / "docs" / "PROJECT_INDEX.json"
        with open(project_index, "r", encoding="utf-8") as f:
            data = json.load(f)

        env_vars = data.get("deployment", {}).get("environment_variables", {})

        # Should document the flag or have a note about research API
        env_vars_str = str(env_vars)
        assert "RESEARCH_API_ENABLED" in env_vars_str or "research" in env_vars_str.lower(), (
            "PROJECT_INDEX.json should document RESEARCH_API_ENABLED environment variable"
        )
