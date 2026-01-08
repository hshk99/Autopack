"""Telegram webhook security module (PR7).

Provides cryptographic verification for Telegram webhook requests.

Telegram webhooks support a secret_token header (X-Telegram-Bot-Api-Secret-Token)
that must be verified to ensure requests come from Telegram's servers.

Security Properties:
- Requests without secret token are rejected in production
- Constant-time comparison prevents timing attacks
- Verification is enabled when TELEGRAM_WEBHOOK_SECRET is set
- Dev mode allows bypassing verification (with warning)

Usage:
    from autopack.notifications.telegram_webhook_security import verify_telegram_webhook

    @app.post("/telegram/webhook")
    async def telegram_webhook(request: Request):
        if not await verify_telegram_webhook(request):
            raise HTTPException(status_code=403, detail="Invalid webhook signature")
        # ... handle webhook
"""

import hmac
import logging
import os
from typing import Optional

from fastapi import Request

logger = logging.getLogger(__name__)


def get_webhook_secret() -> Optional[str]:
    """Get the Telegram webhook secret token.

    This should be set when configuring the webhook with setWebhook API.
    See: https://core.telegram.org/bots/api#setwebhook

    Returns:
        The secret token or None if not configured.
    """
    return os.getenv("TELEGRAM_WEBHOOK_SECRET")


def is_verification_required() -> bool:
    """Check if webhook verification is required.

    Verification is required when:
    - TELEGRAM_WEBHOOK_SECRET is set, OR
    - AUTOPACK_ENV is "production"

    Returns:
        True if verification is required.
    """
    secret = get_webhook_secret()
    env = os.getenv("AUTOPACK_ENV", "development").lower()

    # Required if secret is configured or in production
    if secret:
        return True
    if env == "production":
        logger.warning(
            "[TELEGRAM_SECURITY] Production mode but TELEGRAM_WEBHOOK_SECRET not set - "
            "webhook verification cannot be performed"
        )
        return True

    return False


def verify_secret_token(request_token: Optional[str]) -> bool:
    """Verify the secret token from request header.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        request_token: The X-Telegram-Bot-Api-Secret-Token header value

    Returns:
        True if token is valid, False otherwise.
    """
    expected_secret = get_webhook_secret()

    if not expected_secret:
        # No secret configured - can't verify
        return False

    if not request_token:
        logger.warning("[TELEGRAM_SECURITY] No secret token in request")
        return False

    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(expected_secret.encode(), request_token.encode())


async def verify_telegram_webhook(request: Request) -> bool:
    """Verify a Telegram webhook request.

    Checks the X-Telegram-Bot-Api-Secret-Token header against configured secret.

    Args:
        request: FastAPI Request object

    Returns:
        True if verification passes or is not required, False otherwise.

    Security Note:
        In production, this will reject requests if:
        - TELEGRAM_WEBHOOK_SECRET is set but header doesn't match
        - AUTOPACK_ENV=production and no secret is configured (logs warning)
    """
    env = os.getenv("AUTOPACK_ENV", "development").lower()
    secret = get_webhook_secret()

    # Get the secret token from request header
    request_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")

    # If secret is configured, verify it
    if secret:
        if verify_secret_token(request_token):
            logger.debug("[TELEGRAM_SECURITY] Webhook verification passed")
            return True
        else:
            logger.warning(
                "[TELEGRAM_SECURITY] Webhook verification FAILED - "
                "invalid or missing X-Telegram-Bot-Api-Secret-Token"
            )
            return False

    # No secret configured
    if env == "production":
        # Production without secret - reject for safety.
        # Returns False (→ 403 in handler) rather than raising 500 to avoid
        # leaking internal configuration state to attackers. From the caller's
        # perspective, both "wrong secret" and "no secret configured" look the
        # same: access denied.
        logger.error(
            "[TELEGRAM_SECURITY] Production webhook rejected - "
            "TELEGRAM_WEBHOOK_SECRET must be configured"
        )
        return False
    else:
        # Development mode - allow with warning
        if request_token:
            logger.warning(
                "[TELEGRAM_SECURITY] Secret token provided but "
                "TELEGRAM_WEBHOOK_SECRET not configured - verification skipped"
            )
        else:
            logger.debug("[TELEGRAM_SECURITY] Development mode - webhook verification skipped")
        return True


def generate_webhook_secret() -> str:
    """Generate a secure random webhook secret.

    Useful for initial setup. The generated secret should be:
    1. Set as TELEGRAM_WEBHOOK_SECRET environment variable
    2. Passed to Telegram's setWebhook API as secret_token parameter

    Returns:
        A 32-character hex string suitable for use as webhook secret.
    """
    import secrets

    return secrets.token_hex(16)


# Verification helper for contract tests
def get_verification_status() -> dict:
    """Get current verification configuration status.

    Returns:
        Dict with:
        - secret_configured: bool
        - verification_required: bool
        - environment: str
    """
    return {
        "secret_configured": get_webhook_secret() is not None,
        "verification_required": is_verification_required(),
        "environment": os.getenv("AUTOPACK_ENV", "development"),
    }
