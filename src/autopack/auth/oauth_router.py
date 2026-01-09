"""OAuth credential health API endpoints.

Implements gap analysis item 6.8:
- API endpoint to expose credential health to dashboard
- Credential lifecycle management endpoints

SOT Contract Endpoints:
- GET /api/auth/oauth/health - Overall credential health
- GET /api/auth/oauth/health/{provider} - Provider-specific health
- GET /api/auth/oauth/events - Recent credential events
- POST /api/auth/oauth/refresh/{provider} - Manual refresh trigger
- POST /api/auth/oauth/reset/{provider} - Reset failure count
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks

from .oauth_lifecycle import (
    OAuthCredentialManager,
)
from .router import get_current_user
from .models import User

logger = logging.getLogger(__name__)

# Singleton manager instance
_credential_manager: Optional[OAuthCredentialManager] = None


def get_credential_manager() -> OAuthCredentialManager:
    """Get or create the credential manager singleton."""
    global _credential_manager
    if _credential_manager is None:
        _credential_manager = OAuthCredentialManager()
    return _credential_manager


router = APIRouter(
    prefix="/api/auth/oauth",
    tags=["oauth"],
)


@router.get("/health")
async def get_credential_health_report(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get comprehensive credential health report.

    Returns health status of all registered OAuth credentials,
    suitable for dashboard display.

    SOT endpoint: /api/auth/oauth/health

    Returns:
        Health report with summary and per-credential status
    """
    manager = get_credential_manager()
    return manager.get_health_report()


@router.get("/health/{provider}")
async def get_provider_health(
    provider: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get health status for a specific provider.

    SOT endpoint: /api/auth/oauth/health/{provider}

    Args:
        provider: OAuth provider name (e.g., 'github', 'google')

    Returns:
        CredentialHealth as dictionary
    """
    manager = get_credential_manager()
    health = manager.get_credential_health(provider)
    return health.to_dict()


@router.get("/events")
async def get_credential_events(
    provider: Optional[str] = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get recent credential lifecycle events.

    SOT endpoint: /api/auth/oauth/events

    Args:
        provider: Filter by provider (optional)
        limit: Maximum events to return (default 100)

    Returns:
        List of credential events
    """
    manager = get_credential_manager()
    events = manager.get_credential_events(provider=provider, limit=limit)
    return {
        "events": events,
        "count": len(events),
        "provider_filter": provider,
    }


@router.post("/refresh/{provider}")
async def refresh_credential(
    provider: str,
    background_tasks: BackgroundTasks,
    max_retries: int = 3,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Manually trigger credential refresh.

    Queues a background refresh operation for the specified provider.
    Requires admin/superuser privileges.

    SOT endpoint: /api/auth/oauth/refresh/{provider}

    Args:
        provider: OAuth provider name
        max_retries: Maximum retry attempts

    Returns:
        Status indicating refresh was queued
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Admin privileges required for credential refresh",
        )

    manager = get_credential_manager()

    # Verify credential exists
    cred = manager.get_credential(provider)
    if not cred:
        raise HTTPException(
            status_code=404,
            detail=f"No credential found for provider: {provider}",
        )

    if not cred.refresh_token:
        raise HTTPException(
            status_code=400,
            detail="Credential does not have a refresh token",
        )

    # Queue background refresh
    async def do_refresh():
        result = await manager.refresh_credential(provider, max_retries=max_retries)
        if result.success:
            logger.info(f"Background refresh succeeded for {provider}")
        else:
            logger.warning(f"Background refresh failed for {provider}: {result.error_message}")

    background_tasks.add_task(do_refresh)

    return {
        "status": "queued",
        "provider": provider,
        "max_retries": max_retries,
        "message": f"Refresh queued for {provider}",
    }


@router.post("/reset/{provider}")
async def reset_failure_count(
    provider: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Reset consecutive failure count for a provider.

    Use this after manually resolving credential issues to
    re-enable automatic refresh attempts.
    Requires admin/superuser privileges.

    SOT endpoint: /api/auth/oauth/reset/{provider}

    Args:
        provider: OAuth provider name

    Returns:
        Status indicating reset result
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Admin privileges required for failure count reset",
        )

    manager = get_credential_manager()

    if manager.reset_failure_count(provider):
        return {
            "status": "success",
            "provider": provider,
            "message": f"Failure count reset for {provider}",
        }

    raise HTTPException(
        status_code=404,
        detail=f"No credential found for provider: {provider}",
    )


@router.get("/providers")
async def list_providers(
    current_user: User = Depends(get_current_user),
) -> dict:
    """List all registered OAuth providers.

    SOT endpoint: /api/auth/oauth/providers

    Returns:
        List of provider names with basic status
    """
    manager = get_credential_manager()
    all_health = manager.get_all_credential_health()

    providers = []
    for provider, health in all_health.items():
        providers.append(
            {
                "provider": provider,
                "status": health.status.value,
                "is_healthy": health.is_healthy,
                "requires_attention": health.requires_attention,
            }
        )

    return {
        "providers": providers,
        "count": len(providers),
    }
