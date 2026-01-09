"""Credential health service.

Provides non-secret visibility into provider credentials for health checks
and dashboard display. Implements gap analysis item 6.8.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from .models import CredentialStatus, ProviderCredential

logger = logging.getLogger(__name__)


# Provider configuration: environment variable names and validation patterns
PROVIDER_CONFIG = {
    "youtube": {
        "env_vars": ["YOUTUBE_API_KEY", "GOOGLE_API_KEY"],
        "oauth_vars": ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"],
        "description": "YouTube Data API",
        "scopes": ["readonly", "upload", "manage"],
    },
    "etsy": {
        "env_vars": ["ETSY_API_KEY"],
        "oauth_vars": ["ETSY_CLIENT_ID", "ETSY_CLIENT_SECRET", "ETSY_REFRESH_TOKEN"],
        "description": "Etsy Open API",
        "scopes": ["listings:r", "listings:w", "shops:r"],
    },
    "shopify": {
        "env_vars": ["SHOPIFY_API_KEY", "SHOPIFY_ADMIN_API_ACCESS_TOKEN"],
        "oauth_vars": ["SHOPIFY_CLIENT_ID", "SHOPIFY_CLIENT_SECRET"],
        "description": "Shopify Admin API",
        "scopes": ["read_products", "write_products", "read_orders"],
    },
    "alpaca": {
        "env_vars": ["ALPACA_API_KEY_ID", "ALPACA_SECRET_KEY"],
        "oauth_vars": [],  # Alpaca uses API keys, not OAuth
        "description": "Alpaca Trading API",
        "scopes": ["trading", "data"],
    },
    "anthropic": {
        "env_vars": ["ANTHROPIC_API_KEY"],
        "oauth_vars": [],
        "description": "Anthropic Claude API",
        "scopes": ["messages"],
    },
    "openai": {
        "env_vars": ["OPENAI_API_KEY"],
        "oauth_vars": [],
        "description": "OpenAI API",
        "scopes": ["chat", "completions"],
    },
}


class CredentialHealthService:
    """Service for checking provider credential health.

    Provides non-secret visibility into credentials for:
    - Health endpoints
    - Dashboard display
    - Alerting on expired/missing credentials

    Never exposes actual secret values.
    """

    def __init__(self, environment: str = "prod"):
        """Initialize service.

        Args:
            environment: Current environment (dev, staging, prod)
        """
        self.environment = environment
        self._last_check: Optional[datetime] = None

    def check_provider(self, provider: str) -> ProviderCredential:
        """Check health of a specific provider's credentials.

        Args:
            provider: Provider name (youtube, etsy, shopify, alpaca, etc.)

        Returns:
            ProviderCredential with status and metadata (no secrets)
        """
        config = PROVIDER_CONFIG.get(provider)

        if not config:
            return ProviderCredential(
                provider=provider,
                environment=self.environment,
                status=CredentialStatus.UNKNOWN,
                validation_error=f"Unknown provider: {provider}",
            )

        # Check for environment variables
        env_vars = config["env_vars"]
        oauth_vars = config["oauth_vars"]

        has_api_key = any(os.environ.get(var) for var in env_vars)
        has_oauth = all(os.environ.get(var) for var in oauth_vars) if oauth_vars else False

        if not has_api_key and not has_oauth:
            return ProviderCredential(
                provider=provider,
                environment=self.environment,
                status=CredentialStatus.MISSING,
                validation_error=f"No credentials found. Set one of: {env_vars + oauth_vars}",
            )

        # For now, we can only verify presence, not validity
        # Full validation would require making API calls
        return ProviderCredential(
            provider=provider,
            environment=self.environment,
            status=CredentialStatus.PRESENT,
            last_validated=datetime.now(timezone.utc),
            scopes=config.get("scopes"),
        )

    def check_all_providers(self) -> list[ProviderCredential]:
        """Check health of all known provider credentials.

        Returns:
            List of ProviderCredential objects for all providers
        """
        self._last_check = datetime.now(timezone.utc)
        return [self.check_provider(provider) for provider in PROVIDER_CONFIG.keys()]

    def get_health_summary(self) -> dict:
        """Get summary of credential health for all providers.

        Returns:
            Dictionary with health status suitable for API response
        """
        credentials = self.check_all_providers()

        healthy = [c for c in credentials if c.is_healthy()]
        needs_attention = [c for c in credentials if c.needs_attention()]

        return {
            "environment": self.environment,
            "checked_at": self._last_check.isoformat() if self._last_check else None,
            "total_providers": len(credentials),
            "healthy_count": len(healthy),
            "needs_attention_count": len(needs_attention),
            "overall_status": "healthy" if not needs_attention else "degraded",
            "providers": [c.to_dict() for c in credentials],
            "attention_required": [c.to_dict() for c in needs_attention],
        }

    def check_required_for_action(self, provider: str, action: str) -> tuple[bool, Optional[str]]:
        """Check if credentials are available for a specific action.

        Args:
            provider: Provider name
            action: Action type (publish, list, trade, etc.)

        Returns:
            Tuple of (can_proceed: bool, error_message: Optional[str])
        """
        credential = self.check_provider(provider)

        if credential.status == CredentialStatus.MISSING:
            return False, f"Missing {provider} credentials. Configure in environment."

        if credential.status == CredentialStatus.EXPIRED:
            return False, f"{provider} credentials expired. Refresh required."

        if credential.status == CredentialStatus.NEEDS_REAUTH:
            return False, f"{provider} credentials revoked. Manual reauthorization required."

        if credential.status == CredentialStatus.INVALID:
            return False, f"{provider} credentials invalid: {credential.validation_error}"

        if credential.status == CredentialStatus.PRESENT:
            return True, None

        return False, f"Unable to verify {provider} credentials (status: {credential.status})"
