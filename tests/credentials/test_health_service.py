"""Tests for credential health service.

Validates gap analysis requirement 6.8:
- Non-secret credential status visibility
- Health endpoint for dashboard display
"""

import os
from unittest.mock import patch

from autopack.credentials import CredentialHealthService, CredentialStatus, ProviderCredential


class TestProviderCredential:
    """Test ProviderCredential model."""

    def test_healthy_credential(self):
        """Healthy credential reports correctly."""
        cred = ProviderCredential(
            provider="youtube",
            environment="prod",
            status=CredentialStatus.PRESENT,
        )
        assert cred.is_healthy() is True
        assert cred.needs_attention() is False

    def test_missing_credential(self):
        """Missing credential needs attention."""
        cred = ProviderCredential(
            provider="etsy",
            environment="prod",
            status=CredentialStatus.MISSING,
        )
        assert cred.is_healthy() is False
        assert cred.needs_attention() is True

    def test_expired_credential(self):
        """Expired credential is detected."""
        cred = ProviderCredential(
            provider="shopify",
            environment="prod",
            status=CredentialStatus.EXPIRED,
        )
        assert cred.is_expired() is True
        assert cred.needs_attention() is True

    def test_to_dict_no_secrets(self):
        """to_dict() never exposes secrets."""
        cred = ProviderCredential(
            provider="alpaca",
            environment="prod",
            status=CredentialStatus.PRESENT,
            scopes=["trading", "data"],
        )
        result = cred.to_dict()

        # Should have expected keys
        assert "provider" in result
        assert "status" in result
        assert "is_healthy" in result

        # Should NOT have any secret-looking keys
        assert "api_key" not in result
        assert "secret" not in result
        assert "token" not in result
        assert "password" not in result


class TestCredentialHealthService:
    """Test CredentialHealthService."""

    def test_check_missing_provider(self):
        """Missing credentials are detected."""
        service = CredentialHealthService(environment="prod")

        # Clear any existing env vars
        with patch.dict(os.environ, {}, clear=True):
            cred = service.check_provider("youtube")
            assert cred.status == CredentialStatus.MISSING
            assert cred.needs_attention() is True

    def test_check_present_provider(self):
        """Present credentials are detected."""
        service = CredentialHealthService(environment="prod")

        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "fake-key-for-test"}):
            cred = service.check_provider("youtube")
            assert cred.status == CredentialStatus.PRESENT
            assert cred.is_healthy() is True

    def test_unknown_provider(self):
        """Unknown provider returns UNKNOWN status."""
        service = CredentialHealthService(environment="prod")
        cred = service.check_provider("unknown_provider_xyz")

        assert cred.status == CredentialStatus.UNKNOWN
        assert "Unknown provider" in cred.validation_error

    def test_check_all_providers(self):
        """Check all providers returns list."""
        service = CredentialHealthService(environment="prod")
        credentials = service.check_all_providers()

        assert isinstance(credentials, list)
        assert len(credentials) > 0
        assert all(isinstance(c, ProviderCredential) for c in credentials)

    def test_health_summary_structure(self):
        """Health summary has expected structure."""
        service = CredentialHealthService(environment="prod")
        summary = service.get_health_summary()

        assert "environment" in summary
        assert "checked_at" in summary
        assert "total_providers" in summary
        assert "healthy_count" in summary
        assert "needs_attention_count" in summary
        assert "overall_status" in summary
        assert "providers" in summary
        assert "attention_required" in summary

        # Status should be "degraded" when some creds are missing
        # (since we're running without real credentials)
        assert summary["overall_status"] in ("healthy", "degraded")

    def test_check_required_for_action_missing(self):
        """Cannot proceed without credentials."""
        service = CredentialHealthService(environment="prod")

        with patch.dict(os.environ, {}, clear=True):
            can_proceed, error = service.check_required_for_action("youtube", "publish")
            assert can_proceed is False
            assert "Missing" in error

    def test_check_required_for_action_present(self):
        """Can proceed with credentials."""
        service = CredentialHealthService(environment="prod")

        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "fake-key-for-test"}):
            can_proceed, error = service.check_required_for_action("youtube", "publish")
            assert can_proceed is True
            assert error is None
