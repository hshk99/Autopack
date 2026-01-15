"""Simple API key authentication for multi-device access.

Simplifies auth for personal/internal use while protecting high-impact endpoints.
Replaces enterprise OAuth/JWT lifecycle complexity.
"""

import secrets
import hashlib
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from autopack.database import get_db
from .models import APIKey


def generate_api_key() -> tuple[str, str]:
    """
    Generate a new API key and its hash.

    Returns:
        tuple: (plain_key, hashed_key) - The plain key should be shown once to the user,
               the hashed key should be stored in the database.
    """
    # Generate a 32-byte (256-bit) random key
    plain_key = f"autopack_{secrets.token_urlsafe(32)}"
    # Hash the key for storage (using SHA256)
    hashed_key = hashlib.sha256(plain_key.encode()).hexdigest()
    return plain_key, hashed_key


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """Verify a plain API key against its hash."""
    computed_hash = hashlib.sha256(plain_key.encode()).hexdigest()
    return secrets.compare_digest(computed_hash, hashed_key)


def get_api_key_from_db(db: Session, plain_key: str) -> Optional[APIKey]:
    """
    Find and validate an API key from the database.

    Returns the APIKey model if valid and active, None otherwise.
    """
    if not plain_key.startswith("autopack_"):
        return None

    # Get all active API keys and check against the provided key
    # Note: In a high-security system, you'd index by a key_id prefix,
    # but for personal use, this simpler approach is acceptable
    hashed_key = hashlib.sha256(plain_key.encode()).hexdigest()
    api_key = (
        db.query(APIKey)
        .filter(APIKey.key_hash == hashed_key, APIKey.is_active == True)  # noqa: E712
        .first()
    )

    if api_key:
        # Update last used timestamp
        api_key.last_used_at = datetime.now(timezone.utc)
        db.commit()

    return api_key


async def require_api_key(
    x_api_key: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> APIKey:
    """
    Dependency to require a valid API key for protected endpoints.

    Usage:
        @app.get("/protected")
        async def protected_route(api_key: APIKey = Depends(require_api_key)):
            # Route logic here
            pass
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    api_key_model = get_api_key_from_db(db, x_api_key)
    if not api_key_model:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or inactive API key",
        )

    return api_key_model


async def optional_api_key(
    x_api_key: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> Optional[APIKey]:
    """
    Dependency for optional API key authentication.

    Returns the APIKey model if provided and valid, None otherwise.
    Useful for endpoints that work differently when authenticated.
    """
    if not x_api_key:
        return None

    return get_api_key_from_db(db, x_api_key)
