"""OAuth credential lifecycle management.

Implements gap analysis item 6.8:
- OAuth refresh token handling with bounded retries
- Credential health monitoring and API endpoint
- Integration with external action ledger for pause-on-failure

PR-04 (R-03 G4): Production OAuth hardening
In production mode (AUTOPACK_ENV=production), plaintext credential persistence
is DISABLED by default to prevent accidental secret exposure. Operators must
explicitly enable via AUTOPACK_OAUTH_ALLOW_PLAINTEXT_PERSISTENCE=1 and accept
the documented security implications.

Usage:
    manager = OAuthCredentialManager()

    # Register a provider credential
    manager.register_credential(
        provider="github",
        client_id="...",
        refresh_token="...",
    )

    # Refresh credential with bounded retries
    result = await manager.refresh_credential("github", max_retries=3)

    # Check credential health
    health = manager.get_credential_health("github")
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _is_production() -> bool:
    """Check if running in production mode."""
    return os.getenv("AUTOPACK_ENV", "development").lower() == "production"


def _is_plaintext_persistence_allowed() -> bool:
    """Check if plaintext credential persistence is explicitly allowed.

    PR-04 (R-03 G4): In production, plaintext persistence requires explicit opt-in.
    """
    if not _is_production():
        # Development mode: allowed by default
        return True

    # Production mode: must explicitly opt in
    return os.getenv("AUTOPACK_OAUTH_ALLOW_PLAINTEXT_PERSISTENCE", "0") == "1"


class OAuthProductionSecurityError(RuntimeError):
    """Raised when OAuth operations violate production security constraints."""

    pass


def _sanitize_log_input(value: Optional[str]) -> str:
    """Sanitize input for logging to prevent log injection."""
    if value is None:
        return "None"
    # Replace newlines, carriage returns, and other control characters
    return value.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


class CredentialStatus(str, Enum):
    """Status of an OAuth credential."""

    VALID = "valid"
    EXPIRED = "expired"
    REFRESH_PENDING = "refresh_pending"
    REFRESH_FAILED = "refresh_failed"
    REVOKED = "revoked"
    UNKNOWN = "unknown"


class RefreshResult(str, Enum):
    """Result of a refresh attempt."""

    SUCCESS = "success"
    RATE_LIMITED = "rate_limited"
    INVALID_GRANT = "invalid_grant"
    NETWORK_ERROR = "network_error"
    SERVER_ERROR = "server_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class CredentialHealth:
    """Health status of a credential."""

    provider: str
    status: CredentialStatus
    last_refresh: Optional[datetime]
    last_refresh_result: Optional[RefreshResult]
    expires_at: Optional[datetime]
    consecutive_failures: int
    total_refreshes: int
    total_failures: int
    is_healthy: bool
    requires_attention: bool
    message: str

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "status": self.status.value,
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
            "last_refresh_result": (
                self.last_refresh_result.value if self.last_refresh_result else None
            ),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "consecutive_failures": self.consecutive_failures,
            "total_refreshes": self.total_refreshes,
            "total_failures": self.total_failures,
            "is_healthy": self.is_healthy,
            "requires_attention": self.requires_attention,
            "message": self.message,
        }


@dataclass
class OAuthCredential:
    """Stored OAuth credential."""

    provider: str
    client_id: str
    client_secret: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    scope: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_refresh: Optional[datetime] = None
    last_refresh_result: Optional[RefreshResult] = None
    consecutive_failures: int = 0
    total_refreshes: int = 0
    total_failures: int = 0
    metadata: dict = field(default_factory=dict)

    def is_expired(self, buffer_seconds: int = 60) -> bool:
        """Check if credential is expired (with buffer)."""
        if self.expires_at is None:
            return False
        now = datetime.now(timezone.utc)
        return now >= (self.expires_at - timedelta(seconds=buffer_seconds))

    def to_dict(self, include_secrets: bool = False) -> dict:
        result = {
            "provider": self.provider,
            "client_id": self.client_id,
            "token_type": self.token_type,
            "scope": self.scope,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat(),
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
            "last_refresh_result": (
                self.last_refresh_result.value if self.last_refresh_result else None
            ),
            "consecutive_failures": self.consecutive_failures,
            "total_refreshes": self.total_refreshes,
            "total_failures": self.total_failures,
        }
        if include_secrets:
            result["client_secret"] = self.client_secret
            result["access_token"] = self.access_token
            result["refresh_token"] = self.refresh_token
        return result


@dataclass
class RefreshAttemptResult:
    """Result of a credential refresh attempt."""

    success: bool
    result: RefreshResult
    new_access_token: Optional[str] = None
    new_refresh_token: Optional[str] = None
    new_expires_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_after_seconds: Optional[int] = None


@dataclass
class CredentialEvent:
    """Event in credential lifecycle."""

    timestamp: datetime
    provider: str
    event_type: str
    result: Optional[str]
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "provider": self.provider,
            "event_type": self.event_type,
            "result": self.result,
            "details": self.details,
        }


# Type for refresh handler functions
RefreshHandler = Callable[[OAuthCredential], RefreshAttemptResult]


class OAuthCredentialManager:
    """Manages OAuth credential lifecycle.

    Features:
    - Bounded retry logic for refresh operations
    - Credential health monitoring
    - Event logging for audit
    - Integration with external action ledger
    """

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        max_consecutive_failures: int = 3,
        default_retry_delay_seconds: int = 5,
        pause_on_failure_callback: Optional[Callable[[str, str], None]] = None,
    ):
        """Initialize the manager.

        Args:
            storage_dir: Directory for credential storage
            max_consecutive_failures: Max failures before marking credential unhealthy
            default_retry_delay_seconds: Default delay between retries
            pause_on_failure_callback: Callback for external action ledger integration
        """
        self._storage_dir = storage_dir or Path(".credentials")
        self._max_consecutive_failures = max_consecutive_failures
        self._default_retry_delay = default_retry_delay_seconds
        self._pause_callback = pause_on_failure_callback
        self._credentials: dict[str, OAuthCredential] = {}
        self._refresh_handlers: dict[str, RefreshHandler] = {}
        self._events: list[CredentialEvent] = []
        self._load()

    def _load(self) -> None:
        """Load credentials from storage."""
        creds_file = self._storage_dir / "credentials.json"
        if creds_file.exists():
            try:
                data = json.loads(creds_file.read_text(encoding="utf-8"))
                for provider, cred_data in data.get("credentials", {}).items():
                    self._credentials[provider] = OAuthCredential(
                        provider=cred_data["provider"],
                        client_id=cred_data["client_id"],
                        client_secret=cred_data.get("client_secret"),
                        access_token=cred_data.get("access_token"),
                        refresh_token=cred_data.get("refresh_token"),
                        token_type=cred_data.get("token_type", "Bearer"),
                        scope=cred_data.get("scope"),
                        expires_at=(
                            datetime.fromisoformat(cred_data["expires_at"])
                            if cred_data.get("expires_at")
                            else None
                        ),
                        created_at=datetime.fromisoformat(cred_data["created_at"]),
                        last_refresh=(
                            datetime.fromisoformat(cred_data["last_refresh"])
                            if cred_data.get("last_refresh")
                            else None
                        ),
                        last_refresh_result=(
                            RefreshResult(cred_data["last_refresh_result"])
                            if cred_data.get("last_refresh_result")
                            else None
                        ),
                        consecutive_failures=cred_data.get("consecutive_failures", 0),
                        total_refreshes=cred_data.get("total_refreshes", 0),
                        total_failures=cred_data.get("total_failures", 0),
                    )
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load credentials: {e}")

    def _save(self) -> None:
        """Save credentials to storage.

        PR-04 (R-03 G4): Production security check
        In production, plaintext persistence is forbidden unless explicitly enabled.

        Raises:
            OAuthProductionSecurityError: If plaintext persistence is not allowed in production.
        """
        if not _is_plaintext_persistence_allowed():
            raise OAuthProductionSecurityError(
                "FATAL: Plaintext OAuth credential persistence is disabled in production. "
                "This prevents accidental secret exposure to the filesystem. "
                "Options: (1) Use *_FILE env vars for OAuth credentials, "
                "(2) Set AUTOPACK_OAUTH_ALLOW_PLAINTEXT_PERSISTENCE=1 to explicitly allow "
                "(NOT RECOMMENDED for production). "
                "See docs/DEPLOYMENT.md for secure credential management."
            )

        self._storage_dir.mkdir(parents=True, exist_ok=True)
        creds_file = self._storage_dir / "credentials.json"
        data = {
            "credentials": {
                provider: cred.to_dict(include_secrets=True)
                for provider, cred in self._credentials.items()
            },
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        creds_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _log_event(
        self,
        provider: str,
        event_type: str,
        result: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        """Log a credential lifecycle event."""
        event = CredentialEvent(
            timestamp=datetime.now(timezone.utc),
            provider=provider,
            event_type=event_type,
            result=result,
            details=details or {},
        )
        self._events.append(event)
        # Keep last 1000 events
        if len(self._events) > 1000:
            self._events = self._events[-1000:]

        logger.info(
            "Credential event: %s - %s (%s)",
            _sanitize_log_input(provider),
            _sanitize_log_input(event_type),
            _sanitize_log_input(result),
        )

    def register_credential(
        self,
        provider: str,
        client_id: str,
        client_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        expires_in_seconds: Optional[int] = None,
        scope: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> OAuthCredential:
        """Register a new OAuth credential.

        Args:
            provider: Provider name (e.g., 'github', 'google')
            client_id: OAuth client ID
            client_secret: OAuth client secret
            access_token: Initial access token
            refresh_token: Refresh token for renewal
            expires_in_seconds: Token expiry in seconds
            scope: OAuth scope
            metadata: Additional metadata

        Returns:
            Registered credential
        """
        now = datetime.now(timezone.utc)
        expires_at = None
        if expires_in_seconds:
            expires_at = now + timedelta(seconds=expires_in_seconds)

        credential = OAuthCredential(
            provider=provider,
            client_id=client_id,
            client_secret=client_secret,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scope=scope,
            created_at=now,
            metadata=metadata or {},
        )

        self._credentials[provider] = credential
        self._save()
        self._log_event(provider, "registered")

        return credential

    def register_refresh_handler(self, provider: str, handler: RefreshHandler) -> None:
        """Register a refresh handler for a provider.

        The handler is called when refresh_credential is invoked and
        should return a RefreshAttemptResult.

        Args:
            provider: Provider name
            handler: Async function that performs the refresh
        """
        self._refresh_handlers[provider] = handler
        logger.debug("Registered refresh handler for %s", _sanitize_log_input(provider))

    def get_credential(self, provider: str) -> Optional[OAuthCredential]:
        """Get a credential by provider."""
        return self._credentials.get(provider)

    def get_access_token(self, provider: str) -> Optional[str]:
        """Get the current access token for a provider."""
        cred = self._credentials.get(provider)
        if cred:
            return cred.access_token
        return None

    async def refresh_credential(
        self,
        provider: str,
        max_retries: int = 3,
        retry_delay_seconds: Optional[int] = None,
    ) -> RefreshAttemptResult:
        """Refresh a credential with bounded retries.

        Args:
            provider: Provider name
            max_retries: Maximum number of retry attempts
            retry_delay_seconds: Delay between retries

        Returns:
            RefreshAttemptResult with success status and new tokens
        """
        cred = self._credentials.get(provider)
        if not cred:
            return RefreshAttemptResult(
                success=False,
                result=RefreshResult.UNKNOWN_ERROR,
                error_message=f"No credential found for provider: {provider}",
            )

        if not cred.refresh_token:
            return RefreshAttemptResult(
                success=False,
                result=RefreshResult.INVALID_GRANT,
                error_message="No refresh token available",
            )

        handler = self._refresh_handlers.get(provider)
        if not handler:
            return RefreshAttemptResult(
                success=False,
                result=RefreshResult.UNKNOWN_ERROR,
                error_message=f"No refresh handler for provider: {provider}",
            )

        retry_delay = retry_delay_seconds or self._default_retry_delay
        last_result: Optional[RefreshAttemptResult] = None

        for attempt in range(max_retries + 1):
            self._log_event(
                provider,
                "refresh_attempt",
                details={"attempt": attempt + 1, "max_retries": max_retries},
            )

            try:
                # Call the provider-specific refresh handler
                result = handler(cred)
                last_result = result

                if result.success:
                    # Update credential with new tokens
                    cred.access_token = result.new_access_token
                    if result.new_refresh_token:
                        cred.refresh_token = result.new_refresh_token
                    cred.expires_at = result.new_expires_at
                    cred.last_refresh = datetime.now(timezone.utc)
                    cred.last_refresh_result = RefreshResult.SUCCESS
                    cred.consecutive_failures = 0
                    cred.total_refreshes += 1

                    self._save()
                    self._log_event(provider, "refresh_success")

                    return result

                # Handle specific failure modes
                if result.result == RefreshResult.INVALID_GRANT:
                    # Token revoked, no point retrying
                    cred.last_refresh_result = RefreshResult.INVALID_GRANT
                    cred.consecutive_failures += 1
                    cred.total_failures += 1
                    self._save()
                    self._log_event(provider, "refresh_failed", result="invalid_grant")
                    break

                if result.result == RefreshResult.RATE_LIMITED:
                    # Respect rate limit
                    wait_time = result.retry_after_seconds or retry_delay * 2
                    if attempt < max_retries:
                        self._log_event(
                            provider,
                            "rate_limited",
                            details={"wait_seconds": wait_time},
                        )
                        await asyncio.sleep(wait_time)
                        continue

            except Exception as e:
                logger.error("Refresh error for %s: %s", _sanitize_log_input(provider), e)
                last_result = RefreshAttemptResult(
                    success=False,
                    result=RefreshResult.UNKNOWN_ERROR,
                    error_message=str(e),
                )

            # Retry with exponential backoff
            if attempt < max_retries:
                wait_time = retry_delay * (2**attempt)
                self._log_event(provider, "refresh_retry", details={"wait_seconds": wait_time})
                await asyncio.sleep(wait_time)

        # All retries exhausted
        cred.last_refresh = datetime.now(timezone.utc)
        cred.last_refresh_result = (
            last_result.result if last_result else RefreshResult.UNKNOWN_ERROR
        )
        cred.consecutive_failures += 1
        cred.total_failures += 1
        self._save()

        self._log_event(
            provider,
            "refresh_exhausted",
            result=last_result.result.value if last_result else "unknown",
            details={"consecutive_failures": cred.consecutive_failures},
        )

        # Check if we should pause external actions
        if cred.consecutive_failures >= self._max_consecutive_failures:
            self._trigger_pause(provider, "max_consecutive_failures_reached")

        return last_result or RefreshAttemptResult(
            success=False,
            result=RefreshResult.UNKNOWN_ERROR,
            error_message="All refresh attempts failed",
        )

    def _trigger_pause(self, provider: str, reason: str) -> None:
        """Trigger pause on external action ledger."""
        self._log_event(provider, "pause_triggered", details={"reason": reason})

        if self._pause_callback:
            try:
                self._pause_callback(provider, reason)
                logger.warning(
                    "External actions paused for %s: %s",
                    _sanitize_log_input(provider),
                    _sanitize_log_input(reason),
                )
            except Exception as e:
                logger.error(
                    "Failed to trigger pause for %s: %s",
                    _sanitize_log_input(provider),
                    e,
                )

    def get_credential_health(self, provider: str) -> CredentialHealth:
        """Get health status of a credential.

        Args:
            provider: Provider name

        Returns:
            CredentialHealth with status and metrics
        """
        cred = self._credentials.get(provider)

        if not cred:
            return CredentialHealth(
                provider=provider,
                status=CredentialStatus.UNKNOWN,
                last_refresh=None,
                last_refresh_result=None,
                expires_at=None,
                consecutive_failures=0,
                total_refreshes=0,
                total_failures=0,
                is_healthy=False,
                requires_attention=True,
                message=f"No credential found for provider: {provider}",
            )

        # Determine status
        if cred.last_refresh_result == RefreshResult.INVALID_GRANT:
            status = CredentialStatus.REVOKED
            message = "Credential has been revoked"
            is_healthy = False
            requires_attention = True
        elif cred.consecutive_failures >= self._max_consecutive_failures:
            status = CredentialStatus.REFRESH_FAILED
            message = f"Refresh failed {cred.consecutive_failures} consecutive times"
            is_healthy = False
            requires_attention = True
        elif cred.is_expired():
            status = CredentialStatus.EXPIRED
            message = "Access token has expired"
            is_healthy = False
            requires_attention = True
        elif cred.is_expired(buffer_seconds=300):
            status = CredentialStatus.REFRESH_PENDING
            message = "Access token expiring soon"
            is_healthy = True
            requires_attention = False
        else:
            status = CredentialStatus.VALID
            message = "Credential is valid"
            is_healthy = True
            requires_attention = False

        return CredentialHealth(
            provider=provider,
            status=status,
            last_refresh=cred.last_refresh,
            last_refresh_result=cred.last_refresh_result,
            expires_at=cred.expires_at,
            consecutive_failures=cred.consecutive_failures,
            total_refreshes=cred.total_refreshes,
            total_failures=cred.total_failures,
            is_healthy=is_healthy,
            requires_attention=requires_attention,
            message=message,
        )

    def get_all_credential_health(self) -> dict[str, CredentialHealth]:
        """Get health status of all credentials."""
        return {provider: self.get_credential_health(provider) for provider in self._credentials}

    def get_credential_events(self, provider: Optional[str] = None, limit: int = 100) -> list[dict]:
        """Get recent credential events.

        Args:
            provider: Filter by provider (None for all)
            limit: Maximum events to return

        Returns:
            List of event dictionaries
        """
        events = self._events
        if provider:
            events = [e for e in events if e.provider == provider]
        return [e.to_dict() for e in events[-limit:]]

    def get_health_report(self) -> dict:
        """Get comprehensive health report for dashboard.

        Returns:
            Report dictionary with all credential health info
        """
        now = datetime.now(timezone.utc)
        credentials_health = self.get_all_credential_health()

        healthy_count = sum(1 for h in credentials_health.values() if h.is_healthy)
        attention_count = sum(1 for h in credentials_health.values() if h.requires_attention)

        return {
            "generated_at": now.isoformat(),
            "summary": {
                "total_credentials": len(self._credentials),
                "healthy_count": healthy_count,
                "attention_required_count": attention_count,
                "overall_healthy": attention_count == 0,
            },
            "credentials": {
                provider: health.to_dict() for provider, health in credentials_health.items()
            },
            "recent_events": self.get_credential_events(limit=20),
        }

    def remove_credential(self, provider: str) -> bool:
        """Remove a credential.

        Args:
            provider: Provider name

        Returns:
            True if removed, False if not found
        """
        if provider in self._credentials:
            del self._credentials[provider]
            self._save()
            self._log_event(provider, "removed")
            return True
        return False

    def reset_failure_count(self, provider: str) -> bool:
        """Reset consecutive failure count for a credential.

        Args:
            provider: Provider name

        Returns:
            True if reset, False if not found
        """
        cred = self._credentials.get(provider)
        if cred:
            cred.consecutive_failures = 0
            self._save()
            self._log_event(provider, "failure_count_reset")
            return True
        return False


# Default handlers for common providers
def create_generic_oauth2_handler(
    token_url: str,
    extra_params: Optional[dict] = None,
) -> RefreshHandler:
    """Create a generic OAuth2 refresh handler.

    Args:
        token_url: OAuth2 token endpoint URL
        extra_params: Extra parameters to include in request

    Returns:
        RefreshHandler function
    """

    def handler(cred: OAuthCredential) -> RefreshAttemptResult:
        import urllib.request
        import urllib.parse
        import urllib.error

        data = {
            "grant_type": "refresh_token",
            "refresh_token": cred.refresh_token,
            "client_id": cred.client_id,
        }
        if cred.client_secret:
            data["client_secret"] = cred.client_secret
        if extra_params:
            data.update(extra_params)

        try:
            req = urllib.request.Request(
                token_url,
                data=urllib.parse.urlencode(data).encode("utf-8"),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            expires_at = None
            if "expires_in" in result:
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=result["expires_in"])

            return RefreshAttemptResult(
                success=True,
                result=RefreshResult.SUCCESS,
                new_access_token=result.get("access_token"),
                new_refresh_token=result.get("refresh_token"),
                new_expires_at=expires_at,
            )

        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = e.headers.get("Retry-After")
                return RefreshAttemptResult(
                    success=False,
                    result=RefreshResult.RATE_LIMITED,
                    error_message="Rate limited",
                    retry_after_seconds=int(retry_after) if retry_after else None,
                )
            elif e.code == 400:
                try:
                    error_data = json.loads(e.read().decode("utf-8"))
                    if error_data.get("error") == "invalid_grant":
                        return RefreshAttemptResult(
                            success=False,
                            result=RefreshResult.INVALID_GRANT,
                            error_message=error_data.get("error_description", "Invalid grant"),
                        )
                except Exception:
                    pass
                return RefreshAttemptResult(
                    success=False,
                    result=RefreshResult.INVALID_GRANT,
                    error_message=f"HTTP {e.code}",
                )
            elif e.code >= 500:
                return RefreshAttemptResult(
                    success=False,
                    result=RefreshResult.SERVER_ERROR,
                    error_message=f"HTTP {e.code}",
                )
            else:
                return RefreshAttemptResult(
                    success=False,
                    result=RefreshResult.UNKNOWN_ERROR,
                    error_message=f"HTTP {e.code}",
                )

        except urllib.error.URLError as e:
            return RefreshAttemptResult(
                success=False,
                result=RefreshResult.NETWORK_ERROR,
                error_message=str(e.reason),
            )

        except Exception as e:
            return RefreshAttemptResult(
                success=False,
                result=RefreshResult.UNKNOWN_ERROR,
                error_message=str(e),
            )

    return handler


# Pre-built handlers for common providers
GITHUB_REFRESH_HANDLER = create_generic_oauth2_handler(
    token_url="https://github.com/login/oauth/access_token",
    extra_params={"accept": "application/json"},
)

GOOGLE_REFRESH_HANDLER = create_generic_oauth2_handler(
    token_url="https://oauth2.googleapis.com/token",
)
