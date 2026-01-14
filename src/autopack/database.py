"""Database setup and session management"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import get_database_url
from .db_leak_detector import ConnectionLeakDetector
from .exceptions import DatabaseError

# Enable pool_pre_ping so dropped/closed connections are detected and re-established.
# pool_recycle guards against server-side timeouts on long-lived processes.
# Use get_database_url() for runtime binding (respects DATABASE_URL env var)
engine = create_engine(
    get_database_url(),
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Initialize connection pool leak detector
leak_detector = ConnectionLeakDetector(engine.pool)


def get_db():
    """Dependency for FastAPI to get DB session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_pool_health():
    """Get connection pool health stats.

    Returns:
        dict with pool statistics and health indicators
    """
    return leak_detector.check_pool_health()


def init_db():
    """Initialize database tables with P0.4 safety guardrails.

    Behavior:
    - If AUTOPACK_DB_BOOTSTRAP=1: Creates missing tables (dev/test mode)
    - If AUTOPACK_DB_BOOTSTRAP=0 (default): Fails fast if schema missing (production safe)

    This prevents silent schema drift between SQLite/Postgres environments.
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

    # P0.4: Guard against accidental schema creation in production
    if not settings.db_bootstrap_enabled:
        # Verify schema exists (check for a known core table)
        from sqlalchemy import inspect

        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        if not existing_tables or "runs" not in existing_tables:
            error_msg = (
                "DATABASE SCHEMA MISSING: No tables found (or 'runs' table missing).\n"
                "To bootstrap schema, set environment variable: AUTOPACK_DB_BOOTSTRAP=1\n"
                "For production, run migrations instead of using create_all()."
            )
            logger.error(error_msg)
            raise DatabaseError(error_msg)

        logger.info(f"[DB] Schema validation passed: {len(existing_tables)} tables found")
    else:
        # Bootstrap mode: create missing tables
        logger.warning(
            "[DB] Bootstrap mode enabled (AUTOPACK_DB_BOOTSTRAP=1). "
            "This should ONLY be used in dev/test environments."
        )
        Base.metadata.create_all(bind=engine)
        logger.info("[DB] Schema created/updated via create_all()")
