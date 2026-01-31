"""Health check and root endpoints.

Extracted from main.py as part of PR-API-3a.

IMP-OPS-004: Added /ready endpoint for Kubernetes readiness probes.
IMP-OPS-007: Added background task health monitoring to /health endpoint.
"""

import hashlib
import logging
import os
import re
import threading
from datetime import datetime, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from autopack import models
from autopack.database import engine, get_db, get_pool_health
from autopack.version import __version__

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


# Module-level initialization state tracking for readiness probe
class _InitializationState:
    """Thread-safe tracking of application initialization state.

    Used by /ready endpoint to determine if the app is ready to serve traffic.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._initialized = False
        self._initialization_errors: List[str] = []

    def mark_initialized(self) -> None:
        """Mark the application as fully initialized."""
        with self._lock:
            self._initialized = True
            logger.info("[READY] Application marked as initialized")

    def mark_failed(self, error: str) -> None:
        """Record an initialization error."""
        with self._lock:
            self._initialization_errors.append(error)
            logger.error(f"[READY] Initialization error recorded: {error}")

    def is_initialized(self) -> bool:
        """Check if initialization is complete."""
        with self._lock:
            return self._initialized

    def get_errors(self) -> List[str]:
        """Get list of initialization errors."""
        with self._lock:
            return list(self._initialization_errors)

    def reset(self) -> None:
        """Reset state (for testing)."""
        with self._lock:
            self._initialized = False
            self._initialization_errors = []


# Global initialization state singleton
_init_state = _InitializationState()


def mark_app_initialized() -> None:
    """Mark the application as fully initialized.

    Called by lifespan context manager after all startup tasks complete.
    """
    _init_state.mark_initialized()


def mark_initialization_failed(error: str) -> None:
    """Record an initialization failure.

    Args:
        error: Description of the initialization error
    """
    _init_state.mark_failed(error)


def reset_initialization_state() -> None:
    """Reset initialization state (for testing only)."""
    _init_state.reset()


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


def _check_background_tasks() -> Dict[str, object]:
    """Check health of background tasks.

    IMP-OPS-007: Returns health status of all monitored background tasks.

    Returns:
        Dict with overall status and per-task details
    """
    try:
        from ..app import get_task_monitor

        monitor = get_task_monitor()
        all_status = monitor.get_all_status()
        all_healthy = monitor.is_all_healthy()

        return {
            "status": "healthy" if all_healthy else "degraded",
            "tasks": all_status,
        }
    except RuntimeError:
        # Monitor not initialized yet (app still starting)
        return {
            "status": "initializing",
            "tasks": {},
        }
    except Exception as e:
        logger.warning(f"Background task health check failed: {e}")
        return {
            "status": "error",
            "error": str(e)[:100],
            "tasks": {},
        }


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

    # Get kill switch states (BUILD-146 P12, IMP-REL-001)
    from autopack.feature_gates import get_feature_states

    all_features = get_feature_states()
    kill_switches = {feature_id: info["enabled"] for feature_id, info in all_features.items()}

    # IMP-OPS-007: Check background task health
    background_tasks = _check_background_tasks()

    # Determine overall status
    # Status is degraded if DB or background tasks have issues
    if db_status != "connected":
        overall_status = "degraded"
    elif background_tasks.get("status") == "degraded":
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    # Get version
    version = os.getenv("AUTOPACK_VERSION", "unknown")

    # Build response payload
    payload = {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database_identity": _get_database_identity(),
        "database": db_status,
        "qdrant": qdrant_status,
        "background_tasks": background_tasks,
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


@router.get("/health/database")
def database_pool_health():
    """
    Database connection pool health check endpoint.

    Returns pool utilization, connection status, and leak detection indicators.
    Useful for monitoring pool exhaustion and detecting leaks in production.

    Response:
        {
            "status": "healthy" | "degraded",
            "pool": {
                "pool_size": int,
                "checked_out": int,
                "overflow": int,
                "utilization": float (0-1.0),
                "is_healthy": bool
            },
            "timestamp": ISO8601 timestamp
        }
    """
    pool_health = get_pool_health()

    return {
        "status": "healthy" if pool_health["is_healthy"] else "degraded",
        "pool": pool_health,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/tasks")
def background_task_health():
    """
    Background task health check endpoint.

    IMP-OPS-007: Returns detailed health status of all monitored background tasks.
    Useful for detecting hung, failing, or stuck background tasks.

    Response:
        {
            "status": "healthy" | "degraded" | "initializing" | "error",
            "tasks": {
                "task_name": {
                    "healthy": bool,
                    "last_run": ISO8601 timestamp or null,
                    "age_seconds": float or null,
                    "failure_count": int,
                    "max_age_seconds": float,
                    "max_failures": int
                },
                ...
            },
            "timestamp": ISO8601 timestamp
        }

    A task is considered unhealthy if:
    - It hasn't run within max_age_seconds (default 300s / 5 minutes)
    - It has failed max_failures times consecutively (default 3)
    """
    bg_tasks = _check_background_tasks()

    return {
        "status": bg_tasks.get("status", "unknown"),
        "tasks": bg_tasks.get("tasks", {}),
        "error": bg_tasks.get("error"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _check_schema_initialized() -> Dict[str, object]:
    """Check if database schema is properly initialized.

    Returns:
        Dict with 'ready' bool and 'details' about schema state
    """
    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        # Core tables that must exist for the app to function
        required_tables = {"runs", "phases", "events"}
        missing_tables = required_tables - set(existing_tables)

        if missing_tables:
            return {
                "ready": False,
                "details": f"missing required tables: {sorted(missing_tables)}",
                "table_count": len(existing_tables),
            }

        return {
            "ready": True,
            "details": "schema initialized",
            "table_count": len(existing_tables),
        }
    except Exception as e:
        return {
            "ready": False,
            "details": f"schema check failed: {str(e)[:100]}",
            "table_count": 0,
        }


def _check_database_ready(db: Session) -> Dict[str, object]:
    """Check if database connection is ready for queries.

    Args:
        db: Database session

    Returns:
        Dict with 'ready' bool and connection details
    """
    try:
        # Basic connectivity check
        db.execute(text("SELECT 1"))

        # Verify we can query a core table
        db.query(models.Run).limit(1).all()

        return {
            "ready": True,
            "details": "database connected and queryable",
        }
    except Exception as e:
        return {
            "ready": False,
            "details": f"database error: {str(e)[:100]}",
        }


def _check_dependencies_ready() -> Dict[str, Dict[str, object]]:
    """Check if optional dependencies are ready or properly disabled.

    Returns:
        Dict mapping dependency name to readiness status
    """
    dependencies = {}

    # Qdrant (optional vector database)
    qdrant_host = os.getenv("QDRANT_HOST")
    if not qdrant_host:
        dependencies["qdrant"] = {"ready": True, "details": "disabled (no QDRANT_HOST)"}
    else:
        qdrant_status = _check_qdrant_connection()
        dependencies["qdrant"] = {
            "ready": qdrant_status in ("connected", "disabled"),
            "details": qdrant_status,
        }

    return dependencies


@router.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    """
    Readiness probe endpoint for Kubernetes/container orchestration.

    IMP-OPS-004: Unlike /health (liveness), this endpoint returns 503 until
    all initialization is complete. Use this for readiness probes to prevent
    routing traffic to instances that haven't finished starting up.

    Checks performed:
    1. Application initialization flag is set (lifespan completed)
    2. Database schema is properly initialized
    3. Database connection is ready for queries
    4. Optional dependencies are ready or disabled

    Response (200 when ready):
        {
            "ready": true,
            "status": "ready",
            "timestamp": ISO8601 timestamp,
            "checks": {
                "initialization": {"ready": true, ...},
                "schema": {"ready": true, ...},
                "database": {"ready": true, ...},
                "dependencies": {...}
            },
            "version": str
        }

    Response (503 when not ready):
        Same structure but ready=false and status="not_ready"
    """
    checks: Dict[str, object] = {}
    all_ready = True

    # Check 1: Application initialization state
    app_initialized = _init_state.is_initialized()
    init_errors = _init_state.get_errors()
    checks["initialization"] = {
        "ready": app_initialized,
        "details": "lifespan completed" if app_initialized else "initializing",
        "errors": init_errors if init_errors else None,
    }
    if not app_initialized:
        all_ready = False

    # Check 2: Database schema
    schema_check = _check_schema_initialized()
    checks["schema"] = schema_check
    if not schema_check["ready"]:
        all_ready = False

    # Check 3: Database connectivity
    db_check = _check_database_ready(db)
    checks["database"] = db_check
    if not db_check["ready"]:
        all_ready = False

    # Check 4: Optional dependencies
    dep_checks = _check_dependencies_ready()
    checks["dependencies"] = dep_checks
    for dep_name, dep_status in dep_checks.items():
        if not dep_status.get("ready", False):
            all_ready = False

    # Check 5: Background tasks (IMP-OPS-007)
    bg_tasks = _check_background_tasks()
    checks["background_tasks"] = {
        "ready": bg_tasks.get("status") in ("healthy", "initializing"),
        "status": bg_tasks.get("status"),
        "tasks": bg_tasks.get("tasks", {}),
    }
    # Note: We don't fail readiness if background tasks are degraded
    # They may recover, and the app can still serve traffic
    # However, we do include the status for visibility

    # Build response
    payload = {
        "ready": all_ready,
        "status": "ready" if all_ready else "not_ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "version": __version__,
        "service": "autopack",
        "component": "supervisor_api",
    }

    # Return 503 if not ready, 200 if ready
    if not all_ready:
        return JSONResponse(status_code=503, content=payload)

    return payload
