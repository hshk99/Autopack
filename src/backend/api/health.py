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


def check_qdrant_connection() -> str:
    """Check Qdrant vector database connection.

    BUILD-146 P12: Optional dependency check.

    Returns:
        Connection status string
    """
    qdrant_host = os.getenv("QDRANT_HOST")

    if not qdrant_host:
        return "disabled"

    try:
        import requests
        # Simple health check to Qdrant
        response = requests.get(f"{qdrant_host}/healthz", timeout=2)
        if response.status_code == 200:
            return "connected"
        else:
            return f"unhealthy (status {response.status_code})"
    except ImportError:
        return "client_not_installed"
    except Exception as e:
        logger.warning(f"Qdrant health check failed: {e}")
        return f"error: {str(e)[:50]}"


@router.get("/health", response_model=HealthResponse)
async def health_check(db: Session = Depends(get_db)) -> HealthResponse:
    """
    Health check endpoint with dependency validation.

    Returns the current status, timestamp, database identity, dependency states,
    and kill switch configuration.

    BUILD-146 P4 Ops: The database_identity field can be used to detect
    when API and executor are pointing at different databases (e.g.,
    API using Postgres but executor defaulting to SQLite).

    BUILD-146 P12: Enhanced with database connectivity check, Qdrant status,
    and kill switch states for production readiness validation.
    """
    # Check database connection
    db_status = "connected"
    try:
        # Simple query to verify connection
        db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = f"error: {str(e)[:50]}"

    # Check Qdrant connection (optional)
    qdrant_status = check_qdrant_connection()

    # Check kill switch states (BUILD-146 P12)
    kill_switches = {
        "phase6_metrics": os.getenv("AUTOPACK_ENABLE_PHASE6_METRICS") == "1",
        "consolidated_metrics": os.getenv("AUTOPACK_ENABLE_CONSOLIDATED_METRICS") == "1",
    }

    # Determine overall status
    overall_status = "healthy" if db_status == "connected" else "degraded"

    # Get version (if available from environment)
    version = os.getenv("AUTOPACK_VERSION", "unknown")

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        database_identity=get_database_identity(),
        database=db_status,
        qdrant=qdrant_status,
        kill_switches=kill_switches,
        version=version,
    )
