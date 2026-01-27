"""
Tests for OAuth credential persistence hardening (PR-04 G4).

BUILD-199: Ensures plaintext OAuth credential persistence is disabled
in production by default to prevent accidental secret exposure.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch


class TestOAuthProductionHardening:
    """PR-04 G4: Verify production blocks plaintext credential persistence."""

    def test_production_blocks_plaintext_save(self, tmp_path: Path):
        """In production, saving credentials should fail without explicit opt-in."""
        from autopack.auth.oauth_lifecycle import (
            OAuthCredentialManager,
            OAuthProductionSecurityError,
        )

        with patch.dict(
            os.environ,
            {"AUTOPACK_ENV": "production"},
            clear=False,
        ):
            # Clear the opt-in flag
            os.environ.pop("AUTOPACK_OAUTH_ALLOW_PLAINTEXT_PERSISTENCE", None)

            manager = OAuthCredentialManager(storage_dir=tmp_path / ".creds")

            # Attempting to register (which calls _save) should fail
            with pytest.raises(OAuthProductionSecurityError) as excinfo:
                manager.register_credential(
                    provider="test",
                    client_id="test-client",
                    access_token="secret-token",
                )

            assert "production" in str(excinfo.value).lower()
            assert "plaintext" in str(excinfo.value).lower()

    def test_production_allows_with_explicit_opt_in(self, tmp_path: Path):
        """In production with explicit opt-in, saving should succeed."""
        from autopack.auth.oauth_lifecycle import OAuthCredentialManager

        with patch.dict(
            os.environ,
            {
                "AUTOPACK_ENV": "production",
                "AUTOPACK_OAUTH_ALLOW_PLAINTEXT_PERSISTENCE": "1",
            },
            clear=False,
        ):
            manager = OAuthCredentialManager(storage_dir=tmp_path / ".creds")

            # Should succeed with explicit opt-in
            cred = manager.register_credential(
                provider="test",
                client_id="test-client",
                access_token="secret-token",
            )

            assert cred.provider == "test"
            assert (tmp_path / ".creds" / "credentials.json").exists()

    def test_development_allows_plaintext_save(self, tmp_path: Path):
        """In development mode, plaintext save is allowed by default."""
        from autopack.auth.oauth_lifecycle import OAuthCredentialManager

        with patch.dict(
            os.environ,
            {"AUTOPACK_ENV": "development"},
            clear=False,
        ):
            os.environ.pop("AUTOPACK_OAUTH_ALLOW_PLAINTEXT_PERSISTENCE", None)

            manager = OAuthCredentialManager(storage_dir=tmp_path / ".creds")

            # Should succeed in development
            cred = manager.register_credential(
                provider="test",
                client_id="test-client",
                access_token="secret-token",
            )

            assert cred.provider == "test"
            assert (tmp_path / ".creds" / "credentials.json").exists()

    def test_default_development_mode(self, tmp_path: Path):
        """Default mode (no AUTOPACK_ENV) should allow plaintext save."""
        from autopack.auth.oauth_lifecycle import OAuthCredentialManager

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTOPACK_ENV", None)
            os.environ.pop("AUTOPACK_OAUTH_ALLOW_PLAINTEXT_PERSISTENCE", None)

            manager = OAuthCredentialManager(storage_dir=tmp_path / ".creds")

            # Should succeed with default settings
            cred = manager.register_credential(
                provider="test",
                client_id="test-client",
                access_token="secret-token",
            )

            assert cred.provider == "test"


class TestOAuthSecurityHelpers:
    """Unit tests for OAuth security helper functions."""

    def test_is_production_true(self):
        """_is_production should return True for production mode."""
        from autopack.auth.oauth_lifecycle import _is_production

        with patch.dict(os.environ, {"AUTOPACK_ENV": "production"}, clear=False):
            assert _is_production() is True

    def test_is_production_false(self):
        """_is_production should return False for non-production modes."""
        from autopack.auth.oauth_lifecycle import _is_production

        for mode in ["development", "staging", "test"]:
            with patch.dict(os.environ, {"AUTOPACK_ENV": mode}, clear=False):
                assert _is_production() is False, f"Failed for mode: {mode}"

    def test_is_production_default(self):
        """_is_production should return False when env not set."""
        from autopack.auth.oauth_lifecycle import _is_production

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTOPACK_ENV", None)
            assert _is_production() is False

    def test_plaintext_persistence_allowed_development(self):
        """Plaintext persistence should be allowed in development."""
        from autopack.auth.oauth_lifecycle import _is_plaintext_persistence_allowed

        with patch.dict(os.environ, {"AUTOPACK_ENV": "development"}, clear=False):
            os.environ.pop("AUTOPACK_OAUTH_ALLOW_PLAINTEXT_PERSISTENCE", None)
            assert _is_plaintext_persistence_allowed() is True

    def test_plaintext_persistence_blocked_production(self):
        """Plaintext persistence should be blocked in production by default."""
        from autopack.auth.oauth_lifecycle import _is_plaintext_persistence_allowed

        with patch.dict(os.environ, {"AUTOPACK_ENV": "production"}, clear=False):
            os.environ.pop("AUTOPACK_OAUTH_ALLOW_PLAINTEXT_PERSISTENCE", None)
            assert _is_plaintext_persistence_allowed() is False

    def test_plaintext_persistence_opt_in_production(self):
        """Plaintext persistence should be allowed with explicit opt-in."""
        from autopack.auth.oauth_lifecycle import _is_plaintext_persistence_allowed

        with patch.dict(
            os.environ,
            {
                "AUTOPACK_ENV": "production",
                "AUTOPACK_OAUTH_ALLOW_PLAINTEXT_PERSISTENCE": "1",
            },
            clear=False,
        ):
            assert _is_plaintext_persistence_allowed() is True


class TestOAuthHardeningDocumentation:
    """Verify OAuth hardening is documented."""

    def test_deployment_docs_mention_oauth_hardening(self):
        """DEPLOYMENT.md should document OAuth credential security."""
        docs_path = "docs/DEPLOYMENT.md"

        if not os.path.exists(docs_path):
            pytest.skip("DEPLOYMENT.md not found")

        with open(docs_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for OAuth hardening documentation
        assert "OAUTH" in content.upper() or "oauth" in content.lower(), (
            "DEPLOYMENT.md should mention OAuth credential handling"
        )
