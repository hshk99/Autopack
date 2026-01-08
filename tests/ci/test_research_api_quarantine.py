"""Research API quarantine tests (PR4 - P1-RESEARCH-API-001).

Contract tests ensuring:
1. Research API is NOT mounted in production mode by default
2. Research API IS mounted in dev/test mode by default
3. Feature flag AUTOPACK_ENABLE_RESEARCH_API can override behavior
4. Production posture is clear and documented

Security contract: Don't ship mock state via production API.
"""

import os
import pytest


class TestResearchApiQuarantine:
    """Contract tests for research API feature flag."""

    def test_research_api_not_mounted_in_production_default(self):
        """Research API should NOT be mounted in production by default."""
        # Save original values
        old_testing = os.environ.pop("TESTING", None)
        old_env = os.environ.get("AUTOPACK_ENV")
        old_flag = os.environ.pop("AUTOPACK_ENABLE_RESEARCH_API", None)

        try:
            os.environ["AUTOPACK_ENV"] = "production"
            # Note: NOT setting AUTOPACK_ENABLE_RESEARCH_API

            # Force reimport to pick up new env vars
            import importlib
            import sys
            # Remove cached modules
            modules_to_remove = [k for k in sys.modules.keys() if 'autopack.main' in k]
            for mod in modules_to_remove:
                del sys.modules[mod]

            from autopack.main import app
            from fastapi.testclient import TestClient

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/research/sessions")

            # Should return 404 (route not found) in production
            assert response.status_code == 404, (
                f"Research API should not be mounted in production, got {response.status_code}"
            )

        finally:
            # Restore environment
            if old_testing:
                os.environ["TESTING"] = old_testing
            if old_env:
                os.environ["AUTOPACK_ENV"] = old_env
            else:
                os.environ.pop("AUTOPACK_ENV", None)
            if old_flag:
                os.environ["AUTOPACK_ENABLE_RESEARCH_API"] = old_flag

    def test_research_api_mounted_in_dev_mode(self):
        """Research API should be mounted in development mode."""
        # Save original values
        old_testing = os.environ.get("TESTING")
        old_env = os.environ.get("AUTOPACK_ENV")
        old_flag = os.environ.pop("AUTOPACK_ENABLE_RESEARCH_API", None)

        try:
            os.environ["TESTING"] = "1"
            os.environ.pop("AUTOPACK_ENV", None)  # Ensure dev mode

            # Force reimport to pick up new env vars
            import sys
            modules_to_remove = [k for k in sys.modules.keys() if 'autopack.main' in k]
            for mod in modules_to_remove:
                del sys.modules[mod]

            from autopack.main import app
            from fastapi.testclient import TestClient

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/research/sessions")

            # Should return 200 (empty list) in dev mode
            assert response.status_code == 200, (
                f"Research API should be mounted in dev mode, got {response.status_code}"
            )
        finally:
            # Restore environment
            if old_testing:
                os.environ["TESTING"] = old_testing
            if old_env:
                os.environ["AUTOPACK_ENV"] = old_env
            if old_flag:
                os.environ["AUTOPACK_ENABLE_RESEARCH_API"] = old_flag

    def test_research_api_can_be_enabled_in_production(self):
        """Feature flag can explicitly enable research API in production."""
        # Save original values
        old_testing = os.environ.pop("TESTING", None)
        old_env = os.environ.get("AUTOPACK_ENV")
        old_flag = os.environ.get("AUTOPACK_ENABLE_RESEARCH_API")

        try:
            os.environ["AUTOPACK_ENV"] = "production"
            os.environ["AUTOPACK_ENABLE_RESEARCH_API"] = "true"

            # Force reimport to pick up new env vars
            import importlib
            import sys
            modules_to_remove = [k for k in sys.modules.keys() if 'autopack.main' in k]
            for mod in modules_to_remove:
                del sys.modules[mod]

            from autopack.main import app
            from fastapi.testclient import TestClient

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/research/sessions")

            # Should return 200 when explicitly enabled
            assert response.status_code == 200, (
                f"Research API should be accessible when enabled, got {response.status_code}"
            )

        finally:
            # Restore environment
            if old_testing:
                os.environ["TESTING"] = old_testing
            if old_env:
                os.environ["AUTOPACK_ENV"] = old_env
            else:
                os.environ.pop("AUTOPACK_ENV", None)
            if old_flag:
                os.environ["AUTOPACK_ENABLE_RESEARCH_API"] = old_flag
            else:
                os.environ.pop("AUTOPACK_ENABLE_RESEARCH_API", None)


class TestResearchApiDocumentation:
    """Verify research API quarantine is documented."""

    def test_main_py_documents_research_api_risk(self):
        """main.py should document that research API uses mock state."""
        from pathlib import Path

        main_py = Path("src/autopack/main.py")
        content = main_py.read_text(encoding="utf-8")

        # Check for documentation of the risk
        assert "mock" in content.lower() or "in-memory" in content.lower(), (
            "main.py should document that research API uses mock/in-memory state"
        )
        assert "production-safe" in content.lower() or "not production" in content.lower(), (
            "main.py should document that research API is not production-safe"
        )

    def test_feature_flag_documented(self):
        """AUTOPACK_ENABLE_RESEARCH_API flag should be documented in code."""
        from pathlib import Path

        main_py = Path("src/autopack/main.py")
        content = main_py.read_text(encoding="utf-8")

        assert "AUTOPACK_ENABLE_RESEARCH_API" in content, (
            "main.py should reference AUTOPACK_ENABLE_RESEARCH_API flag"
        )


class TestResearchApiMockWarning:
    """Verify research API mock behavior is clear."""

    def test_research_router_uses_mock_database(self):
        """Research router should clearly use mock/in-memory storage."""
        from pathlib import Path

        router_py = Path("src/autopack/research/api/router.py")
        content = router_py.read_text(encoding="utf-8")

        # Should have clear indication of mock storage
        assert "mock" in content.lower() or "research_sessions = []" in content, (
            "Research router should clearly indicate mock/in-memory storage"
        )

    def test_research_sessions_list_is_global(self):
        """Research sessions should be a global list (indicating mock state)."""
        from autopack.research.api.router import research_sessions

        # Should be a list (not a DB session or persistent storage)
        assert isinstance(research_sessions, list), (
            "research_sessions should be a list (mock in-memory storage)"
        )
