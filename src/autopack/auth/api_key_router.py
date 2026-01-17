"""API key management router for multi-device access.

Provides endpoints to create, list, and revoke API keys.
"""

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from autopack.database import get_db
from .models import APIKey
from .api_key import generate_api_key, require_api_key


router = APIRouter(
    prefix="/api/auth/api-keys",
    tags=["api-keys"],
)


class APIKeyCreate(BaseModel):
    """Request model for creating a new API key."""

    name: str = Field(..., min_length=1, max_length=100, description="Friendly name for the key")
    description: str | None = Field(None, max_length=500, description="Optional description")


class APIKeyResponse(BaseModel):
    """Response model for API key (without the actual key)."""

    id: int
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None

    class Config:
        from_attributes = True


class APIKeyCreated(BaseModel):
    """Response model when a new API key is created (includes the plain key once)."""

    id: int
    name: str
    description: str | None
    key: str = Field(..., description="The API key - save this, it won't be shown again!")
    created_at: datetime


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=APIKeyCreated,
)
async def create_api_key(
    key_data: APIKeyCreate,
    db: Session = Depends(get_db),
    _current_key: APIKey = Depends(require_api_key),  # Require authentication
):
    """
    Create a new API key for multi-device access. Requires authentication.

    **IMPORTANT**: The API key is only shown once in the response.
    Save it securely - it cannot be retrieved later.
    """
    plain_key, hashed_key = generate_api_key()

    api_key = APIKey(
        name=key_data.name,
        key_hash=hashed_key,
        description=key_data.description,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )

    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return APIKeyCreated(
        id=api_key.id,
        name=api_key.name,
        description=api_key.description,
        key=plain_key,
        created_at=api_key.created_at,
    )


@router.get(
    "",
    response_model=List[APIKeyResponse],
)
async def list_api_keys(
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(require_api_key),
):
    """
    List all API keys (requires authentication).

    The actual key values are never returned, only metadata.
    """
    keys = db.query(APIKey).order_by(APIKey.created_at.desc()).all()
    return keys


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(require_api_key),
):
    """
    Revoke (deactivate) an API key.

    The key is not deleted, just marked as inactive.
    Requires authentication with a valid API key.
    """
    key_to_revoke = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not key_to_revoke:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    key_to_revoke.is_active = False
    db.commit()

    return None
