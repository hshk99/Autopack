"""Health check and root endpoints.

Extracted from main.py as part of PR-API-3a.
"""

import hashlib
import logging
import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from autopack import models
from autopack.database import get_db
from autopack.version import __version__

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/")
def read_root():
    """Root endpoint"""
    return {
        "service": "Autopack Supervisor",
        "version": __version__,
        "description": "v7 autonomous build playbook orchestrator",
    }


def _get_database_identity() -> str:
    """Get database identity hash for drift detection."""
    db_url = os.getenv("DATABASE_URL", "sqlite:///./autopack.db")
    # Mask credentials for security
    masked_url = re.sub(r"://([^:]+):([^@]+)@", r"://***:***@", db_url)
    # Normalize path separators for cross-platform consistency
    normalized_url = masked_url.replace("\\", "/")
    # Hash and take first 12 chars
    return hashlib.sha256(normalized_url.encode()).hexdigest()[:12]


def _check_qdrant_connection() -> str:
    """Check Qdrant vector database connection (optional dependency)."""
    qdrant_host = os.getenv("QDRANT_HOST")
    if not qdrant_host:
        return "disabled"
    try:
        import requests

        response = requests.get(f"{qdrant_host}/healthz", timeout=2)
        return (
            "connected"
            if response.status_code == 200
            else f"unhealthy (status {response.status_code})"
        )
    except ImportError:
        return "client_not_installed"
    except Exception as e:
        logger.warning(f"Qdrant health check failed: {e}")
        return f"error: {str(e)[:50]}"


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """
    Enhanced health check endpoint with dependency validation and kill switch states.

    BUILD-129 Phase 3: Treat DB connectivity as part of health to prevent false-positives where
    /health is 200 but /runs/{id} fails with 500 due to DB misconfiguration (e.g., API using
    default Postgres while executor wrote runs into local SQLite).

    BUILD-146 P12 API Consolidation: Enhanced with:
    - Database connectivity check with identity hash
    - Optional Qdrant dependency check
    - Kill switch states reporting
    - Version information
    """
    # Check database connection
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
        db.query(models.Run).limit(1).all()
    except Exception as e:
        logger.error(f"[HEALTH] DB health check failed: {e}", exc_info=True)
        db_status = f"error: {str(e)[:50]}"

    # Check Qdrant (optional)
    qdrant_status = _check_qdrant_connection()

    # Get kill switch states (BUILD-146 P12)
    kill_switches = {
        "phase6_metrics": os.getenv("AUTOPACK_ENABLE_PHASE6_METRICS") == "1",
        "consolidated_metrics": os.getenv("AUTOPACK_ENABLE_CONSOLIDATED_METRICS") == "1",
    }

    # Determine overall status
    overall_status = "healthy" if db_status == "connected" else "degraded"

    # Get version
    version = os.getenv("AUTOPACK_VERSION", "unknown")

    # Build response payload
    payload = {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database_identity": _get_database_identity(),
        "database": db_status,
        "qdrant": qdrant_status,
        "kill_switches": kill_switches,
        "version": version,
        "service": "autopack",
        "component": "supervisor_api",
    }

    # Optional detailed DB identity for debugging (BUILD-129)
    if os.getenv("DEBUG_DB_IDENTITY") == "1":
        try:
            from autopack.db_identity import _get_sqlite_db_path  # type: ignore

            run_ids = [
                r[0] for r in db.query(models.Run.id).order_by(models.Run.id.asc()).limit(5).all()
            ]
            payload["db_identity_detail"] = {
                "database_url": os.getenv("DATABASE_URL"),
                "sqlite_file": str(_get_sqlite_db_path() or ""),
                "runs": db.query(models.Run).count(),
                "phases": db.query(models.Phase).count(),
                "sample_run_ids": run_ids,
            }
        except Exception as _e:
            payload["db_identity_error"] = str(_e)

    # Return 503 if unhealthy, 200 if healthy or degraded
    if overall_status == "unhealthy":
        return JSONResponse(status_code=503, content=payload)

    return payload
