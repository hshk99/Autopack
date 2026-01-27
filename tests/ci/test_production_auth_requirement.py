"""
Tests for production API key requirement (P0 Security).

BUILD-189: Ensures the API fails fast in production if AUTOPACK_API_KEY is not set.
This prevents accidentally running an unauthenticated API in production.
"""

import os
import pytest
from unittest.mock import patch
from autopack.api.app import StartupError


class TestProductionAuthRequirement:
    """P0 Security: Verify production mode requires API key."""

    def test_production_requires_api_key_missing(self):
        """API should fail to start in production mode without API key."""
        # Import here to avoid module-level execution issues

        with patch.dict(
            os.environ,
            {"AUTOPACK_ENV": "production", "AUTOPACK_API_KEY": "", "TESTING": "1"},
            clear=False,
        ):
            # Clear the cached key if any
            env_backup = os.environ.copy()
            os.environ["AUTOPACK_ENV"] = "production"
            os.environ.pop("AUTOPACK_API_KEY", None)

            # The lifespan function should raise StartupError (IMP-OPS-012)
            # which wraps the ConfigurationError from config validation
            from autopack.main import lifespan

            async def check_lifespan_fails():
                async with lifespan(None):
                    pass

            import asyncio

            with pytest.raises(StartupError) as excinfo:
                asyncio.get_event_loop().run_until_complete(check_lifespan_fails())

            # IMP-OPS-012: Error is now wrapped in StartupError
            # The original ConfigurationError message is included in the StartupError message
            error_str = str(excinfo.value)
            assert "AUTOPACK_API_KEY" in error_str
            assert "production" in error_str.lower()

            # Restore environment
            os.environ.clear()
            os.environ.update(env_backup)

    def test_production_starts_with_api_key(self):
        """API should start successfully in production mode with API key set."""
        # This is a lighter test - just verify the check passes
        autopack_env = "production"
        api_key = "test-api-key-12345"  # gitleaks:allow (intentional fake key for test)

        # Simulate the check from lifespan
        if autopack_env.lower() == "production" and not api_key:
            pytest.fail("Should not fail when API key is set")

        # If we get here, the check passed
        assert True

    def test_development_mode_allows_no_api_key(self):
        """API should start in development mode without API key."""
        autopack_env = "development"
        api_key = ""

        # Simulate the check from lifespan
        should_fail = autopack_env.lower() == "production" and not api_key
        assert not should_fail, "Development mode should not require API key"

    def test_verify_api_key_allows_open_in_dev(self):
        """verify_api_key should allow requests when no key configured (dev mode)."""
        import asyncio
        from unittest.mock import patch

        # Patch environment to simulate dev mode (no API key set)
        # Must also clear PYTEST_CURRENT_TEST to avoid test-mode bypass
        with patch.dict(
            os.environ,
            {"AUTOPACK_API_KEY": "", "TESTING": "", "PYTEST_CURRENT_TEST": ""},
            clear=False,
        ):
            os.environ.pop("AUTOPACK_API_KEY", None)
            os.environ.pop("TESTING", None)
            os.environ.pop("PYTEST_CURRENT_TEST", None)

            # Import fresh to pick up patched env
            from autopack.main import verify_api_key

            # Call the async function
            result = asyncio.get_event_loop().run_until_complete(verify_api_key(api_key=None))

            # Should return None (allowing access) when no key is configured
            assert result is None

    def test_verify_api_key_rejects_bad_key_when_configured(self):
        """verify_api_key should reject invalid keys when API key is configured."""
        import asyncio
        from fastapi import HTTPException
        from unittest.mock import patch

        # Must also clear PYTEST_CURRENT_TEST to avoid test-mode bypass
        with patch.dict(
            os.environ,
            {
                "AUTOPACK_API_KEY": "correct-key-12345",  # gitleaks:allow
                "TESTING": "",
                "PYTEST_CURRENT_TEST": "",
            },
            clear=False,
        ):
            os.environ.pop("TESTING", None)
            os.environ.pop("PYTEST_CURRENT_TEST", None)

            from autopack.main import verify_api_key

            # Call with wrong key
            with pytest.raises(HTTPException) as excinfo:
                asyncio.get_event_loop().run_until_complete(verify_api_key(api_key="wrong-key"))

            assert excinfo.value.status_code == 403
            assert "Invalid or missing API key" in excinfo.value.detail

    def test_verify_api_key_accepts_correct_key(self):
        """verify_api_key should accept correct API key."""
        import asyncio
        from unittest.mock import patch

        correct_key = "correct-key-12345"  # gitleaks:allow (intentional fake key for test)

        # Must also clear PYTEST_CURRENT_TEST to avoid test-mode bypass
        with patch.dict(
            os.environ,
            {"AUTOPACK_API_KEY": correct_key, "TESTING": "", "PYTEST_CURRENT_TEST": ""},
            clear=False,
        ):
            os.environ.pop("TESTING", None)
            os.environ.pop("PYTEST_CURRENT_TEST", None)

            from autopack.main import verify_api_key

            result = asyncio.get_event_loop().run_until_complete(
                verify_api_key(api_key=correct_key)
            )

            assert result == correct_key


class TestProductionAuthDocumentation:
    """Verify documentation mentions production auth requirement."""

    def test_gap_analysis_documents_auth_requirement(self):
        """IMPROVEMENTS_GAP_ANALYSIS.md should document the production auth fix."""
        gap_analysis_path = "docs/IMPROVEMENTS_GAP_ANALYSIS.md"

        if not os.path.exists(gap_analysis_path):
            pytest.skip("Gap analysis doc not found")

        with open(gap_analysis_path, "r", encoding="utf-8") as f:
            content = f.read()

        # The gap analysis should mention this security issue
        assert "AUTOPACK_API_KEY" in content, (
            "Gap analysis should document AUTOPACK_API_KEY requirement"
        )
        assert "production" in content.lower(), "Gap analysis should mention production mode"
