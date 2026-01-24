"""Database setup and session management.

IMP-PERF-001: Connection Pooling for DB Sessions
-------------------------------------------------
This module provides connection pooling and session management for the database.

Connection Pool Configuration (PostgreSQL):
    - pool_size: 20 base connections
    - max_overflow: 10 additional connections under peak load
    - pool_timeout: 30 seconds max wait for connection
    - pool_pre_ping: Validate connections before use
    - pool_recycle: Refresh connections every 30 minutes

Session Management Patterns:
    1. get_session() - Context manager for scoped session access (RECOMMENDED)
       ```
       with get_session() as session:
           result = session.query(Model).all()
       # Session automatically returned to pool
       ```

    2. ScopedSession - Thread-local session registry for session reuse
       ```
       session = ScopedSession()
       # ... use session ...
       ScopedSession.remove()  # Return to pool when done
       ```

    3. get_db() - FastAPI dependency (for API endpoints only)
       Used automatically by FastAPI's dependency injection.

    4. SessionLocal() - Direct session creation (AVOID in loops)
       Creates a new session each call. Use get_session() instead.
"""

import logging
from contextlib import contextmanager
from typing import Any, Generator

from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session, Session

from .config import get_database_url
from .db_leak_detector import ConnectionLeakDetector
from .exceptions import DatabaseError

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# IMP-OPS-011: Connection Pool Health Metrics
# These metrics are designed to be compatible with Prometheus-style monitoring.
# They can be exposed via a /metrics endpoint or integrated with prometheus_client.
# -----------------------------------------------------------------------------

# Pool metrics storage (updated by get_pool_stats())
# These are module-level for easy access by monitoring systems
_pool_metrics: dict[str, Any] = {
    "pool_size": 0,
    "checked_out": 0,
    "checked_in": 0,
    "overflow": 0,
    "max_overflow": 0,
    "utilization_pct": 0.0,
}

# Enable pool_pre_ping so dropped/closed connections are detected and re-established.
# pool_recycle guards against server-side timeouts on long-lived processes.
# Use get_database_url() for runtime binding (respects DATABASE_URL env var)

_db_url = get_database_url()
_is_postgres = _db_url.startswith("postgresql")

# Pool configuration only applies to PostgreSQL (SQLite uses SingletonThreadPool)
_engine_kwargs = {
    "pool_pre_ping": True,
    "pool_recycle": 1800,
}

if _is_postgres:
    # Explicit pool configuration for PostgreSQL to prevent exhaustion under high load
    # SQLite's SingletonThreadPool doesn't support these options
    #   - pool_size=20: Base pool size for normal operations
    #   - max_overflow=10: Allow 10 additional connections under peak load
    #   - pool_timeout=30: Wait max 30s for connection before raising TimeoutError
    _engine_kwargs.update(
        {
            "pool_size": 20,
            "max_overflow": 10,
            "pool_timeout": 30,
        }
    )

