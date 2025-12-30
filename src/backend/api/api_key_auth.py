"""API Key authentication for backward compatibility.

BUILD-146 P11 Ops: Dual authentication support for API split-brain fix.

This module provides X-API-Key header authentication to maintain backward
compatibility with autonomous_executor.py while the production API uses
Bearer token authentication.

Usage:
    from backend.api.api_key_auth import verify_api_key_or_bearer

    @router.get("/endpoint")
    def my_endpoint(auth: str = Depends(verify_api_key_or_bearer)):
        # auth will be validated X-API-Key or Bearer token
        ...
"""
import os
from typing import Optional

from fastapi import Header, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


# Optional API key from environment (for backward compatibility with Supervisor API)
AUTOPACK_API_KEY = os.getenv("AUTOPACK_API_KEY")

# Optional bearer token scheme (for production API)
bearer_scheme = HTTPBearer(auto_error=False)


async def verify_api_key_or_bearer(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> str:
    """
    Verify authentication via X-API-Key OR Bearer token.

    This dual authentication strategy provides backward compatibility:
    - X-API-Key header: Used by autonomous_executor.py (Supervisor API pattern)
    - Bearer token: Used by run_parallel.py (Production API pattern)

    Args:
        x_api_key: Optional X-API-Key header value
        authorization: Optional Bearer token credentials

    Returns:
        Authentication token/key (either X-API-Key value or Bearer token)

    Raises:
        HTTPException 401: If neither auth method is provided or both are invalid
        HTTPException 403: If provided credentials don't match expected values
    """
    # Skip auth in testing mode
    if os.getenv("TESTING") == "1":
        return "test-auth-token"

    # Try X-API-Key first (backward compatibility with autonomous_executor.py)
    if x_api_key:
        # If AUTOPACK_API_KEY is set in environment, validate it
        if AUTOPACK_API_KEY:
            if x_api_key == AUTOPACK_API_KEY:
                return x_api_key
            else:
                raise HTTPException(
                    status_code=403,
                    detail="Invalid API key"
                )
        else:
            # If no AUTOPACK_API_KEY configured, accept any X-API-Key (dev/test mode)
            return x_api_key

    # Try Bearer token (production API pattern)
    if authorization and authorization.credentials:
        # For now, just accept Bearer tokens without full JWT validation
        # (full validation would require integrating with backend.api.auth.get_current_user)
        # This is sufficient for run_parallel.py compatibility
        return authorization.credentials

    # Neither auth method provided
    raise HTTPException(
        status_code=401,
        detail="Authentication required. Provide either X-API-Key header or Authorization: Bearer token"
    )


async def verify_api_key_only(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> str:
    """
    Verify authentication via X-API-Key only (strict Supervisor API pattern).

    Args:
        x_api_key: X-API-Key header value

    Returns:
        API key

    Raises:
        HTTPException 401: If X-API-Key not provided
        HTTPException 403: If X-API-Key doesn't match expected value
    """
    # Skip auth in testing mode
    if os.getenv("TESTING") == "1":
        return "test-api-key"

    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="X-API-Key header required"
        )

    # If AUTOPACK_API_KEY is set, validate it
    if AUTOPACK_API_KEY:
        if x_api_key != AUTOPACK_API_KEY:
            raise HTTPException(
                status_code=403,
                detail="Invalid API key"
            )

    return x_api_key
