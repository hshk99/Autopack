"""Health check endpoints."""

from fastapi import APIRouter
from datetime import datetime, timezone
from pydantic import BaseModel
import hashlib
import re
import os

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    timestamp: str
    database_identity: str  # BUILD-146 P4 Ops: DB identity hash to detect drift


def get_database_identity() -> str:
    """Get database identity hash for drift detection.

    BUILD-146 P4 Ops: Returns a hash of the database URL (with credentials masked)
    so that we can detect when API and executor are using different databases.

    Returns:
        Hash of database URL (first 12 chars) for comparison
    """
    db_url = os.getenv("DATABASE_URL", "sqlite:///./autopack.db")

    # Mask credentials for security (replace user:pass@ with ***:***)
    masked_url = re.sub(r'://([^:]+):([^@]+)@', r'://***:***@', db_url)

    # Normalize path separators for cross-platform consistency
    normalized_url = masked_url.replace("\\", "/")

    # Hash and take first 12 chars
    hash_hex = hashlib.sha256(normalized_url.encode()).hexdigest()[:12]

    return hash_hex


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.

    Returns the current status, timestamp, and database identity.

    BUILD-146 P4 Ops: The database_identity field can be used to detect
    when API and executor are pointing at different databases (e.g.,
    API using Postgres but executor defaulting to SQLite).
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat(),
        database_identity=get_database_identity(),
    )