engine = create_engine(_db_url, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# IMP-PERF-001: Scoped session for thread-local session management
# This ensures the same thread reuses the same session, reducing connection churn
ScopedSession = scoped_session(SessionLocal)

# Initialize connection pool leak detector
leak_detector = ConnectionLeakDetector(engine.pool)

# IMP-PERF-001: Track session checkout/checkin metrics
_session_metrics = {
    "total_checkouts": 0,
    "total_checkins": 0,
    "active_sessions": 0,
    "peak_active_sessions": 0,
}


@event.listens_for(engine, "checkout")
def _on_checkout(dbapi_conn, connection_record, connection_proxy):
    """Track connection checkouts from pool."""
    _session_metrics["total_checkouts"] += 1
    _session_metrics["active_sessions"] += 1
    if _session_metrics["active_sessions"] > _session_metrics["peak_active_sessions"]:
        _session_metrics["peak_active_sessions"] = _session_metrics["active_sessions"]


@event.listens_for(engine, "checkin")
def _on_checkin(dbapi_conn, connection_record):
    """Track connection checkins to pool."""
    _session_metrics["total_checkins"] += 1
    _session_metrics["active_sessions"] = max(0, _session_metrics["active_sessions"] - 1)


def get_session_metrics() -> dict:
    """Get session pool metrics for monitoring.

    Returns:
        Dict with checkout/checkin counts, active sessions, and peak usage.
    """
    return dict(_session_metrics)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager for database session access (IMP-PERF-001).

    This is the RECOMMENDED way to access database sessions. It:
    - Uses scoped_session for thread-local session reuse
    - Automatically commits on success
    - Rolls back on exception
    - Returns session to pool on exit

    Usage:
        with get_session() as session:
            result = session.query(Model).filter_by(id=1).first()
            session.add(new_record)
        # Commits automatically, session returned to pool

    Yields:
        SQLAlchemy Session from the thread-local scoped session.

    Raises:
        DatabaseError: If session operations fail.
    """
    session = ScopedSession()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.warning(f"Session rollback due to: {e}")
        raise
    finally:
        ScopedSession.remove()  # Return session to pool


def get_db():
    """Dependency for FastAPI to get DB session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_pool_health():
    """Get connection pool health metrics (IMP-DB-001).

    Returns:
        DatabasePoolStats with comprehensive pool statistics and health indicators
    """
    from datetime import datetime

    from .dashboard_schemas import DatabasePoolStats

    # Get basic pool health from detector
    pool_health = leak_detector.check_pool_health()

    # Extract pool configuration
    pool_size = pool_health.get("pool_size", 0)
    checked_out = pool_health.get("checked_out", 0)
    overflow = pool_health.get("overflow", 0)
    max_overflow = getattr(engine.pool, "_max_overflow", 10)

    # Calculate derived metrics
    checked_in = pool_size - checked_out
    utilization_pct = (checked_out / pool_size * 100) if pool_size > 0 else 0.0
    queue_size = pool_health.get("queue_size", 0)

    # Detect potential leaks (connections checked out longer than threshold)
    potential_leaks = []
    if checked_out > 15:  # Alert when many connections are in use
        potential_leaks.append(
            {
                "severity": "warning",
                "checked_out": checked_out,
                "pool_size": pool_size,
                "message": f"High pool utilization: {utilization_pct:.1f}%",
            }
        )

    # IMP-PERF-001: Include session metrics from event tracking
    session_stats = get_session_metrics()

    return DatabasePoolStats(
        timestamp=datetime.now(),
        pool_size=pool_size,
        checked_out=checked_out,
        checked_in=checked_in,
        overflow=overflow,
        max_overflow=max_overflow,
        utilization_pct=utilization_pct,
        queue_size=queue_size,
        potential_leaks=potential_leaks,
        longest_checkout_sec=0.0,  # Would require tracking individual connections
        avg_checkout_ms=0.0,  # Would require tracking individual connections
        avg_checkin_ms=0.0,  # Would require tracking individual connections
        total_checkouts=session_stats["total_checkouts"],  # IMP-PERF-001: Now tracked
        total_timeouts=0,  # Would require tracking timeout events
    )


def get_pool_stats() -> dict[str, Any]:
    """Get connection pool statistics for monitoring (IMP-OPS-011).

    Returns pool statistics in a format suitable for Prometheus-style metrics.
    Updates module-level _pool_metrics for external monitoring access.

    Returns:
        dict with keys:
            - pool_size: Total connections in pool
            - checked_out: Connections currently in use
            - checked_in: Connections available in pool
            - overflow: Extra connections created beyond pool_size
            - max_overflow: Maximum allowed overflow connections
            - utilization_pct: Percentage of pool in use (0-100)

    Warning:
        Logs warning when pool utilization >= 80% (near exhaustion)
    """
    global _pool_metrics

    pool = engine.pool
    pool_size = pool.size()
    checked_out = pool.checkedout()
    overflow = pool.overflow()
    max_overflow = getattr(pool, "_max_overflow", 10)
    checked_in = pool_size - checked_out

    # Calculate utilization percentage
    utilization_pct = (checked_out / pool_size * 100) if pool_size > 0 else 0.0

    # Update module-level metrics for external monitoring
    _pool_metrics.update(
        {
            "pool_size": pool_size,
            "checked_out": checked_out,
            "checked_in": checked_in,
            "overflow": overflow,
            "max_overflow": max_overflow,
            "utilization_pct": utilization_pct,
        }
    )

    # IMP-OPS-011: Log warning when pool near exhaustion
    if checked_out >= pool_size:
        logger.warning(
            f"[IMP-OPS-011] Connection pool near exhaustion: "
            f"checked_out={checked_out}, pool_size={pool_size}, "
            f"overflow={overflow}, utilization={utilization_pct:.1f}%"
        )
    elif utilization_pct >= 80:
        logger.warning(
            f"[IMP-OPS-011] Connection pool utilization high: "
            f"{utilization_pct:.1f}% ({checked_out}/{pool_size} connections)"
        )

    return dict(_pool_metrics)


def get_pool_metrics() -> dict[str, Any]:
    """Get the current pool metrics without querying the pool.

    Returns the last cached metrics from get_pool_stats(). Useful for
    Prometheus scraping without additional database pool queries.

    Returns:
        dict: Current pool metrics (may be stale if get_pool_stats() not called recently)
    """
    return dict(_pool_metrics)


def init_db():
    """Initialize database tables with P0.4 safety guardrails and migrations.

    Behavior:
    - If AUTOPACK_DB_BOOTSTRAP=1: Creates missing tables via create_all (dev/test mode)
    - If AUTOPACK_DB_BOOTSTRAP=0 (default): Runs Alembic migrations (production safe)

    This prevents silent schema drift between SQLite/Postgres environments.
    Alembic migrations provide version-controlled, reversible schema changes.

    Concurrency Control (IMP-OPS-006):
    - PostgreSQL: Uses advisory lock to prevent corruption during concurrent bootstrap
    - SQLite: No locking needed (file-level locking is inherent)
    """
    from .config import settings
    import logging

    logger = logging.getLogger(__name__)

    # Import models to register them with Base.metadata
    from . import models  # noqa: F401
    from .usage_recorder import (  # noqa: F401
        LlmUsageEvent,
        DoctorUsageStats,
        TokenEfficiencyMetrics,
    )
    from .auth.models import User  # noqa: F401  # BUILD-146 P12 Phase 5

    # Bootstrap mode: create missing tables via create_all (for dev/test)
    # Migration mode: use Alembic (for production - IMP-OPS-002)
    if settings.db_bootstrap_enabled:
        # Bootstrap mode: create missing tables
        logger.warning(
            "[DB] Bootstrap mode enabled (AUTOPACK_DB_BOOTSTRAP=1). "
            "This should ONLY be used in dev/test environments."
        )
        _bootstrap_with_lock()
        logger.info("[DB] Schema created/updated via create_all()")
    else:
        # Production mode: run Alembic migrations (IMP-OPS-002)
        logger.info("[DB] Running Alembic migrations for schema management")
        run_migrations()


# Advisory lock ID for database bootstrap operations (IMP-OPS-006)
# Using a unique 64-bit integer to prevent conflicts with other advisory locks
_BOOTSTRAP_ADVISORY_LOCK_ID = 0x4155544F5041434B  # 'AUTOPACK' in hex


def _bootstrap_with_lock():
    """Bootstrap database with concurrency control (IMP-OPS-006).

    For PostgreSQL: Acquires an advisory lock before running create_all()
    to prevent corruption when multiple instances start simultaneously with
    AUTOPACK_DB_BOOTSTRAP=1.

    For SQLite: Runs create_all() directly (SQLite has inherent file-level locking).
    """
    # Check dialect at runtime (not module-level) to support test mocking
    is_postgres = engine.dialect.name == "postgresql"
    if is_postgres:
        # PostgreSQL: Use advisory lock to prevent concurrent schema modifications
        with engine.connect() as conn:
            logger.info("[DB] Acquiring advisory lock for bootstrap")
            conn.execute(text(f"SELECT pg_advisory_lock({_BOOTSTRAP_ADVISORY_LOCK_ID})"))
            try:
                Base.metadata.create_all(bind=engine)
            finally:
                conn.execute(text(f"SELECT pg_advisory_unlock({_BOOTSTRAP_ADVISORY_LOCK_ID})"))
                logger.info("[DB] Released advisory lock after bootstrap")
    else:
        # SQLite: No advisory lock needed (inherent file-level locking)
        Base.metadata.create_all(bind=engine)


# Session health check interval (25 minutes - before 30 min pool_recycle)
SESSION_HEALTH_CHECK_INTERVAL = 25 * 60


def ensure_session_healthy(session: Session) -> bool:
    """Check session health and refresh if needed.

    Performs a lightweight SELECT 1 query to verify the connection is alive.
    Should be called periodically in long-running operations to prevent
    stale connection issues when runs exceed pool_recycle (30 min).

    Args:
        session: SQLAlchemy session to check

    Returns:
        True if session is healthy or was successfully refreshed
    """
    try:
        session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.warning(f"Session health check failed: {e}")
        try:
            session.rollback()
            session.close()
            logger.info("Session closed for reconnection on next use")
        except Exception as close_err:
            logger.debug(f"Error during session cleanup: {close_err}")
        return True  # Session will reconnect on next use


def run_migrations() -> None:
    """Run Alembic database migrations.

    This function upgrades the database schema to the latest migration version.
    It uses the Alembic command API to execute migrations.

    This should be called during application startup to ensure the database
    schema is up to date before any other database operations are performed.

    Raises:
        Exception: If migration fails. Database may be left in an inconsistent state.
    """
    from alembic import command
    from alembic.config import Config
    import os

    # Create Alembic config
    alembic_cfg = Config()

    # Set script location relative to this file
    script_dir = os.path.join(os.path.dirname(__file__), "migrations")
    alembic_cfg.set_main_option("script_location", script_dir)

    # Set database URL from environment
    db_url = get_database_url()
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # Check if this is a development environment (for logging)
    import sys

    is_dev = "--dev" in sys.argv or os.getenv("AUTOPACK_ENV") == "development"

    if is_dev:
        logger.info(f"[DB] Running Alembic migrations from: {script_dir}")
        logger.info(f"[DB] Database URL: {db_url[:20]}...")  # Truncated for security

    try:
        # Run migrations to head (latest version)
        command.upgrade(alembic_cfg, "head")
        logger.info("[DB] Database migrations completed successfully")
    except Exception as e:
        logger.error(f"[DB] Failed to run migrations: {e}")
        raise DatabaseError(f"Database migration failed: {e}") from e
