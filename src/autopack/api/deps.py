"""API dependencies (auth + rate limiting key function).

PR-API-1: Extract from main.py to support router split.

This module provides:
- verify_api_key: API key authentication dependency
- verify_read_access: Read-only endpoint authentication
- get_client_ip: Client IP extraction respecting trusted proxies
- limiter: Rate limiter instance keyed by client IP

Contract guarantees (tested in tests/api/test_auth_dependency_contract.py):
- TESTING mode bypasses auth entirely (returns 'test-key')
- Production mode requires API key
- Dev mode skips auth if no key configured
- Forwarded headers trusted only from trusted proxies
"""

import ipaddress
import os
from typing import Optional

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from slowapi import Limiter

from ..config import get_api_key


# Security: API Key authentication
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Security(API_KEY_HEADER)) -> Optional[str]:
    """Verify API key for protected endpoints.

    Production auth posture (BUILD-189):
    - In production (AUTOPACK_ENV=production), API key is REQUIRED
    - In dev/test, API key is optional for convenience
    - In testing mode (TESTING=1), auth is skipped entirely

    PR-03 (R-03 G4): Supports AUTOPACK_API_KEY_FILE for Docker secrets.
    """
    # Use get_api_key() which supports *_FILE precedence
    expected_key = get_api_key()
    env_mode = os.getenv("AUTOPACK_ENV", "development").lower()

    # Skip auth in testing mode
    # - Explicit: TESTING=1
    # - Implicit: pytest sets PYTEST_CURRENT_TEST for each test item; treat that as test mode
    #   in non-production to avoid forcing headers in unit/integration tests.
    if os.getenv("TESTING") == "1" or (
        env_mode != "production" and os.getenv("PYTEST_CURRENT_TEST") is not None
    ):
        return "test-key"

    # Production mode: API key is REQUIRED
    if env_mode == "production":
        if not expected_key:
            raise HTTPException(
                status_code=500,
                detail="AUTOPACK_API_KEY must be configured in production mode. "
                "Set AUTOPACK_API_KEY environment variable.",
            )
        if not api_key or api_key != expected_key:
            raise HTTPException(
                status_code=403, detail="Invalid or missing API key. Set X-API-Key header."
            )
        return api_key

    # Dev mode: skip auth if no key configured (for initial setup convenience)
    if not expected_key:
        return None

    if not api_key or api_key != expected_key:
        raise HTTPException(
            status_code=403, detail="Invalid or missing API key. Set X-API-Key header."
        )
    return api_key


async def verify_read_access(api_key: Optional[str] = Security(API_KEY_HEADER)) -> Optional[str]:
    """Verify read access for operator surface endpoints (P0.4 auth gating).

    Policy:
    - In production (AUTOPACK_ENV=production), API key is REQUIRED
    - In dev mode with AUTOPACK_PUBLIC_READ=1, read endpoints are public
    - In dev mode without AUTOPACK_PUBLIC_READ, API key is required if configured
    - In testing mode (TESTING=1), auth is skipped entirely
    """
    env_mode = os.getenv("AUTOPACK_ENV", "development").lower()

    # Skip auth in testing mode (see verify_api_key for rationale)
    if os.getenv("TESTING") == "1" or (
        env_mode != "production" and os.getenv("PYTEST_CURRENT_TEST") is not None
    ):
        return "test-key"

    # Dev mode: check AUTOPACK_PUBLIC_READ opt-in
    if env_mode != "production":
        if os.getenv("AUTOPACK_PUBLIC_READ") == "1":
            return None  # Public read allowed

    # Otherwise, use standard API key verification
    return await verify_api_key(api_key)


# Rate limiting - PR-06: Use X-Forwarded-For when behind nginx/proxy
# Trusted proxy IPs - only trust forwarded headers from these sources
# Default: localhost (127.0.0.1, ::1) and Docker bridge networks (172.16-31.x.x)
# Override via AUTOPACK_TRUSTED_PROXIES env var (comma-separated IPs/CIDRs)
_DEFAULT_TRUSTED_PROXIES = {"127.0.0.1", "::1"}


def _is_trusted_proxy(client_ip: Optional[str]) -> bool:
    """Check if the direct client IP is from a trusted proxy.

    Supports both single IPs and CIDR notation in AUTOPACK_TRUSTED_PROXIES.
    Examples:
    - Single IP: "127.0.0.1"
    - CIDR range: "10.0.0.0/8", "172.16.0.0/12"
    - Both: "127.0.0.1, 10.0.0.0/8, 192.168.1.0/24"
    """
    if not client_ip:
        return False

    try:
        client_ip_obj = ipaddress.ip_address(client_ip)
    except ValueError:
        # Invalid IP format
        return False

    # Check explicit trusted list
    trusted = os.getenv("AUTOPACK_TRUSTED_PROXIES", "").strip()
    if trusted:
        trusted_list = [entry.strip() for entry in trusted.split(",") if entry.strip()]
    else:
        trusted_list = list(_DEFAULT_TRUSTED_PROXIES)

    # Check each trusted entry (single IP or CIDR range)
    for entry in trusted_list:
        try:
            # Try parsing as a network (handles both single IPs and CIDR ranges)
            # "192.168.1.5" becomes "192.168.1.5/32", "10.0.0.0/8" stays as is
            network = ipaddress.ip_network(entry, strict=False)
            if client_ip_obj in network:
                return True
        except ValueError:
            # Invalid entry format, skip it
            continue

    # Trust Docker bridge networks (172.16.0.0/12) when running in compose
    # This covers 172.16.x.x through 172.31.x.x
    docker_bridge = ipaddress.ip_network("172.16.0.0/12")
    if client_ip_obj in docker_bridge:
        return True

    return False


def get_client_ip(request: Request) -> str:
    """
    Extract real client IP, respecting X-Forwarded-For only from trusted proxies.

    Security model:
    - Only trust X-Forwarded-For/X-Real-IP headers if the direct connection
      is from a trusted proxy (localhost, Docker bridge, or AUTOPACK_TRUSTED_PROXIES)
    - If direct connection is untrusted, ignore forwarded headers (spoofing defense)

    Priority (when from trusted proxy):
    1. X-Forwarded-For header (first IP in chain = original client)
    2. X-Real-IP header (nginx convention)
    3. request.client.host (direct connection fallback)
    """
    direct_ip = request.client.host if request.client else None

    # Only trust forwarded headers if connection is from trusted proxy
    if _is_trusted_proxy(direct_ip):
        # X-Forwarded-For: client, proxy1, proxy2, ...
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Take the first IP (original client), strip whitespace
            return forwarded_for.split(",")[0].strip()

        # X-Real-IP (nginx convention - single IP)
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()

    # Use direct connection IP (untrusted proxy or no forwarded headers)
    if direct_ip:
        return direct_ip

    return "127.0.0.1"


# Rate limiter instance - used by routes via app.state.limiter
limiter = Limiter(key_func=get_client_ip)
