"""Tests for OAuth credential lifecycle management."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autopack.auth.oauth_lifecycle import (CredentialHealth, CredentialStatus,
                                           OAuthCredential,
                                           OAuthCredentialManager,
                                           RefreshAttemptResult, RefreshResult,
                                           create_generic_oauth2_handler)


class TestOAuthCredential:
    """Tests for OAuthCredential."""

    def test_credential_creation(self):
        """Test credential creation with defaults."""
        cred = OAuthCredential(
            provider="github",
            client_id="client123",
            client_secret="secret456",
            access_token="access789",
            refresh_token="refresh012",
        )

        assert cred.provider == "github"
        assert cred.client_id == "client123"
        assert cred.token_type == "Bearer"
        assert cred.consecutive_failures == 0

    def test_is_expired_no_expiry(self):
        """Test is_expired with no expiry set."""
        cred = OAuthCredential(
            provider="test",
            client_id="id",
            client_secret=None,
        )
        assert not cred.is_expired()

    def test_is_expired_future(self):
        """Test is_expired with future expiry."""
        cred = OAuthCredential(
            provider="test",
            client_id="id",
            client_secret=None,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert not cred.is_expired()

    def test_is_expired_past(self):
        """Test is_expired with past expiry."""
        cred = OAuthCredential(
            provider="test",
            client_id="id",
            client_secret=None,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        assert cred.is_expired()

    def test_is_expired_with_buffer(self):
        """Test is_expired with buffer time."""
        cred = OAuthCredential(
            provider="test",
            client_id="id",
            client_secret=None,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        )
        # Without buffer (default 60s), should be expired
        assert cred.is_expired(buffer_seconds=60)
        # With smaller buffer, should not be expired
        assert not cred.is_expired(buffer_seconds=10)

    def test_to_dict_without_secrets(self):
        """Test serialization without secrets."""
        cred = OAuthCredential(
            provider="github",
            client_id="client123",
            client_secret="secret456",
            access_token="access789",
            refresh_token="refresh012",
        )

        d = cred.to_dict(include_secrets=False)
        assert "client_secret" not in d
        assert "access_token" not in d
        assert "refresh_token" not in d
        assert d["provider"] == "github"
        assert d["client_id"] == "client123"

    def test_to_dict_with_secrets(self):
        """Test serialization with secrets."""
        cred = OAuthCredential(
            provider="github",
            client_id="client123",
            client_secret="secret456",
            access_token="access789",
            refresh_token="refresh012",
        )

        d = cred.to_dict(include_secrets=True)
        assert d["client_secret"] == "secret456"
        assert d["access_token"] == "access789"
        assert d["refresh_token"] == "refresh012"


class TestCredentialHealth:
    """Tests for CredentialHealth."""

    def test_health_to_dict(self):
        """Test health serialization."""
        now = datetime.now(timezone.utc)
        health = CredentialHealth(
            provider="github",
            status=CredentialStatus.VALID,
            last_refresh=now,
            last_refresh_result=RefreshResult.SUCCESS,
            expires_at=now + timedelta(hours=1),
            consecutive_failures=0,
            total_refreshes=5,
            total_failures=1,
            is_healthy=True,
            requires_attention=False,
            message="Credential is valid",
        )

        d = health.to_dict()
        assert d["provider"] == "github"
        assert d["status"] == "valid"
        assert d["is_healthy"] is True


class TestOAuthCredentialManager:
    """Tests for OAuthCredentialManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.storage_dir = Path(self.temp_dir) / ".credentials"
        self.manager = OAuthCredentialManager(
            storage_dir=self.storage_dir,
            max_consecutive_failures=3,
        )

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_register_credential(self):
        """Test credential registration."""
        cred = self.manager.register_credential(
            provider="github",
            client_id="client123",
            client_secret="secret456",
            access_token="access789",
            refresh_token="refresh012",
            expires_in_seconds=3600,
        )

        assert cred.provider == "github"
        assert cred.expires_at is not None

        # Check it was saved
        retrieved = self.manager.get_credential("github")
        assert retrieved is not None
        assert retrieved.client_id == "client123"

    def test_get_access_token(self):
        """Test getting access token."""
        self.manager.register_credential(
            provider="github",
            client_id="client123",
            access_token="access789",
        )

        token = self.manager.get_access_token("github")
        assert token == "access789"

    def test_get_access_token_not_found(self):
        """Test getting token for unknown provider."""
        token = self.manager.get_access_token("unknown")
        assert token is None

    def test_credential_health_valid(self):
        """Test health for valid credential."""
        self.manager.register_credential(
            provider="github",
            client_id="client123",
            access_token="access789",
            expires_in_seconds=3600,
        )

        health = self.manager.get_credential_health("github")
        assert health.status == CredentialStatus.VALID
        assert health.is_healthy is True
        assert health.requires_attention is False

    def test_credential_health_expired(self):
        """Test health for expired credential."""
        cred = self.manager.register_credential(
            provider="github",
            client_id="client123",
            access_token="access789",
            expires_in_seconds=0,  # Expired immediately
        )
        # Manually set expiry to past
        cred.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        health = self.manager.get_credential_health("github")
        assert health.status == CredentialStatus.EXPIRED
        assert health.is_healthy is False
        assert health.requires_attention is True

    def test_credential_health_unknown_provider(self):
        """Test health for unknown provider."""
        health = self.manager.get_credential_health("unknown")
        assert health.status == CredentialStatus.UNKNOWN
        assert health.is_healthy is False

    def test_get_all_credential_health(self):
        """Test getting health for all credentials."""
        self.manager.register_credential("github", "id1")
        self.manager.register_credential("google", "id2")

        all_health = self.manager.get_all_credential_health()
        assert "github" in all_health
        assert "google" in all_health

    def test_get_health_report(self):
        """Test health report generation."""
        self.manager.register_credential(
            provider="github",
            client_id="client123",
            access_token="token",
            expires_in_seconds=3600,
        )

        report = self.manager.get_health_report()

        assert "generated_at" in report
        assert "summary" in report
        assert report["summary"]["total_credentials"] == 1
        assert report["summary"]["healthy_count"] == 1
        assert "credentials" in report

    def test_remove_credential(self):
        """Test credential removal."""
        self.manager.register_credential("github", "id1")
        assert self.manager.get_credential("github") is not None

        result = self.manager.remove_credential("github")
        assert result is True
        assert self.manager.get_credential("github") is None

    def test_remove_credential_not_found(self):
        """Test removing non-existent credential."""
        result = self.manager.remove_credential("unknown")
        assert result is False

    def test_reset_failure_count(self):
        """Test resetting failure count."""
        self.manager.register_credential("github", "id1")
        cred = self.manager.get_credential("github")
        cred.consecutive_failures = 5

        result = self.manager.reset_failure_count("github")
        assert result is True
        assert cred.consecutive_failures == 0

    def test_log_event(self):
        """Test event logging."""
        self.manager._log_event("github", "test_event", "success", {"key": "value"})

        events = self.manager.get_credential_events("github")
        assert len(events) == 1
        assert events[0]["event_type"] == "test_event"
        assert events[0]["result"] == "success"

    def test_event_limit(self):
        """Test event log limit."""
        # Log more than 1000 events
        for i in range(1100):
            self.manager._log_event("github", f"event_{i}")

        events = self.manager.get_credential_events()
        assert len(events) <= 1000

    def test_register_refresh_handler(self):
        """Test refresh handler registration."""

        def handler(cred):
            return RefreshAttemptResult(success=True, result=RefreshResult.SUCCESS)

        self.manager.register_refresh_handler("github", handler)
        assert "github" in self.manager._refresh_handlers

    @pytest.mark.asyncio
    async def test_refresh_no_credential(self):
        """Test refresh with no credential."""
        result = await self.manager.refresh_credential("unknown")
        assert result.success is False
        assert "No credential found" in result.error_message

    @pytest.mark.asyncio
    async def test_refresh_no_refresh_token(self):
        """Test refresh without refresh token."""
        self.manager.register_credential(
            provider="github",
            client_id="id1",
            access_token="token",
            refresh_token=None,
        )

        result = await self.manager.refresh_credential("github")
        assert result.success is False
        assert result.result == RefreshResult.INVALID_GRANT

    @pytest.mark.asyncio
    async def test_refresh_no_handler(self):
        """Test refresh without handler."""
        self.manager.register_credential(
            provider="github",
            client_id="id1",
            refresh_token="refresh123",
        )

        result = await self.manager.refresh_credential("github")
        assert result.success is False
        assert "No refresh handler" in result.error_message

    @pytest.mark.asyncio
    async def test_refresh_success(self):
        """Test successful refresh."""
        self.manager.register_credential(
            provider="github",
            client_id="id1",
            refresh_token="old_refresh",
        )

        def handler(cred):
            return RefreshAttemptResult(
                success=True,
                result=RefreshResult.SUCCESS,
                new_access_token="new_access",
                new_refresh_token="new_refresh",
                new_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )

        self.manager.register_refresh_handler("github", handler)

        result = await self.manager.refresh_credential("github", max_retries=0)
        assert result.success is True

        cred = self.manager.get_credential("github")
        assert cred.access_token == "new_access"
        assert cred.refresh_token == "new_refresh"
        assert cred.consecutive_failures == 0
        assert cred.total_refreshes == 1

    @pytest.mark.asyncio
    async def test_refresh_failure_counts(self):
        """Test failure counting on refresh."""
        self.manager.register_credential(
            provider="github",
            client_id="id1",
            refresh_token="refresh123",
        )

        def handler(cred):
            return RefreshAttemptResult(
                success=False,
                result=RefreshResult.NETWORK_ERROR,
                error_message="Network timeout",
            )

        self.manager.register_refresh_handler("github", handler)

        result = await self.manager.refresh_credential("github", max_retries=0)
        assert result.success is False

        cred = self.manager.get_credential("github")
        assert cred.consecutive_failures == 1
        assert cred.total_failures == 1

    @pytest.mark.asyncio
    async def test_refresh_invalid_grant_no_retry(self):
        """Test that invalid_grant stops retries."""
        self.manager.register_credential(
            provider="github",
            client_id="id1",
            refresh_token="refresh123",
        )

        call_count = 0

        def handler(cred):
            nonlocal call_count
            call_count += 1
            return RefreshAttemptResult(
                success=False,
                result=RefreshResult.INVALID_GRANT,
                error_message="Token revoked",
            )

        self.manager.register_refresh_handler("github", handler)

        result = await self.manager.refresh_credential("github", max_retries=3)
        assert result.success is False
        assert result.result == RefreshResult.INVALID_GRANT
        # Should only call once (no retries for invalid_grant)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_pause_callback_triggered(self):
        """Test pause callback on max failures."""
        pause_calls = []

        def pause_callback(provider, reason):
            pause_calls.append((provider, reason))

        manager = OAuthCredentialManager(
            storage_dir=self.storage_dir,
            max_consecutive_failures=2,
            pause_on_failure_callback=pause_callback,
        )

        manager.register_credential(
            provider="github",
            client_id="id1",
            refresh_token="refresh123",
        )

        # Set up to fail
        cred = manager.get_credential("github")
        cred.consecutive_failures = 1  # One failure already

        def handler(cred):
            return RefreshAttemptResult(
                success=False,
                result=RefreshResult.NETWORK_ERROR,
            )

        manager.register_refresh_handler("github", handler)

        await manager.refresh_credential("github", max_retries=0)

        # Should have triggered pause (2 >= max_consecutive_failures)
        assert len(pause_calls) == 1
        assert pause_calls[0][0] == "github"

    def test_persistence(self):
        """Test credential persistence across manager instances."""
        # Register credential
        self.manager.register_credential(
            provider="github",
            client_id="client123",
            access_token="access789",
            refresh_token="refresh012",
        )

        # Create new manager with same storage
        new_manager = OAuthCredentialManager(storage_dir=self.storage_dir)

        # Should load the credential
        cred = new_manager.get_credential("github")
        assert cred is not None
        assert cred.client_id == "client123"
        assert cred.access_token == "access789"


class TestGenericOAuth2Handler:
    """Tests for create_generic_oauth2_handler."""

    def test_create_handler(self):
        """Test handler creation."""
        handler = create_generic_oauth2_handler(token_url="https://oauth.example.com/token")
        assert callable(handler)

    def test_handler_returns_result_type(self):
        """Test handler returns RefreshAttemptResult for invalid URL."""
        handler = create_generic_oauth2_handler(token_url="https://invalid.url.test/token")

        cred = OAuthCredential(
            provider="test",
            client_id="client123",
            refresh_token="refresh123",
        )

        # This will fail with network error (expected)
        result = handler(cred)
        assert isinstance(result, RefreshAttemptResult)
        assert result.success is False
        # Network error is expected since URL is invalid
        assert result.result in [RefreshResult.NETWORK_ERROR, RefreshResult.UNKNOWN_ERROR]

    def test_handler_with_extra_params(self):
        """Test handler with extra parameters."""
        handler = create_generic_oauth2_handler(
            token_url="https://invalid.url.test/token",
            extra_params={"scope": "read write"},
        )
        assert callable(handler)
