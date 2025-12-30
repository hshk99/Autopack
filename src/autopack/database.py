"""Database setup and session management"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import get_database_url

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


def get_db():
    """Dependency for FastAPI to get DB session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables"""
    # Import models to register them with Base.metadata
    from . import models  # noqa: F401
    from .usage_recorder import (  # noqa: F401
        LlmUsageEvent,
        DoctorUsageStats,
        TokenEfficiencyMetrics,
    )

    Base.metadata.create_all(bind=engine)
