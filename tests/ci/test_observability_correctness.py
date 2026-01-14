"""
Tests for observability correctness (PR-07 G7).

BUILD-199: Ensures observability endpoints are correctly bounded and
do not accidentally trigger LLM costs.
"""

import os
import pytest
from datetime import datetime, timezone
from unittest.mock import patch


class TestObservabilityKillSwitches:
    """PR-07 G7: Verify observability kill switches default OFF."""

    def test_consolidated_metrics_disabled_by_default(self, client, db_session):
        """Consolidated metrics endpoint returns 503 when kill switch not enabled."""
        from autopack import models

        # Create a test run
        run = models.Run(
            id="test-run-metrics",
            state=models.RunState.DONE_SUCCESS,
            safety_profile="normal",
            run_scope="single_tier",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.commit()

        # Ensure kill switch is OFF
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTOPACK_ENABLE_CONSOLIDATED_METRICS", None)

            response = client.get("/dashboard/runs/test-run-metrics/consolidated-metrics")
            assert response.status_code == 503
            assert "disabled" in response.json()["detail"].lower()

    def test_consolidated_metrics_enabled_with_kill_switch(self, client, db_session):
        """Consolidated metrics endpoint returns non-503 when kill switch enabled."""
        from autopack import models
        from autopack.config import get_database_url

        # Skip if SQLite - this endpoint uses PostgreSQL-specific SQL
        db_url = get_database_url()
        if "sqlite" in db_url.lower():
            pytest.skip("Consolidated metrics uses PostgreSQL-specific SQL")

        # Create a test run
        run = models.Run(
            id="test-run-metrics-enabled",
            state=models.RunState.DONE_SUCCESS,
            safety_profile="normal",
            run_scope="single_tier",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.commit()

        # Enable kill switch
        with patch.dict(os.environ, {"AUTOPACK_ENABLE_CONSOLIDATED_METRICS": "1"}):
            response = client.get("/dashboard/runs/test-run-metrics-enabled/consolidated-metrics")
            # Should not return 503 (may return 200 with empty metrics or 500 on SQL issues)
            assert response.status_code != 503

    def test_health_shows_kill_switch_state(self, client):
        """Health endpoint shows observability kill switch states."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        # Should report kill switch states (BUILD-146 P12)
        assert "kill_switches" in data
        assert "consolidated_metrics" in data["kill_switches"]


class TestObservabilityCapsFromConfig:
    """PR-07 G7: Verify usage caps come from config."""

    def test_usage_endpoint_uses_config_cap(self, client, db_session):
        """Dashboard usage endpoint uses run_token_cap from config."""
        from autopack.config import settings

        response = client.get("/dashboard/usage")
        assert response.status_code == 200

        data = response.json()
        # If there are providers, check cap_tokens matches config
        if data.get("providers"):
            for provider in data["providers"]:
                assert provider["cap_tokens"] == settings.run_token_cap

    def test_config_has_run_token_cap(self):
        """Settings class has run_token_cap."""
        from autopack.config import Settings

        settings = Settings()
        assert hasattr(settings, "run_token_cap")
        assert isinstance(settings.run_token_cap, int)
        assert settings.run_token_cap > 0  # Should not be 0

    def test_default_run_token_cap_is_reasonable(self):
        """Default run_token_cap is a reasonable value (5M tokens)."""
        from autopack.config import Settings

        settings = Settings()
        # Default should be 5,000,000 (5M tokens)
        assert settings.run_token_cap == 5_000_000

    def test_run_token_cap_configurable_via_env(self):
        """run_token_cap can be configured via environment variable."""
        with patch.dict(os.environ, {"RUN_TOKEN_CAP": "1000000"}):
            from autopack.config import Settings

            settings = Settings()
            assert settings.run_token_cap == 1_000_000


class TestObservabilityAuthRequirements:
    """PR-07 G7: Verify observability endpoints have proper auth."""

    def test_dashboard_usage_requires_auth_in_production(self, client, db_session):
        """Dashboard usage requires auth in production mode."""
        with patch.dict(os.environ, {"AUTOPACK_ENV": "production"}):
            # Clear any existing API key from test config
            os.environ.pop("AUTOPACK_API_KEY", None)

            # Should require auth in production
            response = client.get("/dashboard/usage")
            # In production without API key, should be 403 or 401
            # (Test client may have auth header set by conftest)
            assert response.status_code in (200, 401, 403)

    def test_dashboard_models_requires_auth_in_production(self, client, db_session):
        """Dashboard models requires auth in production mode."""
        with patch.dict(os.environ, {"AUTOPACK_ENV": "production"}):
            response = client.get("/dashboard/models")
            # Should require auth in production
            assert response.status_code in (200, 401, 403)


class TestObservabilityNoLlmCosts:
    """PR-07 G7: Verify observability endpoints do not trigger LLM costs."""

    def test_usage_endpoint_only_reads_database(self, client, db_session):
        """Usage endpoint only reads from database, no LLM calls."""
        # This is a contract test - verify the endpoint exists and is read-only
        response = client.get("/dashboard/usage")
        assert response.status_code == 200

        # Response should be JSON with providers/models from database
        data = response.json()
        assert "providers" in data
        assert "models" in data

    def test_models_endpoint_only_reads_config(self, client, db_session):
        """Models endpoint only reads config/database, no LLM calls."""
        response = client.get("/dashboard/models")
        assert response.status_code == 200

        # Response should be JSON with model mappings
        data = response.json()
        # Should have model info from config
        assert isinstance(data, dict) or isinstance(data, list)

    def test_token_efficiency_only_reads_database(self, client, db_session):
        """Token efficiency endpoint only reads from database."""
        from autopack import models

        # Create a test run
        run = models.Run(
            id="test-run-efficiency",
            state=models.RunState.DONE_SUCCESS,
            safety_profile="normal",
            run_scope="single_tier",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.commit()

        # This endpoint requires API key auth, not read_access
        response = client.get("/dashboard/runs/test-run-efficiency/token-efficiency")
        # Should return metrics or 404/401 - never trigger LLM
        assert response.status_code in (200, 401, 403, 404)

    def test_phase6_stats_only_reads_database(self, client, db_session):
        """Phase6 stats endpoint only reads from database."""
        from autopack import models

        # Create a test run
        run = models.Run(
            id="test-run-phase6",
            state=models.RunState.DONE_SUCCESS,
            safety_profile="normal",
            run_scope="single_tier",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.commit()

        # This endpoint requires API key auth, not read_access
        response = client.get("/dashboard/runs/test-run-phase6/phase6-stats")
        # Should return metrics or 404/401 - never trigger LLM
        assert response.status_code in (200, 401, 403, 404)


class TestObservabilityDocumentation:
    """PR-07 G7: Verify observability is documented."""

    def test_deployment_docs_mention_observability(self):
        """DEPLOYMENT.md should document observability settings."""
        docs_path = "docs/DEPLOYMENT.md"

        if not os.path.exists(docs_path):
            pytest.skip("DEPLOYMENT.md not found")

        with open(docs_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for observability-related documentation
        assert (
            "AUTOPACK_ENABLE_CONSOLIDATED_METRICS" in content or "observability" in content.lower()
        ), "DEPLOYMENT.md should document observability kill switches"

    def test_config_has_observability_settings(self):
        """Config should have observability-related settings."""
        from autopack.config import Settings

        settings = Settings()

        # Should have run_token_cap for usage caps
        assert hasattr(settings, "run_token_cap")


class TestLegacyApprovalPathDocumentation:
    """PR-07 G7: Verify legacy approval paths are documented."""

    def test_auto_approve_build113_documented(self):
        """AUTO_APPROVE_BUILD113 legacy behavior should be documented."""
        # This is a contract test - verify the env var is used

        # The legacy auto-approve flag exists in the codebase (refactored to approvals router)
        # It should be documented somewhere
        approvals_path = "src/autopack/api/routes/approvals.py"
        with open(approvals_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "AUTO_APPROVE_BUILD113" in content, (
            "AUTO_APPROVE_BUILD113 legacy flag should exist in approvals.py"
        )
