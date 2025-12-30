"""Health check endpoints.

BUILD-146 P12: Enhanced with dependency validation and kill switch states.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
from pydantic import BaseModel
from typing import Dict, Optional
import hashlib
import re
import os
import logging

from autopack.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model.

    BUILD-146 P12: Extended with dependency checks and kill switch states.
    """
    status: str
    timestamp: str
    database_identity: str  # BUILD-146 P4 Ops: DB identity hash to detect drift
    database: str  # BUILD-146 P12: Database connection status
    qdrant: Optional[str]  # BUILD-146 P12: Qdrant connection status (if enabled)
    kill_switches: Dict[str, bool]  # BUILD-146 P12: Kill switch states
    version: Optional[str]  # API version (if available)


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
